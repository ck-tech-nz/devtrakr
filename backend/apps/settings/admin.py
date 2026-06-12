from django.contrib import admin
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin
from .models import DatabaseBackup, ExternalAPIKey, SiteSettings
from .widgets import ApiKeyGeneratorWidget, ColorOptionListWidget, JsonReadonlyToggleWidget


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin, SingletonModelAdmin):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "priorities":
            kwargs["widget"] = ColorOptionListWidget(
                hint="顺序为 高 → 低（第一行为最高优先级）；主色用于前端徽章/卡片/行底色与滑块渐变，「无底色」表示该档不着色。档位固定，仅可改显示名/颜色/顺序。",
                value_placeholder="值 (如 P0)",
                label_placeholder="显示名 (如 紧急)",
            )
        elif db_field.name == "issue_statuses":
            kwargs["widget"] = ColorOptionListWidget(
                hint="主色用于前端状态胶囊与看板列圆点。状态流转逻辑依赖「值」，档位固定，仅可改显示名/颜色/顺序。",
                value_placeholder="值 (如 进行中)",
                label_placeholder="显示名",
            )
        elif db_field.name == "labels":
            kwargs["widget"] = JsonReadonlyToggleWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(DatabaseBackup)
class DatabaseBackupAdmin(ModelAdmin):
    list_display = ("filename", "status", "file_size", "created_by", "created_at")
    list_filter = ("status",)
    readonly_fields = ("filename", "file_size", "status", "error_message", "created_by", "created_at")


@admin.register(ExternalAPIKey)
class ExternalAPIKeyAdmin(ModelAdmin):
    list_display = ("name", "project", "default_assignee", "is_active", "created_at")
    list_filter = ("is_active",)
    readonly_fields = ("created_at",)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("key",)
        return self.readonly_fields

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "key":
            kwargs["widget"] = ApiKeyGeneratorWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)
