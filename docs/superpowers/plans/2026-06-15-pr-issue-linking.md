# PR ↔ Issue Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull GitHub pull requests into DevTrack, link them to issues by parsing `ISS-xxx` from PR title+body, and surface a non-binding "suggest resolved" hint (with a one-click accept) when a linked PR is merged.

**Architecture:** A new `repos.PullRequest` model mirrors `GitHubIssue`. The PR→Issue link is stored as a JSONField (`linked_issues`) on the PR (no M2M), recomputed every sync. PR sync is folded into the existing `GitHubSyncService` + the hourly `sync_all_repos` task + the manual per-repo sync. Two read endpoints expose PRs (per-repo list, per-issue reverse lookup). Frontend adds a linked-PR card on the issue detail page and a "Pull Requests" tab on the repo detail page.

**Tech Stack:** Django REST Framework, Postgres (jsonb + GIN index), Celery, Nuxt 4 + Nuxt UI, pytest + factory-boy.

**Working location:** worktree `/Users/ck/Git/matrix/devtrakr/.claude/worktrees/pr-issue-linking` on branch `worktree-pr-issue-linking`. DB `devtrakr_wt_pr_issue_linking` (cloned dev data: 264 issues, 1 repo). **Do not switch branches.** Backend commands run from `backend/` via `uv run`. Frontend from `frontend/`.

**Baseline (do not regress):** backend `uv run pytest` = 855 passed. Frontend `npx nuxi typecheck` = **51 pre-existing errors** across 19 files — frontend tasks must keep the count **≤ 51 (delta 0)**, never green.

**Spec:** `docs/superpowers/specs/2026-06-15-pr-issue-linking-design.md`

---

## File Structure

**Backend (`backend/`):**
- `apps/repos/services.py` — MODIFY: add `ISS_REF_RE`, `extract_iss_ids()`, `build_linked_issues()`, and `GitHubSyncService.sync_pull_requests()`. Add `PullRequest` to the model import.
- `apps/repos/models.py` — MODIFY: add `PullRequest` model (+ `GinIndex` import).
- `apps/repos/migrations/000X_pullrequest.py` — CREATE (via `makemigrations`).
- `apps/repos/serializers.py` — MODIFY: add `PullRequestSerializer`.
- `apps/repos/views.py` — MODIFY: add `RepoPullRequestListView`; call `sync_pull_requests` in `RepoSyncView`.
- `apps/repos/urls.py` — MODIFY: add `<int:pk>/pull-requests/` route (before the `<int:pk>/` catch-all).
- `apps/repos/tasks.py` — MODIFY: `sync_all_repos` also calls `sync_pull_requests`.
- `apps/issues/views.py` — MODIFY: add `IssuePullRequestsView`.
- `apps/issues/urls.py` — MODIFY: add `<int:pk>/pull-requests/` route.
- `tests/factories.py` — MODIFY: add `PullRequestFactory`.
- `tests/test_pull_requests.py` — CREATE: parser, model, sync, endpoints.
- `tests/test_repos.py` — MODIFY: assert `RepoSyncView` triggers PR sync.

**Frontend (`frontend/`):**
- `app/composables/usePullRequests.ts` — CREATE: `PullRequestRow`/`LinkedIssueRef` types + `prStateColor()` helper, aligned with `GithubPreview`.
- `app/pages/app/issues/[id].vue` — MODIFY: linked-PR card + suggest/accept; `fetchLinkedPRs()` in `onMounted`.
- `app/pages/app/repos/[id]/index.vue` — MODIFY: "Pull Requests" tab + `fetchPullRequests()` + lazy-load watcher.

---

## Task 1: ISS-ref parser

**Files:**
- Modify: `backend/apps/repos/services.py` (add near `parse_github_ref`, ~line 38)
- Test: `backend/tests/test_pull_requests.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_pull_requests.py`:

```python
import pytest
from apps.repos.services import extract_iss_ids, build_linked_issues
from tests.factories import IssueFactory

pytestmark = pytest.mark.django_db


class TestExtractIssIds:
    def test_basic(self):
        assert extract_iss_ids("fix ISS-42 now") == [42]

    def test_zero_padded(self):
        assert extract_iss_ids("ISS-007 done") == [7]

    def test_case_insensitive(self):
        assert extract_iss_ids("iss-5 and Iss-6") == [5, 6]

    def test_multiple_dedup_keeps_order(self):
        assert extract_iss_ids("ISS-3 ISS-1 ISS-3") == [3, 1]

    def test_no_match_inside_word(self):
        assert extract_iss_ids("XISS-9 and ISS-9Z") == []

    def test_empty(self):
        assert extract_iss_ids("") == []
        assert extract_iss_ids(None) == []


class TestBuildLinkedIssues:
    def test_links_only_existing(self):
        issue = IssueFactory()
        result = build_linked_issues(f"fix ISS-{issue.id}", "")
        assert result == [{"id": issue.id, "ref": f"ISS-{issue.id:03d}", "source": "title"}]

    def test_drops_nonexistent(self):
        result = build_linked_issues("fix ISS-999999", "")
        assert result == []

    def test_drops_soft_deleted(self):
        issue = IssueFactory(is_deleted=True)
        assert build_linked_issues(f"ISS-{issue.id}", "") == []

    def test_title_takes_precedence_over_body(self):
        issue = IssueFactory()
        result = build_linked_issues(f"ISS-{issue.id}", f"also ISS-{issue.id}")
        assert result == [{"id": issue.id, "ref": f"ISS-{issue.id:03d}", "source": "title"}]

    def test_body_source_when_only_in_body(self):
        issue = IssueFactory()
        result = build_linked_issues("no ref", f"closes ISS-{issue.id}")
        assert result == [{"id": issue.id, "ref": f"ISS-{issue.id:03d}", "source": "body"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py -q`
