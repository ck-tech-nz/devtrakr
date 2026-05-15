import os
from pathlib import Path
from datetime import timedelta
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-devtrack-dev-only-change-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1")

ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "django_filters",
    "solo",
    "django_celery_results",
    "django_celery_beat",
    "simple_history",
    # Local apps
    "apps.settings",
    "apps.users",
    "apps.projects",
    "apps.issues",
    "apps.repos",
    "apps.ai",
    "apps.tools",
    "apps.notifications",
    "apps.kpi",
    # Packages
    "page_perms",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "devtrack"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "25432"),
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    # 默认无 throttle,仅在按需 opt-in 的视图上启用
    "DEFAULT_THROTTLE_RATES": {
        "ai_wizard": "10/min",
        "ai_duplicate_check": "30/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/api/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Upload size limit — set higher than 5MB so Django doesn't reject before the view's own check runs
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# MinIO / S3 storage
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "devtrack-uploads")
MINIO_USE_SSL = os.environ.get("MINIO_USE_SSL", "False").lower() in ("true", "1")
MINIO_PUBLIC_URL = os.environ.get("MINIO_PUBLIC_URL", "/uploads")

REPO_CLONE_DIR = os.environ.get("REPO_CLONE_DIR", "/data/repos")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/data/backups")

# Celery
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "django-cache"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Page permissions configuration
PAGE_PERMS = {
    "PROTECTED_PATHS": ["/app/permissions"],
    "SEED_ROUTES": [
        {"path": "/app/issues", "label": "问题跟踪", "icon": "i-heroicons-bug-ant", "permission": "issues.view_issue", "sort_order": 0},
        {"path": "/app/dashboard", "label": "项目概览", "icon": "i-heroicons-squares-2x2", "permission": "issues.view_dashboard", "sort_order": 1},
        {"path": "/app/projects", "label": "项目管理", "icon": "i-heroicons-folder-open", "permission": "projects.view_project", "sort_order": 2},
        {"path": "/app/repos", "label": "GitHub 仓库", "icon": "i-heroicons-code-bracket", "permission": "repos.view_repo", "sort_order": 3, "meta": {"serviceKey": "github"}},
        {"path": "/app/ai/team-analysis", "label": "团队分析", "icon": "i-heroicons-cpu-chip", "permission": "ai.view_analysis", "sort_order": 4, "meta": {"serviceKey": "ai"}},
        {"path": "/app/ai/my-plan", "label": "我的提升计划", "icon": "i-heroicons-clipboard-document-check", "permission": None, "sort_order": 5},
        {"path": "/app/ai/plans", "label": "团队计划管理", "icon": "i-heroicons-clipboard-document-list", "permission": "kpi.change_improvementplan", "sort_order": 6},
        {"path": "/app/users", "label": "用户管理", "icon": "i-heroicons-users", "permission": "users.view_user", "sort_order": 7},
        {"path": "/app/kpi", "label": "KPI 分析", "icon": "i-heroicons-chart-bar-square", "permission": "kpi.view_kpisnapshot", "sort_order": 8},
        {"path": "/app/notifications/manage", "label": "通知管理", "icon": "i-heroicons-bell-alert", "permission": "notifications.view_notification", "sort_order": 9},
        {"path": "/app/settings/kpi-scoring", "label": "KPI 评分规则", "icon": "i-heroicons-adjustments-horizontal", "permission": None, "sort_order": 10, "meta": {"superuserOnly": True}},
        {"path": "/app/settings/backups", "label": "数据库备份", "icon": "i-heroicons-circle-stack", "permission": None, "sort_order": 11, "meta": {"superuserOnly": True}},
        {"path": "/app/permissions", "label": "权限管理", "icon": "i-heroicons-shield-check", "permission": None, "sort_order": 99, "meta": {"superuserOnly": True}},
        {"path": "/app/api-docs", "label": "接口文档", "icon": "i-heroicons-document-text", "permission": "settings.view_externalapikey", "sort_order": 100},
        {"path": "/app/about", "label": "关于系统", "icon": "i-heroicons-information-circle", "permission": None, "sort_order": 101},
    ],
    "SEED_GROUPS": {
        "管理员": {"apps": ["projects", "issues", "settings", "repos", "ai", "users", "tools", "notifications", "kpi"]},
        "开发者": {"permissions": ["view_project", "view_issue", "add_issue", "change_issue", "view_activity", "view_dashboard", "view_analysis", "add_analysis", "view_own_kpi", "view_own_plan"]},
        "产品经理": {"inherit": "开发者", "permissions": ["add_project", "change_project", "manage_project_members", "view_own_plan"]},
        "只读成员": {"permissions_startswith": ["view_"], "exclude_permissions": ["view_user"]},
        "测试": {"permissions": ["view_project", "view_issue", "add_issue", "change_issue", "view_activity", "view_dashboard", "view_analysis", "add_analysis", "view_own_kpi", "view_own_plan"]},
    },
}

