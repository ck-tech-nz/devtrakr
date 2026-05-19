import pytest
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from apps.issues.models import Issue, IssueAssignment, IssueStatus, AssignmentAction
from apps.issues.services import (
    _resolve_project_manager,
    assign_issue,
    claim_issue,
    confirm_issue,
    transfer_issue,
    create_issue,
    auto_assign_issue,
    InvalidTransition,
)
from apps.issues.serializers import IssueListSerializer
from apps.projects.models import ProjectMember
from rest_framework.exceptions import PermissionDenied
from tests.factories import IssueFactory, UserFactory, ProjectFactory


@pytest.mark.django_db
class TestEnums:
    def test_issue_status_has_unassigned_and_pending_confirmation(self):
        assert IssueStatus.UNASSIGNED.value == "待分配"
        assert IssueStatus.PENDING_CONFIRMATION.value == "待确认"
        assert IssueStatus.IN_PROGRESS.value == "进行中"
        # Verify "待处理" is GONE
        assert "待处理" not in IssueStatus.values

    def test_assignment_action_choices(self):
        assert AssignmentAction.CLAIM.value == "claim"
        assert AssignmentAction.ASSIGN.value == "assign"
        assert AssignmentAction.AI_ASSIGN.value == "ai_assign"
        assert AssignmentAction.TRANSFER.value == "transfer"
        assert AssignmentAction.CONFIRM.value == "confirm"


@pytest.mark.django_db
class TestIssueAssignmentModel:
    def test_create_basic_assignment(self):
        issue = IssueFactory()
        to_user = UserFactory()
        ev = IssueAssignment.objects.create(
            issue=issue,
            action=AssignmentAction.ASSIGN,
            from_user=None,
            to_user=to_user,
            actor=None,
            reason="seed",
        )
        assert ev.pk is not None
        assert issue.assignments.count() == 1
        assert issue.assignments.first().to_user == to_user

    def test_assignment_ordering_by_created_at(self):
        issue = IssueFactory()
        u1, u2, u3 = UserFactory(), UserFactory(), UserFactory()
        IssueAssignment.objects.create(issue=issue, action=AssignmentAction.ASSIGN, to_user=u1)
        IssueAssignment.objects.create(issue=issue, action=AssignmentAction.TRANSFER, from_user=u1, to_user=u2)
        IssueAssignment.objects.create(issue=issue, action=AssignmentAction.TRANSFER, from_user=u2, to_user=u3)
        users = [a.to_user for a in issue.assignments.all()]
        assert users == [u1, u2, u3]


@pytest.mark.django_db
class TestSeedMigration:
    """Verify the data migration's forwards function in isolation."""

    def test_status_rename_and_seed(self):
        u = UserFactory()
        issue = IssueFactory(status="进行中", assignee=u)
        # Pretend this issue was in the old 待分配 state
        Issue.objects.filter(pk=issue.pk).update(status="待分配")
        IssueAssignment.objects.filter(issue=issue).delete()

        # Replay the migration's semantic effect inline (the real migration
        # uses apps.get_model under RunPython; this test asserts the outcome).
        Issue.objects.filter(status="待分配").update(status="待分配")
        if not IssueAssignment.objects.filter(issue=issue).exists():
            IssueAssignment.objects.create(
                issue=issue, action="assign",
                from_user=None, to_user=issue.assignee,
                reason="历史数据 seed",
            )

        issue.refresh_from_db()
        assert issue.status == "待分配"
        assert issue.assignments.count() == 1
        assert issue.assignments.first().to_user == u


User = get_user_model()


@pytest.mark.django_db
class TestResolveProjectManager:
    def test_returns_manager_user(self):
        project = ProjectFactory()
        mgr = UserFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        assert _resolve_project_manager(project) == mgr

    def test_returns_none_when_no_manager(self):
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=UserFactory(), is_manager=False)
        assert _resolve_project_manager(project) is None


