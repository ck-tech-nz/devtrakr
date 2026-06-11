# 优先级选项从扁平列表 ["P0",...] 升级为对象列表 [{"value","label","background"},...]
from django.db import migrations

DEFAULT_META = {
    "P0": {"label": "紧急", "background": "#ef4444"},
    "P1": {"label": "高", "background": "#f97316"},
    "P2": {"label": "中", "background": "#facc15"},
    "P3": {"label": "低", "background": ""},
}


def forwards(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    for obj in SiteSettings.objects.all():
        if not isinstance(obj.priorities, list):
            continue
        if all(isinstance(p, dict) for p in obj.priorities):
            continue
        converted = []
        for p in obj.priorities:
            if isinstance(p, dict):
                converted.append(p)
            else:
                meta = DEFAULT_META.get(p, {"label": p, "background": ""})
                converted.append({"value": p, **meta})
        obj.priorities = converted
        obj.save(update_fields=["priorities"])


def backwards(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    for obj in SiteSettings.objects.all():
        if isinstance(obj.priorities, list):
            obj.priorities = [
                p["value"] if isinstance(p, dict) else p for p in obj.priorities
            ]
            obj.save(update_fields=["priorities"])


class Migration(migrations.Migration):
    dependencies = [
        ("settings", "0009_alter_externalapikey_default_assignee_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
