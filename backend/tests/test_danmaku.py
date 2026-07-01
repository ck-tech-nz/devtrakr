from unittest.mock import patch

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


@pytest.mark.django_db
def test_signal_broadcasts_created(django_capture_on_commit_callbacks):
    with patch("apps.issues.signals.broadcast_issue_event") as mock_bcast:
        with django_capture_on_commit_callbacks(execute=True):
            IssueFactory(status="待分配")
    kinds = [c.args[0]["kind"] for c in mock_bcast.call_args_list]
    assert kinds == ["created"]


@pytest.mark.django_db
def test_signal_broadcasts_completed_once(django_capture_on_commit_callbacks):
    issue = IssueFactory(status="进行中")
    with patch("apps.issues.signals.broadcast_issue_event") as mock_bcast:
        with django_capture_on_commit_callbacks(execute=True):
            issue.status = "已解决"
            issue.save()
    kinds = [c.args[0]["kind"] for c in mock_bcast.call_args_list]
    assert kinds == ["completed"]


@pytest.mark.django_db
def test_signal_no_broadcast_on_reopen(django_capture_on_commit_callbacks):
    issue = IssueFactory(status="已解决")
    with patch("apps.issues.signals.broadcast_issue_event") as mock_bcast:
        with django_capture_on_commit_callbacks(execute=True):
            issue.status = "进行中"
            issue.save()
    assert mock_bcast.call_count == 0


@pytest.mark.django_db
def test_signal_rebroadcasts_on_recomplete(django_capture_on_commit_callbacks):
    issue = IssueFactory(status="已解决")
    issue.status = "进行中"
    issue.save()
    with patch("apps.issues.signals.broadcast_issue_event") as mock_bcast:
        with django_capture_on_commit_callbacks(execute=True):
            issue.status = "已发布"
            issue.save()
    kinds = [c.args[0]["kind"] for c in mock_bcast.call_args_list]
    assert kinds == ["completed"]
