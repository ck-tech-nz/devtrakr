from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    name = models.CharField(max_length=50, verbose_name="姓名")
    github_id = models.CharField(max_length=100, blank=True, verbose_name="GitHub ID")
    avatar = models.CharField(max_length=50, blank=True, verbose_name="头像")
    settings = models.JSONField(default=dict, blank=True, verbose_name="用户设置")
    is_bot = models.BooleanField(default=False, verbose_name="是否为机器人")
    default_project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="默认项目",
    )

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def __str__(self):
        return self.name or self.username
