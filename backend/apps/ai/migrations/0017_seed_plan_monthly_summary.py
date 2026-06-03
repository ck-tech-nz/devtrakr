import json
from pathlib import Path

from django.db import migrations

SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
SLUG = "plan_monthly_summary"


def forwards(apps, schema_editor):
    """Seed the monthly-plan-summary Prompt.

    llm_config 是必填 FK（0012 起），因此种子行必须挂一个配置：优先默认配置，
    其次任一启用配置，再退而沿用现有 prompt 的配置（fresh install 上 0012 至少
    留了一个占位配置）。模型名同样不在此硬编码——取所选配置的 available_models
    首项，缺失则沿用现有启用 prompt 的模型。两者均可由管理员在 LLM 后台调整。
    """
    Prompt = apps.get_model("ai", "Prompt")
    LLMConfig = apps.get_model("ai", "LLMConfig")

    data = json.loads((SEED_DIR / f"{SLUG}.json").read_text(encoding="utf-8"))

    template = (
        Prompt.objects.filter(is_active=True).exclude(llm_model="").order_by("id").first()
    )
    config = (
        LLMConfig.objects.filter(is_default=True, is_active=True).first()
        or LLMConfig.objects.filter(is_active=True).order_by("id").first()
        or (template.llm_config if template else None)
        or LLMConfig.objects.order_by("id").first()
    )
    if config is None:
        # 没有任何 LLMConfig（理论上不会发生，0012 会留占位）：无法满足必填 FK，跳过。
        return

    llm_model = (config.available_models or [None])[0] or (
        template.llm_model if template else ""
    )

    Prompt.objects.update_or_create(
        slug=SLUG,
        defaults={
            "name": data["name"],
            "system_prompt": data["system_prompt"],
            "user_prompt_template": data["user_prompt_template"],
            "temperature": data.get("temperature", 0.3),
            "is_active": data.get("is_active", True),
            "llm_config": config,
            "llm_model": llm_model,
        },
    )


def reverse(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0016_wizard_chat_description_field"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
