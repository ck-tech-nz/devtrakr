import os
import re

from django.conf import settings as django_settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class Repo(models.Model):
    CLONE_STATUS_CHOICES = [
        ("not_cloned", "未克隆"),
        ("cloning", "克隆中"),
        ("cloned", "已克隆"),
        ("failed", "失败"),
        ("error", "错误"),
    ]

    name = models.CharField(max_length=100, verbose_name="仓库名")
    full_name = models.CharField(max_length=200, verbose_name="完整名称")
    url = models.CharField(max_length=500, verbose_name="GitHub URL")
    description = models.TextField(blank=True, verbose_name="描述")
    default_branch = models.CharField(max_length=50, default="main", verbose_name="默认分支")
    language = models.CharField(max_length=50, blank=True, verbose_name="主要语言")
    stars = models.PositiveIntegerField(default=0, verbose_name="Star 数")
    status = models.CharField(max_length=20, default="在线", verbose_name="状态")
    connected_at = models.DateTimeField(auto_now_add=True, verbose_name="绑定时间")
    github_token = models.CharField(max_length=200, blank=True, verbose_name="GitHub Token")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="最近同步时间")
    clone_status = models.CharField(max_length=20, choices=CLONE_STATUS_CHOICES, default="not_cloned", verbose_name="克隆状态")
    clone_error = models.TextField(blank=True, verbose_name="克隆错误信息")
    current_branch = models.CharField(max_length=100, blank=True, verbose_name="当前分支")
    cloned_at = models.DateTimeField(null=True, blank=True, verbose_name="克隆时间")

    @property
    def local_path(self):
        if not re.match(r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$", self.full_name):
            raise ValueError(f"Invalid full_name: {self.full_name}")
        return os.path.join(django_settings.REPO_CLONE_DIR, self.full_name)

    class Meta:
        verbose_name = "GitHub 仓库"
        verbose_name_plural = "GitHub 仓库"
        ordering = ["-connected_at"]

    def __str__(self):
        return self.full_name


class GitHubIssue(models.Model):
    STATE_OPEN = "open"
    STATE_CLOSED = "closed"
    STATE_CHOICES = [(STATE_OPEN, "开放"), (STATE_CLOSED, "已关闭")]

    repo = models.ForeignKey(Repo, on_delete=models.CASCADE, related_name="github_issues")
    github_id = models.PositiveIntegerField(verbose_name="GitHub Issue 编号")
    title = models.CharField(max_length=500, verbose_name="标题")
    body = models.TextField(blank=True, verbose_name="内容")
    state = models.CharField(max_length=20, choices=STATE_CHOICES, verbose_name="状态")
    labels = models.JSONField(default=list, verbose_name="标签")
    assignees = models.JSONField(default=list, verbose_name="负责人")
    github_created_at = models.DateTimeField(verbose_name="GitHub 创建时间")
    github_updated_at = models.DateTimeField(verbose_name="GitHub 更新时间")
    github_closed_at = models.DateTimeField(null=True, blank=True, verbose_name="GitHub 关闭时间")
    synced_at = models.DateTimeField(verbose_name="同步时间")

    class Meta:
        verbose_name = "GitHub Issue"
        verbose_name_plural = "GitHub Issues"
        unique_together = ("repo", "github_id")
        ordering = ["-github_created_at"]

    def __str__(self):
        return f"#{self.github_id} {self.title}"


class Commit(models.Model):
    repo = models.ForeignKey(Repo, on_delete=models.CASCADE, related_name="commits")
    hash = models.CharField(max_length=40, verbose_name="提交哈希")
    author_name = models.CharField(max_length=200, verbose_name="作者名")
    author_email = models.CharField(max_length=254, verbose_name="作者邮箱")
    date = models.DateTimeField(verbose_name="提交时间")
    message = models.TextField(verbose_name="提交信息")
    additions = models.IntegerField(default=0, verbose_name="新增行数")
    deletions = models.IntegerField(default=0, verbose_name="删除行数")
    files_changed = models.JSONField(default=list, verbose_name="变更文件")

    class Meta:
        verbose_name = "提交记录"
        verbose_name_plural = "提交记录"
        unique_together = ("repo", "hash")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.hash[:7]} {self.message[:50]}"


class GitAuthorAlias(models.Model):
    repo = models.ForeignKey(Repo, on_delete=models.CASCADE, related_name="author_aliases")
    author_email = models.CharField(max_length=254, verbose_name="作者邮箱")
    author_name = models.CharField(max_length=200, verbose_name="作者名")
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="git_aliases",
        verbose_name="关联用户",
    )

    class Meta:
        verbose_name = "Git 作者映射"
        verbose_name_plural = "Git 作者映射"
        unique_together = ("repo", "author_email")

    def __str__(self):
        label = self.user.name if self.user else "未关联"
        return f"{self.author_name} <{self.author_email}> → {label}"


class PullRequest(models.Model):
    STATE_OPEN = "open"
    STATE_CLOSED = "closed"
    STATE_MERGED = "merged"
    STATE_CHOICES = [
        (STATE_OPEN, "开放"),
        (STATE_CLOSED, "已关闭"),
        (STATE_MERGED, "已合并"),
    ]

    repo = models.ForeignKey(Repo, on_delete=models.CASCADE, related_name="pull_requests")
    number = models.PositiveIntegerField(verbose_name="PR 编号")
    title = models.CharField(max_length=500, verbose_name="标题")
    body = models.TextField(blank=True, verbose_name="内容")
    state = models.CharField(max_length=20, choices=STATE_CHOICES, verbose_name="状态")
    merged_at = models.DateTimeField(null=True, blank=True, verbose_name="合并时间")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="关闭时间")
    base_branch = models.CharField(max_length=255, blank=True, verbose_name="目标分支")
    head_branch = models.CharField(max_length=255, blank=True, verbose_name="源分支")
    author_login = models.CharField(max_length=200, blank=True, verbose_name="作者")
    author_avatar = models.CharField(max_length=500, blank=True, verbose_name="作者头像")
    html_url = models.CharField(max_length=500, blank=True, verbose_name="链接")
    github_created_at = models.DateTimeField(verbose_name="GitHub 创建时间")
    github_updated_at = models.DateTimeField(verbose_name="GitHub 更新时间")
    synced_at = models.DateTimeField(verbose_name="同步时间")
    linked_issues = models.JSONField(default=list, blank=True, verbose_name="关联 Issue")

    class Meta:
        verbose_name = "Pull Request"
        verbose_name_plural = "Pull Requests"
        unique_together = ("repo", "number")
        ordering = ["-github_created_at"]
        indexes = [GinIndex(fields=["linked_issues"], name="pr_linked_issues_gin")]

    def __str__(self):
        return f"#{self.number} {self.title}"
