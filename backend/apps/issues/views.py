from datetime import timedelta
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from apps.permissions import FullDjangoModelPermissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Count, Avg, Case, F, IntegerField, Subquery, OuterRef, Value, TextField, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import TruncDate, Coalesce
from apps.repos.models import Repo, GitHubIssue
from apps.ai.models import Analysis
from apps.ai.services import IssueAnalysisService
from apps.repos.services import GitHubSyncService
from apps.repos.serializers import GitHubIssueBriefSerializer
from .models import Issue, Activity
from .serializers import (
    IssueListSerializer, IssueDetailSerializer,
    IssueCreateUpdateSerializer, BatchUpdateSerializer,
    ActivitySerializer,
    IssueTransferInputSerializer, IssueAssignInputSerializer,
)
from .services import claim_issue, confirm_issue, transfer_issue, assign_issue, InvalidTransition

User = get_user_model()


class AiWizardThrottle(UserRateThrottle):
    """10/min per user for the AI draft SSE endpoint (each request = 3 LLM calls)."""
    scope = "ai_wizard"


class AiCheckDuplicateThrottle(UserRateThrottle):
    """30/min per user for duplicate check (lighter, single LLM call)."""
    scope = "ai_duplicate_check"


def _with_ai_fields(qs):
    """Annotate issues with cause/solution from latest completed AI analysis."""
    latest = (
        Analysis.objects.filter(
            issue_id=OuterRef('pk'),
            analysis_type='issue_code_analysis',
            status='done',
        ).order_by('-created_at')
    )
    return qs.annotate(
        ai_cause=Coalesce(
            Subquery(latest.annotate(_v=KeyTextTransform('cause', 'parsed_result')).values('_v')[:1]),
            Value(''),
            output_field=TextField(),
        ),
        ai_solution=Coalesce(
            Subquery(latest.annotate(_v=KeyTextTransform('solution', 'parsed_result')).values('_v')[:1]),
            Value(''),
            output_field=TextField(),
        ),
    )


class IssueListCreateView(generics.ListCreateAPIView):
    queryset = Issue.objects.select_related("created_by", "assignee").prefetch_related("github_issues__repo")
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["priority", "status", "assignee", "project", "helpers"]
    search_fields = ["title", "=id"]
    ordering_fields = ["created_at", "priority", "updated_at"]
    ordering = ["status_order", "priority", "-created_at"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return IssueCreateUpdateSerializer
        return IssueListSerializer

    def get_queryset(self):
        qs = _with_ai_fields(super().get_queryset()).annotate(
            status_order=Case(
                When(status="未计划", then=Value(0)),
                When(status="待分配", then=Value(1)),
                When(status="待确认", then=Value(2)),
                When(status="进行中", then=Value(3)),
                When(status="已解决", then=Value(4)),
                When(status="已发布", then=Value(5)),
                When(status="已关闭", then=Value(6)),
                default=Value(7),
                output_field=IntegerField(),
            ),
        )
        labels = self.request.query_params.get("labels")
        if labels:
            qs = qs.filter(labels__contains=[labels])
        exclude_statuses = self.request.query_params.get("exclude_statuses")
        if exclude_statuses:
            qs = qs.exclude(status__in=exclude_statuses.split(","))
        return qs


class IssueDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Issue.objects.select_related("created_by", "assignee").prefetch_related("attachments")
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]

    def get_queryset(self):
        return _with_ai_fields(super().get_queryset())

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return IssueCreateUpdateSerializer
        return IssueDetailSerializer

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["is_deleted", "deleted_at"])


class BatchUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BatchUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        issues = Issue.objects.filter(id__in=data["ids"])
        count = issues.count()

        if data["action"] == "assign":
            user = User.objects.get(id=data["value"])
            issues.update(assignee=user)
        elif data["action"] == "set_priority":
            issues.update(priority=data["value"])
        elif data["action"] == "set_status":
            issues.update(status=data["value"])
        elif data["action"] == "delete":
            issues.update(is_deleted=True, deleted_at=timezone.now())

        return Response({"updated": count})


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        prev_week_start = week_start - timedelta(days=7)
        return Response({
            "total": Issue.objects.count(),
            # 本周新增数量（用于"总数"卡片的对比文案）
            "total_added_this_week": Issue.objects.filter(created_at__gte=week_start).count(),
            # 待分配 + 待确认 视作"待处理"统计口径
            "pending": Issue.objects.filter(status__in=["待分配", "待确认"]).count(),
            "pending_yesterday": Issue.objects.filter(
                status__in=["待分配", "待确认"], created_at__lt=today_start
            ).count(),
            "in_progress": Issue.objects.filter(status="进行中").count(),
            "resolved_this_week": Issue.objects.filter(resolved_at__gte=week_start).count(),
            # 上一周（周一至周日）解决数量，用于计算同比
            "resolved_prev_week": Issue.objects.filter(
                resolved_at__gte=prev_week_start, resolved_at__lt=week_start
            ).count(),
        })


class DashboardTrendsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        start = today - timedelta(days=29)
        dates = [start + timedelta(days=i) for i in range(30)]

        created_counts = dict(
            Issue.objects.filter(created_at__date__gte=start)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .values_list("date", "count")
        )
        resolved_counts = dict(
            Issue.objects.filter(resolved_at__date__gte=start)
            .annotate(date=TruncDate("resolved_at"))
            .values("date")
            .annotate(count=Count("id"))
            .values_list("date", "count")
        )

        return Response([
            {
                "date": d.isoformat(),
                "created": created_counts.get(d, 0),
                "resolved": resolved_counts.get(d, 0),
            }
            for d in dates
        ])


class DashboardPriorityDistributionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = (
            Issue.objects.values("priority")
            .annotate(count=Count("id"))
            .order_by("priority")
        )
        return Response(list(data))


class DashboardLeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        data = (
            Issue.objects.filter(status="已解决", resolved_at__gte=month_start)
            .values("assignee")
            .annotate(
                monthly_resolved_count=Count("id"),
                avg_resolution_hours=Avg(F("resolved_at") - F("created_at")),
            )
            .order_by("-monthly_resolved_count")[:5]
        )
        result = []
        for entry in data:
            user = User.objects.filter(id=entry["assignee"]).first()
            if user:
                avg_hours = entry["avg_resolution_hours"]
                if avg_hours:
                    avg_hours = round(avg_hours.total_seconds() / 3600, 1)
                result.append({
                    "user_id": str(user.id),
                    "user_name": user.name,
                    "monthly_resolved_count": entry["monthly_resolved_count"],
                    "avg_resolution_hours": avg_hours,
                })
        return Response(result)


class DashboardRecentActivityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        activities = Activity.objects.select_related("user", "issue")[:20]
        return Response(ActivitySerializer(activities, many=True).data)


class IssueGitHubCreateView(APIView):
    """根据 DevTrack Issue 在 GitHub 上创建 issue 并自动关联。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        repo_id = request.data.get("repo")
        if not repo_id:
            return Response({"detail": "请指定仓库"}, status=status.HTTP_400_BAD_REQUEST)

        repo = Repo.objects.filter(pk=repo_id).first()
        if not repo or not repo.github_token:
            return Response({"detail": "仓库不存在或未配置 Token"}, status=status.HTTP_400_BAD_REQUEST)

        body = f"来自 DevTrack #{issue.pk}: {issue.title}\n\n{issue.description}"
        try:
            svc = GitHubSyncService()
            gh_issue = svc.create_issue(repo, issue.title, body)
        except Exception as e:
            return Response({"detail": f"GitHub 创建失败: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        issue.github_issues.add(gh_issue)
        return Response(GitHubIssueBriefSerializer(gh_issue).data, status=status.HTTP_201_CREATED)


class IssueGitHubLinkView(APIView):
    """关联/解除关联已有的 GitHub Issue。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        gh_ids = request.data.get("github_issue_ids", [])
        gh_issues = GitHubIssue.objects.filter(id__in=gh_ids)
        issue.github_issues.add(*gh_issues)
        return Response({"linked": len(gh_issues)})

    def delete(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        gh_ids = request.data.get("github_issue_ids", [])
        gh_issues = GitHubIssue.objects.filter(id__in=gh_ids)
        issue.github_issues.remove(*gh_issues)
        return Response({"unlinked": len(gh_issues)})


class IssueAIAnalyzeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = Issue.objects.select_related("repo").filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        if not issue.repo:
            return Response({"detail": "请先关联仓库"}, status=status.HTTP_400_BAD_REQUEST)
        if issue.repo.clone_status != "cloned":
            return Response({"detail": "请先同步代码"}, status=status.HTTP_400_BAD_REQUEST)

        svc = IssueAnalysisService()
        existing = svc.get_running_analysis(issue)
        if existing:
            return Response(
                {"analysis_id": existing.id, "status": "running"},
                status=status.HTTP_409_CONFLICT,
            )

        analysis = svc.analyze_async(issue, triggered_by="manual", user=request.user)
        return Response(
            {"analysis_id": analysis.id, "status": "running"},
            status=status.HTTP_202_ACCEPTED,
        )


class IssueAIStatusView(APIView):
    """查询 Issue 是否有正在运行的 AI 分析。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        svc = IssueAnalysisService()
        running = svc.get_running_analysis(issue)
        if running:
            return Response({"analysis_id": running.id, "status": "running"})
        return Response({"analysis_id": None, "status": "idle"})


class IssueAnalysesView(APIView):
    """GET /api/issues/{id}/analyses/ — 返回该 Issue 的 AI 分析历史"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        analyses = (
            Analysis.objects
            .filter(issue=issue, analysis_type="issue_code_analysis")
            .select_related("triggered_by_user")
            .order_by("-created_at")
        )

        data = []
        for a in analyses:
            results = None
            if a.status == Analysis.Status.DONE and a.parsed_result:
                pr = a.parsed_result
                if "target_field" in pr:
                    results = {pr["target_field"]: pr.get("content", "")}
                else:
                    results = {k: v for k, v in pr.items()
                              if k in ("cause", "solution", "remark") and v}

            data.append({
                "id": a.id,
                "status": a.status,
                "triggered_by": a.triggered_by,
                "triggered_by_user": (
                    a.triggered_by_user.name or a.triggered_by_user.username
                ) if a.triggered_by_user else None,
                "created_at": a.created_at.isoformat(),
                "error_message": a.error_message if a.status == Analysis.Status.FAILED else None,
                "results": results,
            })

        return Response(data)


