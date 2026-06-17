# backend/apps/backups/models.py
from django.conf import settings
from django.db import models


class BackupTarget(models.Model):
    """一个可备份的数据库目标。所有字段都是非敏感引用——密钥留在主机上。"""

    ENGINE_CHOICES = [("postgres", "PostgreSQL")]

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="backup_targets",
        verbose_name="关联项目",
        help_text="留空表示站点级目标(如 DevTrakr 自身)",
    )
    name = models.CharField(max_length=100, verbose_name="名称")
    engine = models.CharField(
        max_length=20, choices=ENGINE_CHOICES, default="postgres", verbose_name="引擎"
    )

    # SSH 引用:密钥留主机(容器内 ~/.ssh + ssh-agent / 挂载的 key 文件)
    ssh_host = models.CharField(
        max_length=255, blank=True, default="",
        verbose_name="SSH 主机", help_text="留空=本地执行(备份 DevTrakr 自身)",
    )
    ssh_user = models.CharField(max_length=64, blank=True, default="", verbose_name="SSH 用户")
    ssh_port = models.PositiveIntegerField(null=True, blank=True, verbose_name="SSH 端口")
    docker_container = models.CharField(
        max_length=128, blank=True, default="",
        verbose_name="DB 容器名", help_text="留空=主机上直接执行 pg_dump",
    )

    # DB 引用:密码靠远程 .pgpass / env,不进库
    db_name = models.CharField(max_length=128, verbose_name="数据库名")
    db_user = models.CharField(max_length=64, blank=True, default="", verbose_name="DB 用户")
    db_host = models.CharField(max_length=255, blank=True, default="", verbose_name="DB 主机(远程视角)")
    db_port = models.PositiveIntegerField(null=True, blank=True, verbose_name="DB 端口")

    # 调度
    schedule_cron = models.CharField(
        max_length=64, blank=True, default="",
        verbose_name="定时(cron)", help_text="5 段 cron;留空=仅手动",
    )
    schedule_enabled = models.BooleanField(default=True, verbose_name="启用定时")

    # 保留
    retention_count = models.PositiveIntegerField(
        default=7, verbose_name="保留份数", help_text="保留最近 N 个成功备份;0=不限",
    )

    is_active = models.BooleanField(default=True, verbose_name="启用")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "备份目标"
        verbose_name_plural = "备份目标"
        ordering = ["project_id", "name"]

    def __str__(self):
        return self.name


class DatabaseBackup(models.Model):
    target = models.ForeignKey(
        BackupTarget, on_delete=models.SET_NULL, null=True, blank=True, related_name="backups",
    )
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("running", "备份中"), ("success", "成功"), ("failed", "失败")],
    )
    error_message = models.TextField(blank=True, default="")
    trigger = models.CharField(
        max_length=20,
        choices=[("manual", "手动"), ("scheduled", "定时")],
        default="manual",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "数据库备份"
        verbose_name_plural = "数据库备份"

    def __str__(self):
        return self.filename
