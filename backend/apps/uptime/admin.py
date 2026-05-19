from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import UptimeMonitor, UptimeCheck


@admin.register(UptimeMonitor)
class UptimeMonitorAdmin(ModelAdmin):
    list_display = ("id", "name", "environment", "project", "url", "last_status", "is_enabled", "last_check_at")
    list_filter = ("environment", "last_status", "is_enabled", "project")
    search_fields = ("name", "url")
    readonly_fields = (
        "next_check_at", "last_check_at", "last_status", "last_up_at",
        "outage_started_at", "consecutive_failures", "active_incident_issue",
        "created_at", "updated_at",
    )


@admin.register(UptimeCheck)
class UptimeCheckAdmin(ModelAdmin):
    list_display = ("monitor", "checked_at", "is_up", "status_code", "response_ms", "error")
    list_filter = ("is_up",)
    search_fields = ("monitor__name", "error")
    date_hierarchy = "checked_at"
