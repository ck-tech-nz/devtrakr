import json
from pathlib import Path

from django.db import migrations


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
V1_SLUGS = ("wizard_classify", "wizard_extract", "wizard_generate")
V2_SLUG = "wizard_oneshot"


def seed_oneshot(apps, schema_editor):
    """Seed the v2 multimodal prompt. v1 rows are left ACTIVE so that the
    AI_WIZARD_LEGACY rollback flag actually works — the legacy code path
    queries Prompt by slug + is_active=True. The dispatcher in
    AiWizardService.stream_draft selects v2 by default.
    """
    Prompt = apps.get_model("ai", "Prompt")
    data = json.loads((SEED_DIR / f"{V2_SLUG}.json").read_text(encoding="utf-8"))
    Prompt.objects.update_or_create(
        slug=V2_SLUG,
        defaults={
            "name": data["name"],
            "system_prompt": data["system_prompt"],
            "user_prompt_template": data["user_prompt_template"],
            "llm_model": data["llm_model"],
            "temperature": data["temperature"],
            "is_active": data["is_active"],
        },
    )
    # If a previous run of this migration already deactivated v1 prompts (the
    # state this PR shipped originally), re-activate them now so the rollback
    # flag works on already-migrated databases.
    Prompt.objects.filter(slug__in=V1_SLUGS).update(is_active=True)


def reverse_seed_oneshot(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug=V2_SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0006_update_wizard_generate_prompt"),
    ]

    operations = [
        migrations.RunPython(
            seed_oneshot,
            reverse_code=reverse_seed_oneshot,
        ),
    ]
