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

    def test_oversized_digits_ignored(self):
        assert extract_iss_ids("ISS-" + "9" * 30) == []


class TestBuildLinkedIssues:
    def test_links_only_existing(self):
        issue = IssueFactory()
        result = build_linked_issues(f"fix ISS-{issue.id}", "")
        assert result == [{"id": issue.id, "ref": f"ISS-{issue.id:03d}", "source": "title"}]

    def test_drops_nonexistent(self):
        result = build_linked_issues("fix ISS-999999", "")
        assert result == []

    def test_oversized_digits_no_crash(self):
        assert build_linked_issues("ISS-" + "9" * 30, "") == []

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

    def test_suggest_resolved_false_when_pr_closed_unmerged(self, auth_client):
        from tests.factories import RepoFactory, PullRequestFactory, IssueFactory
        issue = IssueFactory(status="进行中")
        PullRequestFactory(
            repo=RepoFactory(), number=1, state="closed",
            linked_issues=self._link(issue),
        )
        response = auth_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert response.data["suggest_resolved"] is False
        assert len(response.data["results"]) == 1

    def test_multiple_prs_suggest_when_any_merged(self, auth_client):
        from tests.factories import RepoFactory, PullRequestFactory, IssueFactory
        repo = RepoFactory()
        issue = IssueFactory(status="进行中")
        PullRequestFactory(
            repo=repo, number=1, state="open",
            linked_issues=self._link(issue),
        )
        PullRequestFactory(
            repo=repo, number=2, state="merged",
            linked_issues=self._link(issue),
        )
        response = auth_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert len(response.data["results"]) == 2
        assert response.data["suggest_resolved"] is True

    @pytest.mark.parametrize(
        "completed_status", ["已解决", "已发布", "已关闭"]
    )
    def test_suggest_resolved_false_for_all_completed_statuses(
        self, auth_client, completed_status
    ):
        from tests.factories import RepoFactory, PullRequestFactory, IssueFactory
        issue = IssueFactory(status=completed_status)
        PullRequestFactory(
            repo=RepoFactory(), number=1, state="merged",
            linked_issues=self._link(issue),
        )
        response = auth_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert response.data["suggest_resolved"] is False

    def test_unauthenticated(self, api_client):
        from tests.factories import IssueFactory
        issue = IssueFactory()
        response = api_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert response.status_code == 401

    def test_forbidden_without_view_permission(self, regular_client):
        from tests.factories import IssueFactory
        issue = IssueFactory()
        response = regular_client.get(f"/api/issues/{issue.id}/pull-requests/")
        assert response.status_code == 403
