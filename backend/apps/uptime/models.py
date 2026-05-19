from django.db import models


class UptimeMonitor(models.Model):
    STATUS_UP = "up"
    STATUS_DOWN = "down"
    STATUS_UNKNOWN = "unknown"
    STATUS_CHOICES = [
        (STATUS_UP, "正常"),
        (STATUS_DOWN, "宕机"),
        (STATUS_UNKNOWN, "未知"),
    ]

    ENV_PRODUCTION = "production"
    ENV_STAGING = "staging"
    ENV_TEST = "test"
    ENV_CHOICES = [
        (ENV_PRODUCTION, "生产"),
        (ENV_STAGING, "预发"),
        (ENV_TEST, "测试"),
    ]

    METHOD_GET = "GET"
    METHOD_CHOICES = [
        (METHOD_GET, "GET"),
    ]

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="uptime_monitors",
    )
    name = models.CharField(max_length=100, verbose_name="名称")
    environment = models.CharField(
        max_length=20, choices=ENV_CHOICES, default=ENV_PRODUCTION, verbose_name="环境",
    )
    url = models.URLField(max_length=500, verbose_name="URL")
    method = models.CharField(
        max_length=10, choices=METHOD_CHOICES, default=METHOD_GET, verbose_name="方法",
    )
    expected_status = models.CharField(max_length=50, default="200", verbose_name="期望状态码")
    expected_body = models.CharField(max_length=200, blank=True, verbose_name="期望响应体关键字")
    interval_minutes = models.PositiveIntegerField(default=1, verbose_name="检查间隔(分钟)")
    timeout_secs = models.PositiveIntegerField(default=20, verbose_name="超时(秒)")
    is_enabled = models.BooleanField(default=True, verbose_name="启用")

    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_check_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNKNOWN)
    last_up_at = models.DateTimeField(null=True, blank=True)
    outage_started_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    active_incident_issue = models.ForeignKey(
        "issues.Issue", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "系统监控"
        verbose_name_plural = "系统监控"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.url})"


class UptimeCheck(models.Model):
    monitor = models.ForeignKey(
        UptimeMonitor, on_delete=models.CASCADE, related_name="checks",
    )
    checked_at = models.DateTimeField(db_index=True)
    is_up = models.BooleanField()
    status_code = models.PositiveIntegerField(null=True, blank=True)
    response_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "监控检查记录"
        verbose_name_plural = "监控检查记录"
        indexes = [
            models.Index(fields=["monitor", "-checked_at"]),
        ]
        ordering = ["-checked_at"]

    def __str__(self):
        return f"{self.monitor.name} @ {self.checked_at} {'up' if self.is_up else 'down'}"
