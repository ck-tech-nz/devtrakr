"""
工单结算

settle_issue(issue) — 计算并冻结工单的价格/工时/规则快照到 Issue.settlement。
一旦结算,后续修改 KPIScoringConfig 不会影响该工单的金额。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.issues.models import Issue
from apps.kpi.metrics import (
    _issue_estimated_hours,
    _issue_actual_hours,
    _price_at_index,
    _price_for_hours,
)
from apps.kpi.models import KPIScoringConfig, _default_piece_rate_config

User = get_user_model()


def _season_key(dt) -> str:
    """以月为赛季。"""
    return dt.strftime("%Y-%m")


def _resolve_size_label(est_hours: float, hour_brackets: list[dict]) -> str:
    """返回规模标签 (小型/中型/大型),与 _price_for_hours 的边界保持一致。"""
    for br in hour_brackets:
        min_h = br.get("min_hours") or 0
        max_h = br.get("max_hours")
        if est_hours > min_h and (max_h is None or est_hours <= max_h):
            return br.get("label") or ("大型" if (max_h is None or max_h > 16) else "中型")
    return "小型"


def settle_issue(issue, config: dict | None = None, save: bool = True) -> dict | None:
    """计算并冻结 issue 的结算信息。已结算的工单返回现有 settlement,不重复结算。

    Parameters
    ----------
    issue : Issue
    config : dict | None
        piece_rate_config dict;缺省时取当前 KPIScoringConfig 单例
    save : bool
        是否立即保存到数据库

    Returns
    -------
    dict | None
        结算 payload;若 issue 无 assignee 或无 resolved_at 则返回 None
    """
    if issue.settlement:
        return issue.settlement
    if issue.assignee_id is None:
        return None

    cfg = config
    if cfg is None:
        cfg = KPIScoringConfig.get_solo().piece_rate_config or _default_piece_rate_config()

    count_tiers = cfg.get("count_tiers", [])
    hour_brackets = cfg.get("hour_brackets", [])

    resolved_dt = issue.resolved_at or timezone.now()
    season = _season_key(resolved_dt)

    est_hours = _issue_estimated_hours(issue)
    actual_hours = _issue_actual_hours(issue)

    bracket_price = _price_for_hours(est_hours, hour_brackets)
    small_tier_index: int | None = None

    # 中/大型固定价不依赖 count → 不需要事务锁
    if bracket_price is not None:
        price = bracket_price
        size = _resolve_size_label(est_hours, hour_brackets)
        payload = _build_payload(
            price, size, est_hours, actual_hours, season,
            small_tier_index, cfg,
        )
        if save:
            issue.settlement = payload
            issue.save(update_fields=["settlement"])
        return payload

    # 小型工单走 count_tiers 梯度,需要锁 assignee 避免 race 在 20→21 边界双反定价
    with transaction.atomic():
        # select_for_update 锁住 assignee 行 → 同人并发结算被串行化
        User.objects.select_for_update().filter(pk=issue.assignee_id).first()

        # 重新读 issue 以防其他事务已结算
        fresh = Issue.objects.filter(pk=issue.pk).only("settlement").first()
        if fresh and fresh.settlement:
            issue.settlement = fresh.settlement
            return fresh.settlement

        small_tier_index = (
            Issue.objects
            .filter(assignee_id=issue.assignee_id)
            .filter(settlement__size="小型")
            .filter(settlement__season=season)
            .exclude(pk=issue.pk)
            .count()
        )
        price = _price_at_index(small_tier_index, count_tiers)
        payload = _build_payload(
            price, "小型", est_hours, actual_hours, season,
            small_tier_index, cfg,
        )

        if save:
            issue.settlement = payload
            issue.save(update_fields=["settlement"])

    return payload


def _build_payload(price, size, est_hours, actual_hours, season,
                   small_tier_index, cfg):
    return {
        "price": int(price),
        "size": size,
        "estimated_hours": round(est_hours, 2),
        "actual_hours": round(actual_hours, 2) if actual_hours is not None else None,
        "season": season,
        "small_tier_index": small_tier_index,
        "rule_snapshot": cfg,
        "settled_at": timezone.now().isoformat(),
    }


def backfill_settlements(config: dict | None = None) -> int:
    """为所有已解决但未结算的工单回填 settlement。返回结算数量。

    按 (assignee, resolved_at asc) 顺序处理,保证小型工单的 tier_index 与历史顺序一致。
    """
    from apps.issues.models import IssueStatus

    qs = (
        Issue.objects
        .filter(
            Q(status=IssueStatus.RESOLVED)
            | Q(status=IssueStatus.PUBLISHED)
            | Q(status=IssueStatus.CLOSED)
        )
        .filter(settlement__isnull=True)
        .filter(assignee__isnull=False)
        .order_by("assignee_id", "resolved_at", "id")
    )

    count = 0
    for issue in qs.iterator():
        settle_issue(issue, config=config, save=True)
        count += 1
    return count
