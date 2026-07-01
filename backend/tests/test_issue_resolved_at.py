import pytest

from apps.issues.models import Issue
from tests.factories import IssueFactory


@pytest.mark.django_db
def test_resolved_at_set_on_entering_terminal():
    issue = IssueFactory(status="进行中")
    assert issue.resolved_at is None
    issue.status = "已解决"
    issue.save()
    issue.refresh_from_db()
    assert issue.resolved_at is not None


@pytest.mark.django_db
def test_resolved_at_cleared_on_reopen():
    issue = IssueFactory(status="已解决")
    issue.refresh_from_db()
    assert issue.resolved_at is not None
    issue.status = "进行中"
    issue.save()
    issue.refresh_from_db()
    assert issue.resolved_at is None


@pytest.mark.django_db
def test_resolved_at_restamped_on_recomplete():
    issue = IssueFactory(status="已解决")
    issue.refresh_from_db()
    first = issue.resolved_at
    issue.status = "进行中"
    issue.save()
    issue.status = "已关闭"
    issue.save()
    issue.refresh_from_db()
    assert issue.resolved_at is not None
    assert issue.resolved_at >= first


@pytest.mark.django_db
def test_resolved_at_not_rewritten_terminal_to_terminal():
    issue = IssueFactory(status="已解决")
    issue.refresh_from_db()
    first = issue.resolved_at
    issue.status = "已发布"
    issue.save()
    issue.refresh_from_db()
    assert issue.resolved_at == first


@pytest.mark.django_db
def test_resolved_at_persists_under_partial_update_fields():
    # 关闭端点用 save(update_fields=["status"]);override 必须把 resolved_at 补进去
    issue = IssueFactory(status="进行中")
    issue.status = "已关闭"
    issue.save(update_fields=["status"])
    issue.refresh_from_db()
    assert issue.resolved_at is not None
