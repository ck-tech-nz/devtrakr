"""
提升计划 API 视图
"""
from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.permissions import FullDjangoModelPermissions
from apps.tools.storage import upload_image
from .models import ImprovementPlan, ActionItem, ActionItemComment, KPIScoringConfig
from .plan_serializers import (
    PlanListSerializer, PlanDetailSerializer,
    ActionItemSerializer, ActionItemCommentSerializer,
)


def _plan_detail_qs():
    """带预取的计划查询集，供所有返回 PlanDetailSerializer 的视图复用，
    避免 action_items 的 reviewed_by / comments.author / carried_to 触发 N+1。"""
    return (
        ImprovementPlan.objects.select_related("user", "reviewed_by")
        .prefetch_related(
            Prefetch(
                "action_items",
                queryset=ActionItem.objects.select_related("reviewed_by")
                .prefetch_related("comments__author", "carried_to"),
            )
        )
    )


class PlanListView(APIView):
    """GET /api/kpi/plans/ — 管理员查看团队计划列表。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def get(self, request):
        period = request.query_params.get("period", timezone.now().strftime("%Y-%m"))
        plans = (
            ImprovementPlan.objects.filter(period=period)
            .select_related("user", "reviewed_by")
            .prefetch_related("action_items")
            .order_by("user__name")
        )
        serializer = PlanListSerializer(plans, many=True)
        return Response(serializer.data)


class MyPlanView(APIView):
    """GET /api/kpi/plans/me/ — 员工查看自己的计划。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        current_period = now.strftime("%Y-%m")

        # 指定月份：返回该月计划详情（用于"过往月份"展开查看自己的任务）
        period = request.query_params.get("period")
        if period and period != current_period:
            plan = (
                _plan_detail_qs()
                .filter(
                    user=request.user,
                    period=period,
                    status__in=["published", "archived"],
                )
                .first()
            )
            return Response({"plan": PlanDetailSerializer(plan).data if plan else None})

        current = (
            _plan_detail_qs()
            .filter(
                user=request.user,
                period=current_period,
                status__in=["published", "archived"],
            )
            .first()
        )

        # 历史：除当月外，所有已发布/已归档的月份（含计数，详情按需用 ?period= 拉取）
        history = (
            ImprovementPlan.objects.filter(
                user=request.user,
                status__in=["published", "archived"],
            )
            .exclude(period=current_period)
            .prefetch_related("action_items")
            .order_by("-period")[:12]
        )

        return Response({
            "current": PlanDetailSerializer(current).data if current else None,
            "history": PlanListSerializer(history, many=True).data,
        })


class PlanDetailView(APIView):
    """GET /api/kpi/plans/{id}/ — 计划详情。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def get(self, request, pk):
        try:
            plan = _plan_detail_qs().get(pk=pk)
        except ImprovementPlan.DoesNotExist:
            return Response({"detail": "计划不存在"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PlanDetailSerializer(plan, context={"manager": True}).data)


class PlanPublishView(APIView):
    """POST /api/kpi/plans/{id}/publish/ — 发布计划。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def post(self, request, pk):
        try:
            plan = _plan_detail_qs().get(pk=pk)
        except ImprovementPlan.DoesNotExist:
            return Response({"detail": "计划不存在"}, status=status.HTTP_404_NOT_FOUND)
        if plan.status != ImprovementPlan.Status.DRAFT:
            return Response({"detail": "只能发布草案状态的计划"}, status=status.HTTP_400_BAD_REQUEST)
        plan.status = ImprovementPlan.Status.PUBLISHED
        plan.reviewed_by = request.user
        plan.published_at = timezone.now()
        plan.save(update_fields=["status", "reviewed_by", "published_at", "updated_at"])
        return Response(PlanDetailSerializer(plan, context={"manager": True}).data)


