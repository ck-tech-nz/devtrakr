import pytest

from apps.issues.services_danmaku import build_payload
from tests.factories import IssueFactory, UserFactory


@pytest.mark.django_db
def test_build_payload_created():
    issue = IssueFactory(status="进行中")
    p = build_payload(issue, "created")
    assert p["kind"] == "created"
    assert p["issue_id"] == issue.id
    assert p["issue_number"] == f"ISS-{issue.id:03d}"
    assert p["status"] == "进行中"
    assert p["actor_name"] == issue.created_by.name
    assert p["occurred_at"] is not None


@pytest.mark.django_db
def test_build_payload_completed_uses_assignee_and_resolved_at():
    user = UserFactory()
    issue = IssueFactory(status="已解决", assignee=user)
    issue.refresh_from_db()
    p = build_payload(issue, "completed")
    assert p["kind"] == "completed"
    assert p["actor_name"] == user.name
    assert p["occurred_at"] == issue.resolved_at.isoformat()
