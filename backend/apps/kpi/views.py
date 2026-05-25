"""
KPI API views
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.permissions import IsAdminUser

from apps.issues.models import Issue
from apps.kpi.metrics import RESOLVED_STATUSES
from apps.permissions import FullDjangoModelPermissions
from .models import KPISnapshot, KPIScoringConfig
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
            im = d.get("issue_metrics") or {}
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
                "issue_summary": {
                    "resolved_count": im.get("resolved_count", 0),
                    "avg_resolution_hours": im.get("avg_resolution_hours") or 0,
                },
            })
        developers.sort(key=lambda x: x["scores"].get("overall", 0), reverse=True)

        # 耗时分布: 创建到解决的时长落入哪个桶
        target_user_ids = [u.id for u in users]
        start_dt = timezone.make_aware(datetime.combine(period_start, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(period_end, datetime.max.time()))
        resolution_buckets = {"lt4h": 0, "h4_8": 0, "h8_24": 0, "d1_3": 0, "gt3d": 0}
        resolved_issues_period = Issue.objects.filter(
            assignee_id__in=target_user_ids,
            status__in=RESOLVED_STATUSES,
            resolved_at__gte=start_dt,
            resolved_at__lte=end_dt,
            resolved_at__isnull=False,
        ).only("created_at", "resolved_at")
        for issue in resolved_issues_period:
            if not issue.created_at:
                continue
            hrs = (issue.resolved_at - issue.created_at).total_seconds() / 3600
            if hrs < 4:
                resolution_buckets["lt4h"] += 1
            elif hrs < 8:
                resolution_buckets["h4_8"] += 1
            elif hrs < 24:
                resolution_buckets["h8_24"] += 1
            elif hrs < 72:
                resolution_buckets["d1_3"] += 1
            else:
                resolution_buckets["gt3d"] += 1

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
                "top_tier_user": (
                    {
                        "user_id": top_tier_dev["user_id"],
                        "user_name": top_tier_dev["user_name"],
                        "avatar": top_tier_dev["avatar"],
                        "overall": top_tier_dev["scores"].get("overall", 0),
                    } if top_tier_dev else None
                ),
                "resolution_buckets": resolution_buckets,
            },
        })


# ------------------------------------------------------------------
# Team trend (rolling window, independent of page period)
# ------------------------------------------------------------------


def _trend_window(granularity: str, anchor: date) -> tuple[date, date]:
    """返回 (window_start, window_end) — 锚点向前滚动 12 个单位。

    day:   anchor 向前 30 天
    week:  anchor 所在周的周一,向前 11 周
    month: anchor 所在月的 1 号,向前 11 个月
    """
    if granularity == "day":
        return anchor - timedelta(days=29), anchor
    if granularity == "week":
        monday = anchor - timedelta(days=anchor.weekday())
        return monday - timedelta(weeks=11), anchor
    # month
    month_start = anchor.replace(day=1)
    year = month_start.year
    month = month_start.month - 11
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1), anchor


def _bucket_resolved(
    granularity: str,
    user_ids: list[int],
    window_start: date,
    window_end: date,
) -> list[dict]:
    """聚合 [window_start, window_end] 内已解决工单,按粒度分桶,缺失桶补 0。"""
    start_dt = timezone.make_aware(datetime.combine(window_start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(window_end, datetime.max.time()))

    qs = Issue.objects.filter(
        assignee_id__in=user_ids,
        status__in=RESOLVED_STATUSES,
        resolved_at__gte=start_dt,
        resolved_at__lte=end_dt,
        resolved_at__isnull=False,
    )

    if granularity == "day":
        rows = (
            qs.annotate(day=TruncDate("resolved_at"))
            .values("day")
            .annotate(count=Count("id"))
        )
        row_map = {r["day"].isoformat(): r["count"] for r in rows if r["day"]}
        buckets = []
        cur = window_start
        while cur <= window_end:
            buckets.append({
                "key": cur.isoformat(),
                "label": cur.strftime("%m-%d"),
                "resolved": row_map.get(cur.isoformat(), 0),
            })
            cur += timedelta(days=1)
        return buckets

    if granularity == "week":
        row_map: dict[date, int] = defaultdict(int)
        for dt in qs.values_list("resolved_at", flat=True):
            d = timezone.localtime(dt).date()
            monday = d - timedelta(days=d.weekday())
            row_map[monday] += 1
        buckets = []
        cur = window_start  # 已是周一
        while cur <= window_end:
            iso = cur.isocalendar()
            buckets.append({
                "key": cur.isoformat(),
                "label": f"W{iso.week:02d}",
                "resolved": row_map.get(cur, 0),
            })
            cur += timedelta(days=7)
        return buckets

    # month
    row_map = defaultdict(int)
    for dt in qs.values_list("resolved_at", flat=True):
        d = timezone.localtime(dt).date()
        row_map[d.replace(day=1)] += 1
    buckets = []
    cur = window_start
    while cur <= window_end:
        buckets.append({
            "key": cur.isoformat()[:7],
            "label": cur.strftime("%Y-%m"),
            "resolved": row_map.get(cur, 0),
        })
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return buckets


def _parse_trend_params(request) -> tuple[str, date]:
    """统一解析 granularity + anchor。"""
    granularity = request.query_params.get("granularity", "week")
    if granularity not in ("day", "week", "month"):
        granularity = "week"
    anchor_str = request.query_params.get("anchor")
    if anchor_str:
        try:
            anchor = date.fromisoformat(anchor_str)
        except ValueError:
            anchor = timezone.now().date()
    else:
        anchor = timezone.now().date()
    return granularity, anchor


class KPITeamTrendView(APIView):
    """GET /api/kpi/team/trend/?granularity=day|week|month&role=&anchor=YYYY-MM-DD

    独立的滚动窗口趋势,不受页面 period 约束。
    """

    permission_classes = [FullDjangoModelPermissions]
    queryset = KPISnapshot.objects.none()

    def get(self, request):
        granularity, anchor = _parse_trend_params(request)
        role = request.query_params.get("role")
        users = KPIService()._get_target_users(role)
        user_ids = [u.id for u in users]

        window_start, window_end = _trend_window(granularity, anchor)
        buckets = _bucket_resolved(granularity, user_ids, window_start, window_end)

        return Response({
            "granularity": granularity,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "buckets": buckets,
        })


class KPIUserResolutionTrendView(APIView):
    """GET /api/kpi/users/<int:user_id>/resolution-trend/ — 单用户滚动窗口趋势。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if not _has_kpi_access(request, user_id):
            return Response({"detail": "权限不足"}, status=status.HTTP_403_FORBIDDEN)
        granularity, anchor = _parse_trend_params(request)
        window_start, window_end = _trend_window(granularity, anchor)
        buckets = _bucket_resolved(granularity, [user_id], window_start, window_end)
        return Response({
            "granularity": granularity,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "buckets": buckets,
        })


class KPIMeResolutionTrendView(KPIUserResolutionTrendView):
    """GET /api/kpi/me/resolution-trend/"""
    def get(self, request):
        return super().get(request, user_id=request.user.id)


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
