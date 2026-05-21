from django.contrib.auth.models import Permission
from django.db import models


class PageRoute(models.Model):
    path = models.CharField(max_length=255, unique=True, verbose_name="路由路径")
    label = models.CharField(max_length=100, verbose_name="显示名称")
    icon = models.CharField(max_length=100, blank=True, default="", verbose_name="图标")
    permission = models.ForeignKey(
        Permission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_routes",
        verbose_name="所需权限",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="父级菜单",
    )
    is_group = models.BooleanField(default=False, verbose_name="是分组")
    show_in_nav = models.BooleanField(default=True, verbose_name="显示在导航栏")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    meta = models.JSONField(default=dict, blank=True, verbose_name="元数据")
    source = models.CharField(
        max_length=20, default="manual", verbose_name="来源",
        help_text="seed = sync command, manual = UI",
    )

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "页面路由"
        verbose_name_plural = "页面路由"

    def __str__(self):
        if self.is_group:
            return f"[分组] {self.label}"
        return f"{self.path} → {self.permission or '(无权限要求)'}"
