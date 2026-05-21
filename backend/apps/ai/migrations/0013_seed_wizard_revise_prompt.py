import json
from pathlib import Path

from django.db import migrations


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
SLUG = "wizard_revise"
ONESHOT_SLUG = "wizard_oneshot"


def seed_revise(apps, schema_editor):
    """Seed wizard_revise (用于多轮草稿修订) 并绑到与 wizard_oneshot 相同的
    LLMConfig (通常是 DashScope qwen-vl-max-latest)。

    Prompt.llm_config 自 0012 起强制 NOT NULL, 所以 create 时必须带上;
    若 oneshot 不存在或没绑 llm_config, 退回到默认 LLMConfig。
    """
    Prompt = apps.get_model("ai", "Prompt")
    LLMConfig = apps.get_model("ai", "LLMConfig")
    data = json.loads((SEED_DIR / f"{SLUG}.json").read_text(encoding="utf-8"))

    oneshot = Prompt.objects.filter(slug=ONESHOT_SLUG).first()
    cfg_id = oneshot.llm_config_id if (oneshot and oneshot.llm_config_id) else None
    if cfg_id is None:
        fallback = (
            LLMConfig.objects.filter(is_active=True)
            .order_by("-is_default", "id")
            .first()
        )
        cfg_id = fallback.id if fallback else None
    if cfg_id is None:
        # 数据库里完全没有 LLMConfig - 跳过 seed; 管理员日后手工补
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


def unseed_revise(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0012_require_prompt_llm_config"),
    ]

    operations = [
        migrations.RunPython(seed_revise, reverse_code=unseed_revise),
    ]
