import json
from pathlib import Path

from django.db import migrations


SEED_FILE = Path(__file__).resolve().parent.parent / "seed_prompts" / "wizard_generate.json"


def update_prompt(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    Prompt.objects.filter(slug="wizard_generate").update(
        name=data["name"],
        system_prompt=data["system_prompt"],
        user_prompt_template=data["user_prompt_template"],
        llm_model=data["llm_model"],
        temperature=data["temperature"],
    )


def noop(apps, schema_editor):
    # Reverting would restore the old prompt; intentionally not implemented
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0005_seed_wizard_prompts"),
    ]

    operations = [
        migrations.RunPython(update_prompt, reverse_code=noop),
    ]
