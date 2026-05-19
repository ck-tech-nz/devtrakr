import re
from rest_framework import serializers
from apps.uptime.models import UptimeMonitor, UptimeCheck
from apps.uptime.url_safety import check_url_safety

EXPECTED_STATUS_RE = re.compile(r"^\d{3}(,\d{3})*$")


class UptimeMonitorSerializer(serializers.ModelSerializer):
    interval_minutes = serializers.IntegerField(min_value=1, max_value=1440)
    timeout_secs = serializers.IntegerField(min_value=1, max_value=60)
    active_incident_issue_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = UptimeMonitor
        fields = [
            "id", "project", "project_name",
            "name", "environment", "url", "method", "expected_status", "expected_body",
            "interval_minutes", "timeout_secs", "is_enabled",
            "last_status", "last_check_at", "last_up_at",
            "outage_started_at", "active_incident_issue_id",
        ]
        read_only_fields = [
            "id", "project", "project_name",
            "last_status", "last_check_at", "last_up_at",
            "outage_started_at", "active_incident_issue_id",
        ]

    project_name = serializers.CharField(source="project.name", read_only=True)

    def validate_method(self, value):
        if value != "GET":
            raise serializers.ValidationError("v1 仅支持 GET")
        return value

    def validate_expected_status(self, value):
        if not EXPECTED_STATUS_RE.match(value):
            raise serializers.ValidationError("格式必须是单个状态码或逗号分隔(例如 '200' 或 '200,204')")
        return value

    def validate_url(self, value):
        if not (value.startswith("http://") or value.startswith("https://")):
            raise serializers.ValidationError("URL 必须以 http:// 或 https:// 开头")
        safe, reason = check_url_safety(value)
        if not safe:
            raise serializers.ValidationError(reason)
        return value


class UptimeCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = UptimeCheck
        fields = ["checked_at", "is_up", "status_code", "response_ms", "error"]
