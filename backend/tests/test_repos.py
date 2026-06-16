import pytest
from unittest.mock import patch, MagicMock
from tests.factories import RepoFactory, GitHubIssueFactory

pytestmark = pytest.mark.django_db


class TestRepoList:
    def test_list_repos(self, auth_client):
        RepoFactory.create_batch(3)
        response = auth_client.get("/api/repos/")
        assert response.status_code == 200
        assert len(response.data) == 3

    def test_unauthenticated(self, api_client):
        response = api_client.get("/api/repos/")
        assert response.status_code == 401


class TestRepoDetail:
    def test_get_repo_detail(self, auth_client):
        repo = RepoFactory(name="my-repo", full_name="org/my-repo")
        response = auth_client.get(f"/api/repos/{repo.id}/")
        assert response.status_code == 200
        assert response.data["full_name"] == "org/my-repo"


class TestRepoCreate:
    def test_create_repo(self, auth_client):
        response = auth_client.post("/api/repos/", {
            "name": "new-repo",
            "full_name": "org/new-repo",
            "url": "https://github.com/org/new-repo",
            "description": "A new repo",
            "default_branch": "main",
            "language": "Python",
            "stars": 0,
        })
        assert response.status_code == 201
        assert response.data["name"] == "new-repo"


class TestRepoDelete:
    def test_delete_repo(self, auth_client):
        repo = RepoFactory()
        response = auth_client.delete(f"/api/repos/{repo.id}/")
        assert response.status_code == 204


class TestRepoIssueCounts:
    def test_list_includes_issue_counts(self, auth_client):
        repo = RepoFactory()
        GitHubIssueFactory.create_batch(3, repo=repo, state="open")
        GitHubIssueFactory.create_batch(2, repo=repo, state="closed")
        response = auth_client.get("/api/repos/")
        assert response.status_code == 200
        data = response.data[0]
        assert data["open_issues_count"] == 3
        assert data["closed_issues_count"] == 2

    def test_detail_includes_issue_counts(self, auth_client):
        repo = RepoFactory()
        GitHubIssueFactory.create_batch(5, repo=repo, state="open")
        response = auth_client.get(f"/api/repos/{repo.id}/")
        assert response.status_code == 200
        assert response.data["open_issues_count"] == 5
        assert response.data["closed_issues_count"] == 0

    def test_detail_includes_last_synced_at(self, auth_client):
        repo = RepoFactory()
        response = auth_client.get(f"/api/repos/{repo.id}/")
        assert "last_synced_at" in response.data


class TestRepoSync:
    def test_sync_triggers_service(self, auth_client):
        repo = RepoFactory(github_token="ghp_test123")
        with patch("apps.repos.views.GitHubSyncService") as MockService:
            mock_instance = MagicMock()
            MockService.return_value = mock_instance
            response = auth_client.post(f"/api/repos/{repo.id}/sync/")
        assert response.status_code == 200
        mock_instance.sync_repo.assert_called_once()
        assert response.data["id"] == repo.id

    def test_sync_triggers_pull_requests(self, auth_client):
        repo = RepoFactory(github_token="ghp_test123")
        with patch("apps.repos.views.GitHubSyncService") as MockService:
            mock_instance = MagicMock()
            MockService.return_value = mock_instance
            response = auth_client.post(f"/api/repos/{repo.id}/sync/")
        assert response.status_code == 200
        mock_instance.sync_pull_requests.assert_called_once()

    def test_sync_returns_502_on_github_failure(self, auth_client):
        repo = RepoFactory(github_token="ghp_test123")
        with patch("apps.repos.views.GitHubSyncService") as MockService:
            mock_instance = MagicMock()
            mock_instance.sync_repo.side_effect = Exception("API rate limit")
            MockService.return_value = mock_instance
            response = auth_client.post(f"/api/repos/{repo.id}/sync/")
        assert response.status_code == 502

    def test_sync_unauthenticated(self, api_client):
        repo = RepoFactory()
        response = api_client.post(f"/api/repos/{repo.id}/sync/")
        assert response.status_code == 401

    def test_sync_returns_404_for_nonexistent_repo(self, auth_client):
        response = auth_client.post("/api/repos/99999/sync/")
        assert response.status_code == 404


class TestGitHubIssueDetail:
    def test_get_github_issue_detail(self, auth_client):
        from tests.factories import GitHubIssueFactory
        issue = GitHubIssueFactory(
            title="Fix bug",
            body="Detailed description here",
            state="open",
            labels=["bug", "P1"],
            assignees=["octocat"],
        )
        response = auth_client.get(f"/api/repos/github-issues/{issue.id}/")
        assert response.status_code == 200
        assert response.data["title"] == "Fix bug"
        assert response.data["body"] == "Detailed description here"
        assert response.data["state"] == "open"
        assert response.data["labels"] == ["bug", "P1"]
        assert response.data["assignees"] == ["octocat"]
        assert "github_closed_at" in response.data
        assert "repo_full_name" in response.data

    def test_get_github_issue_detail_unauthenticated(self, api_client):
        from tests.factories import GitHubIssueFactory
        issue = GitHubIssueFactory()
        response = api_client.get(f"/api/repos/github-issues/{issue.id}/")
        assert response.status_code == 401
