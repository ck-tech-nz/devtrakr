from django.db import migrations


SYSTEM_PROMPT = """你是项目工单分配助手。请根据问题描述,从候选项目成员中挑选最合适的一位。
只返回 JSON 对象:{"assignee_id": <整数>, "reason": "<不超过200字的推荐理由>"}
不要输出 markdown 代码块,不要输出 JSON 之外的任何内容。"""

USER_PROMPT = """【问题】
标题: {title}
描述: {description}
标签: {labels}
优先级: {priority}

【候选成员】
{members_block}"""


def forwards(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.update_or_create(
        slug="issue_auto_assign",
        defaults={
            "name": "工单自动分配",
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt_template": USER_PROMPT,
            "llm_model": "gpt-4o",
            "temperature": 0.2,
            "is_active": True,
        },
    )


def reverse(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug="issue_auto_assign").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0008_reactivate_wizard_v1_prompts"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
