from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.backups.models import BackupTarget, DatabaseBackup


@admin.register(BackupTarget)
class BackupTargetAdmin(ModelAdmin):
    list_display = ("name", "project", "db_name", "ssh_host", "schedule_cron", "schedule_enabled", "is_active")
    list_editable = ("schedule_enabled", "is_active")
    list_filter = ("is_active", "schedule_enabled", "engine", "project")
    search_fields = ("name", "db_name", "ssh_host")


@admin.register(DatabaseBackup)
class DatabaseBackupAdmin(ModelAdmin):
    list_display = ("filename", "target", "status", "file_size", "trigger", "created_by", "created_at")
    list_filter = ("status", "trigger")
    readonly_fields = (
        "target", "filename", "file_size", "status",
        "error_message", "trigger", "created_by", "created_at",
    )
