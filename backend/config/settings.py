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
    "apps.uptime",
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

# AI Issue Wizard rollback flag — set "True" to fall back to the 3-stage
# legacy pipeline (wizard_classify/extract/generate). Defaults to False;
# v1 prompt rows are preserved for the 7-day rollback window post-deploy.
AI_WIZARD_LEGACY = os.environ.get("AI_WIZARD_LEGACY", "False").lower() in ("true", "1")

# 对话式 wizard 首份 draft 出来后, 是否额外跑一次重复检测 (issue_duplicate_check prompt)
# 关掉的两种方式 (二选一即可):
#   1. env: WIZARD_CHAT_DUP_CHECK_ENABLED=0  (需重启, 永久关停)
#   2. /admin/ai/prompt/ 把 slug=issue_duplicate_check 的 prompt 设为 is_active=False
#      (热切换, 不用重启, 同时也关闭老 /api/issues/check-duplicate/ 端点)
WIZARD_CHAT_DUP_CHECK_ENABLED = os.environ.get(
    "WIZARD_CHAT_DUP_CHECK_ENABLED", "True",
).lower() in ("true", "1")

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

# Uptime monitoring
UPTIME_TICK_SECONDS = 60
UPTIME_FAILURE_THRESHOLD = 3
UPTIME_CHECK_RETENTION_DAYS = 30
UPTIME_DEFAULT_TIMEOUT_SECS = 20
UPTIME_SYSTEM_BOT_USERNAME = "bot"

# Page permissions seed file (DB ↔ JSON round-trip via sync_page_perms / dump_page_perms)
PAGE_PERMS_SEED_FILE = BASE_DIR / "page_perms.json"

# Remote DevTrakr targets — used by the Notification admin "发布到 test / prod" buttons.
# Keys are issued by the remote (ExternalAPIKey on test/prod), stored locally in .env.
DEVTRAKR_TEST_URL = os.environ.get("DEVTRAKR_TEST_URL", "https://devtrakr-test.matrixai.xin/api/external/notifications/create/")
DEVTRAKR_TEST_KEY = os.environ.get("DEVTRAKR_TEST_KEY", "")
DEVTRAKR_PROD_URL = os.environ.get("DEVTRAKR_PROD_URL", "https://devtrakr.matrixai.xin/api/external/notifications/create/")
DEVTRAKR_PROD_KEY = os.environ.get("DEVTRAKR_PROD_KEY", "")

# 电话线路(SIP 网关)状态代理 — 前端经 /api/dashboard/gateway-status/ 拉取。
# API_KEY 是密钥,只写 .env 不入库;后端主机需能出网访问该 URL。
GATEWAY_STATUS_URL = os.environ.get("GATEWAY_STATUS_URL", "")
GATEWAY_STATUS_API_KEY = os.environ.get("GATEWAY_STATUS_API_KEY", "")
GATEWAY_STATUS_CACHE_TTL = int(os.environ.get("GATEWAY_STATUS_CACHE_TTL") or "12")

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
                        "title": "页面路由",
                        "icon": "menu",
                        "link": reverse_lazy("admin:page_perms_pageroute_changelist"),
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
            }
        ],
    },
}