class IssueAttachmentsView(APIView):
    """POST: link attachment to issue. DELETE: unlink (does NOT delete the file)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from apps.tools.models import Attachment
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=404)
        attachment_id = request.data.get("attachment_id")
        attachment = Attachment.objects.filter(pk=attachment_id).first()
        if not attachment:
            return Response({"detail": "附件不存在"}, status=404)
        issue.attachments.add(attachment)
        return Response(status=204)

    def delete(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=404)
        attachment_id = request.data.get("attachment_id")
        attachment = issue.attachments.filter(pk=attachment_id).first()
        if not attachment:
            return Response({"detail": "附件不存在"}, status=404)
        issue.attachments.remove(attachment)
        return Response(status=204)


FIELD_LABELS = {
    "title": "标题",
    "description": "描述",
    "priority": "优先级",
    "status": "状态",
    "labels": "标签",
    "assignee": "负责人",
    "reporter": "提出人",
    "remark": "备注",
    "estimated_completion": "预计完成",
    "estimated_hours": "预计工时",
    "actual_hours": "实际工时",
    "cause": "原因分析",
    "solution": "解决办法",
    "resolved_at": "解决时间",
    "repo": "关联仓库",
    "project": "项目",
    "is_deleted": "已删除",
    "deleted_at": "删除时间",
    "source": "来源",
    "source_meta": "来源元数据",
    "settlement": "结算快照",
    "updated_by": "更新人",
    "helpers": "协助人",
    "attachments": "附件",
    "github_issues": "关联 GitHub Issues",
}


def _is_manager(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name="管理员").exists()


def _format_value(field_name, value):
    if value is None or value == "":
        return None
    if field_name in ("description", "remark", "cause", "solution"):
        text = str(value)
        return text if len(text) <= 80 else text[:77] + "…"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def _resolve_fk_display(field_name, value):
    if value is None:
        return None
    if field_name in ("assignee", "updated_by", "created_by"):
        u = User.objects.filter(pk=value).first()
        return (u.name or u.username) if u else f"#{value}"
    if field_name == "repo":
        r = Repo.objects.filter(pk=value).first()
        return r.full_name if r else f"#{value}"
    if field_name == "project":
        from apps.projects.models import Project
        p = Project.objects.filter(pk=value).first()
        return p.name if p else f"#{value}"
    return value


class IssueHistoryView(APIView):
    """GET /api/issues/{id}/history/ — 字段更新历史 (仅管理员)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not _is_manager(request.user):
            return Response({"detail": "仅管理员可查看历史"}, status=status.HTTP_403_FORBIDDEN)

        issue = Issue.all_objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        records = list(
            issue.history.select_related("history_user").order_by("history_date")
        )

        result = []
        prev = None
        for rec in records:
            user = rec.history_user
            entry = {
                "id": rec.history_id,
                "type": rec.history_type,
                "date": rec.history_date.isoformat(),
                "user": (user.name or user.username) if user else None,
                "changes": [],
            }
            if prev is None:
                entry["changes"].append({
                    "field": "_created",
                    "label": "创建",
                    "before": None,
                    "after": None,
                })
            else:
                try:
                    delta = rec.diff_against(prev)
                    for change in delta.changes:
                        fname = change.field
                        if fname in ("updated_at", "id"):
                            continue
                        old_v = _resolve_fk_display(fname, change.old)
                        new_v = _resolve_fk_display(fname, change.new)
                        entry["changes"].append({
                            "field": fname,
                            "label": FIELD_LABELS.get(fname, fname),
                            "before": _format_value(fname, old_v),
                            "after": _format_value(fname, new_v),
                        })
                except Exception:
                    pass

            if entry["changes"] or prev is None:
                result.append(entry)
            prev = rec

        result.reverse()
        return Response(result)