Expected: FAIL — `ImportError: cannot import name 'extract_iss_ids'`.

- [ ] **Step 3: Implement the parser**

In `backend/apps/repos/services.py`, after the `parse_github_ref` function (after line 37), add:

```python
ISS_REF_RE = re.compile(r"\bISS-0*(\d+)\b", re.IGNORECASE)


def extract_iss_ids(text):
    """从文本中提取 ISS-xxx 引用的 issue id(去重,保持首次出现顺序)。"""
    ids = []
    for m in ISS_REF_RE.finditer(text or ""):
        n = int(m.group(1))
        if n not in ids:
            ids.append(n)
    return ids


def build_linked_issues(title, body):
    """解析 PR 标题/正文中的 ISS-xxx,仅保留真实存在(未删除)的 issue。

    标题命中标 source=title,否则 body;返回如
    [{"id": 42, "ref": "ISS-042", "source": "title"}]。
    """
    from apps.issues.models import Issue  # 延迟导入避免循环依赖

    ordered = []
    seen = set()
    for n in extract_iss_ids(title):
        if n not in seen:
            seen.add(n)
            ordered.append((n, "title"))
    for n in extract_iss_ids(body):
        if n not in seen:
            seen.add(n)
            ordered.append((n, "body"))
    if not ordered:
        return []
    existing = set(
        Issue.objects.filter(
            pk__in=[n for n, _ in ordered], is_deleted=False
        ).values_list("pk", flat=True)
    )
    return [
        {"id": n, "ref": f"ISS-{n:03d}", "source": src}
        for n, src in ordered
        if n in existing
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py -q`
Expected: PASS (12 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/repos/services.py backend/tests/test_pull_requests.py
git commit -m "feat(repos): 解析 PR 文本中的 ISS-xxx 引用

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: PullRequest model + migration + factory

**Files:**
- Modify: `backend/apps/repos/models.py`
- Create: `backend/apps/repos/migrations/000X_pullrequest.py` (generated)
- Modify: `backend/tests/factories.py`
- Test: `backend/tests/test_pull_requests.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_pull_requests.py`:

```python
class TestPullRequestModel:
    def test_create_and_str(self):
        from apps.repos.models import PullRequest
        from tests.factories import PullRequestFactory
        pr = PullRequestFactory(number=7, title="Fix login")
        assert str(pr) == "#7 Fix login"
        assert pr.state in ("open", "closed", "merged")
        assert PullRequest.objects.count() == 1

    def test_unique_repo_number(self):
        from django.db import IntegrityError
        from tests.factories import PullRequestFactory
        pr = PullRequestFactory(number=1)
        with pytest.raises(IntegrityError):
            PullRequestFactory(repo=pr.repo, number=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py::TestPullRequestModel -q`
Expected: FAIL — `ImportError: cannot import name 'PullRequest'`.

- [ ] **Step 3: Add the model**

In `backend/apps/repos/models.py`, add the import at the top (after line 5 `from django.db import models`):

```python
from django.contrib.postgres.indexes import GinIndex
```

Append at the end of the file:

```python
class PullRequest(models.Model):
    STATE_OPEN = "open"
    STATE_CLOSED = "closed"
    STATE_MERGED = "merged"
    STATE_CHOICES = [
        (STATE_OPEN, "开放"),
        (STATE_CLOSED, "已关闭"),
        (STATE_MERGED, "已合并"),
    ]

    repo = models.ForeignKey(Repo, on_delete=models.CASCADE, related_name="pull_requests")
    number = models.PositiveIntegerField(verbose_name="PR 编号")
    title = models.CharField(max_length=500, verbose_name="标题")
    body = models.TextField(blank=True, verbose_name="内容")
    state = models.CharField(max_length=20, choices=STATE_CHOICES, verbose_name="状态")
    merged_at = models.DateTimeField(null=True, blank=True, verbose_name="合并时间")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="关闭时间")
    base_branch = models.CharField(max_length=255, blank=True, verbose_name="目标分支")
    head_branch = models.CharField(max_length=255, blank=True, verbose_name="源分支")
    author_login = models.CharField(max_length=200, blank=True, verbose_name="作者")
    author_avatar = models.CharField(max_length=500, blank=True, verbose_name="作者头像")
    html_url = models.CharField(max_length=500, blank=True, verbose_name="链接")
    github_created_at = models.DateTimeField(verbose_name="GitHub 创建时间")
    github_updated_at = models.DateTimeField(verbose_name="GitHub 更新时间")
    synced_at = models.DateTimeField(verbose_name="同步时间")
    linked_issues = models.JSONField(default=list, blank=True, verbose_name="关联 Issue")

    class Meta:
        verbose_name = "Pull Request"
        verbose_name_plural = "Pull Requests"
        unique_together = ("repo", "number")
        ordering = ["-github_created_at"]
        indexes = [GinIndex(fields=["linked_issues"], name="pr_linked_issues_gin")]

    def __str__(self):
        return f"#{self.number} {self.title}"
```

- [ ] **Step 4: Add the factory**

In `backend/tests/factories.py`, change the repos import line (line 8) to add `PullRequest`:

```python
from apps.repos.models import Repo, GitHubIssue, Commit, GitAuthorAlias, PullRequest
```

Add after `GitHubIssueFactory` (after line 138):

```python
class PullRequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PullRequest

    repo = factory.SubFactory(RepoFactory)
    number = factory.Sequence(lambda n: n + 1)
    title = factory.LazyFunction(lambda: fake.sentence())
    body = factory.LazyFunction(lambda: fake.paragraph())
    state = "open"
    base_branch = "main"
    head_branch = factory.Sequence(lambda n: f"feat/branch-{n}")
    author_login = factory.LazyFunction(lambda: fake.user_name())
    html_url = factory.LazyAttribute(lambda o: f"https://github.com/{o.repo.full_name}/pull/{o.number}")
    github_created_at = factory.LazyFunction(tz.now)
    github_updated_at = factory.LazyFunction(tz.now)
    synced_at = factory.LazyFunction(tz.now)
    linked_issues = factory.LazyFunction(list)
```

- [ ] **Step 5: Generate and apply the migration**

Run (from `backend/`):
```bash
uv run python manage.py makemigrations repos
uv run python manage.py migrate
```
Expected: a new `repos/migrations/000X_pullrequest.py` is created (CreateModel + AddIndex), and migrate applies it ("Applying repos.000X_pullrequest... OK").

- [ ] **Step 6: Run tests to verify they pass**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py::TestPullRequestModel -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/repos/models.py backend/apps/repos/migrations/ backend/tests/factories.py backend/tests/test_pull_requests.py
git commit -m "feat(repos): 新增 PullRequest 模型与 linked_issues GIN 索引

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `sync_pull_requests` service method

**Files:**
- Modify: `backend/apps/repos/services.py`
- Test: `backend/tests/test_pull_requests.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_pull_requests.py`:

```python
from unittest.mock import patch, MagicMock


def _page(items):
    resp = MagicMock()
    resp.json.return_value = items
    resp.raise_for_status.return_value = None
    return resp


class TestSyncPullRequests:
    def _pr_payload(self, number, title, body="", merged_at=None, state="open"):
        return {
            "number": number, "title": title, "body": body,
            "state": state, "merged_at": merged_at, "closed_at": None,
            "base": {"ref": "main"}, "head": {"ref": "feat/x"},
            "user": {"login": "octocat", "avatar_url": "http://x/a.png"},
            "html_url": f"https://github.com/org/r/pull/{number}",
            "created_at": "2026-06-01T00:00:00Z", "updated_at": "2026-06-02T00:00:00Z",
        }

    def test_creates_prs_and_links_issue(self):
        from apps.repos.models import PullRequest
        from apps.repos.services import GitHubSyncService
        from tests.factories import RepoFactory, IssueFactory
        repo = RepoFactory(github_token="ghp_x")
        issue = IssueFactory()
        with patch("apps.repos.services.requests.get") as mock_get:
            mock_get.side_effect = [
                _page([self._pr_payload(1, f"fix ISS-{issue.id}")]),
                _page([]),
            ]
            GitHubSyncService().sync_pull_requests(repo)
        pr = PullRequest.objects.get(repo=repo, number=1)
        assert pr.linked_issues == [{"id": issue.id, "ref": f"ISS-{issue.id:03d}", "source": "title"}]
        assert pr.state == "open"
        assert pr.base_branch == "main"

    def test_merged_state_derived_from_merged_at(self):
        from apps.repos.models import PullRequest
        from apps.repos.services import GitHubSyncService
        from tests.factories import RepoFactory
        repo = RepoFactory(github_token="ghp_x")
        with patch("apps.repos.services.requests.get") as mock_get:
            mock_get.side_effect = [
                _page([self._pr_payload(2, "done", merged_at="2026-06-03T00:00:00Z", state="closed")]),
                _page([]),
            ]
            GitHubSyncService().sync_pull_requests(repo)
        assert PullRequest.objects.get(repo=repo, number=2).state == "merged"

    def test_resync_recomputes_links(self):
        from apps.repos.models import PullRequest
        from apps.repos.services import GitHubSyncService
        from tests.factories import RepoFactory, IssueFactory
        repo = RepoFactory(github_token="ghp_x")
        issue = IssueFactory()
        svc = GitHubSyncService()
        with patch("apps.repos.services.requests.get") as mock_get:
            mock_get.side_effect = [_page([self._pr_payload(3, "wip")]), _page([])]
            svc.sync_pull_requests(repo)
        assert PullRequest.objects.get(repo=repo, number=3).linked_issues == []
        with patch("apps.repos.services.requests.get") as mock_get:
            mock_get.side_effect = [_page([self._pr_payload(3, f"wip ISS-{issue.id}")]), _page([])]
            svc.sync_pull_requests(repo)
        assert PullRequest.objects.get(repo=repo, number=3).linked_issues[0]["id"] == issue.id
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py::TestSyncPullRequests -q`
Expected: FAIL — `AttributeError: 'GitHubSyncService' object has no attribute 'sync_pull_requests'`.

- [ ] **Step 3: Implement the method**

In `backend/apps/repos/services.py`, update the model import (line 17) to include `PullRequest`:

```python
from .models import Repo, GitHubIssue, Commit, GitAuthorAlias, PullRequest
```

Add this method to the `GitHubSyncService` class, after `sync_repo` (after line 139):

```python
    def sync_pull_requests(self, repo: Repo) -> None:
        headers = self._headers(repo)
        page = 1
        while True:
            response = requests.get(
                f"{self.GITHUB_API}/repos/{repo.full_name}/pulls",
                headers=headers,
                params={"state": "all", "per_page": self.PER_PAGE, "page": page},
                timeout=30,
            )
            response.raise_for_status()
            items = response.json()
            if not items:
                break
            for item in items:
                merged_at = parse_datetime(item["merged_at"]) if item.get("merged_at") else None
                if merged_at:
                    state = PullRequest.STATE_MERGED
                else:
                    state = item.get("state") or PullRequest.STATE_OPEN
                user = item.get("user") or {}
                base = item.get("base") or {}
                head = item.get("head") or {}
                PullRequest.objects.update_or_create(
                    repo=repo,
                    number=item["number"],
                    defaults={
                        "title": item.get("title") or "",
                        "body": item.get("body") or "",
                        "state": state,
                        "merged_at": merged_at,
                        "closed_at": parse_datetime(item["closed_at"]) if item.get("closed_at") else None,
                        "base_branch": base.get("ref") or "",
                        "head_branch": head.get("ref") or "",
                        "author_login": user.get("login") or "",
                        "author_avatar": user.get("avatar_url") or "",
                        "html_url": item.get("html_url") or "",
                        "github_created_at": parse_datetime(item["created_at"]),
                        "github_updated_at": parse_datetime(item["updated_at"]),
                        "synced_at": timezone.now(),
                        "linked_issues": build_linked_issues(
                            item.get("title") or "", item.get("body") or ""
                        ),
                    },
                )
            page += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py::TestSyncPullRequests -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/repos/services.py backend/tests/test_pull_requests.py
git commit -m "feat(repos): GitHubSyncService 同步 PR 并回填 ISS 关联

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Wire PR sync into the task + manual sync

**Files:**
- Modify: `backend/apps/repos/tasks.py`
- Modify: `backend/apps/repos/views.py` (`RepoSyncView.post`)
- Test: `backend/tests/test_repos.py`, `backend/tests/test_pull_requests.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_repos.py`, find `TestRepoSync.test_sync_triggers_service` (line 76-84) and add this method right after it (inside `class TestRepoSync`):

```python
    def test_sync_triggers_pull_requests(self, auth_client):
        repo = RepoFactory(github_token="ghp_test123")
        with patch("apps.repos.views.GitHubSyncService") as MockService:
            mock_instance = MagicMock()
            MockService.return_value = mock_instance
            response = auth_client.post(f"/api/repos/{repo.id}/sync/")
        assert response.status_code == 200
        mock_instance.sync_pull_requests.assert_called_once()
```

Append to `backend/tests/test_pull_requests.py`:

```python
class TestSyncAllReposTask:
    def test_task_syncs_issues_and_prs(self):
        from apps.repos.tasks import sync_all_repos
        from tests.factories import RepoFactory
        RepoFactory(github_token="ghp_x")
        with patch("apps.repos.tasks.GitHubSyncService") as MockService:
            mock_instance = MagicMock()
            MockService.return_value = mock_instance
            sync_all_repos()
        mock_instance.sync_repo.assert_called_once()
        mock_instance.sync_pull_requests.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
uv run pytest tests/test_repos.py::TestRepoSync::test_sync_triggers_pull_requests tests/test_pull_requests.py::TestSyncAllReposTask -q
```
Expected: FAIL — `sync_pull_requests.assert_called_once()` raises (not called).

- [ ] **Step 3: Wire the task**

In `backend/apps/repos/tasks.py`, replace the body of `sync_all_repos` (lines 21-28) with:

```python
@shared_task(ignore_result=False)
def sync_all_repos():
    """Sync GitHub issues and pull requests for all repos with tokens."""
    service = GitHubSyncService()
    for repo in Repo.objects.exclude(github_token=""):
        try:
            service.sync_repo(repo)
            service.sync_pull_requests(repo)
        except Exception as e:
            logger.error("Failed to sync repo %s: %s", repo.full_name, e)
```

- [ ] **Step 4: Wire the manual sync view**

In `backend/apps/repos/views.py`, in `RepoSyncView.post`, find the line `GitHubSyncService().sync_repo(repo)` (line 92) and replace it with:

```python
            service = GitHubSyncService()
            service.sync_repo(repo)
            service.sync_pull_requests(repo)
```

- [ ] **Step 5: Run tests to verify they pass**

Run (from `backend/`):
```bash
uv run pytest tests/test_repos.py::TestRepoSync tests/test_pull_requests.py::TestSyncAllReposTask -q
```
Expected: PASS (all green, including the existing `TestRepoSync` cases).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/repos/tasks.py backend/apps/repos/views.py backend/tests/test_repos.py backend/tests/test_pull_requests.py
git commit -m "feat(repos): 手动同步与每小时任务一并拉取 PR

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: PR serializer + per-repo list endpoint

**Files:**
- Modify: `backend/apps/repos/serializers.py`
- Modify: `backend/apps/repos/views.py`
- Modify: `backend/apps/repos/urls.py`
- Test: `backend/tests/test_pull_requests.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_pull_requests.py`:

```python
class TestRepoPullRequestList:
    def test_list_for_repo(self, auth_client):
        from tests.factories import RepoFactory, PullRequestFactory, IssueFactory
        repo = RepoFactory()
        issue = IssueFactory(title="Login bug")
        PullRequestFactory(repo=repo, number=1, state="merged",
                           linked_issues=[{"id": issue.id, "ref": f"ISS-{issue.id:03d}", "source": "title"}])
        PullRequestFactory(repo=repo, number=2, state="open", linked_issues=[])
        PullRequestFactory()  # other repo
        response = auth_client.get(f"/api/repos/{repo.id}/pull-requests/")
        assert response.status_code == 200
        assert len(response.data) == 2
        merged = next(p for p in response.data if p["number"] == 1)
        assert merged["state"] == "merged"
        assert merged["linked_issues"][0]["title"] == "Login bug"
        assert merged["linked_issues"][0]["status"] == issue.status

    def test_filter_by_state(self, auth_client):
        from tests.factories import RepoFactory, PullRequestFactory
        repo = RepoFactory()
        PullRequestFactory(repo=repo, number=1, state="merged")
        PullRequestFactory(repo=repo, number=2, state="open")
        response = auth_client.get(f"/api/repos/{repo.id}/pull-requests/?state=merged")
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["state"] == "merged"

    def test_unauthenticated(self, api_client):
        from tests.factories import RepoFactory
        repo = RepoFactory()
        response = api_client.get(f"/api/repos/{repo.id}/pull-requests/")
        assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py::TestRepoPullRequestList -q`
Expected: FAIL — 404 (route does not exist).

- [ ] **Step 3: Add the serializer**

In `backend/apps/repos/serializers.py`, update the import (line 2) to include `PullRequest`:

```python
from .models import Repo, GitHubIssue, GitAuthorAlias, PullRequest
```

Append at the end of the file:

```python
class PullRequestSerializer(serializers.ModelSerializer):
    repo_full_name = serializers.CharField(source="repo.full_name", read_only=True)
    linked_issues = serializers.SerializerMethodField()

    class Meta:
        model = PullRequest
        fields = [
            "id", "repo", "repo_full_name", "number", "title", "state",
            "merged_at", "closed_at", "base_branch", "head_branch",
            "author_login", "author_avatar", "html_url",
            "github_created_at", "github_updated_at", "linked_issues",
        ]
        read_only_fields = fields

    def get_linked_issues(self, obj):
        from apps.issues.models import Issue
        refs = obj.linked_issues or []
        ids = [r.get("id") for r in refs if r.get("id") is not None]
        if not ids:
            return []
        issues = {
            i.id: i
            for i in Issue.objects.filter(pk__in=ids).only("id", "title", "status")
        }
        result = []
        for r in refs:
            issue = issues.get(r.get("id"))
            if issue:
                result.append({
                    "id": issue.id,
                    "title": issue.title,
                    "status": issue.status,
                    "ref": r.get("ref"),
                    "source": r.get("source"),
                })
        return result
```

- [ ] **Step 4: Add the view**

In `backend/apps/repos/views.py`, update the serializer import (line 10) to add `PullRequestSerializer`:

```python
from .serializers import RepoSerializer, GitHubIssueBriefSerializer, GitHubIssueDetailSerializer, GitAuthorAliasSerializer, PullRequestSerializer
```

Update the models import (line 9) to add `PullRequest`:

```python
from .models import Repo, GitHubIssue, GitAuthorAlias, PullRequest
```

Add this view after `GitHubIssueDetailView` (after line 70):

```python
class RepoPullRequestListView(generics.ListAPIView):
    serializer_class = PullRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = (
            PullRequest.objects.select_related("repo")
            .filter(repo_id=self.kwargs["pk"])
            .order_by("-github_created_at")
        )
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        return qs
```

- [ ] **Step 5: Add the URL**

In `backend/apps/repos/urls.py`, add `RepoPullRequestListView` to the import block (after line 7), then add this route **before** the `<int:pk>/` catch-all (before line 23):

```python
    path("<int:pk>/pull-requests/", RepoPullRequestListView.as_view(), name="repo-pull-requests"),
```

- [ ] **Step 6: Run test to verify it passes**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py::TestRepoPullRequestList -q`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/repos/serializers.py backend/apps/repos/views.py backend/apps/repos/urls.py backend/tests/test_pull_requests.py
git commit -m "feat(repos): 新增仓库 PR 列表接口

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Per-issue reverse lookup + suggest_resolved

**Files:**
- Modify: `backend/apps/issues/views.py`
- Modify: `backend/apps/issues/urls.py`
- Test: `backend/tests/test_pull_requests.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_pull_requests.py`:

```python
class TestIssuePullRequests:
    def _link(self, issue):
        return [{"id": issue.id, "ref": f"ISS-{issue.id:03d}", "source": "title"}]

    def test_reverse_lookup(self, auth_client):
        from tests.factories import RepoFactory, PullRequestFactory, IssueFactory
        repo = RepoFactory()
        issue = IssueFactory(status="进行中")
        PullRequestFactory(repo=repo, number=1, state="open", linked_issues=self._link(issue))
        PullRequestFactory(repo=repo, number=2, linked_issues=[])
        response = auth_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["number"] == 1

    def test_suggest_resolved_true_when_merged_and_open_issue(self, auth_client):
        from tests.factories import RepoFactory, PullRequestFactory, IssueFactory
        issue = IssueFactory(status="进行中")
        PullRequestFactory(repo=RepoFactory(), number=1, state="merged", linked_issues=self._link(issue))
        response = auth_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert response.data["suggest_resolved"] is True

    def test_suggest_resolved_false_when_pr_open(self, auth_client):
        from tests.factories import RepoFactory, PullRequestFactory, IssueFactory
        issue = IssueFactory(status="进行中")
        PullRequestFactory(repo=RepoFactory(), number=1, state="open", linked_issues=self._link(issue))
        response = auth_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert response.data["suggest_resolved"] is False

    def test_suggest_resolved_false_when_issue_already_completed(self, auth_client):
        from tests.factories import RepoFactory, PullRequestFactory, IssueFactory
        issue = IssueFactory(status="已解决")
        PullRequestFactory(repo=RepoFactory(), number=1, state="merged", linked_issues=self._link(issue))
        response = auth_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert response.data["suggest_resolved"] is False

    def test_404_for_missing_issue(self, auth_client):
        response = auth_client.get("/api/issues/999999/pull-requests/")
        assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py::TestIssuePullRequests -q`
Expected: FAIL — 404 (route does not exist) for the success cases.

- [ ] **Step 3: Add the view**

In `backend/apps/issues/views.py`, add this view at the end of the file:

```python
class IssuePullRequestsView(APIView):
    """反查关联到该 Issue 的 PR,并给出是否建议标记为已解决。"""
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    queryset = Issue.objects.none()

    def get(self, request, pk):
        from apps.repos.models import PullRequest
        from apps.repos.serializers import PullRequestSerializer
        try:
            issue = Issue.objects.get(pk=pk, is_deleted=False)
        except Issue.DoesNotExist:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        prs = (
            PullRequest.objects.filter(linked_issues__contains=[{"id": issue.id}])
            .select_related("repo")
            .order_by("-github_created_at")
        )
        completed = ("已解决", "已发布", "已关闭")
        suggest_resolved = (
            issue.status not in completed
            and prs.filter(state=PullRequest.STATE_MERGED).exists()
        )
        return Response({
            "results": PullRequestSerializer(prs, many=True).data,
            "suggest_resolved": suggest_resolved,
        })
```

- [ ] **Step 4: Add the URL**

In `backend/apps/issues/urls.py`, add `IssuePullRequestsView` to the import block (after line 10), then add this route after the `<int:pk>/` detail route (after line 20):

```python
    path("<int:pk>/pull-requests/", IssuePullRequestsView.as_view(), name="issue-pull-requests"),
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `backend/`): `uv run pytest tests/test_pull_requests.py::TestIssuePullRequests -q`
Expected: PASS (5 passed).

- [ ] **Step 6: Run the full backend suite (no regressions)**

Run (from `backend/`): `uv run pytest -q`
Expected: PASS — 855 prior + new tests, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/issues/views.py backend/apps/issues/urls.py backend/tests/test_pull_requests.py
git commit -m "feat(issues): Issue 反查关联 PR 与已解决建议

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Frontend — linked-PR card on issue detail

**Files:**
- Create: `frontend/app/composables/usePullRequests.ts`
- Modify: `frontend/app/pages/app/issues/[id].vue`

> No frontend component-test harness exists. Verify with `npx nuxi typecheck` (count must stay ≤ 51) and a manual visual check.

- [ ] **Step 1: Create the types/helper composable**

Create `frontend/app/composables/usePullRequests.ts`:

```typescript
// PR 行类型,与 useLinkPreview 的 GithubPreview 字段保持一致
export interface LinkedIssueRef {
  id: number
  title: string
  status: string
  ref: string
  source: 'title' | 'body'
}

export interface PullRequestRow {
  id: number
  repo: number
  repo_full_name: string
  number: number
  title: string
  state: 'open' | 'closed' | 'merged'
  merged_at: string | null
  closed_at: string | null
  base_branch: string
  head_branch: string
  author_login: string
  author_avatar: string
  html_url: string
  github_created_at: string
  github_updated_at: string
  linked_issues: LinkedIssueRef[]
}

// PR 状态徽标颜色(open→警告,merged→紫色用 secondary,closed→中性)
export function prStateColor(state: string): 'warning' | 'secondary' | 'neutral' {
  if (state === 'open') return 'warning'
  if (state === 'merged') return 'secondary'
  return 'neutral'
}
```

- [ ] **Step 2: Add state + fetch in the issue detail page**

In `frontend/app/pages/app/issues/[id].vue`, in the `<script setup>` block near the other `ref` declarations (e.g. by `allGHIssues`), add:

```typescript
const linkedPRs = ref<PullRequestRow[]>([])
const suggestResolved = ref(false)

async function fetchLinkedPRs() {
  if (!issue.value?.id) return
  try {
    const res = await api<{ results: PullRequestRow[]; suggest_resolved: boolean }>(
      `/api/issues/${issue.value.id}/pull-requests/`
    )
    linkedPRs.value = res.results || []
    suggestResolved.value = !!res.suggest_resolved
  } catch (e) {
    console.error('Failed to load linked PRs:', e)
  }
}

// 采纳建议:走与状态胶囊相同的 PATCH 路径,完成后刷新 PR 区
async function acceptResolveSuggestion() {
  await autoSave('status', '已解决')
  await fetchLinkedPRs()
}
```

If `can` is not already destructured from `useAuth()` in this file, add near the top of `<script setup>`:

```typescript
const { can } = useAuth()
```

- [ ] **Step 3: Call `fetchLinkedPRs` on mount**

In `frontend/app/pages/app/issues/[id].vue`, inside `onMounted` (after `fetchGHIssues()` on line 1503), add:

```typescript
  fetchLinkedPRs()
```

- [ ] **Step 4: Add the card to the template**

In `frontend/app/pages/app/issues/[id].vue`, immediately after the GitHub 关联 card (after its closing `</div>` on line 524), add:

```vue
        <div v-if="linkedPRs.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">关联 PR</h3>

          <!-- 建议已解决:仅在有合并 PR 且未完成时显示 -->
          <div v-if="suggestResolved" class="flex items-center justify-between gap-2 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 rounded-lg px-3 py-2">
            <span class="text-xs text-emerald-700 dark:text-emerald-300">关联 PR 已合并 · 建议标记为已解决</span>
            <UButton
              v-if="can('issues.change_issue')"
              size="xs"
              color="success"
              variant="soft"
              @click="acceptResolveSuggestion"
            >
              采纳建议
            </UButton>
          </div>

          <div class="space-y-2">
            <a
              v-for="pr in linkedPRs"
              :key="pr.id"
              :href="pr.html_url"
              target="_blank"
              class="flex items-center justify-between bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <div class="min-w-0 flex-1">
                <div class="flex items-center space-x-2">
                  <UBadge :color="prStateColor(pr.state)" variant="subtle" size="xs">{{ pr.state }}</UBadge>
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ pr.repo_full_name }}#{{ pr.number }}</span>
                </div>
                <p class="text-sm text-gray-900 dark:text-gray-100 truncate mt-0.5">{{ pr.title }}</p>
              </div>
              <UIcon name="i-heroicons-arrow-top-right-on-square" class="w-4 h-4 text-gray-400 shrink-0" />
            </a>
          </div>
        </div>
