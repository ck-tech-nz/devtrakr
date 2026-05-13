from django.conf import settings
from django.db import models


class Priority(models.TextChoices):
    P0 = 'P0', '紧急'
    P1 = 'P1', '高'
    P2 = 'P2', '中'
    P3 = 'P3', '低'


class IssueStatus(models.TextChoices):
    UNPLANNED = '未计划', '未计划'
    PENDING = '待处理', '待处理'
    IN_PROGRESS = '进行中', '进行中'
    RESOLVED = '已解决', '已解决'
    PUBLISHED = '已发布', '已发布'
    CLOSED = '已关闭', '已关闭'


class IssueManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Issue(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="issues"
    )
    title = models.CharField(max_length=200, verbose_name="标题")
    description = models.TextField(blank=True, verbose_name="描述")
    github_issues = models.ManyToManyField(
        "repos.GitHubIssue", blank=True, related_name="devtrack_issues",
        verbose_name="关联 GitHub Issues",
    )
    attachments = models.ManyToManyField(
        "tools.Attachment", blank=True,
        related_name="issues", verbose_name="附件",
    )
    repo = models.ForeignKey(
        "repos.Repo", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="issues",
        verbose_name="关联仓库",
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, verbose_name="优先级")
    status = models.CharField(max_length=20, choices=IssueStatus.choices, verbose_name="状态")
    labels = models.JSONField(default=list, verbose_name="标签", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_issues", verbose_name="创建人",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_issues", verbose_name="负责人",
    )
    helpers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="helped_issues",
        verbose_name="协助人",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="updated_issues", verbose_name="更新人",
    )
    reporter = models.CharField(max_length=100, blank=True, default="", verbose_name="提出人")
    remark = models.TextField(blank=True, verbose_name="备注")
    estimated_completion = models.DateField(null=True, blank=True, verbose_name="预计完成")
    estimated_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=4.0,
        verbose_name="预计工时", help_text="用于工单规模分级 (小型/中型/大型) 的依据,默认 4 小时",
    )
    actual_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="实际工时")
    cause = models.TextField(blank=True, verbose_name="原因分析")
    solution = models.TextField(blank=True, verbose_name="解决办法")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="解决时间")
    source = models.CharField(max_length=50, null=True, blank=True, verbose_name="来源")
    source_meta = models.JSONField(null=True, blank=True, verbose_name="来源元数据")

    settlement = models.JSONField(
        null=True, blank=True, verbose_name="结算快照",
        help_text="工单标记完成时冻结的价格/工时/规则,不受后续配置修改影响",
    )

    is_deleted = models.BooleanField(default=False, verbose_name="已删除")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="删除时间")

    objects = IssueManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "问题"
        verbose_name_plural = "问题"
        ordering = ["-created_at"]
        permissions = [
            ("batch_update_issue", "Can batch update issues"),
            ("view_dashboard", "Can view dashboard"),
        ]

    def __str__(self):
        return f"#{self.pk} {self.title}"


class Activity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="activities")
    action = models.CharField(max_length=20, verbose_name="动作")
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="activities")
    detail = models.CharField(max_length=200, blank=True, verbose_name="详情")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "活动记录"
        verbose_name_plural = "活动记录"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} {self.action} {self.issue}"
