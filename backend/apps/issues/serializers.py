import json
import re
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from apps.settings.models import SiteSettings
from apps.projects.models import Project
from apps.repos.serializers import GitHubIssueBriefSerializer
from apps.tools.models import Attachment
from apps.tools.serializers import AttachmentSerializer
from apps.notifications.services import create_mention_notifications
from .models import Issue, IssueStatus, Activity, IssueAssignment

User = get_user_model()

# Issue 的 source 字段必须从此白名单中取值,防止前端伪造来源
ALLOWED_ISSUE_SOURCES = ("ai_wizard", "github", "external_api")
# source_meta 序列化后的 JSON 字节上限,防止滥用作为大容量存储
SOURCE_META_MAX_BYTES = 4096


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
    manager_name = serializers.SerializerMethodField()
    helpers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    helpers_names = serializers.SerializerMethodField()
    resolution_hours = serializers.SerializerMethodField()
    github_issues = GitHubIssueLinkSerializer(many=True, read_only=True)
    ai_cause = serializers.CharField(read_only=True, default='')
    ai_solution = serializers.CharField(read_only=True, default='')
    can_claim = serializers.SerializerMethodField()
    can_confirm = serializers.SerializerMethodField()
    can_transfer = serializers.SerializerMethodField()
    can_assign = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = [
            "id", "project", "repo", "title", "priority",
            "status", "labels", "reporter",
            "created_by", "created_by_name",
            "updated_by", "updated_by_name",
            "assignee", "assignee_name", "manager", "manager_name",
            "helpers", "helpers_names", "remark", "cause", "solution",
            "ai_cause", "ai_solution",
            "resolution_hours", "created_at", "updated_at", "github_issues",
            "estimated_completion", "estimated_hours", "source",
            "can_claim", "can_confirm", "can_transfer", "can_assign",
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

    def get_manager_name(self, obj):
        if obj.manager:
            return obj.manager.name or obj.manager.username
        return None

    def _request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None) if request else None

    def get_can_claim(self, obj):
        from apps.projects.models import ProjectMember
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status != "待分配":
            return False
        return ProjectMember.objects.filter(project=obj.project, user=user).exists()

    def get_can_confirm(self, obj):
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status != "待确认":
            return False
        return obj.assignee_id == user.id

    def get_can_transfer(self, obj):
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status not in ("待确认", "进行中"):
            return False
        return obj.assignee_id == user.id or obj.manager_id == user.id

    def get_can_assign(self, obj):
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status != "待分配":
            return False
        return obj.manager_id == user.id


class IssueAssignmentSerializer(serializers.ModelSerializer):
    from_user_name = serializers.SerializerMethodField()
    to_user_name = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = IssueAssignment
        fields = [
            "id", "action", "reason", "created_at",
            "from_user", "from_user_name",
            "to_user", "to_user_name",
            "actor", "actor_name",
        ]
        read_only_fields = fields

    def get_from_user_name(self, obj):
        if obj.from_user:
            return obj.from_user.name or obj.from_user.username
        return None

    def get_to_user_name(self, obj):
        if obj.to_user:
            return obj.to_user.name or obj.to_user.username
        return None

    def get_actor_name(self, obj):
        if obj.actor:
            return obj.actor.name or obj.actor.username
        return None


