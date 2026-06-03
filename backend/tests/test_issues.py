import pytest
from tests.factories import UserFactory, IssueFactory, SiteSettingsFactory

pytestmark = pytest.mark.django_db


class TestIssueList:
    def test_list_issues(self, auth_client, site_settings):
        IssueFactory.create_batch(3)
        response = auth_client.get("/api/issues/")
        assert response.status_code == 200
        assert response.data["count"] == 3

    def test_filter_by_priority(self, auth_client, site_settings):
        IssueFactory(priority="P0")
        IssueFactory(priority="P1")
        response = auth_client.get("/api/issues/?priority=P0")
        assert response.data["count"] == 1

    def test_filter_by_status(self, auth_client, site_settings):
        IssueFactory(status="待分配")
        IssueFactory(status="进行中")
        response = auth_client.get("/api/issues/?status=待分配")
        assert response.data["count"] == 1

    def test_filter_by_assignee(self, auth_client, site_settings):
        user = UserFactory()
        IssueFactory(assignee=user)
        IssueFactory()
        response = auth_client.get(f"/api/issues/?assignee={user.id}")
        assert response.data["count"] == 1

    def test_search_by_title(self, auth_client, site_settings):
        IssueFactory(title="登录页面崩溃")
        IssueFactory(title="支付功能异常")
        response = auth_client.get("/api/issues/?search=登录")
        assert response.data["count"] == 1

    def test_ordering(self, auth_client, site_settings):
        IssueFactory(priority="P3")
        IssueFactory(priority="P0")
        response = auth_client.get("/api/issues/?ordering=priority")
        results = response.data["results"]
        assert results[0]["priority"] == "P0"

    def test_search_by_number(self, auth_client, site_settings):
        issue = IssueFactory(title="某个问题")
        response = auth_client.get(f"/api/issues/?search={issue.pk}")
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == issue.pk

    def test_unauthenticated(self, api_client):
        response = api_client.get("/api/issues/")
        assert response.status_code == 401


class TestIssueDetail:
    def test_get_issue_detail(self, auth_client, site_settings):
        issue = IssueFactory(title="Bug修复")
        response = auth_client.get(f"/api/issues/{issue.id}/")
        assert response.status_code == 200
        assert response.data["title"] == "Bug修复"
        assert isinstance(response.data["id"], int)

    def test_resolution_hours_computed(self, auth_client, site_settings):
        from django.utils import timezone
        from datetime import timedelta
        issue = IssueFactory()
        issue.resolved_at = issue.created_at + timedelta(hours=5)
        issue.save()
        response = auth_client.get(f"/api/issues/{issue.id}/")
        assert response.data["resolution_hours"] == pytest.approx(5.0, abs=0.1)

    def test_resolution_hours_null_when_unresolved(self, auth_client, site_settings):
        issue = IssueFactory()
        response = auth_client.get(f"/api/issues/{issue.id}/")
        assert response.data["resolution_hours"] is None


class TestIssueCreate:
    def test_create_issue(self, auth_client, site_settings):
        from tests.factories import ProjectFactory
        project = ProjectFactory()
        response = auth_client.post("/api/issues/", {
            "project": str(project.id),
            "title": "新Issue",
            "priority": "P1",
            "status": "待分配",
            "labels": ["前端", "Bug"],
        }, format="json")
        assert response.status_code == 201
        assert response.data["title"] == "新Issue"

    def test_create_issue_invalid_label(self, auth_client, site_settings):
        from tests.factories import ProjectFactory
        project = ProjectFactory()
        response = auth_client.post("/api/issues/", {
            "project": str(project.id),
            "title": "新Issue",
            "priority": "P1",
            "status": "待分配",
            "labels": ["不存在的标签"],
        }, format="json")
        assert response.status_code == 400

    def test_create_issue_creates_activity(self, auth_client, site_settings):
        from tests.factories import ProjectFactory
        from apps.issues.models import Activity
        project = ProjectFactory()
        auth_client.post("/api/issues/", {
            "project": str(project.id),
            "title": "新Issue",
            "priority": "P1",
            "status": "待分配",
            "labels": [],
        }, format="json")
        assert Activity.objects.filter(action="created").count() == 1