class IssueCloseWithGitHubView(APIView):
    """关闭 DevTrack Issue，同时关闭关联的 GitHub Issues。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)

        old_status = issue.status
        issue.status = "已关闭"
        issue.save(update_fields=["status"])

        Activity.objects.create(
            user=request.user, issue=issue, action="closed",
            detail=f"状态从 {old_status} 改为 已关闭",
        )

        # 关闭关联的 GitHub Issues
        svc = GitHubSyncService()
        errors = []
        for gh_issue in issue.github_issues.filter(state=GitHubIssue.STATE_OPEN):
            try:
                svc.close_issue(gh_issue)
            except Exception as e:
                errors.append(f"#{gh_issue.github_id}: {e}")

        result = {"detail": "已关闭", "github_closed": issue.github_issues.count() - len(errors)}
        if errors:
            result["github_errors"] = errors
        return Response(result)


class IssueAiDraftView(APIView):
    """POST /api/issues/ai-draft/ — SSE stream that drafts an Issue from
    a free-form bug description via the 3-stage AI wizard pipeline.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [AiWizardThrottle]

    def perform_content_negotiation(self, request, force=False):
        # We return StreamingHttpResponse directly for success and let any
        # error Response use JSONRenderer. Bypass DRF's Accept-header check
        # since clients send Accept: text/event-stream which won't match
        # the default registered renderers (JSONRenderer/BrowsableAPIRenderer).
        from rest_framework.renderers import JSONRenderer
        return (JSONRenderer(), "application/json")

    def post(self, request):
        from django.http import StreamingHttpResponse
        import json as _json
        from rest_framework.exceptions import PermissionDenied
        from .serializers import AiDraftInputSerializer
        from .services_ai_wizard import AiWizardService

        # AI 草稿仅服务于创建 Issue 的用户——无创建权限的用户无需调用 LLM
        if not request.user.has_perm("issues.add_issue"):
            raise PermissionDenied("无权创建问题")

        serializer = AiDraftInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        request_user = request.user
        def event_stream():
            svc = AiWizardService()
            try:
                for event_name, payload in svc.stream_draft(
                    description=data["description"],
                    project_id=data["project"].id,
                    attachment_ids=[str(x) for x in (data.get("attachment_ids") or [])],
                    user=request_user,
                ):
                    if event_name == "_heartbeat":
                        # SSE 注释行;客户端会忽略,但 yield 在客户端断开后
                        # 会抛 BrokenPipeError 让生成器停止,避免触发下一次 LLM 调用
                        yield ": heartbeat\n\n"
                    else:
                        yield f"event: {event_name}\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # 客户端在流中途断开,停止生成器避免空耗 LLM 调用
                import logging
                logging.getLogger(__name__).info("SSE client disconnected; stopping draft stream")
                return

        resp = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        resp["X-Accel-Buffering"] = "no"
        resp["Cache-Control"] = "no-cache"
        return resp


def _get_issue_or_404(pk):
    return Issue.objects.filter(pk=pk).first()


def _serialize_issue(issue, request):
    return IssueListSerializer(issue, context={"request": request}).data


class IssueClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = _get_issue_or_404(pk)
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        try:
            claim_issue(issue, actor=request.user)
        except InvalidTransition as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)
        return Response(_serialize_issue(issue, request))


class IssueConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = _get_issue_or_404(pk)
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        try:
            confirm_issue(issue, actor=request.user)
        except InvalidTransition as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)
        return Response(_serialize_issue(issue, request))


class IssueTransferView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = _get_issue_or_404(pk)
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        ser = IssueTransferInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            transfer_issue(
                issue, actor=request.user,
                to_user=ser.validated_data["to_user"],
                reason=ser.validated_data["reason"],
            )
        except InvalidTransition as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_issue(issue, request))


class IssueAssignView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = _get_issue_or_404(pk)
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        ser = IssueAssignInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            assign_issue(
                issue, actor=request.user,
                to_user=ser.validated_data["to_user"],
            )
        except InvalidTransition as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)
        return Response(_serialize_issue(issue, request))


class IssueCheckDuplicateView(APIView):
    """POST /api/issues/check-duplicate/ — AI-driven near-duplicate detection.

    Used by the create-issue modal on title/description blur. Returns up to
    five open issues in the same project that the LLM judged similar. Silent
    on configuration or LLM failures: always returns 200 with possibly empty
    candidates so the modal continues to function.
    """
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    throttle_classes = [AiCheckDuplicateThrottle]
    queryset = Issue.objects.none()  # FullDjangoModelPermissions 需要 queryset 确定模型

    def post(self, request):
        from .serializers import DuplicateCheckInputSerializer
        from .services import check_duplicates

        if not request.user.has_perm("issues.view_issue"):
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = DuplicateCheckInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        candidates = check_duplicates(
            project_id=data["project"],
            title=data["title"],
            description=data["description"],
        )
        return Response({"candidates": candidates})
