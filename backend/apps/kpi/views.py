"""
KPI API views
"""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.permissions import IsAdminUser

from apps.permissions import FullDjangoModelPermissions
from .models import KPISnapshot, KPIScoringConfig
from .serializers import KPITeamDeveloperSerializer, KPISummarySerializer
from .services import KPIService

User = get_user_model()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _all_periods(today: date) -> list[tuple[date, date]]:
    """返回所有标准周期 (week, month, quarter) 的 (start, end)。"""
    # week
    week_start = today - timedelta(days=today.weekday())
    # month
    month_start = today.replace(day=1)
    # quarter
    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = today.replace(month=quarter_start_month, day=1)

    return [
        (week_start, today),
        (month_start, today),
        (quarter_start, today),
    ]


def _parse_period(request) -> tuple[date, date]:
    """Parse period from query params. Returns (start, end).

    Supports:
      ?period=week   — current week (Mon-Sun)
      ?period=month  — current month (default)
      ?period=quarter — current quarter
      ?start=YYYY-MM-DD&end=YYYY-MM-DD — custom range
    """
    start_str = request.query_params.get("start")
    end_str = request.query_params.get("end")
    if start_str and end_str:
        return date.fromisoformat(start_str), date.fromisoformat(end_str)

    today = timezone.now().date()
    period = request.query_params.get("period", "month")

    if period == "week":
        start = today - timedelta(days=today.weekday())  # Monday
        end = start + timedelta(days=6)
        return start, min(end, today)
    elif period == "quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=quarter_start_month, day=1)
        return start, today
    else:  # month (default)
        start = today.replace(day=1)
        return start, today


def _has_kpi_access(request, user_id: int) -> bool:
    """Return True if the requesting user can view the given user_id's KPI."""
    if request.user.has_perm("kpi.view_kpisnapshot"):
        return True
    if request.user.id == user_id and request.user.has_perm("kpi.view_own_kpi"):
        return True
    return False


def _get_snapshot(user_id: int, period_start: date, period_end: date) -> KPISnapshot | None:
    """Get the latest snapshot for a user in the given period."""
    return (
        KPISnapshot.objects.filter(
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
        )
        .select_related("user")
        .first()
    )


# ------------------------------------------------------------------
# Team dashboard
# ------------------------------------------------------------------

class KPITeamView(APIView):
    """GET /api/kpi/team/ — team dashboard (managers only)."""

    permission_classes = [FullDjangoModelPermissions]
    queryset = KPISnapshot.objects.none()  # needed for FullDjangoModelPermissions

    def get(self, request):
        from apps.kpi.scoring import compute_rankings

        period_start, period_end = _parse_period(request)
        role = request.query_params.get("role")
        svc = KPIService()
        users = svc._get_target_users(role)

        # 按需计算每个用户的 KPI
        user_data = []
        for user in users:
            d = svc.compute_for_user(user, period_start, period_end)
            user_data.append(d)

        # 计算排名
        all_scores = [{"user_id": d["user"].pk, "scores": d["scores"]} for d in user_data]
        rankings_map = compute_rankings(all_scores)

        # 构造响应
        developers = []
        for d in user_data:
            u = d["user"]
            wm = d.get("workload_metrics") or {}
            developers.append({
                "user_id": u.id,
                "user_name": u.name,
                "avatar": u.avatar or "",
                "scores": d["scores"],
                "rankings": rankings_map.get(u.pk, {}),
                "workload": {
                    "completed_count": wm.get("completed_count", 0),
                    "small_count": wm.get("small_count", 0),
                    "medium_count": wm.get("medium_count", 0),
                    "large_count": wm.get("large_count", 0),
                    "estimated_earnings": wm.get("estimated_earnings", 0),
                    "avg_first_response_hours": wm.get("avg_first_response_hours", 0),
                    "avg_delay_ratio": wm.get("avg_delay_ratio", 0),
                    "over_estimate_count": wm.get("over_estimate_count", 0),
                    "total_delay_hours": wm.get("total_delay_hours", 0),
                    "total_overrun_hours": wm.get("total_overrun_hours", 0),
                    "rework_count": wm.get("rework_count", 0),
                    "protection_helper_count": wm.get("protection_helper_count", 0),
                },
            })
        developers.sort(key=lambda x: x["scores"].get("overall", 0), reverse=True)

        # 汇总
        total_resolved = sum(d["issue_metrics"].get("resolved_count", 0) for d in user_data)
        avg_hours_list = [
            d["issue_metrics"].get("avg_resolution_hours")
            for d in user_data
            if d["issue_metrics"].get("avg_resolution_hours") is not None
        ]
        overall_scores = [d["scores"].get("overall", 0) for d in user_data]
        total_earnings = sum(
            (d.get("workload_metrics") or {}).get("estimated_earnings", 0) for d in user_data
        )
        total_rework = sum(
            (d.get("workload_metrics") or {}).get("rework_count", 0) for d in user_data
        )
        total_tickets = sum(
            (d.get("workload_metrics") or {}).get("completed_count", 0) for d in user_data
        )
        top_tier_dev = max(
            developers, key=lambda x: x["scores"].get("overall", 0), default=None
        )

        return Response({
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "developers": developers,
            "summary": {
                "active_count": len(user_data),
                "resolved_count": total_resolved,
                "avg_resolution_hours": (
                    round(sum(avg_hours_list) / len(avg_hours_list), 1)
                    if avg_hours_list else None
                ),
                "avg_overall_score": (
                    round(sum(overall_scores) / len(overall_scores), 1)
                    if overall_scores else None
                ),
                "total_tickets": total_tickets,
                "total_earnings": total_earnings,
                "total_rework": total_rework,
                "top_tier": (
                    top_tier_dev["scores"].get("tier") if top_tier_dev else None
                ),
            },
        })


