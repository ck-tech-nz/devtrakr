"""Idempotent re-activation of wizard v1 prompts.

The original 0007 migration set v1 prompts (wizard_classify/extract/generate)
to is_active=False, which silently broke the AI_WIZARD_LEGACY=True rollback
flag (the legacy code path queries Prompt by slug + is_active=True).

0007 has since been corrected to leave v1 active, but Django tracks migrations
by name — already-migrated environments will not re-run the corrected 0007.
This migration runs on every environment regardless of 0007 history and
brings v1 prompts back to is_active=True.

Safe to run on fresh DBs (no-op when prompts are already active).
"""

from django.db import migrations


V1_SLUGS = ("wizard_classify", "wizard_extract", "wizard_generate")


def reactivate_v1(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug__in=V1_SLUGS).update(is_active=True)


def noop_reverse(apps, schema_editor):
    # Reverse is a no-op: we never want to re-break the rollback flag.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0007_add_wizard_oneshot_prompt"),
    ]

    operations = [
        migrations.RunPython(reactivate_v1, reverse_code=noop_reverse),
    ]
