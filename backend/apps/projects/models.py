from django.conf import settings
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=100, verbose_name="项目名")
    description = models.TextField(blank=True, verbose_name="描述")
    status = models.CharField(max_length=20, verbose_name="状态")
    remark = models.TextField(blank=True, verbose_name="备注")
    estimated_completion = models.DateField(null=True, blank=True, verbose_name="预计完成")
    actual_hours = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="实际工时"
    )
    repos = models.ManyToManyField(
        "repos.Repo", blank=True, related_name="projects",
        verbose_name="关联仓库",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ProjectMember",
        related_name="projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "项目"
        verbose_name_plural = "项目"
        ordering = ["-updated_at"]
        permissions = [
            ("manage_project_members", "Can manage project members"),
        ]

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="project_members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships"
    )
    role = models.ForeignKey(
        "auth.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_memberships",
        verbose_name="角色",
    )
    personal_description = models.TextField(
        blank=True, default="", verbose_name="个人描述"
    )
    is_manager = models.BooleanField(default=False, verbose_name="项目经理")

    class Meta:
        verbose_name = "项目成员"
        verbose_name_plural = "项目成员"
        unique_together = ("project", "user")
        constraints = [
            models.UniqueConstraint(
                fields=["project"],
                condition=models.Q(is_manager=True),
                name="one_manager_per_project",
            ),
        ]

    def __str__(self):
        role_name = self.role.name if self.role_id else "-"
        flag = " [经理]" if self.is_manager else ""
        return f"{self.user} - {self.project} ({role_name}){flag}"