class TestIssueUpdate:
    def test_update_issue(self, auth_client, site_settings):
        issue = IssueFactory()
        response = auth_client.patch(f"/api/issues/{issue.id}/", {
            "title": "更新后的标题",
        })
        assert response.status_code == 200
        assert response.data["title"] == "更新后的标题"

    def test_update_status_creates_activity(self, auth_client, site_settings):
        from apps.issues.models import Activity
        issue = IssueFactory(status="待分配")
        auth_client.patch(f"/api/issues/{issue.id}/", {"status": "已解决"})
        assert Activity.objects.filter(action="resolved").exists()

    def test_update_assignee_creates_activity(self, auth_client, site_settings):
        from apps.issues.models import Activity
        user = UserFactory()
        issue = IssueFactory()
        auth_client.patch(f"/api/issues/{issue.id}/", {"assignee": str(user.id)})
        assert Activity.objects.filter(action="assigned").exists()

    def test_patch_assignee_advances_unassigned_status(self, auth_client, site_settings):
        # 有负责人后不应停留在「待分配」
        user = UserFactory()
        issue = IssueFactory(status="待分配", assignee=None)
        auth_client.patch(f"/api/issues/{issue.id}/", {"assignee": str(user.id)})
        issue.refresh_from_db()
        assert issue.assignee_id == user.id
        assert issue.status == "待确认"

    def test_admin_can_update_estimated_hours(self, auth_client, site_settings):
        issue = IssueFactory(estimated_hours=4.0)
        response = auth_client.patch(
            f"/api/issues/{issue.id}/", {"estimated_hours": 12.5}
        )
        assert response.status_code == 200
        issue.refresh_from_db()
        assert float(issue.estimated_hours) == 12.5

    def test_patch_repo_must_belong_to_project(self, auth_client, site_settings):
        # PATCH 仓库时, 必须是 issue 所在项目关联的仓库
        from tests.factories import RepoFactory, ProjectFactory
        project = ProjectFactory()
        in_project = RepoFactory()
        outside_repo = RepoFactory()
        project.repos.add(in_project)
        issue = IssueFactory(project=project, repo=None)

        # 不在项目里的仓库 → 400
        bad = auth_client.patch(f"/api/issues/{issue.id}/", {"repo": outside_repo.id})
        assert bad.status_code == 400

        # 项目里的仓库 → 200
        ok = auth_client.patch(f"/api/issues/{issue.id}/", {"repo": in_project.id})
        assert ok.status_code == 200
        issue.refresh_from_db()
        assert issue.repo_id == in_project.id

    def test_non_admin_estimated_hours_change_ignored(self, api_client, site_settings):
        """非管理员 PATCH estimated_hours 应被静默忽略,其他字段正常更新。"""
        from django.contrib.auth.models import Group, Permission
        dev = UserFactory()
        dev_group, _ = Group.objects.get_or_create(name="开发者")
        dev_group.permissions.add(
            Permission.objects.get(content_type__app_label="issues", codename="change_issue")
        )
        dev.groups.add(dev_group)
        api_client.force_authenticate(user=dev)

        issue = IssueFactory(estimated_hours=4.0)
        response = api_client.patch(
            f"/api/issues/{issue.id}/",
            {"estimated_hours": 99.0, "remark": "fyi"},
        )
        assert response.status_code == 200
        issue.refresh_from_db()
        assert float(issue.estimated_hours) == 4.0  # unchanged
        assert issue.remark == "fyi"  # 其他字段正常更新


class TestIssueDelete:
    def test_soft_delete_issue(self, auth_client, site_settings):
        issue = IssueFactory()
        response = auth_client.delete(f"/api/issues/{issue.id}/")
        assert response.status_code == 204
        # Issue still exists in DB but is_deleted=True
        from apps.issues.models import Issue
        assert Issue.all_objects.filter(id=issue.id, is_deleted=True).exists()
        # Not visible via normal queryset
        assert not Issue.objects.filter(id=issue.id).exists()

    def test_soft_deleted_issue_not_in_list(self, auth_client, site_settings):
        issue = IssueFactory()
        auth_client.delete(f"/api/issues/{issue.id}/")
        response = auth_client.get("/api/issues/")
        assert response.data["count"] == 0

    def test_soft_deleted_issue_not_accessible(self, auth_client, site_settings):
        issue = IssueFactory()
        auth_client.delete(f"/api/issues/{issue.id}/")
        response = auth_client.get(f"/api/issues/{issue.id}/")
        assert response.status_code == 404


