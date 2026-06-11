import secrets
import string

from django.conf import settings as django_settings
from django.db import models
from solo.models import SingletonModel


API_KEY_PREFIX = "sk-"
API_KEY_RANDOM_LEN = 56
API_KEY_ALPHABET = string.ascii_letters + string.digits


def generate_api_key() -> str:
    return API_KEY_PREFIX + "".join(
        secrets.choice(API_KEY_ALPHABET) for _ in range(API_KEY_RANDOM_LEN)
    )


def default_labels():
    return {
        "前端": {"foreground": "#ffffff", "background": "#0075ca", "description": "前端相关问题"},
        "后端": {"foreground": "#ffffff", "background": "#e99695", "description": "后端相关问题"},
        "Bug": {"foreground": "#ffffff", "background": "#d73a4a", "description": "程序错误"},
        "优化": {"foreground": "#ffffff", "background": "#a2eeef", "description": "性能或代码优化"},
        "需求": {"foreground": "#ffffff", "background": "#7057ff", "description": "新功能需求"},
        "文档": {"foreground": "#ffffff", "background": "#0075ca", "description": "文档改进"},
        "CI/CD": {"foreground": "#ffffff", "background": "#e4e669", "description": "持续集成与部署"},
        "安全": {"foreground": "#ffffff", "background": "#d73a4a", "description": "安全相关问题"},
        "性能": {"foreground": "#ffffff", "background": "#f9d0c4", "description": "性能问题"},
        "UI/UX": {"foreground": "#ffffff", "background": "#bfd4f2", "description": "界面与体验"},
    }


def default_priorities():
    # 顺序为高→低;background 是该优先级主色(前端据此派生卡片/行/滑块底色),空串表示无底色(基线档)
    return [
        {"value": "P0", "label": "紧急", "background": "#ef4444"},
        {"value": "P1", "label": "高", "background": "#f97316"},
        {"value": "P2", "label": "中", "background": "#facc15"},
        {"value": "P3", "label": "低", "background": ""},
    ]


def default_issue_statuses():
    return ["未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"]


def default_modules():
    return ["通知中心", "审批流程", "用户管理", "项目管理", "表单", "其他"]


class SiteSettings(SingletonModel):
    labels = models.JSONField(
        default=default_labels,
        verbose_name="Issue 标签",
    )
    priorities = models.JSONField(
        default=default_priorities,
        verbose_name="优先级选项",
    )
    issue_statuses = models.JSONField(
        default=default_issue_statuses,
        verbose_name="Issue 状态选项",
    )
    modules = models.JSONField(
        default=default_modules,
        verbose_name="功能模块",
    )
    default_project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="默认项目",
    )

    class Meta:
        verbose_name = "系统设置"
        verbose_name_plural = "系统设置"

    def __str__(self):
        return "系统设置"


class DatabaseBackup(models.Model):
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("running", "备份中"),
            ("success", "成功"),
            ("failed", "失败"),
        ],
    )
    error_message = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "数据库备份"
        verbose_name_plural = "数据库备份"

    def __str__(self):
        return self.filename


class ExternalAPIKey(models.Model):
    """External API key.

    project=NULL means a site-level key (e.g. for broadcast notification publishing).
    project=<Project> means a project-scoped key (e.g. for issue creation).
    """

    name = models.CharField(max_length=100, verbose_name="名称")
    key = models.CharField(max_length=64, unique=True, verbose_name="API Key")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="关联项目",
        help_text="留空表示站点级 key(只可用于站点级接口,例如发布通知)",
    )
    default_assignee = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="默认负责人",
    )
    is_active = models.BooleanField(default=True, verbose_name="启用")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "外部 API Key"
        verbose_name_plural = "外部 API Keys"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = generate_api_key()
        super().save(*args, **kwargs)
