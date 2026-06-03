from django.contrib import admin
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin
from .models import KPISnapshot, KPIScoringConfig


@admin.register(KPISnapshot)
class KPISnapshotAdmin(ModelAdmin):
    list_display = ("user", "period_start", "period_end", "computed_at")
    list_filter = ("period_start", "period_end")
    search_fields = ("user__username", "user__name")
    readonly_fields = ("id", "computed_at", "created_at")


@admin.register(KPIScoringConfig)
class KPIScoringConfigAdmin(SingletonModelAdmin, ModelAdmin):
    """单例：维度库等评分规则在此以 JSON 表单编辑。"""