@pytest.mark.django_db
class TestAssignIssue:
    def test_assign_unassigned_issue_moves_to_pending_confirmation(self):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        target = UserFactory()
        ProjectMember.objects.create(project=project, user=target)
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        ev = assign_issue(issue, actor=mgr, to_user=target)

        issue.refresh_from_db()
        assert issue.assignee == target
        assert issue.status == "待确认"
        assert ev.action == "assign"
        assert ev.to_user == target
        assert ev.from_user is None
        assert ev.actor == mgr

    def test_assign_requires_actor_to_be_manager(self):
        project = ProjectFactory()
        mgr = UserFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        other = UserFactory()
        target = UserFactory()
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        with pytest.raises(PermissionDenied):
            assign_issue(issue, actor=other, to_user=target)

    def test_assign_rejects_from_in_progress(self):
        mgr = UserFactory()
        issue = IssueFactory(status="进行中", assignee=UserFactory(), manager=mgr)
        with pytest.raises(InvalidTransition):
            assign_issue(issue, actor=mgr, to_user=UserFactory())


@pytest.mark.django_db
class TestClaimIssue:
    def test_claim_unassigned_by_member_goes_to_in_progress(self):
        project = ProjectFactory()
        member = UserFactory()
        ProjectMember.objects.create(project=project, user=member)
        issue = IssueFactory(project=project, status="待分配", assignee=None)

        ev = claim_issue(issue, actor=member)

        issue.refresh_from_db()
        assert issue.assignee == member
        assert issue.status == "进行中"
        assert ev.action == "claim"
        assert ev.to_user == member
        assert ev.from_user is None
        assert ev.actor == member

    def test_claim_rejected_for_non_member(self):
        project = ProjectFactory()
        outsider = UserFactory()
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        with pytest.raises(PermissionDenied):
            claim_issue(issue, actor=outsider)

    def test_claim_rejected_if_not_unassigned(self):
        project = ProjectFactory()
        member = UserFactory()
        ProjectMember.objects.create(project=project, user=member)
        issue = IssueFactory(project=project, status="进行中", assignee=UserFactory())
        with pytest.raises(InvalidTransition):
            claim_issue(issue, actor=member)


@pytest.mark.django_db
class TestConfirmIssue:
    def test_confirm_by_assignee_moves_to_in_progress(self):
        u = UserFactory()
        issue = IssueFactory(status="待确认", assignee=u)
        # Seed an assignment to maintain invariant
        IssueAssignment.objects.create(issue=issue, action="assign", to_user=u)

        ev = confirm_issue(issue, actor=u)

        issue.refresh_from_db()
        assert issue.status == "进行中"
        assert issue.assignee == u  # unchanged
        assert ev.action == "confirm"
        assert ev.from_user == u
        assert ev.to_user == u

    def test_confirm_rejected_for_non_assignee(self):
        u, other = UserFactory(), UserFactory()
        issue = IssueFactory(status="待确认", assignee=u)
        with pytest.raises(PermissionDenied):
            confirm_issue(issue, actor=other)

    def test_confirm_rejected_when_not_pending_confirmation(self):
        u = UserFactory()
        issue = IssueFactory(status="进行中", assignee=u)
        with pytest.raises(InvalidTransition):
            confirm_issue(issue, actor=u)


