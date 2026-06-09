from django.db import migrations

SEED = [
    {"category": "quote", "content": "Talk is cheap. Show me the code.", "source": "Linus Torvalds", "sort_order": 1},
    {"category": "quote", "content": "过早优化是万恶之源。", "source": "Donald Knuth", "sort_order": 2},
    {"category": "prompt", "content": "给 AI 加一句「请先列出方案与取舍，再逐步实现」，产出质量立升。", "source": "", "sort_order": 3},
    {"category": "pitfall", "content": "改完代码先本地 typecheck + 跑测试再提交，别让 CI 替你发现低级错误。", "source": "", "sort_order": 4},
    {"category": "value", "content": "对用户诚实：测试失败就说失败，别粉饰。", "source": "", "sort_order": 5},
]


def seed(apps, schema_editor):
    Bulletin = apps.get_model("notifications", "Bulletin")
    for row in SEED:
        Bulletin.objects.get_or_create(content=row["content"], defaults=row)


def unseed(apps, schema_editor):
    Bulletin = apps.get_model("notifications", "Bulletin")
    Bulletin.objects.filter(content__in=[r["content"] for r in SEED]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0003_bulletin"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
