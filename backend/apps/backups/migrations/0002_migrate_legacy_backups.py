from django.conf import settings as dj_settings
from django.db import migrations


def forward(apps, schema_editor):
    LegacyBackup = apps.get_model("settings", "DatabaseBackup")
    BackupTarget = apps.get_model("backups", "BackupTarget")
    NewBackup = apps.get_model("backups", "DatabaseBackup")

    if not LegacyBackup.objects.exists() and BackupTarget.objects.filter(
        name="DevTrakr 自身", project__isnull=True
    ).exists():
        return

    self_target, _ = BackupTarget.objects.get_or_create(
        name="DevTrakr 自身",
        project=None,
        defaults={
            "engine": "postgres",
            "db_name": dj_settings.DATABASES["default"].get("NAME", "devtrack"),
        },
    )

    for old in LegacyBackup.objects.all():
        new = NewBackup.objects.create(
            target=self_target,
            filename=old.filename,
            file_size=old.file_size,
            status=old.status,
            error_message=old.error_message,
            trigger="manual",
            created_by_id=old.created_by_id,
        )
        NewBackup.objects.filter(pk=new.pk).update(created_at=old.created_at)


def reverse(apps, schema_editor):
    # 不可逆:只清掉自身目标迁过来的记录,不还原旧表
    BackupTarget = apps.get_model("backups", "BackupTarget")
    BackupTarget.objects.filter(name="DevTrakr 自身", project__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("backups", "0001_initial"),
        ("settings", "0012_issue_statuses_disabled_flag"),
    ]
    operations = [
        migrations.RunPython(forward, reverse),
    ]
