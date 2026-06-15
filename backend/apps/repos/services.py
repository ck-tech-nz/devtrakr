import logging
import os
import re
import shutil
import stat
import subprocess
from subprocess import CalledProcessError
import tempfile

import requests
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Repo, GitHubIssue, Commit, GitAuthorAlias

logger = logging.getLogger(__name__)

GITHUB_REF_RE = re.compile(
    r"^https?://github\.com/([\w.-]+)/([\w.-]+)/(pull|issues)/(\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)


def parse_github_ref(url):
    """解析 GitHub PR/issue 链接 → {owner, repo, kind, number};非法返回 None。"""
    m = GITHUB_REF_RE.match(url or "")
    if not m:
        return None
    return {
        "owner": m.group(1),
        "repo": m.group(2),
        "kind": m.group(3).lower(),
        "number": int(m.group(4)),
    }


class GitHubPreviewService:
    """单条 GitHub PR/issue 取数用于悬停预览卡片(仅调 api.github.com 固定主机,无 SSRF)。"""
    GITHUB_API = "https://api.github.com"
    CACHE_TTL = 300

    def fetch_preview(self, owner, repo, kind, number):
        cache_key = f"gh-preview:{owner}/{repo}/{kind}/{number}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        api_path = "pulls" if kind == "pull" else "issues"
        token = (
            Repo.objects.filter(full_name=f"{owner}/{repo}")
            .exclude(github_token="")
            .values_list("github_token", flat=True)
            .first()
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = requests.get(
                f"{self.GITHUB_API}/repos/{owner}/{repo}/{api_path}/{number}",
                headers=headers,
                timeout=10,
            )
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        item = resp.json()
        if kind == "pull":
            state = "merged" if item.get("merged") else item.get("state", "open")
            norm_kind = "pr"
        else:
            state = item.get("state", "open")
            norm_kind = "issue"
        user = item.get("user") or {}
        data = {
            "kind": norm_kind,
            "number": number,
            "title": item.get("title") or "",
            "state": state,
            "author_login": user.get("login") or "",
            "author_avatar": user.get("avatar_url") or "",
            "repo_full_name": f"{owner}/{repo}",
            "html_url": item.get("html_url") or "",
        }
        cache.set(cache_key, data, self.CACHE_TTL)
        return data


class GitHubSyncService:
    GITHUB_API = "https://api.github.com"
    PER_PAGE = 100

    def sync_repo(self, repo: Repo) -> None:
        headers = self._headers(repo)
        page = 1
        while True:
            response = requests.get(
                f"{self.GITHUB_API}/repos/{repo.full_name}/issues",
                headers=headers,
                params={"state": "all", "per_page": self.PER_PAGE, "page": page},
                timeout=30,
            )
            response.raise_for_status()
            items = response.json()
            if not items:
                break
            for item in items:
                if "pull_request" in item:
                    continue
                github_updated_at = parse_datetime(item["updated_at"])
                existing = GitHubIssue.objects.filter(
                    repo=repo, github_id=item["number"]
                ).first()
                if existing and existing.github_updated_at == github_updated_at:
                    continue
                GitHubIssue.objects.update_or_create(
                    repo=repo,
                    github_id=item["number"],
                    defaults={
                        "title": item["title"],
                        "body": item.get("body") or "",
                        "state": item["state"],
                        "labels": [label["name"] for label in item.get("labels", [])],
                        "assignees": [a["login"] for a in item.get("assignees", [])],
                        "github_created_at": parse_datetime(item["created_at"]),
                        "github_updated_at": github_updated_at,
                        "github_closed_at": parse_datetime(item["closed_at"]) if item.get("closed_at") else None,
                        "synced_at": timezone.now(),
                    },
                )
            page += 1
        repo.last_synced_at = timezone.now()
        repo.save(update_fields=["last_synced_at"])

    def _headers(self, repo: Repo) -> dict:
        return {
            "Authorization": f"Bearer {repo.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_issue(self, repo: Repo, title: str, body: str = "") -> GitHubIssue:
        """在 GitHub 上创建 issue 并同步到本地。"""
        response = requests.post(
            f"{self.GITHUB_API}/repos/{repo.full_name}/issues",
            headers=self._headers(repo),
            json={"title": title, "body": body},
            timeout=30,
        )
        response.raise_for_status()
        item = response.json()
        gh_issue, _ = GitHubIssue.objects.update_or_create(
            repo=repo,
            github_id=item["number"],
            defaults={
                "title": item["title"],
                "body": item.get("body") or "",
                "state": item["state"],
                "labels": [l["name"] for l in item.get("labels", [])],
                "assignees": [a["login"] for a in item.get("assignees", [])],
                "github_created_at": parse_datetime(item["created_at"]),
                "github_updated_at": parse_datetime(item["updated_at"]),
                "github_closed_at": None,
                "synced_at": timezone.now(),
            },
        )
        return gh_issue

    def close_issue(self, gh_issue: GitHubIssue) -> None:
        """关闭 GitHub 上的 issue。"""
        repo = gh_issue.repo
        response = requests.patch(
            f"{self.GITHUB_API}/repos/{repo.full_name}/issues/{gh_issue.github_id}",
            headers=self._headers(repo),
            json={"state": "closed"},
            timeout=30,
        )
        response.raise_for_status()
        gh_issue.state = GitHubIssue.STATE_CLOSED
        gh_issue.github_closed_at = timezone.now()
        gh_issue.synced_at = timezone.now()
        gh_issue.save(update_fields=["state", "github_closed_at", "synced_at"])

    def sync_all(self) -> None:
        for repo in Repo.objects.exclude(github_token=""):
            try:
                self.sync_repo(repo)
            except Exception:
                logger.exception("Failed to sync %s", repo.full_name)


class RepoCloneService:
    def clone_or_pull(self, repo, branch=None):
        repo.clone_status = "cloning"
        repo.clone_error = ""
        repo.save(update_fields=["clone_status", "clone_error"])

        askpass_path = None
        try:
            local_path = repo.local_path
            env, askpass_path = self._make_askpass(repo.github_token)

            # 清理残留的损坏目录（上次克隆失败留下的）
            if os.path.exists(local_path):
                check = subprocess.run(
                    ["git", "-C", local_path, "rev-parse", "HEAD"],
                    capture_output=True, text=True, timeout=10,
                )
                if check.returncode != 0:
                    shutil.rmtree(local_path)

            if not os.path.exists(local_path):
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                clone_url = repo.url if repo.url.endswith(".git") else f"{repo.url}.git"
                subprocess.run(
                    ["git", "clone", clone_url, local_path],
                    env=env, capture_output=True, text=True,
                    timeout=300, check=True,
                )
            else:
                subprocess.run(
                    ["git", "-C", local_path, "fetch", "--all"],
                    env=env, capture_output=True, text=True,
                    timeout=300, check=True,
                )
                target = branch or self._detect_default_branch(local_path) or repo.default_branch or "main"
                subprocess.run(
                    ["git", "-C", local_path, "reset", "--hard", f"origin/{target}"],
                    capture_output=True, text=True, timeout=60, check=True,
                )

            # 检测并更新实际默认分支
            detected = self._detect_default_branch(local_path)
            if detected:
                repo.default_branch = detected

            if branch:
                subprocess.run(
                    ["git", "-C", local_path, "checkout", branch],
                    env=env, capture_output=True, text=True,
                    timeout=60, check=True,
                )
                repo.current_branch = branch
            else:
                repo.current_branch = repo.default_branch or "main"

            repo.clone_status = "cloned"
            repo.cloned_at = timezone.now()
            repo.save(update_fields=["clone_status", "clone_error", "current_branch", "cloned_at", "default_branch"])
            try:
                self.sync_commits(repo)
            except Exception:
                logger.exception("sync_commits failed for %s", repo.full_name)
        except CalledProcessError as e:
            repo.clone_status = "failed"
            repo.clone_error = e.stderr or str(e)
            repo.save(update_fields=["clone_status", "clone_error"])
        except Exception as e:
            repo.clone_status = "failed"
            repo.clone_error = str(e)
            repo.save(update_fields=["clone_status", "clone_error"])
        finally:
            self._cleanup_askpass(askpass_path)

    def get_log(self, repo, limit=50):
        local_path = repo.local_path
        if not os.path.exists(local_path):
            return []
        result = subprocess.run(
            ["git", "-C", local_path, "log",
             "--format=%H%x00%an%x00%aI%x00%s", f"-n{limit}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\x00")
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits

    def get_branches(self, repo):
        local_path = repo.local_path
        if not os.path.exists(local_path):
            return []
        result = subprocess.run(
            ["git", "-C", local_path, "branch", "-r",
             "--format=%(refname:short)"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
        return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]

    def sync_commits(self, repo):
        local_path = repo.local_path
        if not os.path.exists(local_path):
            return

        existing_hashes = set(
            Commit.objects.filter(repo=repo).values_list("hash", flat=True)
        )

        result = subprocess.run(
            ["git", "-C", local_path, "log",
             "--format=%H%x00%ae%x00%an%x00%aI%x00%s", "--stat"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return

        parsed = self._parse_git_log_stat(result.stdout)

        new_commits = [
            Commit(
                repo=repo,
                hash=c["hash"],
                author_email=c["author_email"],
                author_name=c["author_name"],
                date=c["date"],
                message=c["message"],
                additions=c["additions"],
                deletions=c["deletions"],
                files_changed=c["files_changed"],
            )
            for c in parsed
            if c["hash"] not in existing_hashes
        ]
        Commit.objects.bulk_create(new_commits, ignore_conflicts=True)

        User = get_user_model()
        seen = {}
        for c in parsed:
            key = c["author_email"]
            if key not in seen:
                seen[key] = c["author_name"]

        for email, name in seen.items():
            alias, created = GitAuthorAlias.objects.get_or_create(
                repo=repo,
                author_email=email,
                defaults={"author_name": name},
            )
            if created and alias.user is None:
                matched_user = User.objects.filter(email=email).first()
                if matched_user:
                    alias.user = matched_user
                    alias.save(update_fields=["user"])

    @staticmethod
    def _parse_git_log_stat(output):
        """解析 git log --format=... --stat 的输出，返回提交列表。"""
        stat_summary_re = re.compile(
            r"\s*\d+ files? changed"
            r"(?:,\s*(\d+) insertions?\(\+\))?"
            r"(?:,\s*(\d+) deletions?\(-\))?"
        )
        file_line_re = re.compile(r"\s*(.+?)\s+\|")

        commits = []
        current = None
        for line in output.split("\n"):
            # Format header line: hash\x00email\x00name\x00date\x00message
            if "\x00" in line:
                if current is not None:
                    commits.append(current)
                parts = line.split("\x00", 4)
                if len(parts) == 5:
                    current = {
                        "hash": parts[0],
                        "author_email": parts[1],
                        "author_name": parts[2],
                        "date": parts[3],
                        "message": parts[4],
                        "additions": 0,
                        "deletions": 0,
                        "files_changed": [],
                    }
                else:
                    current = None
                continue

            if current is None:
                continue

            m = stat_summary_re.match(line)
            if m:
                current["additions"] = int(m.group(1) or 0)
                current["deletions"] = int(m.group(2) or 0)
                continue

            fm = file_line_re.match(line)
            if fm:
                current["files_changed"].append(fm.group(1).strip())

        if current is not None:
            commits.append(current)

        return commits

    @staticmethod
    def _detect_default_branch(local_path):
        """从本地仓库检测远程默认分支。"""
        result = subprocess.run(
            ["git", "-C", local_path, "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            ref = result.stdout.strip()
            return ref.split("/")[-1] if "/" in ref else None
        result = subprocess.run(
            ["git", "-C", local_path, "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        for candidate in ("main", "master", "develop"):
            result = subprocess.run(
                ["git", "-C", local_path, "rev-parse", "--verify", f"origin/{candidate}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return candidate
        return None

    @staticmethod
    def _make_askpass(token):
        env = os.environ.copy()
        if not token:
            return env, None
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False)
        f.write(f"#!/bin/sh\necho {token}\n")
        f.close()
        os.chmod(f.name, stat.S_IRWXU)
        env["GIT_ASKPASS"] = f.name
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env, f.name

    @staticmethod
    def _cleanup_askpass(askpass_path):
        if askpass_path:
            try:
                os.unlink(askpass_path)
            except OSError:
                pass
