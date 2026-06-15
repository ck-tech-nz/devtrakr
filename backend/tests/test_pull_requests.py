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
