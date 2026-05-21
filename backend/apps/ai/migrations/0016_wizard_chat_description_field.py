import json
from pathlib import Path

from django.db import migrations


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
SLUG = "wizard_chat"


def update_chat_prompt(apps, schema_editor):
    """Re-seed wizard_chat system_prompt with the new `description` field rule.

    Without this, LLM has no way to emit a revised description text - the backend
    used to hardcode description from the first user message, so "改一下描述" was
    silently ignored.
    """
    Prompt = apps.get_model("ai", "Prompt")
    data = json.loads((SEED_DIR / f"{SLUG}.json").read_text(encoding="utf-8"))
    Prompt.objects.filter(slug=SLUG).update(
        system_prompt=data["system_prompt"],
        user_prompt_template=data["user_prompt_template"],
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0015_seed_wizard_chat_prompt"),
    ]

    operations = [
        migrations.RunPython(update_chat_prompt, reverse_code=noop),
    ]