class TestBatchDelete:
    def test_batch_delete(self, auth_client, site_settings):
        issues = IssueFactory.create_batch(3)
        response = auth_client.post("/api/issues/batch-update/", {
            "ids": [i.id for i in issues],
            "action": "delete",
        }, format="json")
        assert response.status_code == 200
        assert response.data["updated"] == 3
        from apps.issues.models import Issue
        assert Issue.objects.count() == 0
        assert Issue.all_objects.filter(is_deleted=True).count() == 3


class TestBatchUpdate:
    def test_batch_assign(self, auth_client, site_settings):
        issues = IssueFactory.create_batch(3)
        user = UserFactory()
        response = auth_client.post("/api/issues/batch-update/", {
            "ids": [str(i.id) for i in issues],
            "action": "assign",
            "value": str(user.id),
        }, format="json")
        assert response.status_code == 200
        assert response.data["updated"] == 3
        # 批量分配后「待分配」应推进到「待确认」(IssueFactory 默认 status=待分配)
        from apps.issues.models import Issue
        assigned = Issue.objects.filter(id__in=[i.id for i in issues])
        assert all(i.assignee_id == user.id for i in assigned)
        assert not assigned.filter(status="待分配").exists()

    def test_batch_assign_keeps_active_status(self, auth_client, site_settings):
        # 已在进行中的 issue 批量改派,不应被强制改回「待确认」
        user = UserFactory()
        issue = IssueFactory(status="进行中")
        auth_client.post("/api/issues/batch-update/", {
            "ids": [str(issue.id)],
            "action": "assign",
            "value": str(user.id),
        }, format="json")
        issue.refresh_from_db()
        assert issue.assignee_id == user.id
        assert issue.status == "进行中"

    def test_batch_set_priority(self, auth_client, site_settings):
        issues = IssueFactory.create_batch(2)
        response = auth_client.post("/api/issues/batch-update/", {
            "ids": [str(i.id) for i in issues],
            "action": "set_priority",
            "value": "P0",
        }, format="json")
        assert response.status_code == 200
        from apps.issues.models import Issue
        for issue in Issue.objects.filter(id__in=[i.id for i in issues]):
            assert issue.priority == "P0"


class TestMentionNotification:
    def test_create_issue_with_mention(self, auth_client, auth_user, site_settings):
        from tests.factories import ProjectFactory, UserFactory
        from apps.notifications.models import NotificationRecipient
        user2 = UserFactory()
        project = ProjectFactory()
        response = auth_client.post("/api/issues/", {
            "project": str(project.id),
            "title": "测试提及",
            "description": f"请 @[{user2.name}](user:{user2.id}) 看看",
            "priority": "P2",
            "status": "待分配",
            "labels": ["前端"],
        }, format="json")
        assert response.status_code == 201
        assert NotificationRecipient.objects.filter(user=user2).count() == 1

    def test_update_issue_with_new_mention(self, auth_client, auth_user, site_settings):
        from tests.factories import UserFactory
        from apps.notifications.models import NotificationRecipient
        user2 = UserFactory()
        issue = IssueFactory(created_by=auth_user, description="原始描述")
        response = auth_client.patch(f"/api/issues/{issue.id}/", {
            "description": f"请 @[{user2.name}](user:{user2.id}) 看看",
        }, format="json")
        assert response.status_code == 200
        assert NotificationRecipient.objects.filter(user=user2).count() == 1


