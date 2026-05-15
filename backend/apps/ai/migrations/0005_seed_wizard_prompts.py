import json
from pathlib import Path

from django.db import migrations


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
SLUGS = ("wizard_classify", "wizard_extract", "wizard_generate")


def seed_wizard_prompts(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    for slug in SLUGS:
        data = json.loads((SEED_DIR / f"{slug}.json").read_text(encoding="utf-8"))
        Prompt.objects.update_or_create(
            slug=slug,
            defaults={
                "name": data["name"],
                "system_prompt": data["system_prompt"],
                "user_prompt_template": data["user_prompt_template"],
                "llm_model": data["llm_model"],
                "temperature": data["temperature"],
                "is_active": data["is_active"],
            },
        )


def unseed_wizard_prompts(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug__in=SLUGS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0004_fix_duplicate_check_model"),
    ]

    operations = [
        migrations.RunPython(seed_wizard_prompts, reverse_code=unseed_wizard_prompts),
    ]