# ------------------------------------------------------------------
# Individual KPI views (by user_id)
# ------------------------------------------------------------------

def _compute_user(request, user_id):
    """按需计算单用户 KPI（任意周期）。"""
    user = User.objects.filter(pk=user_id).first()
    if not user:
        return None, None, None
    period_start, period_end = _parse_period(request)
    data = KPIService().compute_for_user(user, period_start, period_end)
    return user, (period_start, period_end), data


class KPIUserSummaryView(APIView):
    """GET /api/kpi/users/{user_id}/summary/"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if not _has_kpi_access(request, user_id):
            return Response({"detail": "权限不足"}, status=status.HTTP_403_FORBIDDEN)

        user, period, data = _compute_user(request, user_id)
        if not user:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "user_id": user.id,
            "user_name": user.name,
            "avatar": user.avatar or "",
            "groups": list(user.groups.values_list("name", flat=True)),
            "scores": data["scores"],
            "rankings": {},
            "period_start": period[0].isoformat(),
            "period_end": period[1].isoformat(),
        })


class KPIUserIssuesView(APIView):
    """GET /api/kpi/users/{user_id}/issues/"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if not _has_kpi_access(request, user_id):
            return Response({"detail": "权限不足"}, status=status.HTTP_403_FORBIDDEN)

        user, _, data = _compute_user(request, user_id)
        if not user:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        return Response(data["issue_metrics"])


class KPIUserCommitsView(APIView):
    """GET /api/kpi/users/{user_id}/commits/"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if not _has_kpi_access(request, user_id):
            return Response({"detail": "权限不足"}, status=status.HTTP_403_FORBIDDEN)

        user, _, data = _compute_user(request, user_id)
        if not user:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        return Response(data["commit_metrics"])


class KPIUserWorkloadView(APIView):
    """GET /api/kpi/users/{user_id}/workload/ — 工单计件、重修、SLA 指标。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if not _has_kpi_access(request, user_id):
            return Response({"detail": "权限不足"}, status=status.HTTP_403_FORBIDDEN)

        user, _, data = _compute_user(request, user_id)
        if not user:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        payload = dict(data["workload_metrics"])
        payload["tier"] = data["scores"].get("tier")
        payload["overall_score"] = data["scores"].get("overall", 0)
        return Response(payload)


