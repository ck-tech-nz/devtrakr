from django.db import migrations


NEW = ["未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"]
OLD = ["未计划", "待处理", "进行中", "已解决", "已发布", "已关闭"]


def update_to_new(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    obj = SiteSettings.objects.first()
    if obj is None:
        return
    obj.issue_statuses = NEW
    obj.save(update_fields=["issue_statuses"])


def revert_to_old(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    obj = SiteSettings.objects.first()
    if obj is None:
        return
    obj.issue_statuses = OLD
    obj.save(update_fields=["issue_statuses"])


class Migration(migrations.Migration):

    dependencies = [
        ("settings", "0007_default_project_and_modules"),
    ]

    operations = [
        migrations.RunPython(update_to_new, revert_to_old),
    ]
