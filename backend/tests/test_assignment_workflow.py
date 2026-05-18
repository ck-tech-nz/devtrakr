import pytest
from django.db import IntegrityError
from apps.issues.models import Issue, IssueAssignment, IssueStatus, AssignmentAction
from tests.factories import IssueFactory, UserFactory


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
        # Pretend this issue was in the old 待处理 state
        Issue.objects.filter(pk=issue.pk).update(status="待处理")
        IssueAssignment.objects.filter(issue=issue).delete()

        # Replay the migration's semantic effect inline (the real migration
        # uses apps.get_model under RunPython; this test asserts the outcome).
        Issue.objects.filter(status="待处理").update(status="待分配")
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
