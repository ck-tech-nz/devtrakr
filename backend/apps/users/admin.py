from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from apps.widgets import JsonSchemaWidget
from .models import User

# 与前端 useUserSettings 的字段一一对应。未列出的键不会被保存逻辑丢弃(见 JsonSchemaWidget),
# 但新增设置项时仍应在此登记,管理后台才能看到/编辑。
USER_SETTINGS_SCHEMA = {
    "sidebar_auto_collapse": {"type": "boolean", "label": "侧边栏自动折叠", "default": False},
    "theme": {"type": "select", "label": "主题", "choices": ["light", "dark", "auto"], "default": "light"},
    "issues_view_mode": {"type": "select", "label": "问题视图模式", "choices": ["kanban", "table"], "default": "table"},
    "project_view_mode": {"type": "select", "label": "项目视图模式", "choices": ["kanban", "table"], "default": "kanban"},
    "issues_show_completed": {"type": "boolean", "label": "问题列表-查看全部(含已完成)", "default": False},
    "issues_title_col_width": {"type": "number", "label": "问题列表-标题列宽(px,空=自适应)", "default": None},
    "pending_tasks_collapsed": {"type": "boolean", "label": "我的待办-折叠", "default": False},
    "ai_wizard_send_mode": {"type": "select", "label": "AI 向导发送方式", "choices": ["modifier", "enter"], "default": "modifier"},
    "system_alert_dismissed": {"type": "text", "label": "系统公告-已忽略签名", "default": ""},
    "dashboard_layout": {"type": "json", "label": "工作台布局", "default": []},
    "issues_kanban_hidden": {"type": "json", "label": "问题看板-隐藏列", "default": ["未计划", "已关闭"]},
    "project_kanban_hidden": {"type": "json", "label": "项目看板-隐藏列", "default": []},
    "issues_table_hidden": {"type": "json", "label": "问题列表-隐藏列", "default": ["github_issues"]},
    "issues_filters": {"type": "json", "label": "问题列表-筛选条件", "default": {}},
    "issue_detail_panels": {"type": "json", "label": "问题详情-面板折叠", "default": {}},
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