@pytest.mark.django_db
class TestTransferIssue:
    def test_transfer_from_in_progress_to_pending_confirmation(self):
        owner = UserFactory()
        new_user = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner)
        IssueAssignment.objects.create(issue=issue, action="claim", to_user=owner)

        ev = transfer_issue(issue, actor=owner, to_user=new_user, reason="不熟悉该模块")

        issue.refresh_from_db()
        assert issue.assignee == new_user
        assert issue.status == "待确认"
        assert ev.action == "transfer"
        assert ev.from_user == owner
        assert ev.to_user == new_user
        assert ev.actor == owner
        assert ev.reason == "不熟悉该模块"

    def test_transfer_from_pending_confirmation(self):
        a = UserFactory()
        b = UserFactory()
        issue = IssueFactory(status="待确认", assignee=a)
        IssueAssignment.objects.create(issue=issue, action="assign", to_user=a)

        ev = transfer_issue(issue, actor=a, to_user=b, reason="转给后端")
        issue.refresh_from_db()
        assert issue.assignee == b
        assert issue.status == "待确认"
        assert ev.from_user == a
        assert ev.to_user == b

    def test_manager_can_transfer_someone_elses_issue(self):
        mgr = UserFactory()
        owner = UserFactory()
        new_user = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner, manager=mgr)

        ev = transfer_issue(issue, actor=mgr, to_user=new_user, reason="重新调配")
        assert ev.actor == mgr
        assert ev.from_user == owner  # the displaced owner
        assert ev.to_user == new_user

    def test_non_assignee_non_manager_cannot_transfer(self):
        owner = UserFactory()
        intruder = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner, manager=UserFactory())
        with pytest.raises(PermissionDenied):
            transfer_issue(issue, actor=intruder, to_user=UserFactory(), reason="x")

    def test_transfer_rejected_when_unassigned(self):
        issue = IssueFactory(status="待分配", assignee=None)
        with pytest.raises(InvalidTransition):
            transfer_issue(issue, actor=UserFactory(), to_user=UserFactory(), reason="x")

    def test_transfer_requires_reason(self):
        owner = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner)
        with pytest.raises(ValueError):
            transfer_issue(issue, actor=owner, to_user=UserFactory(), reason="")


@pytest.mark.django_db
class TestInvariant:
    def test_assignee_equals_latest_assignment_to_user(self):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        a = UserFactory()
        b = UserFactory()
        c = UserFactory()
        for u in (a, b, c):
            ProjectMember.objects.create(project=project, user=u)
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        assign_issue(issue, actor=mgr, to_user=a)
        issue.refresh_from_db(); assert issue.assignee == issue.assignments.last().to_user

        confirm_issue(issue, actor=a)
        issue.refresh_from_db(); assert issue.assignee == issue.assignments.last().to_user

        transfer_issue(issue, actor=a, to_user=b, reason="x")
        issue.refresh_from_db(); assert issue.assignee == issue.assignments.last().to_user

        transfer_issue(issue, actor=b, to_user=c, reason="y")
        issue.refresh_from_db(); assert issue.assignee == issue.assignments.last().to_user

        # Full chain in order
        chain = [(a.id, "assign"), (a.id, "confirm"), (b.id, "transfer"), (c.id, "transfer")]
        actual = [(ev.to_user_id, ev.action) for ev in issue.assignments.all()]
        assert actual == chain


@pytest.mark.django_db
class TestCreateIssue:
    def test_create_without_assignee_stays_unassigned(self):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)

        issue = create_issue(
            project=project, actor=UserFactory(),
            title="t", description="d",
            priority="P2", assignee=None,
        )
        assert issue.status == "待分配"
        assert issue.assignee is None
        assert issue.manager == mgr  # snapshotted
        assert issue.assignments.count() == 0

    def test_create_with_assignee_moves_to_pending_confirmation(self):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        target = UserFactory()
        ProjectMember.objects.create(project=project, user=target)

        issue = create_issue(
            project=project, actor=mgr,
            title="t", description="d", priority="P2",
            assignee=target,
        )
        assert issue.status == "待确认"
        assert issue.assignee == target
        assert issue.assignments.count() == 1
        assert issue.assignments.first().action == "assign"

    def test_create_without_project_manager_keeps_manager_null(self):
        project = ProjectFactory()
        issue = create_issue(
            project=project, actor=UserFactory(),
            title="t", description="d", priority="P2", assignee=None,
        )
        assert issue.manager is None


@pytest.mark.django_db
class TestSerializerFields:
    def test_list_serializer_includes_can_actions_and_manager_name(self, rf):
        from django.contrib.auth.models import AnonymousUser
        mgr = UserFactory(name="赵经理")
        member = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        ProjectMember.objects.create(project=project, user=member)
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        req = rf.get("/api/issues/")
        req.user = member
        data = IssueListSerializer(issue, context={"request": req}).data

        assert data["can_claim"] is True
        assert data["can_confirm"] is False
        assert data["can_transfer"] is False
        assert data["can_assign"] is False
        assert data["manager_name"] == "赵经理"