@pytest.mark.django_db
class TestIssueRelated:
    """JSON 字段 + 两类来源 (ai_dup / manual) + 添加/删除/解析端点"""

    def test_create_with_ai_related_persists_kind_ai_dup(self, auth_client, site_settings):
        from tests.factories import IssueFactory, ProjectFactory
        project = ProjectFactory()
        other = IssueFactory(project=project)
        resp = auth_client.post("/api/issues/", {
            "project": project.id,
            "title": "新 issue",
            "description": "x",
            "priority": "P2",
            "status": "待分配",
            "labels": [],
            "ai_related": [{"id": other.id, "reason": "标题相似"}],
        }, format="json")
        assert resp.status_code == 201, resp.data
        from apps.issues.models import Issue
        new_issue = Issue.objects.get(id=resp.data["id"])
        assert len(new_issue.related_issues) == 1
        entry = new_issue.related_issues[0]
        assert entry["id"] == other.id
        assert entry["kind"] == "ai_dup"
        assert entry["reason"] == "标题相似"
        assert entry["added_at"]

    def test_create_with_ai_related_skips_invalid_ids(self, auth_client, site_settings):
        """不存在的 id / 自身 id 被静默过滤; 不会让创建失败"""
        from tests.factories import ProjectFactory
        project = ProjectFactory()
        resp = auth_client.post("/api/issues/", {
            "project": project.id, "title": "x", "description": "y", "priority": "P2",
            "status": "待分配", "labels": [],
            "ai_related": [{"id": 999999, "reason": "ghost"}, {"id": "not-int"}],
        }, format="json")
        assert resp.status_code == 201
        from apps.issues.models import Issue
        new_issue = Issue.objects.get(id=resp.data["id"])
        assert new_issue.related_issues == []

    def test_detail_serializer_resolves_related_issues(self, auth_client, site_settings):
        from tests.factories import IssueFactory
        target = IssueFactory(title="目标 issue", status="进行中")
        issue = IssueFactory(related_issues=[
            {"id": target.id, "kind": "ai_dup", "reason": "r", "added_at": "2026-05-21T00:00:00"},
        ])
        resp = auth_client.get(f"/api/issues/{issue.id}/")
        assert resp.status_code == 200
        resolved = resp.data["related_issues_resolved"]
        assert len(resolved) == 1
        assert resolved[0]["id"] == target.id
        assert resolved[0]["title"] == "目标 issue"
        assert resolved[0]["status"] == "进行中"
        assert resolved[0]["kind"] == "ai_dup"

    def test_detail_skips_orphan_related_ids(self, auth_client, site_settings):
        """被关联的 issue 被删除后, related_issues 里残留的 id 在 resolved 输出里被跳过"""
        from tests.factories import IssueFactory
        issue = IssueFactory(related_issues=[
            {"id": 999999, "kind": "manual", "reason": "", "added_at": ""},
        ])
        resp = auth_client.get(f"/api/issues/{issue.id}/")
        assert resp.status_code == 200
        assert resp.data["related_issues_resolved"] == []

    def test_post_related_adds_manual_entry(self, auth_client, site_settings):
        from tests.factories import IssueFactory
        a, b = IssueFactory(), IssueFactory()
        resp = auth_client.post(f"/api/issues/{a.id}/related/", {"id": b.id, "reason": "看着像"}, format="json")
        assert resp.status_code == 200
        a.refresh_from_db()
        assert len(a.related_issues) == 1
        assert a.related_issues[0]["id"] == b.id
        assert a.related_issues[0]["kind"] == "manual"
        assert a.related_issues[0]["reason"] == "看着像"

    def test_post_related_rejects_self_link(self, auth_client, site_settings):
        from tests.factories import IssueFactory
        a = IssueFactory()
        resp = auth_client.post(f"/api/issues/{a.id}/related/", {"id": a.id}, format="json")
        assert resp.status_code == 400

    def test_post_related_rejects_duplicate(self, auth_client, site_settings):
        from tests.factories import IssueFactory
        a, b = IssueFactory(), IssueFactory()
        auth_client.post(f"/api/issues/{a.id}/related/", {"id": b.id}, format="json")
        resp2 = auth_client.post(f"/api/issues/{a.id}/related/", {"id": b.id}, format="json")
        assert resp2.status_code == 409

    def test_post_related_rejects_missing_target(self, auth_client, site_settings):
        from tests.factories import IssueFactory
        a = IssueFactory()
        resp = auth_client.post(f"/api/issues/{a.id}/related/", {"id": 999999}, format="json")
        assert resp.status_code == 404

    def test_delete_related_removes_any_kind(self, auth_client, site_settings):
        """DELETE 不分 kind, 用户既能解除 AI 标注的也能解除人工标注的"""
        from tests.factories import IssueFactory
        target = IssueFactory()
        issue = IssueFactory(related_issues=[
            {"id": target.id, "kind": "ai_dup", "reason": "r", "added_at": ""},
        ])
        resp = auth_client.delete(f"/api/issues/{issue.id}/related/{target.id}/")
        assert resp.status_code == 200
        issue.refresh_from_db()
        assert issue.related_issues == []