UNFOLD = {
    "SITE_TITLE": "DevTrack",
    "SITE_HEADER": "DevTrack 管理后台",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "项目管理",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "项目",
                        "icon": "folder_open",
                        "link": reverse_lazy("admin:projects_project_changelist"),
                    },
                    {
                        "title": "问题",
                        "icon": "bug_report",
                        "link": reverse_lazy("admin:issues_issue_changelist"),
                    },
                    {
                        "title": "活动",
                        "icon": "history",
                        "link": reverse_lazy("admin:issues_activity_changelist"),
                    },
                ],
            },
            {
                "title": "代码仓库",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "仓库",
                        "icon": "source",
                        "link": reverse_lazy("admin:repos_repo_changelist"),
                    },
                    {
                        "title": "GitHub Issues",
                        "icon": "label",
                        "link": reverse_lazy("admin:repos_githubissue_changelist"),
                    },
                ],
            },
            {
                "title": "AI 配置",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "LLM 配置",
                        "icon": "smart_toy",
                        "link": reverse_lazy("admin:ai_llmconfig_changelist"),
                    },
                    {
                        "title": "提示词",
                        "icon": "description",
                        "link": reverse_lazy("admin:ai_prompt_changelist"),
                    },
                    {
                        "title": "分析记录",
                        "icon": "analytics",
                        "link": reverse_lazy("admin:ai_analysis_changelist"),
                    },
                ],
            },
            {
                "title": "用户与权限",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "用户",
                        "icon": "people",
                        "link": reverse_lazy("admin:users_user_changelist"),
                    },
                    {
                        "title": "用户组",
                        "icon": "group_work",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
            {
                "title": "通知",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "通知",
                        "icon": "notifications",
                        "link": reverse_lazy("admin:notifications_notification_changelist"),
                    },
                    {
                        "title": "通知接收",
                        "icon": "mark_email_read",
                        "link": reverse_lazy("admin:notifications_notificationrecipient_changelist"),
                    },
                ],
            },
            {
                "title": "系统",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "站点设置",
                        "icon": "settings",
                        "link": reverse_lazy("admin:settings_sitesettings_changelist"),
                    },
                    {
                        "title": "附件",
                        "icon": "attach_file",
                        "link": reverse_lazy("admin:tools_attachment_changelist"),
                    },
                    {
                        "title": "外部 API Keys",
                        "icon": "key",
                        "link": reverse_lazy("admin:settings_externalapikey_changelist"),
                    },
                ],
            },
            {
                "title": "定时任务",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "任务结果",
                        "icon": "task_alt",
                        "link": reverse_lazy("admin:django_celery_results_taskresult_changelist"),
                    },
                    {
                        "title": "定时任务",
                        "icon": "schedule",
                        "link": reverse_lazy("admin:django_celery_beat_periodictask_changelist"),
                    },
                    {
                        "title": "执行间隔",
                        "icon": "timer",
                        "link": reverse_lazy("admin:django_celery_beat_intervalschedule_changelist"),
                    },
                    {
                        "title": "Cron 计划",
                        "icon": "event_repeat",
                        "link": reverse_lazy("admin:django_celery_beat_crontabschedule_changelist"),
                    },
                ],
            },
        ],
    },
}
