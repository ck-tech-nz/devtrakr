import re
from rest_framework import serializers
from django.utils import timezone
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from apps.settings.models import SiteSettings
from apps.repos.serializers import GitHubIssueBriefSerializer
from apps.tools.models import Attachment
from apps.tools.serializers import AttachmentSerializer
from apps.notifications.services import create_mention_notifications
from .models import Issue, IssueStatus, Activity

User = get_user_model()


def _sync_attachments(issue, user):
    """Link Attachment records whose URL appears in issue.description to the issue."""
    if not issue.description:
        return
    minio_base = django_settings.MINIO_PUBLIC_URL
    urls = set(re.findall(r'https?://\S+', issue.description))
    cleaned = {re.sub(r'[)"\']+$', '', u) for u in urls}
    for url in cleaned:
        if url.startswith(minio_base):
            for att in Attachment.objects.filter(file_url=url, uploaded_by=user):
                issue.attachments.add(att)


class ActivitySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    issue_title = serializers.CharField(source="issue.title", read_only=True)
    issue_id = serializers.IntegerField(source="issue.id", read_only=True)

    class Meta:
        model = Activity
        fields = ["id", "user_name", "action", "issue_title", "issue_id", "detail", "created_at"]


class GitHubIssueLinkSerializer(serializers.ModelSerializer):
    """列表页用的轻量序列化，只返回构建链接需要的字段。"""
    repo_full_name = serializers.CharField(source="repo.full_name", read_only=True)

    class Meta:
        from apps.repos.models import GitHubIssue
        model = GitHubIssue
        fields = ["id", "github_id", "repo_full_name", "title", "state"]
        read_only_fields = fields


class IssueListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    assignee_name = serializers.CharField(source="assignee.name", read_only=True, default=None)
    helpers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    helpers_names = serializers.SerializerMethodField()
    resolution_hours = serializers.SerializerMethodField()
    github_issues = GitHubIssueLinkSerializer(many=True, read_only=True)
    ai_cause = serializers.CharField(read_only=True, default='')
    ai_solution = serializers.CharField(read_only=True, default='')

    class Meta:
        model = Issue
        fields = [
            "id", "project", "repo", "title", "priority",
            "status", "labels", "reporter",
            "created_by", "created_by_name",
            "updated_by", "updated_by_name",
            "assignee", "assignee_name", "helpers", "helpers_names", "remark", "cause", "solution",
            "ai_cause", "ai_solution",
            "resolution_hours", "created_at", "updated_at", "github_issues",
            "estimated_completion", "estimated_hours", "source",
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.name or obj.created_by.username
        return None

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.name or obj.updated_by.username
        return None

    def get_helpers_names(self, obj):
        return [u.name or u.username for u in obj.helpers.all()]

    def get_resolution_hours(self, obj):
        if obj.resolved_at and obj.created_at:
            delta = obj.resolved_at - obj.created_at
            return round(delta.total_seconds() / 3600, 1)
        return None


class IssueDetailSerializer(IssueListSerializer):
    github_issues = GitHubIssueBriefSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta(IssueListSerializer.Meta):
        fields = IssueListSerializer.Meta.fields + [
            "description", "estimated_completion",
            "actual_hours", "resolved_at", "github_issues", "attachments",
            "source_meta", "settlement",
        ]


class IssueCreateUpdateSerializer(serializers.ModelSerializer):
    helpers = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.all(), required=False,
    )
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, write_only=True, default=list,
    )

    class Meta:
        model = Issue
        fields = [
            "id", "project", "repo", "title", "description", "priority", "status",
            "labels", "assignee", "helpers", "reporter", "remark", "estimated_completion",
            "estimated_hours", "actual_hours", "cause", "solution", "attachment_ids",
        ]
        read_only_fields = ["id"]

    def validate_labels(self, value):
        site_settings = SiteSettings.get_solo()
        labels = site_settings.labels
        valid = set(labels.keys()) if isinstance(labels, dict) else set(labels)
        invalid = [label for label in value if label not in valid]
        if invalid:
            raise serializers.ValidationError(f"无效的标签: {invalid}")
        return value

    def validate_priority(self, value):
        site_settings = SiteSettings.get_solo()
        if value not in site_settings.priorities:
            raise serializers.ValidationError(f"无效的优先级: {value}")
        return value

    def validate_status(self, value):
        if value not in IssueStatus.values:
            raise serializers.ValidationError(f"无效的状态: {value}")
        return value

    def _user_can_edit_estimated_hours(self) -> bool:
        user = self.context["request"].user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.groups.filter(name="管理员").exists()

    def create(self, validated_data):
        helpers = validated_data.pop("helpers", [])
        attachment_ids = validated_data.pop("attachment_ids", [])
        # 非管理员创建时忽略客户端传入的 estimated_hours,使用模型默认值 (4h)
        if "estimated_hours" in validated_data and not self._user_can_edit_estimated_hours():
            validated_data.pop("estimated_hours")
        validated_data["created_by"] = self.context["request"].user
        issue = super().create(validated_data)
        if helpers:
            issue.helpers.set(helpers)
        Activity.objects.create(
            user=self.context["request"].user,
            issue=issue,
            action="created",
        )
        if attachment_ids:
            atts = Attachment.objects.filter(
                id__in=attachment_ids, uploaded_by=self.context["request"].user,
            )
            issue.attachments.add(*atts)
        create_mention_notifications(
            issue=issue,
            old_description="",
            new_description=issue.description,
            actor=self.context["request"].user,
        )
        return issue

    def update(self, instance, validated_data):
        old_description = instance.description
        helpers = validated_data.pop("helpers", None)
        user = self.context["request"].user
        old_status = instance.status
        old_assignee = instance.assignee_id
        # 仅管理员可修改 estimated_hours,其他人静默忽略
        if "estimated_hours" in validated_data and not self._user_can_edit_estimated_hours():
            validated_data.pop("estimated_hours")
        validated_data["updated_by"] = user
        issue = super().update(instance, validated_data)
        if helpers is not None:
            issue.helpers.set(helpers)

        new_status = validated_data.get("status")
        if new_status and new_status != old_status:
            action = "resolved" if new_status == "已解决" else "closed" if new_status == "已关闭" else "updated"
            Activity.objects.create(
                user=user, issue=issue, action=action,
                detail=f"状态从 {old_status} 改为 {new_status}",
            )
            if new_status in ("已解决", "已发布", "已关闭") and not issue.resolved_at:
                issue.resolved_at = timezone.now()
                issue.save(update_fields=["resolved_at"])
            # 首次进入完成状态时锁定结算 (已结算的不再重算 → 重修不会双倍计价)
            if new_status in ("已解决", "已发布", "已关闭") and not issue.settlement:
                from apps.kpi.settlement import settle_issue
                settle_issue(issue)

        new_assignee = validated_data.get("assignee")
        if "assignee" in validated_data and str(getattr(new_assignee, "id", None)) != str(old_assignee):
            Activity.objects.create(
                user=user, issue=issue, action="assigned",
                detail=f"分配给 {new_assignee.name}" if new_assignee else "取消分配",
            )

        _sync_attachments(issue, user)
        if "description" in validated_data:
            create_mention_notifications(
                issue=issue,
                old_description=old_description,
                new_description=issue.description,
                actor=user,
            )
        return issue


class BatchUpdateSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField())
    action = serializers.ChoiceField(choices=["assign", "set_priority", "set_status", "delete"])
    value = serializers.CharField(required=False, default="")