```

- [ ] **Step 5: Typecheck (delta must be 0)**

Run (from `frontend/`): `npx nuxi typecheck 2>&1 | grep -cE "error TS"`
Expected: `51` (unchanged). If higher, fix the newly-introduced errors in the files you touched.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/composables/usePullRequests.ts frontend/app/pages/app/issues/\[id\].vue
git commit -m "feat(issues): Issue 详情页展示关联 PR 与采纳建议

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Frontend — Pull Requests tab on repo detail

**Files:**
- Modify: `frontend/app/pages/app/repos/[id]/index.vue`

- [ ] **Step 1: Add the tab item + column defs**

In `frontend/app/pages/app/repos/[id]/index.vue`, change `tabItems` (lines 481-485) to:

```typescript
const tabItems = [
  { label: 'Issues', slot: 'issues', value: 'issues' },
  { label: 'Pull Requests', slot: 'pull-requests', value: 'pull-requests' },
  { label: '提交记录', slot: 'git-log', value: 'git-log' },
  { label: '开发者洞察', slot: 'insights', value: 'insights' },
]
```

Add after `gitLogColumns` (after line 501):

```typescript
const prColumns = [
  { accessorKey: 'number', header: '#' },
  { accessorKey: 'title', header: '标题' },
  { accessorKey: 'state', header: '状态' },
  { accessorKey: 'linked_issues', header: '关联 Issue' },
  { accessorKey: 'github_updated_at', header: '更新时间' },
]
```

- [ ] **Step 2: Add PR state + fetch function**

In `frontend/app/pages/app/repos/[id]/index.vue`, near the other state refs (e.g. by `gitLog`), add:

```typescript
const pullRequests = ref<PullRequestRow[]>([])
const prsLoading = ref(false)

