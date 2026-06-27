import pytest
from django.contrib.auth.models import Group

from tests.factories import IssueFactory, ProjectFactory, UserFactory


@pytest.mark.django_db
class TestMyTasksEndpoint:
    """GET /api/issues/my-tasks/ — 一次查询返回当前用户的「我的待办」聚合,
    取代前端按状态拆成的 5~6 个 /issues/?assignee/helpers 请求。"""

    def test_requires_auth(self, api_client):
        resp = api_client.get("/api/issues/my-tasks/")
        assert resp.status_code in (401, 403)

    def test_returns_assignee_actionable_issues(self, auth_client, auth_user):
        mine = IssueFactory(assignee=auth_user, status="待分配")
        IssueFactory(assignee=auth_user, status="待确认")
        IssueFactory(assignee=auth_user, status="进行中")
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.data["results"]}
        assert mine.id in ids
        assert resp.data["count"] == 3

    def test_excludes_assignee_completed_statuses(self, auth_client, auth_user):
        IssueFactory(assignee=auth_user, status="已解决")
        IssueFactory(assignee=auth_user, status="已发布")
        IssueFactory(assignee=auth_user, status="已关闭")
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        assert resp.data["count"] == 0
        assert resp.data["results"] == []

    def test_includes_helper_issues_but_not_helper_pending_confirmation(self, auth_client, auth_user):
        helped = IssueFactory(status="进行中")
        helped.helpers.add(auth_user)
        # 协助人不含「待确认」(待确认仅对负责人是待办)
        not_mine = IssueFactory(status="待确认")
        not_mine.helpers.add(auth_user)
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.data["results"]}
        assert helped.id in ids
        assert not_mine.id not in ids
        assert resp.data["count"] == 1

    def test_dedupes_assignee_and_helper_overlap(self, auth_client, auth_user):
        """既是负责人又是协助人的同一工单只计一次。"""
        both = IssueFactory(assignee=auth_user, status="进行中")
        both.helpers.add(auth_user)
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert len(resp.data["results"]) == 1

    def test_non_tester_excludes_published(self, auth_client, auth_user):
        # auth_user 在「管理员」组,不在「测试」组
        IssueFactory(status="已发布")
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        assert resp.data["count"] == 0

    def test_tester_includes_published(self, auth_client, auth_user):
        tester_group, _ = Group.objects.get_or_create(name="测试")
        auth_user.groups.add(tester_group)
        pub = IssueFactory(status="已发布")
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.data["results"]}
        assert pub.id in ids
        assert resp.data["count"] == 1

    def test_results_include_project_name(self, auth_client, auth_user):
        project = ProjectFactory(name="支付网关")
        IssueFactory(assignee=auth_user, status="进行中", project=project)
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        assert resp.data["results"][0]["project_name"] == "支付网关"

    def test_orders_by_priority_urgent_first(self, auth_client, auth_user):
        IssueFactory(assignee=auth_user, status="进行中", priority="P3")
        IssueFactory(assignee=auth_user, status="进行中", priority="P0")
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        priorities = [t["priority"] for t in resp.data["results"]]
        assert priorities == ["P0", "P3"]

    def test_caps_results_at_20_but_count_is_total(self, auth_client, auth_user):
        for _ in range(22):
            IssueFactory(assignee=auth_user, status="进行中")
        resp = auth_client.get("/api/issues/my-tasks/")
        assert resp.status_code == 200
        assert resp.data["count"] == 22
        assert len(resp.data["results"]) == 20
