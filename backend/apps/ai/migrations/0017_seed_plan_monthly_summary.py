import json
from pathlib import Path

from django.db import migrations

SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
SLUG = "plan_monthly_summary"


def forwards(apps, schema_editor):
    """Seed the monthly-plan-summary Prompt.

    llm_config 是必填 FK（0012 起），因此种子行必须挂一个配置：优先默认配置，
    其次任一启用配置，再退而沿用现有 prompt 的配置；若库里一个配置都没有，则
    自建一个停用占位配置（见下），确保 prompt 始终落库、不会被静默跳过。模型名
    同样不在此硬编码——取所选配置的 available_models 首项，缺失则沿用现有启用
    prompt 的模型。两者均可由管理员在 LLM 后台调整。
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
        # 全新库且无任何 LLMConfig（0012 仅在存在 orphan prompt 时才留占位，
        # 故不能依赖它）：照 0012 的先例建一个停用占位配置，保证必填 FK 可满足、
        # prompt 始终落库；管理员在 LLM 后台配置真实 config 前它不会被运行时选中。
        config = LLMConfig.objects.create(
            name="[未配置 - 请在管理后台设置]",
            api_key="", base_url="", available_models=[],
            supports_json_mode=True, is_default=False, is_active=False,
        )

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
