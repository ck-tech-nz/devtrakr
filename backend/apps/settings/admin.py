from django.contrib import admin
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin
from .models import ExternalAPIKey, SiteSettings
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
            from apps.issues.models import SYSTEM_ASSIGNED_STATUSES

            kwargs["widget"] = ColorOptionListWidget(
                hint="主色用于前端状态胶囊与看板列圆点。状态流转逻辑依赖「值」，档位固定，仅可改显示名/颜色/顺序。勾选「禁用」后该状态在前端各选择/展示入口隐藏（已有该状态的工单仍正常显示）；流程关键状态不可禁用。",
                value_placeholder="值 (如 进行中)",
                label_placeholder="显示名",
                allow_disable=True,
                locked_values=SYSTEM_ASSIGNED_STATUSES,
            )
        elif db_field.name == "labels":
            kwargs["widget"] = JsonReadonlyToggleWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)


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
