import json
from pathlib import Path

from django.db import migrations


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
SLUG = "wizard_revise"


def update_revise_prompt(apps, schema_editor):
    """更新 wizard_revise prompt - 让 LLM 同时做 action 分类 (submit | update),
    避免前端用硬编码词表识别"OK了"等肯定意图导致的误判。
    """
    Prompt = apps.get_model("ai", "Prompt")
    data = json.loads((SEED_DIR / f"{SLUG}.json").read_text(encoding="utf-8"))
    Prompt.objects.filter(slug=SLUG).update(
        name=data["name"],
        system_prompt=data["system_prompt"],
        user_prompt_template=data["user_prompt_template"],
        llm_model=data["llm_model"],
        temperature=data["temperature"],
    )


def noop(apps, schema_editor):
    # 不做精确回滚 - 旧 prompt 只是缺少 action 字段, 后端仍能处理 (缺失视为 update)
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0013_seed_wizard_revise_prompt"),
    ]

    operations = [
        migrations.RunPython(update_revise_prompt, reverse_code=noop),
    ]
