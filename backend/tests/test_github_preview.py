import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from tests.factories import RepoFactory
from apps.repos.services import parse_github_ref, GitHubPreviewService


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_parse_github_ref_pull():
    assert parse_github_ref("https://github.com/octocat/hello/pull/42") == {
        "owner": "octocat", "repo": "hello", "kind": "pull", "number": 42,
    }


def test_parse_github_ref_issue_with_query():
    assert parse_github_ref("https://github.com/octocat/hello/issues/7?x=1") == {
        "owner": "octocat", "repo": "hello", "kind": "issues", "number": 7,
    }


def test_parse_github_ref_rejects_non_github_and_bare_repo():
    assert parse_github_ref("https://example.com/a/b/pull/1") is None
    assert parse_github_ref("https://github.com/octocat/hello") is None
    assert parse_github_ref("") is None


@pytest.mark.django_db
def test_fetch_preview_pr_merged_uses_repo_token():
    RepoFactory(full_name="octocat/hello", github_token="ghp_x")
    payload = {"number": 42, "title": "Add feature", "state": "closed", "merged": True,
               "html_url": "https://github.com/octocat/hello/pull/42",
               "user": {"login": "alice", "avatar_url": "https://a/x.png"}}
    with patch("apps.repos.services.requests.get") as mg:
        mg.return_value = MagicMock(status_code=200, json=lambda: payload)
        data = GitHubPreviewService().fetch_preview("octocat", "hello", "pull", 42)
    assert data["kind"] == "pr"
    assert data["state"] == "merged"
    assert data["author_login"] == "alice"
    assert data["repo_full_name"] == "octocat/hello"
    assert mg.call_args.kwargs["headers"].get("Authorization") == "Bearer ghp_x"


@pytest.mark.django_db
def test_fetch_preview_issue_open_unauthenticated():
    payload = {"number": 7, "title": "Bug", "state": "open", "html_url": "u",
               "user": {"login": "bob", "avatar_url": "av"}}
    with patch("apps.repos.services.requests.get") as mg:
        mg.return_value = MagicMock(status_code=200, json=lambda: payload)
        data = GitHubPreviewService().fetch_preview("octocat", "hello", "issues", 7)
    assert data["kind"] == "issue"
    assert data["state"] == "open"
    assert "Authorization" not in mg.call_args.kwargs["headers"]


@pytest.mark.django_db
def test_fetch_preview_none_on_404():
    with patch("apps.repos.services.requests.get") as mg:
        mg.return_value = MagicMock(status_code=404, json=lambda: {})
        assert GitHubPreviewService().fetch_preview("o", "r", "pull", 1) is None


@pytest.mark.django_db
def test_endpoint_returns_card(auth_client):
    payload = {"number": 42, "title": "T", "state": "open", "html_url": "u",
               "user": {"login": "a", "avatar_url": "av"}}
    with patch("apps.repos.services.requests.get") as mg:
        mg.return_value = MagicMock(status_code=200, json=lambda: payload)
        resp = auth_client.get("/api/repos/github-preview/",
                               {"url": "https://github.com/octocat/hello/pull/42"})
    assert resp.status_code == 200
    assert resp.data["kind"] == "pr"


@pytest.mark.django_db
def test_endpoint_unsupported_for_non_github(auth_client):
    resp = auth_client.get("/api/repos/github-preview/", {"url": "https://example.com/x"})
    assert resp.status_code == 200
    assert resp.data == {"supported": False}
