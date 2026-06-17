# 为 Issue 状态对象补充 disabled 字段(默认 False),支持「禁用某状态」功能。
# 读取侧均把缺失视为 False,本迁移只是把存量数据补全,使其显式可见。
from django.db import migrations


def forwards(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    for obj in SiteSettings.objects.all():
        if not isinstance(obj.issue_statuses, list):
            continue
        changed = False
        for s in obj.issue_statuses:
            if isinstance(s, dict) and "disabled" not in s:
                s["disabled"] = False
                changed = True
        if changed:
            obj.save(update_fields=["issue_statuses"])


def backwards(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    for obj in SiteSettings.objects.all():
        if not isinstance(obj.issue_statuses, list):
            continue
        changed = False
        for s in obj.issue_statuses:
            if isinstance(s, dict) and "disabled" in s:
                del s["disabled"]
                changed = True
        if changed:
            obj.save(update_fields=["issue_statuses"])


class Migration(migrations.Migration):
    dependencies = [
        ("settings", "0011_issue_statuses_to_objects"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
