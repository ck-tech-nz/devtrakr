from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from apps.widgets import JsonSchemaWidget
from .models import User

USER_SETTINGS_SCHEMA = {
    "sidebar_auto_collapse": {"type": "boolean", "label": "侧边栏自动折叠", "default": False},
    "issues_view_mode": {"type": "select", "label": "问题视图模式", "choices": ["kanban", "table"], "default": "table"},
    "project_view_mode": {"type": "select", "label": "项目视图模式", "choices": ["kanban", "table"], "default": "kanban"},
    "theme": {"type": "select", "label": "主题", "choices": ["light", "dark", "auto"], "default": "light"},
}


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    # unfold 表单：让修改密码 / 新建用户 / 编辑用户页面在 unfold 下正常渲染与提交
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = ("username", "name", "email", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("扩展信息", {"fields": ("name", "github_id", "avatar", "is_bot", "settings")}),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "settings":
            kwargs["widget"] = JsonSchemaWidget(schema=USER_SETTINGS_SCHEMA)
        return super().formfield_for_dbfield(db_field, request, **kwargs)