class KPIUserTrendsView(APIView):
    """GET /api/kpi/users/{user_id}/trends/ — last N snapshots."""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if not _has_kpi_access(request, user_id):
            return Response({"detail": "权限不足"}, status=status.HTTP_403_FORBIDDEN)

        limit = int(request.query_params.get("limit", 6))
        snapshots = (
            KPISnapshot.objects.filter(user_id=user_id)
            .order_by("period_end", "computed_at")[:limit]
        )
        data = [
            {
                "period_start": s.period_start.isoformat(),
                "period_end": s.period_end.isoformat(),
                "scores": s.scores,
                "rankings": s.rankings,
                "computed_at": s.computed_at.isoformat(),
            }
            for s in snapshots
        ]
        return Response(data)


class KPIUserSuggestionsView(APIView):
    """GET /api/kpi/users/{user_id}/suggestions/"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if not _has_kpi_access(request, user_id):
            return Response({"detail": "权限不足"}, status=status.HTTP_403_FORBIDDEN)

        user, _, data = _compute_user(request, user_id)
        if not user:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        return Response(data["suggestions"])


# ------------------------------------------------------------------
# Refresh
# ------------------------------------------------------------------

class KPIRefreshView(APIView):
    """POST /api/kpi/refresh/ — trigger KPI recalculation."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.has_perm("kpi.refresh_kpi"):
            return Response({"detail": "权限不足"}, status=status.HTTP_403_FORBIDDEN)

        # 仅保存月度快照（用于趋势历史），视图层按需计算
        today = timezone.now().date()
        month_start = today.replace(day=1)
        result = KPIService().refresh(period_start=month_start, period_end=today)
        return Response({
            "status": "completed",
            "computed_at": result["computed_at"],
            "user_count": result["user_count"],
        })


# ------------------------------------------------------------------
# /me shortcuts
# ------------------------------------------------------------------

class KPIMeSummaryView(KPIUserSummaryView):
    """GET /api/kpi/me/summary/"""
    def get(self, request):
        return super().get(request, user_id=request.user.id)


class KPIMeIssuesView(KPIUserIssuesView):
    """GET /api/kpi/me/issues/"""
    def get(self, request):
        return super().get(request, user_id=request.user.id)


class KPIMeCommitsView(KPIUserCommitsView):
    """GET /api/kpi/me/commits/"""
    def get(self, request):
        return super().get(request, user_id=request.user.id)


class KPIMeWorkloadView(KPIUserWorkloadView):
    """GET /api/kpi/me/workload/"""
    def get(self, request):
        return super().get(request, user_id=request.user.id)


class KPIMeTrendsView(KPIUserTrendsView):
    """GET /api/kpi/me/trends/"""
    def get(self, request):
        return super().get(request, user_id=request.user.id)


class KPIMeSuggestionsView(KPIUserSuggestionsView):
    """GET /api/kpi/me/suggestions/"""
    def get(self, request):
        return super().get(request, user_id=request.user.id)


# ------------------------------------------------------------------
# Scoring config
# ------------------------------------------------------------------

class KPIScoringConfigView(APIView):
    """GET/PUT /api/kpi/scoring-config/ — 查看和修改评分规则。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        cfg = KPIScoringConfig.get_solo()
        return Response({
            "dimension_weights": cfg.dimension_weights,
            "efficiency_formula": cfg.efficiency_formula,
            "output_formula": cfg.output_formula,
            "quality_formula": cfg.quality_formula,
            "capability_formula": cfg.capability_formula,
            "ceilings": cfg.ceilings,
            "piece_rate_config": cfg.piece_rate_config,
            "updated_at": cfg.updated_at,
        })

    def put(self, request):
        cfg = KPIScoringConfig.get_solo()
        fields = [
            "dimension_weights", "efficiency_formula", "output_formula",
            "quality_formula", "capability_formula", "ceilings",
            "piece_rate_config",
        ]
        for field in fields:
            if field in request.data:
                setattr(cfg, field, request.data[field])
        cfg.save()
        return Response({
            "dimension_weights": cfg.dimension_weights,
            "efficiency_formula": cfg.efficiency_formula,
            "output_formula": cfg.output_formula,
            "quality_formula": cfg.quality_formula,
            "capability_formula": cfg.capability_formula,
            "ceilings": cfg.ceilings,
            "piece_rate_config": cfg.piece_rate_config,
            "updated_at": cfg.updated_at,
        })
