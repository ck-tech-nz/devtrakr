"""Rename status 待处理→待分配 on existing issues, and seed IssueAssignment
rows for issues that already have an assignee so the invariant
`Issue.assignee == latest_assignment.to_user` holds for legacy data.

Idempotent: only updates rows matching the old value and only seeds
issues that have no assignments yet.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    IssueAssignment = apps.get_model("issues", "IssueAssignment")

    # 1) Rename status on existing rows (includes soft-deleted)
    Issue._default_manager.filter(status="待处理").update(status="待分配")

    # 2) Seed assignment events for issues with an existing assignee
    for issue in Issue._default_manager.filter(assignee__isnull=False).iterator():
        if IssueAssignment.objects.filter(issue=issue).exists():
            continue
        IssueAssignment.objects.create(
            issue=issue,
            action="assign",
            from_user=None,
            to_user=issue.assignee,
            actor=None,
            reason="历史数据 seed",
            created_at=issue.created_at,
        )


def reverse(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    IssueAssignment = apps.get_model("issues", "IssueAssignment")
    Issue._default_manager.filter(status="待分配").update(status="待处理")
    IssueAssignment.objects.filter(reason="历史数据 seed").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0010_assignment_workflow"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