async function fetchPullRequests() {
  prsLoading.value = true
  try {
    pullRequests.value = await api<PullRequestRow[]>(`/api/repos/${route.params.id}/pull-requests/`)
  } catch (e) {
    console.error('Failed to load pull requests:', e)
  } finally {
    prsLoading.value = false
  }
}
```

- [ ] **Step 3: Lazy-load on tab switch**

In `frontend/app/pages/app/repos/[id]/index.vue`, update the `watch(activeTab, ...)` (lines 755-762) by adding inside the callback:

```typescript
  if (val === 'pull-requests' && !pullRequests.value.length) {
    fetchPullRequests()
  }
```

- [ ] **Step 4: Add the tab slot template**

In `frontend/app/pages/app/repos/[id]/index.vue`, add this template block right after the `</template>` that closes `#issues` (after line 208, before `<template #git-log>`):

```vue
      <template #pull-requests>
        <div class="mt-4">
          <div v-if="prsLoading" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">加载 PR 中...</div>
          </div>
          <div v-else-if="!pullRequests.length" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">暂无 PR,点击上方「同步」拉取</div>
          </div>
          <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
            <UTable :data="pullRequests" :columns="prColumns" :ui="{ th: 'text-xs', td: 'text-sm' }">
              <template #number-cell="{ row }">
                <a :href="row.original.html_url" target="_blank" class="font-mono text-xs text-primary-500 hover:underline">#{{ row.original.number }}</a>
              </template>
              <template #state-cell="{ row }">
                <UBadge :color="prStateColor(row.original.state)" variant="subtle" size="xs">{{ row.original.state }}</UBadge>
              </template>
              <template #linked_issues-cell="{ row }">
                <div class="flex flex-wrap gap-1">
                  <NuxtLink
                    v-for="li in row.original.linked_issues"
                    :key="li.id"
                    :to="`/app/issues/${li.id}`"
                    class="text-xs text-primary-500 hover:underline"
                  >{{ li.ref }}</NuxtLink>
                  <span v-if="!row.original.linked_issues.length" class="text-xs text-gray-400">-</span>
                </div>
              </template>
              <template #github_updated_at-cell="{ row }">
                {{ row.original.github_updated_at?.slice(0, 16)?.replace('T', ' ') || '-' }}
              </template>
            </UTable>
          </div>
        </div>
      </template>
```

