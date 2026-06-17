from rest_framework import serializers

from apps.backups.models import BackupTarget, DatabaseBackup
from apps.backups.services import parse_cron


class DatabaseBackupSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.name", read_only=True, default=None)

    class Meta:
        model = DatabaseBackup
        fields = [
            "id", "target", "filename", "file_size", "status",
            "error_message", "trigger", "created_by_name", "created_at",
        ]
        read_only_fields = fields


class BackupTargetSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True, default=None)
    latest_backup = serializers.SerializerMethodField()

    class Meta:
        model = BackupTarget
        fields = [
            "id", "project", "project_name", "name", "engine",
            "ssh_host", "ssh_user", "ssh_port", "docker_container",
            "db_name", "db_user", "db_host", "db_port",
            "schedule_cron", "schedule_enabled", "retention_count",
            "is_active", "created_at", "updated_at", "latest_backup",
        ]
        read_only_fields = ["id", "project_name", "created_at", "updated_at", "latest_backup"]

    def get_latest_backup(self, obj):
        b = obj.backups.first()
        if not b:
            return None
        return {"status": b.status, "created_at": b.created_at}

    def validate_schedule_cron(self, value):
        if value:
            try:
                parse_cron(value)
            except ValueError as e:
                raise serializers.ValidationError(str(e))
        return value
