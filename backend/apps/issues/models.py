from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class Priority(models.TextChoices):
    P0 = 'P0', '紧急'
    P1 = 'P1', '高'
    P2 = 'P2', '中'
    P3 = 'P3', '低'


class IssueStatus(models.TextChoices):
    UNPLANNED = '未计划', '未计划'
    UNASSIGNED = '待分配', '待分配'
    PENDING_CONFIRMATION = '待确认', '待确认'
    IN_PROGRESS = '进行中', '进行中'
    RESOLVED = '已解决', '已解决'
    PUBLISHED = '已发布', '已发布'
    CLOSED = '已关闭', '已关闭'


# 由「状态选择器以外的代码路径」赋值的状态,不可在站点设置中禁用——否则工单会被
# 置入一个 UI 不可见的状态(无法选择/筛选/看板展示),形成"看不到的工单"。
# 仅「未计划 / 已发布」从不被任何代码路径赋值,因此只有这两个可被禁用。
SYSTEM_ASSIGNED_STATUSES = (
    IssueStatus.UNASSIGNED.value,            # create_issue / uptime 建单初始状态
    IssueStatus.PENDING_CONFIRMATION.value,  # assign / transfer / confirm 目标
    IssueStatus.IN_PROGRESS.value,           # claim / confirm 目标
    IssueStatus.RESOLVED.value,              # uptime fire_recovery 监控恢复自动置为已解决
    IssueStatus.CLOSED.value,                # IssueCloseWithGitHubView 关闭动作
)


class AssignmentAction(models.TextChoices):
    CLAIM = 'claim', '认领'
    ASSIGN = 'assign', '指派'
    AI_ASSIGN = 'ai_assign', 'AI分配'
    TRANSFER = 'transfer', '转单'
    CONFIRM = 'confirm', '确认'


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
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="managed_issues",
        verbose_name="项目经理快照",
        help_text="创建时快照,后续 project.manager 变更不影响此字段",
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

    # 关联到其它 issue 的轻量记录, 仅在 detail 页面展示。schema:
    #   [{"id": int, "kind": "manual"|"ai_dup", "reason": str, "added_at": iso}]
    # 选 JSON 而非 M2M(self) 因为读取场景只在 detail 渲染、写入低频、未来想扩 schema 免迁移。
    # 引用完整性弱 (被删的 issue 会留 orphan id), 展示层负责跳过 + 真要做反查再加 GIN 索引。
    related_issues = models.JSONField(
        default=list, blank=True, verbose_name="关联 Issue",
    )

    is_deleted = models.BooleanField(default=False, verbose_name="已删除")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="删除时间")

    objects = IssueManager()
    all_objects = models.Manager()
    history = HistoricalRecords(
        excluded_fields=["updated_at"],
        m2m_fields=["github_issues", "attachments", "helpers"],
    )

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


class IssueAssignment(models.Model):
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name='assignments',
    )
    action = models.CharField(max_length=20, choices=AssignmentAction.choices)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="转出方",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="接收方",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="操作人",
    )
    reason = models.TextField(blank=True, default='', verbose_name="原因")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "分配事件"
        verbose_name_plural = "分配事件"
        ordering = ['created_at']
        indexes = [models.Index(fields=['issue', '-created_at'])]

    def __str__(self):
        return f"{self.issue_id} {self.action} → {self.to_user_id}"


class IssueComment(models.Model):
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="issue_comments", verbose_name="作者",
    )
    content = models.TextField(verbose_name="内容")  # markdown 原文,附件以内联链接存在
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "问题评论"
        verbose_name_plural = "问题评论"
        ordering = ["created_at", "id"]  # 旧→新,同 GitHub; id 兜底保证同时间戳时排序稳定
        indexes = [models.Index(fields=["issue", "created_at"])]

    def __str__(self):
        return f"#{self.issue_id} {self.author}: {self.content[:30]}"


class IssueChatParticipant(models.Model):
    """聊天会话成员 + 已读指针。一行 = 某用户参与某问题的评论会话。"""
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="chat_participants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="issue_chats"
    )
    last_read_comment = models.ForeignKey(
        IssueComment, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("issue", "user")]
        indexes = [models.Index(fields=["user", "-updated_at"])]

    def unread_count(self) -> int:
        """该会话对本用户的未读评论数:比指针更新、且非本人所发。"""
        qs = self.issue.comments.exclude(author_id=self.user_id)
        if self.last_read_comment_id:
            qs = qs.filter(id__gt=self.last_read_comment_id)
        return qs.count()
