"""
KPI 编排服务

KPIService.refresh — 编排完整的 KPI 计算流水线
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kpi.metrics import (
    compute_commit_metrics,
    compute_issue_metrics,
    compute_workload_metrics,
)
from apps.kpi.models import KPIScoringConfig, KPISnapshot
from apps.kpi.scoring import compute_rankings, compute_scores, compute_tier
from apps.kpi.suggestions import generate_suggestions

User = get_user_model()


class KPIService:
    """KPI 计算编排器：指标 → 评分 → 排名 → 建议 → 快照。"""

    def refresh(
        self,
        period_start: date,
        period_end: date,
        role: str | None = None,
    ) -> dict:
        """执行完整的 KPI 计算流水线并保存快照。

        Parameters
        ----------
        period_start : date
            统计起始日期
        period_end : date
            统计截止日期
        role : str | None
            角色（用户组名称），为 None 时计算所有活跃非机器人用户

        Returns
        -------
        dict
            {"user_count": N, "computed_at": "ISO 8601 string"}
        """
        users = self._get_target_users(role)
        now = timezone.now()
        cfg = KPIScoringConfig.get_solo()
        piece_cfg = cfg.piece_rate_config or {}

        # 第一轮：为每个用户计算指标和评分
        user_data: list[dict] = []
        for user in users:
            issue_metrics = compute_issue_metrics(user, period_start, period_end)
            commit_metrics = compute_commit_metrics(user, period_start, period_end)
            workload_metrics = compute_workload_metrics(
                user, period_start, period_end, piece_cfg
            )
            prev_scores = self._get_previous_scores(user, period_start)
            scores = compute_scores(issue_metrics, commit_metrics, prev_scores)
            scores["tier"] = compute_tier(
                scores.get("overall", 0), piece_cfg.get("tier_thresholds")
            )

            user_data.append({
                "user": user,
                "issue_metrics": issue_metrics,
                "commit_metrics": commit_metrics,
                "workload_metrics": workload_metrics,
                "scores": scores,
                "prev_scores": prev_scores,
            })

        # 计算团队排名
        all_user_scores = [
            {"user_id": d["user"].pk, "scores": d["scores"]}
            for d in user_data
        ]
        rankings_map = compute_rankings(all_user_scores)

        # 计算团队平均分
        team_avgs = self._compute_team_averages(user_data)

        # 第二轮：生成建议并保存快照
        for d in user_data:
            user = d["user"]
            suggestions = generate_suggestions(
                d["scores"],
                d["issue_metrics"],
                d["commit_metrics"],
                team_avgs,
                d["prev_scores"],
            )

            KPISnapshot.objects.update_or_create(
                user=user,
                period_start=period_start,
                period_end=period_end,
                defaults={
                    "issue_metrics": d["issue_metrics"],
                    "commit_metrics": d["commit_metrics"],
                    "workload_metrics": d["workload_metrics"],
                    "scores": d["scores"],
                    "rankings": rankings_map.get(user.pk, {}),
                    "suggestions": suggestions,
                    "computed_at": now,
                },
            )

        return {
            "user_count": len(user_data),
            "computed_at": now.isoformat(),
        }

    # ------------------------------------------------------------------
    # 按需计算（单用户，任意周期）
    # ------------------------------------------------------------------

    def compute_for_user(self, user, period_start: date, period_end: date) -> dict:
        """为单个用户按需计算 KPI，不保存快照。"""
        cfg = KPIScoringConfig.get_solo()
        piece_cfg = cfg.piece_rate_config or {}

        issue_metrics = compute_issue_metrics(user, period_start, period_end)
        commit_metrics = compute_commit_metrics(user, period_start, period_end)
        workload_metrics = compute_workload_metrics(
            user, period_start, period_end, piece_cfg
        )
        prev_scores = self._get_previous_scores(user, period_start)
        scores = compute_scores(issue_metrics, commit_metrics, prev_scores)
        scores["tier"] = compute_tier(
            scores.get("overall", 0), piece_cfg.get("tier_thresholds")
        )
        suggestions = generate_suggestions(scores, issue_metrics, commit_metrics, {}, prev_scores)

        return {
            "user": user,
            "issue_metrics": issue_metrics,
            "commit_metrics": commit_metrics,
            "workload_metrics": workload_metrics,
            "scores": scores,
            "suggestions": suggestions,
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _get_target_users(self, role: str | None = None):
        """获取目标用户：活跃、非机器人。可选按用户组过滤。"""
        qs = User.objects.filter(is_active=True, is_bot=False)
        if role:
            qs = qs.filter(groups__name=role)
        return qs

    def _get_previous_scores(self, user, current_start: date) -> dict | None:
        """获取当前周期之前最近一次快照的评分，用于趋势/成长计算。"""
        snapshot = (
            KPISnapshot.objects.filter(user=user, period_end__lt=current_start)
            .order_by("-period_end", "-computed_at")
            .first()
        )
        if snapshot and snapshot.scores:
            return snapshot.scores
        return None

    def _compute_team_averages(self, user_data: list[dict]) -> dict:
        """计算团队各维度平均分。"""
        dims = ("efficiency", "output", "quality", "capability")
        n = len(user_data)
        if n == 0:
            return {d: 0 for d in dims}

        totals = {d: 0 for d in dims}
        for d in user_data:
            for dim in dims:
                totals[dim] += d["scores"].get(dim, 0)

        return {d: round(totals[d] / n, 2) for d in dims}
