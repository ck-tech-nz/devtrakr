from django.apps import AppConfig


class BackupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backups"
    verbose_name = "数据库备份"

    def ready(self):
        from apps.backups import signals  # noqa: F401
