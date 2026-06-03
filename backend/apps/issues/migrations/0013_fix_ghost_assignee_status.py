"""Backfill: any issue that already has an assignee but is still「待分配」
gets moved to「待确认」.

These "ghost assignee" rows were produced by assignment paths that set
`assignee` without advancing status (batch assign / direct PATCH). Now that
both paths flip status, this one-off cleans up existing data so the invariant
"有负责人 ⇒ 状态不是待分配" holds.

Idempotent: only touches rows matching (assignee set, status=待分配).
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    # _default_manager includes soft-deleted rows so legacy data is fully cleaned.
    Issue._default_manager.filter(
        assignee__isnull=False, status="待分配"
    ).update(status="待确认")


def reverse(apps, schema_editor):
    # 不可逆:无法区分哪些「待确认」原本是「待分配」。
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0012_historicalissue_related_issues_issue_related_issues"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
