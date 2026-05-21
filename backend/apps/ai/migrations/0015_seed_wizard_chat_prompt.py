import json
from pathlib import Path

from django.db import migrations


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
SLUG = "wizard_chat"
REVISE_SLUG = "wizard_revise"


def seed_chat(apps, schema_editor):
    """Seed wizard_chat - 取代 wizard_oneshot + wizard_revise 的对话式 prompt。
    旧 prompts 暂保留 (api/issues/ai-draft/ 和 ai-draft/revise/ 端点仍可用),
    新流量走 /api/issues/ai-draft/chat/。
    """
    Prompt = apps.get_model("ai", "Prompt")
    LLMConfig = apps.get_model("ai", "LLMConfig")
    data = json.loads((SEED_DIR / f"{SLUG}.json").read_text(encoding="utf-8"))

    # 沿用 wizard_revise 的 llm_config (同样的 vision 模型即可)
    revise = Prompt.objects.filter(slug=REVISE_SLUG).first()
    cfg_id = revise.llm_config_id if (revise and revise.llm_config_id) else None
    if cfg_id is None:
        fallback = (
            LLMConfig.objects.filter(is_active=True)
            .order_by("-is_default", "id")
            .first()
        )
        cfg_id = fallback.id if fallback else None
    if cfg_id is None:
        return

    Prompt.objects.update_or_create(
        slug=SLUG,
        defaults={
            "name": data["name"],
            "system_prompt": data["system_prompt"],
            "user_prompt_template": data["user_prompt_template"],
            "llm_model": data["llm_model"],
            "temperature": data["temperature"],
            "is_active": data["is_active"],
            "llm_config_id": cfg_id,
        },
    )


def unseed_chat(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0014_revise_prompt_action_classifier"),
    ]

    operations = [
        migrations.RunPython(seed_chat, reverse_code=unseed_chat),
    ]