- [ ] **Step 5: Refresh PRs after a manual sync**

In `frontend/app/pages/app/repos/[id]/index.vue`, in `handleSync` (after `await fetchIssues()` on line 690), add:

```typescript
    await fetchPullRequests()
```

- [ ] **Step 6: Typecheck (delta must be 0)**

Run (from `frontend/`): `npx nuxi typecheck 2>&1 | grep -cE "error TS"`
Expected: `51` (unchanged).

- [ ] **Step 7: Commit**

```bash
git add frontend/app/pages/app/repos/\[id\]/index.vue
git commit -m "feat(repos): 仓库详情页新增 Pull Requests 页签

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final Verification

- [ ] **Backend:** from `backend/`, `uv run pytest -q` → all pass (855 + ~25 new).
- [ ] **Frontend:** from `frontend/`, `npx nuxi typecheck 2>&1 | grep -cE "error TS"` → `51`.
- [ ] **Manual smoke (optional):** start backend + frontend, open an issue whose title/body a synced merged PR references → linked-PR card shows the PR with a `merged` badge and the "采纳建议" button; open the repo page → "Pull Requests" tab lists PRs with clickable `ISS-xxx` chips.

## Notes for the implementer

- **jsonb containment:** `linked_issues__contains=[{"id": issue.id}]` compiles to Postgres `@>`, which matches array elements that are supersets of `{"id": N}` — so the extra `ref`/`source` keys don't break the match. The `pr_linked_issues_gin` index backs this.
- **No new periodic-task migration:** the hourly `sync_all_repos` schedule already exists; Task 4 only extends the task body. Never edit the existing `apps/ai/migrations/0002_seed_celery_periodic_tasks.py`.
- **`uv run` warning:** running `uv` in the worktree prints a benign `VIRTUAL_ENV does not match` line; it uses the worktree `.venv` correctly. Do not silence it.
- **Accept button:** uses the existing `autoSave('status','已解决')` path (PATCH `/api/issues/{id}/`), which sets `resolved_at` and freezes the KPI settlement snapshot when an assignee exists — identical to clicking the status chip. No new resolve endpoint.
- **Nuxt auto-import:** `prStateColor` and the `PullRequestRow`/`LinkedIssueRef` types live in `app/composables/usePullRequests.ts` and are auto-imported (same as `GithubPreview` from `useLinkPreview.ts`). If `npx nuxi typecheck` reports them as undefined, add `import { prStateColor, type PullRequestRow } from '~/composables/usePullRequests'` to the page's `<script setup>`.