class PlanArchiveView(APIView):
    """POST /api/kpi/plans/{id}/archive/ — 归档计划。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def post(self, request, pk):
        try:
            plan = _plan_detail_qs().get(pk=pk)
        except ImprovementPlan.DoesNotExist:
            return Response({"detail": "计划不存在"}, status=status.HTTP_404_NOT_FOUND)
        if plan.status != ImprovementPlan.Status.PUBLISHED:
            return Response({"detail": "只能归档已发布的计划"}, status=status.HTTP_400_BAD_REQUEST)
        plan.status = ImprovementPlan.Status.ARCHIVED
        plan.archived_at = timezone.now()
        plan.save(update_fields=["status", "archived_at", "updated_at"])
        return Response(PlanDetailSerializer(plan, context={"manager": True}).data)


class PlanGenerateView(APIView):
    """POST /api/kpi/plans/generate/ — 为指定用户生成 AI 草案。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def post(self, request):
        from django.contrib.auth import get_user_model
        from .plan_generator import generate_action_items
        from .services import KPIService

        User = get_user_model()
        svc = KPIService()
        today = timezone.now().date()
        month_start = today.replace(day=1)
        period = today.strftime("%Y-%m")

        user_id = request.data.get("user_id")

        # 确定目标用户列表
        if user_id:
            try:
                target_users = [User.objects.get(pk=user_id)]
            except User.DoesNotExist:
                return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)
        else:
            # 批量模式：为所有活跃用户生成
            target_users = list(svc._get_target_users())

        # 预计算团队均值（只算一次）
        all_users = svc._get_target_users()
        team_scores = [svc.compute_for_user(u, month_start, today)["scores"] for u in all_users]
        dims = ("efficiency", "output", "quality", "capability")
        team_avgs = {}
        if team_scores:
            for d in dims:
                vals = [s.get(d, 0) for s in team_scores]
                team_avgs[d] = round(sum(vals) / len(vals), 1)

        created = 0
        for target_user in target_users:
            if ImprovementPlan.objects.filter(user=target_user, period=period).exists():
                continue

            kpi_data = svc.compute_for_user(target_user, month_start, today)
            items_data = generate_action_items(
                kpi_data["scores"], kpi_data["issue_metrics"],
                kpi_data["commit_metrics"], team_avgs,
            )

            plan = ImprovementPlan.objects.create(
                user=target_user, period=period,
                status=ImprovementPlan.Status.DRAFT,
                source_kpi_scores=kpi_data["scores"],
            )
            for i, item_data in enumerate(items_data):
                ActionItem.objects.create(plan=plan, sort_order=i, **item_data)
            created += 1

        if user_id and created == 1:
            plan = _plan_detail_qs().filter(user_id=user_id, period=period).first()
            return Response(PlanDetailSerializer(plan, context={"manager": True}).data, status=status.HTTP_201_CREATED)

        return Response({"created": created, "period": period}, status=status.HTTP_201_CREATED)


