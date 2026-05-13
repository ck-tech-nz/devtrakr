"""
KPI 评分引擎

compute_scores   — 根据指标计算 5 维评分 + 综合分
compute_rankings — 根据所有用户评分计算排名与百分位

评分规则从 KPIScoringConfig（数据库单例）读取，支持在线修改。
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------


def _load_config():
    """从数据库加载评分配置，不存在时自动创建默认值。"""
    from apps.kpi.models import KPIScoringConfig
    return KPIScoringConfig.get_solo()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _saturate(value: float, ceiling: float) -> float:
    """将 value 映射到 0-100，ceiling 为饱和天花板。"""
    if ceiling <= 0:
        return 0.0
    return min(value / ceiling * 100, 100.0)


def _clamp(score: float) -> int:
    """将分数限制在 0-100 整数范围内。"""
    return max(0, min(100, round(score)))


def _p0p1_avg_hours(im: dict) -> float:
    """加权计算 P0/P1 平均解决时间（P0 权重 2, P1 权重 1）。"""
    pb = im.get("priority_breakdown", {})
    p0 = pb.get("P0", {})
    p1 = pb.get("P1", {})

    p0_resolved = p0.get("resolved", 0)
    p1_resolved = p1.get("resolved", 0)
    p0_hours = p0.get("avg_hours", 0)
    p1_hours = p1.get("avg_hours", 0)

    weighted_sum = p0_hours * p0_resolved * 2 + p1_hours * p1_resolved * 1
    total_weight = p0_resolved * 2 + p1_resolved * 1

    if total_weight == 0:
        return 0.0
    return weighted_sum / total_weight


def _p0_handling_ratio(im: dict) -> float:
    """P0 已解决 / 全部已解决 * 100。"""
    resolved_count = im.get("resolved_count", 0)
    if resolved_count == 0:
        return 0.0
    pb = im.get("priority_breakdown", {})
    p0_resolved = pb.get("P0", {}).get("resolved", 0)
    return p0_resolved / resolved_count * 100


def _commit_size_score(avg_size: float) -> float:
    """理想 commit 大小 50-150 行，偏离越多扣分越多。"""
    ideal_low = 50
    ideal_high = 150

    if ideal_low <= avg_size <= ideal_high:
        return 100.0

    if avg_size < ideal_low:
        deviation = ideal_low - avg_size
    else:
        deviation = avg_size - ideal_high

    return 100.0 * math.exp(-(deviation ** 2) / (2 * 100 ** 2))


# ---------------------------------------------------------------------------
# 评分计算
# ---------------------------------------------------------------------------


def compute_scores(
    issue_metrics: dict,
    commit_metrics: dict,
    prev_scores: dict | None = None,
) -> dict:
    """根据问题指标和 commit 指标计算 5 维评分 + 综合分。

    评分规则从 KPIScoringConfig 数据库单例读取。
    """
    cfg = _load_config()
    c = cfg.ceilings
    ef = cfg.efficiency_formula
    of = cfg.output_formula
    qf = cfg.quality_formula
    cf = cfg.capability_formula
    dw = cfg.dimension_weights

    im = issue_metrics
    cm = commit_metrics

    # ----- Efficiency -----
    daily_score = _saturate(im.get("daily_resolved_avg", 0), c.get("daily_resolved", 3))

    avg_hours = im.get("avg_resolution_hours", 0)
    avg_hours_ceil = c.get("avg_hours", 168)
    if avg_hours > 0:
        speed_score = max(0.0, (avg_hours_ceil - avg_hours) / avg_hours_ceil * 100)
    else:
        speed_score = 0.0 if im.get("resolved_count", 0) == 0 else 100.0

    p0p1_hours = _p0p1_avg_hours(im)
    p0p1_ceil = c.get("p0p1_hours", 48)
    if p0p1_hours > 0:
        p0p1_speed = max(0.0, (p0p1_ceil - p0p1_hours) / p0p1_ceil * 100)
    else:
        pb = im.get("priority_breakdown", {})
        has_p0p1_resolved = (
            pb.get("P0", {}).get("resolved", 0) + pb.get("P1", {}).get("resolved", 0)
        ) > 0
        p0p1_speed = 100.0 if has_p0p1_resolved else 0.0

    efficiency = (
        daily_score * ef.get("daily_resolved", 0.4)
        + speed_score * ef.get("speed", 0.4)
        + p0p1_speed * ef.get("p0p1_speed", 0.2)
    )

    # ----- Output -----
    wiv_score = _saturate(im.get("weighted_issue_value", 0), c.get("weighted_value", 200))
    resolved_score = _saturate(im.get("resolved_count", 0), c.get("resolved_count", 30))
    commit_vol_score = _saturate(cm.get("total_commits", 0), c.get("commit_volume", 100))
    repo_breadth_score = _saturate(len(cm.get("repo_coverage", [])), c.get("repo_breadth", 5))

    output = (
        wiv_score * of.get("weighted_issue_value", 0.4)
        + resolved_score * of.get("resolved_count", 0.3)
        + commit_vol_score * of.get("commit_volume", 0.2)
        + repo_breadth_score * of.get("repo_breadth", 0.1)
    )

    # ----- Quality -----
    bug_rate = cm.get("self_introduced_bug_rate", 0)
    inv_bug = (1 - bug_rate) * 100

    churn = cm.get("churn_rate", 0)
    inv_churn = (1 - churn) * 100

    cs_score = _commit_size_score(cm.get("avg_commit_size", 0))

    conv_ratio = cm.get("conventional_ratio", 0)
    conv_score = conv_ratio * 100

    quality = (
        inv_bug * qf.get("inv_bug_rate", 0.30)
        + inv_churn * qf.get("inv_churn_rate", 0.25)
        + cs_score * qf.get("commit_size", 0.20)
        + conv_score * qf.get("conventional_ratio", 0.25)
    )

    # ----- Capability -----
    ft_score = _saturate(cm.get("file_type_breadth", 0), c.get("file_type", 8))
    rc_score = _saturate(len(cm.get("repo_coverage", [])), c.get("repo_breadth", 5))
    p0_ratio = _p0_handling_ratio(im)
    helper_score = _saturate(im.get("as_helper_count", 0), c.get("helper_count", 10))

    capability = (
        ft_score * cf.get("file_type_breadth", 0.25)
        + rc_score * cf.get("repo_coverage", 0.25)
        + p0_ratio * cf.get("p0_handling_ratio", 0.25)
        + helper_score * cf.get("helper_participation", 0.25)
    )

    # ----- Growth -----
    if prev_scores and any(
        prev_scores.get(k) is not None
        for k in ("efficiency", "output", "quality", "capability")
    ):
        current = {
            "efficiency": efficiency,
            "output": output,
            "quality": quality,
            "capability": capability,
        }
        deltas = []
        for dim in ("efficiency", "output", "quality", "capability"):
            prev_val = prev_scores.get(dim)
            if prev_val is not None:
                deltas.append(current[dim] - prev_val)

        if deltas:
            avg_delta = sum(deltas) / len(deltas)
            growth = 50 + avg_delta
        else:
            growth = 50
    else:
        growth = 50

    # ----- Overall -----
    overall = (
        efficiency * dw.get("efficiency", 0.25)
        + output * dw.get("output", 0.25)
        + quality * dw.get("quality", 0.25)
        + capability * dw.get("capability", 0.15)
        + growth * dw.get("growth", 0.10)
    )

    return {
        "efficiency": _clamp(efficiency),
        "output": _clamp(output),
        "quality": _clamp(quality),
        "capability": _clamp(capability),
        "growth": _clamp(growth),
        "overall": _clamp(overall),
    }


# ---------------------------------------------------------------------------
# 段位计算
# ---------------------------------------------------------------------------

TIER_ORDER = ("bronze", "silver", "gold", "platinum", "diamond", "master")
TIER_LABELS = {
    "bronze": "青铜",
    "silver": "白银",
    "gold": "黄金",
    "platinum": "铂金",
    "diamond": "钻石",
    "master": "王者",
}


def compute_tier(overall_score: float, thresholds: dict | None = None) -> dict:
    """根据综合分映射段位，返回 {key, label, threshold, next_label, next_threshold}。"""
    from apps.kpi.models import _default_piece_rate_config

    th = thresholds or _default_piece_rate_config()["tier_thresholds"]
    # 按 threshold 降序匹配
    ordered = sorted(
        ((k, th.get(k, 0)) for k in TIER_ORDER if k in th),
        key=lambda x: x[1],
        reverse=True,
    )
    current_key = "bronze"
    current_threshold = 0
    next_key: str | None = None
    next_threshold: int | None = None
    for i, (key, t) in enumerate(ordered):
        if overall_score >= t:
            current_key = key
            current_threshold = t
            # next tier = 上一档（即更高的段位）
            if i > 0:
                next_key, next_threshold = ordered[i - 1]
            break
    else:
        # 低于所有阈值 → 最低段位（已包含 bronze threshold=0 的情况）
        if ordered:
            current_key, current_threshold = ordered[-1]

    return {
        "key": current_key,
        "label": TIER_LABELS.get(current_key, current_key),
        "threshold": current_threshold,
        "next_key": next_key,
        "next_label": TIER_LABELS.get(next_key) if next_key else None,
        "next_threshold": next_threshold,
    }


# ---------------------------------------------------------------------------
# 排名计算
# ---------------------------------------------------------------------------


def compute_rankings(all_user_scores: list[dict]) -> dict:
    """根据所有用户的评分计算排名与百分位。"""
    n = len(all_user_scores)
    if n == 0:
        return {}

    dimensions = ("efficiency", "output", "quality", "capability", "growth", "overall")
    result: dict = {}

    dim_scores: dict[str, list[tuple]] = {}
    for dim in dimensions:
        scored = [
            (entry["user_id"], entry["scores"].get(dim, 0))
            for entry in all_user_scores
        ]
        dim_scores[dim] = scored

    for entry in all_user_scores:
        uid = entry["user_id"]
        result[uid] = {"total_developers": n}

    for dim in dimensions:
        scores_list = dim_scores[dim]
        values = [s[1] for s in scores_list]

        for uid, score in scores_list:
            if n == 1:
                percentile = 50
            else:
                count_below = sum(1 for v in values if v < score)
                percentile = round(count_below / (n - 1) * 100)

            result[uid][f"{dim}_percentile"] = percentile

        sorted_scores = sorted(scores_list, key=lambda x: x[1], reverse=True)
        for rank, (uid, _score) in enumerate(sorted_scores, start=1):
            result[uid][f"{dim}_rank"] = rank

    return result
