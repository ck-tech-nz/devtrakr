import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class Type(models.TextChoices):
        MENTION = "mention", "提及"
        SYSTEM = "system", "系统"
        BROADCAST = "broadcast", "广播"

    class TargetType(models.TextChoices):
        USER = "user", "个人"
        GROUP = "group", "组"
        ALL = "all", "全员"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification_type = models.CharField(max_length=20, choices=Type.choices, verbose_name="类型")
    title = models.CharField(max_length=200, verbose_name="标题")
    content = models.TextField(blank=True, verbose_name="内容")
    source_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sent_notifications", verbose_name="触发者",
    )
    source_issue = models.ForeignKey(
        "issues.Issue", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="notifications", verbose_name="关联问题",
    )
    target_type = models.CharField(max_length=10, choices=TargetType.choices, verbose_name="目标类型")
    target_group = models.ForeignKey(
        "auth.Group", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="目标组",
    )
    target_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        related_name="targeted_notifications", verbose_name="目标用户",
    )
    is_draft = models.BooleanField(default=False, verbose_name="草稿")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "通知"
        verbose_name_plural = "通知"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class NotificationRecipient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="recipients",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notification_recipients",
    )
    is_read = models.BooleanField(default=False, verbose_name="已读")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="阅读时间")
    is_deleted = models.BooleanField(default=False, verbose_name="已删除")

    class Meta:
        verbose_name = "通知接收"
        verbose_name_plural = "通知接收"
        unique_together = [("notification", "user")]

    def __str__(self):
        return f"{self.notification.title} → {self.user}"


class BulletinQuerySet(models.QuerySet):
    def currently_active(self):
        now = timezone.now()
        return (
            self.filter(is_active=True)
            .filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
            .order_by("sort_order", "-created_at")
        )


class Bulletin(models.Model):
    """Ambient header-carousel content shown to everyone, WITHOUT per-user read
    tracking — distinct from Notification (inbox + read state). Named Bulletin to
    avoid colliding with Notification.Type.BROADCAST."""

    class Category(models.TextChoices):
        QUOTE = "quote", "名言"
        PROMPT = "prompt", "提示词"
        PITFALL = "pitfall", "避坑"
        VALUE = "value", "价值观"
        ANNOUNCEMENT = "announcement", "公告"

    category = models.CharField(max_length=20, choices=Category.choices, verbose_name="分类")
    content = models.TextField(verbose_name="内容")
    source = models.CharField(max_length=200, blank=True, default="", verbose_name="出处")
    link_url = models.URLField(blank=True, default="", verbose_name="链接")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_bulletins", verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BulletinQuerySet.as_manager()

    class Meta:
        verbose_name = "走马灯公告"
        verbose_name_plural = "走马灯公告"
        ordering = ["sort_order", "-created_at"]

    def __str__(self):
        return f"[{self.get_category_display()}] {self.content[:30]}"