class IssueDetailSerializer(IssueListSerializer):
    github_issues = GitHubIssueBriefSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    assignments = IssueAssignmentSerializer(many=True, read_only=True)
    related_issues_resolved = serializers.SerializerMethodField()

    class Meta(IssueListSerializer.Meta):
        fields = IssueListSerializer.Meta.fields + [
            "description", "estimated_completion",
            "actual_hours", "resolved_at", "github_issues", "attachments",
            "source_meta", "settlement", "assignments",
            "related_issues", "related_issues_resolved",
        ]

    def get_related_issues_resolved(self, obj):
        """把 JSON 里的 id 拉成完整摘要 (title/status/priority); orphan id 丢弃。
        一次 in-bulk 查询, N 个 id 一个 SQL, detail 页面只渲一次完全可接受。
        """
        entries = obj.related_issues or []
        if not entries:
            return []
        ids = []
        meta_by_id: dict[int, dict] = {}
        for e in entries:
            try:
                rid = int(e.get("id"))
            except (TypeError, ValueError):
                continue
            ids.append(rid)
            meta_by_id[rid] = e
        if not ids:
            return []
        rows = (
            Issue.objects.filter(id__in=ids)
            .values("id", "title", "status", "priority")
        )
        by_id = {r["id"]: r for r in rows}
        out = []
        for e in entries:
            try:
                rid = int(e.get("id"))
            except (TypeError, ValueError):
                continue
            row = by_id.get(rid)
            if not row:
                continue  # orphan, 静默跳过
            out.append({
                **row,
                "kind": e.get("kind") or "manual",
                "reason": e.get("reason") or "",
                "added_at": e.get("added_at") or "",
            })
        return out


class IssueCreateUpdateSerializer(serializers.ModelSerializer):
    helpers = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.all(), required=False,
    )
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, write_only=True, default=list,
    )
    # AI wizard 的 dup-hint 命中时, 客户端可把候选 id 列表 + reason 直接传过来,
    # 创建后落到 related_issues 字段, kind="ai_dup"
    ai_related = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True, default=list,
    )

    class Meta:
        model = Issue
        fields = [
            "id", "project", "repo", "title", "description", "priority", "status",
            "labels", "assignee", "helpers", "reporter", "remark", "estimated_completion",
            "estimated_hours", "actual_hours", "cause", "solution", "attachment_ids",
            "source", "source_meta", "ai_related",
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

    def validate_source(self, value):
        if not value:
            return value
        if value not in ALLOWED_ISSUE_SOURCES:
            raise serializers.ValidationError(
                f"无效的 source: {value}. 必须是 {ALLOWED_ISSUE_SOURCES} 之一"
            )
        return value

    def validate_source_meta(self, value):
        if not value:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("source_meta 必须是对象")
        size = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        if size > SOURCE_META_MAX_BYTES:
            raise serializers.ValidationError(
                f"source_meta 过大（{size} 字节，上限 {SOURCE_META_MAX_BYTES}）"
            )
        return value

    def validate(self, attrs):
        # repo 必须属于 issue 所在项目的关联仓库列表; 前端只让选项目内仓库,
        # 这里防 UI 绕过. PATCH 时若只改其一, 缺失字段回退到实例当前值
        repo = attrs.get("repo", getattr(self.instance, "repo", None))
        project = attrs.get("project", getattr(self.instance, "project", None))
        if repo and project and not project.repos.filter(pk=repo.pk).exists():
            raise serializers.ValidationError({"repo": "所选仓库不属于该项目"})
        return attrs

    def _user_can_edit_estimated_hours(self) -> bool:
        user = self.context["request"].user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.groups.filter(name="管理员").exists()

    @transaction.atomic
    def create(self, validated_data):
        from .services import create_issue
        helpers = validated_data.pop("helpers", [])
        attachment_ids = validated_data.pop("attachment_ids", [])
        ai_related = validated_data.pop("ai_related", []) or []
        # 非管理员创建时忽略客户端传入的 estimated_hours,使用模型默认值 (4h)
        if "estimated_hours" in validated_data and not self._user_can_edit_estimated_hours():
            validated_data.pop("estimated_hours")

        actor = self.context["request"].user
        assignee = validated_data.pop("assignee", None)
        # 客户端传入的 status 由工作流决定,忽略
        validated_data.pop("status", None)
        project = validated_data.pop("project")
        title = validated_data.pop("title")
        description = validated_data.pop("description", "")
        priority = validated_data.pop("priority")

        issue = create_issue(
            project=project, actor=actor,
            title=title, description=description, priority=priority,
            assignee=assignee,
            **validated_data,
        )
        if helpers:
            issue.helpers.set(helpers)
        Activity.objects.create(user=actor, issue=issue, action="created")
        if attachment_ids:
            atts = Attachment.objects.filter(id__in=attachment_ids, uploaded_by=actor)
            issue.attachments.add(*atts)
        # AI wizard 命中重复检测时, 把候选记到 related_issues, kind=ai_dup
        if ai_related:
            from django.utils import timezone
            ts = timezone.now().isoformat()
            # 先做类型清洗 - 客户端可能传字符串/None, filter(id__in=) 不接受这些
            requested_ids: list[int] = []
            for r in ai_related:
                if not isinstance(r, dict):
                    continue
                try:
                    requested_ids.append(int(r.get("id")))
                except (TypeError, ValueError):
                    continue
            valid_ids = set(
                Issue.objects.filter(id__in=requested_ids)
                .values_list("id", flat=True)
            )
            cleaned = []
            seen_ids: set[int] = set()
            for r in ai_related:
                if not isinstance(r, dict):
                    continue
                try:
                    rid = int(r.get("id"))
                except (TypeError, ValueError):
                    continue
                if rid not in valid_ids or rid in seen_ids or rid == issue.id:
                    continue
                seen_ids.add(rid)
                cleaned.append({
                    "id": rid,
                    "kind": "ai_dup",
                    "reason": str(r.get("reason") or "")[:200],
                    "added_at": ts,
                })
            if cleaned:
                issue.related_issues = cleaned
                issue.save(update_fields=["related_issues", "updated_at"])
        create_mention_notifications(
            issue=issue,
            old_description="",
            new_description=issue.description,
            actor=actor,
        )
        return issue

    @transaction.atomic
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

        # 有负责人后不应停留在「待分配」;若本次未显式改状态,则置为「待确认」
        if (
            issue.assignee_id
            and issue.status == IssueStatus.UNASSIGNED.value
            and not validated_data.get("status")
        ):
            issue.status = IssueStatus.PENDING_CONFIRMATION.value
            issue.save(update_fields=["status", "updated_at"])

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


class DuplicateCheckInputSerializer(serializers.Serializer):
    project = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")


class AiDraftInputSerializer(serializers.Serializer):
    description = serializers.CharField(min_length=5, max_length=4000)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )


class AiChatInputSerializer(serializers.Serializer):
    """对话式 issue 创建入参 - 客户端持有完整消息历史, 服务端无状态转发。

    messages 每条 {role: user|assistant, content: str}, 服务端做严格校验:
      - 必须以 user 开头/结尾 (LLM 协议要求)
      - 单条 content ≤ 4000 字符
      - 数组最大 20 条 (10 轮), 服务端会再截断

    两类附件 ID:
    - attachment_ids:                本轮新上传的图片 (挂到 LLM vision 的最后一条 user 上)
    - conversation_attachment_ids:   全对话累计的所有图片 (用于 draft.description 渲染 markdown)
                                     缺省时回退到 attachment_ids
    """
    messages = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=40,   # 服务端 _truncate 再砍到 20; 这里防超大 payload
    )
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
    conversation_attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )


class AiDraftReviseInputSerializer(serializers.Serializer):
    """多轮草稿修订入参 — 客户端传当前草稿全貌 + 一句修订意见。

    current_draft 接收 8 个白名单字段, 多传的字段会被 sanitize 步骤丢弃。
    project 仍需传, 主要用于权限校验和 attachment owner 检查; LLM 不直接读项目。
    """
    current_draft = serializers.DictField(child=serializers.JSONField(), allow_empty=False)
    instruction = serializers.CharField(min_length=1, max_length=2000)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )


class IssueTransferInputSerializer(serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    reason = serializers.CharField(max_length=500)


class IssueAssignInputSerializer(serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
