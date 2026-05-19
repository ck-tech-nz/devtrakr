"""Tests for claim/confirm/transfer/assign API endpoints."""
import pytest
from tests.factories import UserFactory, IssueFactory, ProjectFactory, ProjectMemberFactory
from apps.issues.models import IssueAssignment


@pytest.mark.django_db
class TestClaimAPI:
    def test_claim_unassigned(self, auth_client, auth_user):
        """项目成员接单「待分配」→ 200，状态变为「进行中」。"""
        project = ProjectFactory()
        # auth_user needs to be a project member to claim
        ProjectMemberFactory(project=project, user=auth_user)
        issue = IssueFactory(project=project, status="待分配", assignee=None)

        resp = auth_client.post(f"/api/issues/{issue.pk}/claim/")
        assert resp.status_code == 200
        assert resp.data["status"] == "进行中"
        assert resp.data["assignee"] == auth_user.pk

    def test_claim_outsider_forbidden(self, api_client):
        """非项目成员接单 → 403。"""
        outsider = UserFactory()
        api_client.force_authenticate(user=outsider)
        issue = IssueFactory(status="待分配", assignee=None)

        resp = api_client.post(f"/api/issues/{issue.pk}/claim/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestConfirmAPI:
    def test_confirm_by_assignee(self, api_client):
        """当前负责人确认「待确认」→ 200，状态变为「进行中」。"""
        assignee = UserFactory()
        issue = IssueFactory(status="待确认", assignee=assignee)
        api_client.force_authenticate(user=assignee)

        resp = api_client.post(f"/api/issues/{issue.pk}/confirm/")
        assert resp.status_code == 200
        assert resp.data["status"] == "进行中"


@pytest.mark.django_db
class TestTransferAPI:
    def test_transfer_with_reason(self, api_client):
        """当前负责人携带原因转单 → 200，新负责人已更新。"""
        assignee = UserFactory()
        new_assignee = UserFactory()
        issue = IssueFactory(status="进行中", assignee=assignee)
        api_client.force_authenticate(user=assignee)

        resp = api_client.post(
            f"/api/issues/{issue.pk}/transfer/",
            {"to_user": new_assignee.pk, "reason": "需要专业支持"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["assignee"] == new_assignee.pk

    def test_transfer_empty_reason_rejected(self, api_client):
        """空原因转单 → 400。"""
        assignee = UserFactory()
        new_assignee = UserFactory()
        issue = IssueFactory(status="进行中", assignee=assignee)
        api_client.force_authenticate(user=assignee)

        resp = api_client.post(
            f"/api/issues/{issue.pk}/transfer/",
            {"to_user": new_assignee.pk, "reason": "   "},
            format="json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAssignAPI:
    def test_assign_by_manager(self, api_client):
        """项目经理指派「待分配」给某人 → 200，状态变为「待确认」。"""
        manager = UserFactory()
        to_user = UserFactory()
        project = ProjectFactory()
        ProjectMemberFactory(project=project, user=manager, is_manager=True)
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=manager)
        api_client.force_authenticate(user=manager)

        resp = api_client.post(
            f"/api/issues/{issue.pk}/assign/",
            {"to_user": to_user.pk},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["assignee"] == to_user.pk
        assert resp.data["status"] == "待确认"

    def test_assign_by_non_manager_forbidden(self, api_client):
        """非项目经理指派 → 403。"""
        non_manager = UserFactory()
        to_user = UserFactory()
        issue = IssueFactory(status="待分配", assignee=None)
        api_client.force_authenticate(user=non_manager)

        resp = api_client.post(
            f"/api/issues/{issue.pk}/assign/",
            {"to_user": to_user.pk},
            format="json",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestIssueDetailAssignments:
    def test_detail_includes_assignments_list(self, auth_client):
        """GET /api/issues/{id}/ 返回按时间升序的 assignments 列表。"""
        to_user1 = UserFactory(name="张三")
        to_user2 = UserFactory(name="李四")
        actor = UserFactory(name="王五")
        issue = IssueFactory(status="进行中")

        assignment1 = IssueAssignment.objects.create(
            issue=issue,
            action="claim",
            to_user=to_user1,
            actor=actor,
            reason="",
        )
        assignment2 = IssueAssignment.objects.create(
            issue=issue,
            action="transfer",
            from_user=to_user1,
            to_user=to_user2,
            actor=actor,
            reason="需要专业支持",
        )

        resp = auth_client.get(f"/api/issues/{issue.pk}/")
        assert resp.status_code == 200

        assignments = resp.data["assignments"]
        assert len(assignments) == 2

        # 按 created_at 升序（模型 Meta.ordering）
        assert assignments[0]["action"] == "claim"
        assert assignments[0]["to_user_name"] == "张三"
        assert assignments[0]["reason"] == ""

        assert assignments[1]["action"] == "transfer"
        assert assignments[1]["to_user_name"] == "李四"
        assert assignments[1]["reason"] == "需要专业支持"
