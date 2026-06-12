# Issue 状态选项从扁平列表 ["未计划",...] 升级为对象列表 [{"value","label","background"},...]
from django.db import migrations

DEFAULT_META = {
    "未计划": {"label": "未计划", "background": "#8b5cf6"},
    "待分配": {"label": "待分配", "background": "#f59e0b"},
    "待确认": {"label": "待确认", "background": "#eab308"},
    "进行中": {"label": "进行中", "background": "#3b82f6"},
    "已解决": {"label": "已解决", "background": "#10b981"},
    "已发布": {"label": "已发布", "background": "#14b8a6"},
    "已关闭": {"label": "已关闭", "background": "#6b7280"},
}


def forwards(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    for obj in SiteSettings.objects.all():
        if not isinstance(obj.issue_statuses, list):
            continue
        if all(isinstance(s, dict) for s in obj.issue_statuses):
            continue
        converted = []
        for s in obj.issue_statuses:
            if isinstance(s, dict):
                converted.append(s)
            else:
                meta = DEFAULT_META.get(s, {"label": s, "background": ""})
                converted.append({"value": s, **meta})
        obj.issue_statuses = converted
        obj.save(update_fields=["issue_statuses"])


def backwards(apps, schema_editor):
    # 回滚有损:自定义的 label/background 会被丢弃,只保留 value 列表。
    # .get 兜底防御缺 value 键的脏数据,避免回滚中途 KeyError
    SiteSettings = apps.get_model("settings", "SiteSettings")
    for obj in SiteSettings.objects.all():
        if isinstance(obj.issue_statuses, list):
            obj.issue_statuses = [
                s.get("value", "") if isinstance(s, dict) else s
                for s in obj.issue_statuses
            ]
            obj.save(update_fields=["issue_statuses"])


class Migration(migrations.Migration):
    dependencies = [
        ("settings", "0010_priorities_to_objects"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