class PlanEditView(APIView):
    """PUT /api/kpi/plans/{id}/edit/ — 管理员编辑计划。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def put(self, request, pk):
        try:
            plan = _plan_detail_qs().get(pk=pk)
        except ImprovementPlan.DoesNotExist:
            return Response({"detail": "计划不存在"}, status=status.HTTP_404_NOT_FOUND)

        items_data = request.data.get("action_items", [])
        existing_ids = set(str(item.id) for item in plan.action_items.all())
        incoming_ids = set(str(item["id"]) for item in items_data if item.get("id"))

        to_delete = existing_ids - incoming_ids
        if to_delete:
            ActionItem.objects.filter(id__in=to_delete, plan=plan).delete()

        for i, item_data in enumerate(items_data):
            item_id = item_data.get("id")
            defaults = {
                "title": item_data.get("title", ""),
                "description": item_data.get("description", ""),
                "measurable_target": item_data.get("measurable_target", ""),
                "points": item_data.get("points", 10),
                "priority": item_data.get("priority", "medium"),
                "dimension": item_data.get("dimension", "general"),
                "sort_order": i,
            }
            # 截止日期：仅当传入时更新（避免覆盖已有值为 None）
            if "due_date" in item_data:
                defaults["due_date"] = item_data.get("due_date") or None
            # 本任务点评维度：仅当传入合法列表时更新
            dims = item_data.get("review_dimensions")
            if isinstance(dims, list) and all(isinstance(d, dict) and "key" in d for d in dims):
                defaults["review_dimensions"] = dims
            if item_id and str(item_id) in existing_ids:
                ActionItem.objects.filter(id=item_id, plan=plan).update(**defaults)
            else:
                ActionItem.objects.create(plan=plan, source=ActionItem.Source.MANAGER, **defaults)

        plan = _plan_detail_qs().get(pk=pk)  # 重取并预取，避免响应渲染时 N+1
        return Response(PlanDetailSerializer(plan, context={"manager": True}).data)


class ActionItemStatusView(APIView):
    """POST /api/kpi/action-items/{id}/status/ — 员工更新状态。"""
    permission_classes = [IsAuthenticated]

    EMPLOYEE_TRANSITIONS = {
        "pending": ["in_progress"],
        "in_progress": ["submitted"],
    }

    def post(self, request, pk):
        try:
            item = ActionItem.objects.select_related("plan").get(pk=pk)
        except ActionItem.DoesNotExist:
            return Response({"detail": "行动项不存在"}, status=status.HTTP_404_NOT_FOUND)
        if item.plan.user != request.user:
            return Response({"detail": "只能操作自己的行动项"}, status=status.HTTP_403_FORBIDDEN)
        new_status = request.data.get("status")
        allowed = self.EMPLOYEE_TRANSITIONS.get(item.status, [])
        if new_status not in allowed:
            return Response(
                {"detail": f"不允许从 {item.status} 变更为 {new_status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        update_fields = ["status", "updated_at"]

        # 开始执行时强制"立计划"——把"被派的任务"变成"我承诺的任务"
        if new_status == ActionItem.Status.IN_PROGRESS:
            start_plan = (request.data.get("start_plan") or "").strip()
            if not start_plan:
                return Response({"detail": "开始执行前请填写「我打算怎么做」"},
                                status=status.HTTP_400_BAD_REQUEST)
            self_eta = request.data.get("self_eta")
            if not self_eta:
                return Response({"detail": "请填写预计完成日期"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                ActionItem._meta.get_field("self_eta").to_python(self_eta)
            except (DjangoValidationError, ValueError, TypeError):
                return Response({"detail": "预计完成日期格式须为 YYYY-MM-DD"},
                                status=status.HTTP_400_BAD_REQUEST)
            item.start_plan = start_plan
            item.self_eta = self_eta
            update_fields += ["start_plan", "self_eta"]

        # 提交完成时强制"结构化复盘 + 自评"——制造认知摩擦，驱动自我觉察
        if new_status == ActionItem.Status.SUBMITTED:
            self_assessment = (request.data.get("self_assessment") or "").strip()
            if not self_assessment:
                return Response({"detail": "提交需填写复盘（你的思考与判断）"},
                                status=status.HTTP_400_BAD_REQUEST)
            self_scores = request.data.get("self_scores") or {}
            if not isinstance(self_scores, dict):
                return Response({"detail": "self_scores 须为对象"}, status=status.HTTP_400_BAD_REQUEST)
            valid_keys = {d["key"] for d in (item.review_dimensions or []) if isinstance(d, dict) and "key" in d}
            for k, v in self_scores.items():
                if k not in valid_keys:
                    return Response({"detail": f"自评维度 {k} 不属于本任务"}, status=status.HTTP_400_BAD_REQUEST)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not (1 <= v <= 5):
                    return Response({"detail": f"自评维度 {k} 须为 1-5"}, status=status.HTTP_400_BAD_REQUEST)
            if valid_keys and set(self_scores.keys()) != valid_keys:
                return Response({"detail": "请对每个维度完成自评"}, status=status.HTTP_400_BAD_REQUEST)
            item.self_scores = self_scores
            item.self_assessment = self_assessment
            item.self_assessed_at = timezone.now()
            update_fields += ["self_scores", "self_assessment", "self_assessed_at"]

        item.status = new_status
        item.save(update_fields=update_fields)

        # 可选的"成果说明" → 落成一条评论（支持线上/线下反馈）
        note = (request.data.get("note") or "").strip()
        if note:
            attachment_url = attachment_key = ""
            if "attachment" in request.FILES:
                attachment_url, attachment_key = upload_image(request.FILES["attachment"])
            ActionItemComment.objects.create(
                action_item=item, author=request.user, content=note,
                attachment_url=attachment_url, attachment_key=attachment_key,
            )

        return Response(ActionItemSerializer(item).data)


class ActionItemVerifyView(APIView):
    """POST /api/kpi/action-items/{id}/verify/ — 管理员验收。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def post(self, request, pk):
        try:
            item = ActionItem.objects.get(pk=pk)
        except ActionItem.DoesNotExist:
            return Response({"detail": "行动项不存在"}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        if new_status not in ("verified", "not_achieved"):
            return Response({"detail": "状态必须为 verified 或 not_achieved"},
                            status=status.HTTP_400_BAD_REQUEST)

        # 状态机：仅可验收员工已提交（或此前已判过、用于重开/改判）的任务，
        # 禁止对 pending / in_progress（员工尚未提交）的任务直接打分验收
        if item.status in (ActionItem.Status.PENDING, ActionItem.Status.IN_PROGRESS):
            return Response({"detail": "该任务尚未提交，无法验收"},
                            status=status.HTTP_400_BAD_REQUEST)

        dims = request.data.get("review_dimensions")
        if dims is None:
            dims = item.review_dimensions or []
        if not isinstance(dims, list) or not all(isinstance(d, dict) and "key" in d for d in dims):
            return Response({"detail": "review_dimensions 格式不正确"}, status=status.HTTP_400_BAD_REQUEST)

        update_fields = ["status", "scores", "review_comment", "review_dimensions",
                         "reviewed_by", "reviewed_at", "updated_at"]

        if new_status == "verified":
            review_comment = (request.data.get("review_comment") or "").strip()
            if not review_comment:
                return Response({"detail": "验收需填写总评"}, status=status.HTTP_400_BAD_REQUEST)
            scores = request.data.get("scores") or {}
            if not isinstance(scores, dict):
                return Response({"detail": "scores 须为对象"}, status=status.HTTP_400_BAD_REQUEST)
            valid_keys = {d["key"] for d in dims}
            for k, v in scores.items():
                if k not in valid_keys:
                    return Response({"detail": f"维度 {k} 不属于本任务"}, status=status.HTTP_400_BAD_REQUEST)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not (1 <= v <= 5):
                    return Response({"detail": f"维度 {k} 评分须为 1-5"}, status=status.HTTP_400_BAD_REQUEST)
            item.scores = scores
            item.review_comment = review_comment
            item.review_dimensions = dims
            # 由「未达成」改判为达成时，清除归因，避免残留陈旧数据
            if item.not_achieved_reason:
                item.not_achieved_reason = ""
                update_fields.append("not_achieved_reason")
        else:
            # 未达成：强制原因（总评）+ 归因，便于诊断、问责与后续干预
            review_comment = (request.data.get("review_comment") or "").strip()
            if not review_comment:
                return Response({"detail": "标记未达成需填写原因"}, status=status.HTTP_400_BAD_REQUEST)
            reason = request.data.get("not_achieved_reason")
            valid_reasons = {c[0] for c in ActionItem.NotAchievedReason.choices}
            if reason not in valid_reasons:
                return Response({"detail": "请选择未达成归因"}, status=status.HTTP_400_BAD_REQUEST)
            item.review_comment = review_comment
            item.review_dimensions = dims
            item.not_achieved_reason = reason
            update_fields.append("not_achieved_reason")

        item.status = new_status
        item.reviewed_by = request.user
        item.reviewed_at = timezone.now()
        item.save(update_fields=update_fields)

        # 未达成的下一步：顺延重做 → 在下月计划克隆一条新任务（保留溯源）
        # 幂等：已顺延过则复用既有克隆，避免重复点击/重试产生重复任务
        carried = None
        if new_status == "not_achieved" and request.data.get("next_action") == "carry_over":
            carried = item.carried_to.first() or self._carry_over(item, request.user)

        data = ActionItemSerializer(item).data
        if carried is not None:
            data["carried_to_period"] = carried.plan.period
        return Response(data)

    @staticmethod
    def _carry_over(item, user):
        plan = item.plan
        y, m = (int(x) for x in plan.period.split("-"))
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        next_period = f"{ny}-{nm:02d}"
        next_plan, _ = ImprovementPlan.objects.get_or_create(
            user=plan.user, period=next_period,
            defaults={"status": ImprovementPlan.Status.PUBLISHED,
                      "source_kpi_scores": {}, "created_by": user},
        )
        if next_plan.status != ImprovementPlan.Status.PUBLISHED:
            next_plan.status = ImprovementPlan.Status.PUBLISHED
            if not next_plan.published_at:
                next_plan.published_at = timezone.now()
            next_plan.save(update_fields=["status", "published_at", "updated_at"])
        last = next_plan.action_items.order_by("-sort_order").first()
        return ActionItem.objects.create(
            plan=next_plan,
            source=ActionItem.Source.MANAGER,
            status=ActionItem.Status.PENDING,
            title=item.title,
            description=item.description,
            measurable_target=item.measurable_target,
            priority=item.priority,
            dimension=item.dimension,
            review_dimensions=item.review_dimensions,
            carried_from=item,
            sort_order=(last.sort_order + 1) if last else 0,
        )


class ActionItemAcknowledgeView(APIView):
    """POST /api/kpi/action-items/{id}/acknowledge/ — 员工确认点评并填写改进措施（闭环）。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            item = ActionItem.objects.select_related("plan").get(pk=pk)
        except ActionItem.DoesNotExist:
            return Response({"detail": "行动项不存在"}, status=status.HTTP_404_NOT_FOUND)
        if item.plan.user != request.user:
            return Response({"detail": "只能确认自己的任务"}, status=status.HTTP_403_FORBIDDEN)
        if item.status not in ("verified", "not_achieved"):
            return Response({"detail": "仅可在已验收/未达成后确认"}, status=status.HTTP_400_BAD_REQUEST)
        improve_note = (request.data.get("improve_note") or "").strip()
        if item.status == "not_achieved" and not improve_note:
            return Response({"detail": "未达成需填写改进措施"}, status=status.HTTP_400_BAD_REQUEST)
        item.improve_note = improve_note
        item.acknowledged = True
        item.acknowledged_at = timezone.now()
        item.save(update_fields=["improve_note", "acknowledged", "acknowledged_at", "updated_at"])
        return Response(ActionItemSerializer(item).data)


class TaskDispatchView(APIView):
    """POST /api/kpi/tasks/dispatch/ — 管理者即时派发任务（月度自动归桶、直接发布）。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def post(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user_id = request.data.get("user_id")
        title = (request.data.get("title") or "").strip()
        due_date = request.data.get("due_date")
        if not user_id or not title or not due_date:
            return Response({"detail": "user_id、title、due_date 均为必填"},
                            status=status.HTTP_400_BAD_REQUEST)

        # 校验 due_date 格式（避免畸形输入直达 ORM 触发 500）
        try:
            ActionItem._meta.get_field("due_date").to_python(due_date)
        except (DjangoValidationError, ValueError, TypeError):
            return Response({"detail": "due_date 格式须为 YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        period = timezone.now().strftime("%Y-%m")
        plan, _created = ImprovementPlan.objects.get_or_create(
            user=target, period=period,
            defaults={"status": ImprovementPlan.Status.PUBLISHED,
                      "source_kpi_scores": {}, "created_by": request.user},
        )
        if plan.status != ImprovementPlan.Status.PUBLISHED:
            plan.status = ImprovementPlan.Status.PUBLISHED
            if not plan.published_at:
                plan.published_at = timezone.now()
            plan.save(update_fields=["status", "published_at", "updated_at"])

        dims = request.data.get("review_dimensions")
        if not dims:
            dims = KPIScoringConfig.get_solo().review_dimensions
        if not isinstance(dims, list) or not all(isinstance(d, dict) and "key" in d for d in dims):
            return Response({"detail": "review_dimensions 格式不正确"}, status=status.HTTP_400_BAD_REQUEST)

        last = plan.action_items.order_by("-sort_order").first()
        next_order = (last.sort_order + 1) if last else 0

        item = ActionItem.objects.create(
            plan=plan,
            source=ActionItem.Source.MANAGER,
            status=ActionItem.Status.PENDING,
            title=title,
            description=request.data.get("description", ""),
            measurable_target=request.data.get("measurable_target", ""),
            priority=request.data.get("priority", ActionItem.Priority.MEDIUM),
            due_date=due_date,
            review_dimensions=dims,
            sort_order=next_order,
        )
        return Response(ActionItemSerializer(item).data, status=status.HTTP_201_CREATED)


def _fmt_scores(scores, dims):
    if not scores:
        return "—"
    labels = {d["key"]: d.get("label", d["key"]) for d in (dims or []) if isinstance(d, dict)}
    return "、".join(f"{labels.get(k, k)} {v}" for k, v in scores.items())


class PlanAISummaryView(APIView):
    """POST /api/kpi/plans/{id}/ai-summary/ — 调用 LLM 生成月度小结（仅管理者）。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def post(self, request, pk):
        import json
        from apps.ai.client import LLMClient
        from apps.ai.models import Prompt

        try:
            plan = _plan_detail_qs().get(pk=pk)
        except ImprovementPlan.DoesNotExist:
            return Response({"detail": "计划不存在"}, status=status.HTTP_404_NOT_FOUND)

        prompt = Prompt.objects.filter(slug="plan_monthly_summary", is_active=True).first()
        if prompt is None:
            return Response({"detail": "未配置月度小结 Prompt（plan_monthly_summary）"},
                            status=status.HTTP_400_BAD_REQUEST)

        items = list(plan.action_items.all())
        today = timezone.now().date()

        def _overdue(it):
            return bool(it.due_date and it.due_date < today
                        and it.status not in ("verified", "not_achieved"))

        lines = []
        for it in items:
            lines.append(
                f"- [{it.get_status_display()}] {it.title}"
                f" | 截止 {it.due_date or '—'}"
                f" | 目标: {it.measurable_target or '—'}"
                f" | 自评: {_fmt_scores(it.self_scores, it.review_dimensions)}"
                f" | 自评说明: {(it.self_assessment or '—')[:300]}"
                f" | 经理评分: {_fmt_scores(it.scores, it.review_dimensions)}"
                f" | 总评: {it.review_comment or '—'}"
            )
        ctx = {
            "user_name": plan.user.name or plan.user.username,
            "period": plan.period,
            "total": len(items),
            "in_progress": sum(1 for i in items if i.status == "in_progress"),
            "submitted": sum(1 for i in items if i.status == "submitted"),
            "done": sum(1 for i in items if i.status == "verified"),
            "overdue": sum(1 for i in items if _overdue(i)),
            "tasks": "\n".join(lines) or "（本月暂无任务）",
        }

        try:
            user_prompt = prompt.user_prompt_template.format(**ctx)
            raw = LLMClient(prompt.llm_config).complete(
                model=prompt.llm_model,
                system_prompt=prompt.system_prompt,
                user_prompt=user_prompt,
                temperature=prompt.temperature,
                timeout=60,
            )
        except KeyError as e:
            return Response({"detail": f"Prompt 模板缺少变量 {e}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"detail": "AI 调用失败，请稍后重试或检查 LLM 配置"},
                            status=status.HTTP_502_BAD_GATEWAY)

        summary = ""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                summary = (data.get("summary") or "").strip()
        except (json.JSONDecodeError, TypeError):
            summary = ""
        if not summary:
            summary = (raw or "").strip()
        summary = summary[:8000]  # 兜底上限：防止异常 LLM 返回超长文本无界落库

        plan.ai_summary = summary
        plan.ai_summary_at = timezone.now()
        plan.ai_summary_model = prompt.llm_model
        plan.save(update_fields=["ai_summary", "ai_summary_at", "ai_summary_model", "updated_at"])
        return Response(PlanDetailSerializer(plan, context={"manager": True}).data)


class PlanEvaluationView(APIView):
    """PUT /api/kpi/plans/{id}/evaluation/ — 保存 AI 小结(可编辑) 与 员工评价（仅管理者）。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def put(self, request, pk):
        try:
            plan = _plan_detail_qs().get(pk=pk)
        except ImprovementPlan.DoesNotExist:
            return Response({"detail": "计划不存在"}, status=status.HTTP_404_NOT_FOUND)

        update_fields = ["updated_at"]
        if "ai_summary" in request.data:
            plan.ai_summary = (request.data.get("ai_summary") or "").strip()
            update_fields.append("ai_summary")
        if "employee_evaluation" in request.data:
            plan.employee_evaluation = (request.data.get("employee_evaluation") or "").strip()
            update_fields.append("employee_evaluation")
        plan.save(update_fields=update_fields)
        return Response(PlanDetailSerializer(plan, context={"manager": True}).data)


class ReviewDimensionsView(APIView):
    """GET /api/kpi/review-dimensions/ — 点评维度库（任何已登录用户可读，仅维度，不含奖赏公式）。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"review_dimensions": KPIScoringConfig.get_solo().review_dimensions})


class ActionItemCommentListView(APIView):
    """GET/POST /api/kpi/action-items/{id}/comments/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        comments = ActionItemComment.objects.filter(action_item_id=pk).select_related("author")
        serializer = ActionItemCommentSerializer(comments, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        try:
            item = ActionItem.objects.select_related("plan").get(pk=pk)
        except ActionItem.DoesNotExist:
            return Response({"detail": "行动项不存在"}, status=status.HTTP_404_NOT_FOUND)
        if item.plan.user != request.user and not request.user.has_perm("kpi.change_improvementplan"):
            return Response({"detail": "无权评论"}, status=status.HTTP_403_FORBIDDEN)
        content = request.data.get("content", "").strip()
        if not content:
            return Response({"detail": "评论内容不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        attachment_url = ""
        attachment_key = ""
        if "attachment" in request.FILES:
            attachment_url, attachment_key = upload_image(request.FILES["attachment"])
        comment = ActionItemComment.objects.create(
            action_item=item, author=request.user, content=content,
            attachment_url=attachment_url, attachment_key=attachment_key,
        )
        return Response(ActionItemCommentSerializer(comment).data, status=status.HTTP_201_CREATED)
