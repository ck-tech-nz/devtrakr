"""
KPI 指标计算模块

compute_issue_metrics    — 问题指标
compute_commit_metrics   — Commit 指标
compute_workload_metrics — 工作量/Code Arena 指标（计件、重修、SLA）
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.issues.models import Activity, Issue
from apps.repos.models import Commit, GitAuthorAlias

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RESOLVED_STATUSES = {"已解决", "已发布", "已关闭"}

PRIORITY_WEIGHTS = {"P0": 4, "P1": 3, "P2": 2, "P3": 1}

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|refactor|chore|docs|style|test|perf|ci|build)(\(.+\))?[!]?:\s.+"
)

# ---------------------------------------------------------------------------
# 问题指标
# ---------------------------------------------------------------------------


def compute_issue_metrics(
    user, period_start: date, period_end: date
) -> dict:
    """计算指定用户在 [period_start, period_end] 内的问题指标。"""

    start_dt = timezone.make_aware(datetime.combine(period_start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(period_end, datetime.max.time()))

    # 分配给该用户且在时间范围内创建的 Issues
    assigned_qs = Issue.objects.filter(
        assignee=user,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    )

    assigned_count = assigned_qs.count()

    if assigned_count == 0:
        return _empty_issue_metrics()

    resolved_qs = assigned_qs.filter(status__in=RESOLVED_STATUSES)
    resolved_count = resolved_qs.count()
    resolution_rate = round(resolved_count / assigned_count, 4) if assigned_count else 0

    # 平均解决时间（小时）
    resolved_with_time = resolved_qs.filter(resolved_at__isnull=False)
    if resolved_with_time.exists():
        total_hours = sum(
            (issue.resolved_at - issue.created_at).total_seconds() / 3600
            for issue in resolved_with_time
        )
        avg_resolution_hours = round(total_hours / resolved_with_time.count(), 2)
    else:
        avg_resolution_hours = 0

    # 每日 / 每周平均解决量
    period_days = max((period_end - period_start).days, 1)
    daily_resolved_avg = round(resolved_count / period_days, 4)
    weekly_resolved_avg = round(daily_resolved_avg * 7, 4)

    # 按优先级拆分
    priority_breakdown = {}
    for prio in ("P0", "P1", "P2", "P3"):
        prio_qs = assigned_qs.filter(priority=prio)
        prio_assigned = prio_qs.count()
        prio_resolved_qs = prio_qs.filter(status__in=RESOLVED_STATUSES, resolved_at__isnull=False)
        prio_resolved = prio_resolved_qs.count()

        if prio_resolved:
            prio_hours = sum(
                (i.resolved_at - i.created_at).total_seconds() / 3600
                for i in prio_resolved_qs
            )
            prio_avg_hours = round(prio_hours / prio_resolved, 2)
        else:
            prio_avg_hours = 0

        priority_breakdown[prio] = {
            "assigned": prio_assigned,
            "resolved": prio_resolved,
            "avg_hours": prio_avg_hours,
        }

    # 加权 Issue 价值
    weighted_issue_value = 0
    for issue in resolved_with_time:
        resolution_hours = (issue.resolved_at - issue.created_at).total_seconds() / 3600
        helper_count = issue.helpers.count()
        activity_count = issue.activities.count()

        complexity_signal = (
            resolution_hours * 0.4
            + helper_count * 0.3
            + activity_count * 0.3
        )
        priority_weight = PRIORITY_WEIGHTS.get(issue.priority, 1)
        weighted_issue_value += priority_weight * complexity_signal

    weighted_issue_value = round(weighted_issue_value, 4)

    # 作为协助人参与（不是负责人）
    as_helper_count = (
        Issue.objects.filter(
            helpers=user,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        )
        .exclude(assignee=user)
        .distinct()
        .count()
    )

    return {
        "assigned_count": assigned_count,
        "resolved_count": resolved_count,
        "resolution_rate": resolution_rate,
        "avg_resolution_hours": avg_resolution_hours,
        "daily_resolved_avg": daily_resolved_avg,
        "weekly_resolved_avg": weekly_resolved_avg,
        "priority_breakdown": priority_breakdown,
        "weighted_issue_value": weighted_issue_value,
        "as_helper_count": as_helper_count,
    }


def _empty_issue_metrics() -> dict:
    return {
        "assigned_count": 0,
        "resolved_count": 0,
        "resolution_rate": 0,
        "avg_resolution_hours": 0,
        "daily_resolved_avg": 0,
        "weekly_resolved_avg": 0,
        "priority_breakdown": {
            prio: {"assigned": 0, "resolved": 0, "avg_hours": 0}
            for prio in ("P0", "P1", "P2", "P3")
        },
        "weighted_issue_value": 0,
        "as_helper_count": 0,
    }


# ---------------------------------------------------------------------------
# Commit 指标
# ---------------------------------------------------------------------------


def compute_commit_metrics(
    user, period_start: date, period_end: date
) -> dict:
    """计算指定用户在 [period_start, period_end] 内的 Commit 指标。"""

    start_dt = timezone.make_aware(datetime.combine(period_start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(period_end, datetime.max.time()))

    # 通过 GitAuthorAlias 找到用户的所有邮箱
    author_emails = set(
        GitAuthorAlias.objects.filter(user=user).values_list("author_email", flat=True)
    )

    if not author_emails:
        return _empty_commit_metrics()

    commits_qs = Commit.objects.filter(
        author_email__in=author_emails,
        date__gte=start_dt,
        date__lte=end_dt,
    )

    commits = list(commits_qs.order_by("date"))
    total_commits = len(commits)

    if total_commits == 0:
        return _empty_commit_metrics()

    # 基础统计
    total_additions = sum(c.additions for c in commits)
    total_deletions = sum(c.deletions for c in commits)
    lines_changed = total_additions + total_deletions

    # Commit 大小分布
    small = medium = large = 0
    for c in commits:
        size = c.additions + c.deletions
        if size < 50:
            small += 1
        elif size <= 200:
            medium += 1
        else:
            large += 1

    commit_size_distribution = {"small": small, "medium": medium, "large": large}
    avg_commit_size = round(lines_changed / total_commits, 2) if total_commits else 0

    # 文件类型广度
    extensions = set()
    for c in commits:
        for f in c.files_changed or []:
            if "." in f:
                ext = f.rsplit(".", 1)[-1]
                extensions.add(ext)
    file_type_breadth = len(extensions)

    # 工作节奏
    by_hour = [0] * 24
    by_weekday = [0] * 7
    for c in commits:
        local_dt = timezone.localtime(c.date)
        by_hour[local_dt.hour] += 1
        by_weekday[local_dt.weekday()] += 1

    work_rhythm = {"by_hour": by_hour, "by_weekday": by_weekday}

    # Conventional commit 分析
    conventional_count = 0
    type_counts: dict[str, int] = defaultdict(int)
    refactor_count = 0
    for c in commits:
        first_line = c.message.split("\n", 1)[0]
        m = CONVENTIONAL_RE.match(first_line)
        if m:
            conventional_count += 1
            ctype = m.group(1)
            type_counts[ctype] += 1
            if ctype == "refactor":
                refactor_count += 1

    conventional_ratio = round(conventional_count / total_commits, 4)
    refactor_ratio = round(refactor_count / total_commits, 4)
    commit_type_distribution = dict(type_counts)

    # Self-introduced bug rate
    # feat/refactor commit 之后 72 小时内同一作者在相同文件上提交 fix
    feat_refactor_commits = [
        c for c in commits
        if CONVENTIONAL_RE.match(c.message.split("\n", 1)[0])
        and CONVENTIONAL_RE.match(c.message.split("\n", 1)[0]).group(1) in ("feat", "refactor")
    ]

    fix_commits = [
        c for c in commits
        if CONVENTIONAL_RE.match(c.message.split("\n", 1)[0])
        and CONVENTIONAL_RE.match(c.message.split("\n", 1)[0]).group(1) == "fix"
    ]

    self_bug_count = 0
    for fc in feat_refactor_commits:
        fc_files = set(fc.files_changed or [])
        for fix_c in fix_commits:
            if fix_c.date <= fc.date:
                continue
            time_diff = (fix_c.date - fc.date).total_seconds()
            if time_diff > 72 * 3600:
                continue
            fix_files = set(fix_c.files_changed or [])
            if fc_files & fix_files:
                self_bug_count += 1
                break  # 每个 feat/refactor 只计一次

    fr_count = len(feat_refactor_commits)
    self_introduced_bug_rate = round(self_bug_count / fr_count, 4) if fr_count else 0

    # Churn rate — 30 天内同一文件再次修改的比例
    file_modify_dates: dict[str, list[datetime]] = defaultdict(list)
    for c in commits:
        for f in c.files_changed or []:
            file_modify_dates[f].append(c.date)

    churn_files = 0
    total_file_touches = 0
    for f, dates in file_modify_dates.items():
        dates_sorted = sorted(dates)
        total_file_touches += len(dates_sorted)
        for i in range(1, len(dates_sorted)):
            if (dates_sorted[i] - dates_sorted[i - 1]).days <= 30:
                churn_files += 1

    churn_rate = round(churn_files / total_file_touches, 4) if total_file_touches else 0

    # Repo 覆盖
    repo_map: dict[int, dict] = {}
    for c in commits:
        if c.repo_id not in repo_map:
            repo_map[c.repo_id] = {"repo_id": c.repo_id, "repo_name": c.repo.name, "commits": 0}
        repo_map[c.repo_id]["commits"] += 1
    repo_coverage = list(repo_map.values())

    return {
        "total_commits": total_commits,
        "additions": total_additions,
        "deletions": total_deletions,
        "lines_changed": lines_changed,
        "self_introduced_bug_rate": self_introduced_bug_rate,
        "churn_rate": churn_rate,
        "commit_size_distribution": commit_size_distribution,
        "avg_commit_size": avg_commit_size,
        "file_type_breadth": file_type_breadth,
        "work_rhythm": work_rhythm,
        "refactor_ratio": refactor_ratio,
        "commit_type_distribution": commit_type_distribution,
        "conventional_ratio": conventional_ratio,
        "repo_coverage": repo_coverage,
    }


def _empty_commit_metrics() -> dict:
    return {
        "total_commits": 0,
        "additions": 0,
        "deletions": 0,
        "lines_changed": 0,
        "self_introduced_bug_rate": 0,
        "churn_rate": 0,
        "commit_size_distribution": {"small": 0, "medium": 0, "large": 0},
        "avg_commit_size": 0,
        "file_type_breadth": 0,
        "work_rhythm": {"by_hour": [0] * 24, "by_weekday": [0] * 7},
        "refactor_ratio": 0,
        "commit_type_distribution": {},
        "conventional_ratio": 0,
        "repo_coverage": [],
    }


# ---------------------------------------------------------------------------
# 工作量 / Code Arena 指标
# ---------------------------------------------------------------------------

RESOLVED_ACTIONS = ("resolved", "closed")
NON_RESOLVED_STATUSES = ("未计划", "待处理", "进行中")


def _price_for_hours(hours: float, hour_brackets: list[dict]) -> int | None:
    """根据工时返回固定价格 (中/大型),匹配不到返回 None (走计件梯度)。

    边界: (min_hours, max_hours]。例如 中型 (4, 16] 意为 "超过 4h 且不超过 16h"。
    这样默认 4h 工单恰好落入「小型」,会走 count_tiers 梯度。
    """
    for br in hour_brackets:
        min_h = br.get("min_hours") or 0
        max_h = br.get("max_hours")
        if hours > min_h and (max_h is None or hours <= max_h):
            return int(br.get("price", 0))
    return None


def _price_at_index(idx: int, count_tiers: list[dict]) -> int:
    """根据当前累计普通工单序号返回单价。"""
    cum = 0
    for tier in count_tiers:
        cap = tier.get("max_count")
        if cap is None or idx < cum + cap:
            return int(tier.get("price", 0))
        cum += cap
    return int(count_tiers[-1].get("price", 0)) if count_tiers else 0


def _issue_estimated_hours(issue) -> float:
    """工单规模分级使用预计工时,缺失时回退到默认 4 小时。"""
    if issue.estimated_hours is not None:
        return float(issue.estimated_hours)
    return 4.0


def _issue_actual_hours(issue) -> float | None:
    """实际工时:优先用字段值,缺失时按 resolved_at - created_at 推算。"""
    if issue.actual_hours is not None:
        return float(issue.actual_hours)
    if issue.resolved_at and issue.created_at:
        return (issue.resolved_at - issue.created_at).total_seconds() / 3600
    return None


def compute_workload_metrics(
    user, period_start: date, period_end: date, config: dict | None = None
) -> dict:
    """计算工作量/Code Arena 指标：计件、重修、首次响应。

    Parameters
    ----------
    config : dict | None
        piece_rate_config dict；缺省时使用 _default_piece_rate_config()。
    """
    from apps.kpi.models import _default_piece_rate_config

    cfg = config or _default_piece_rate_config()
    count_tiers = cfg.get("count_tiers", [])
    hour_brackets = cfg.get("hour_brackets", [])
    protection_days = int(cfg.get("protection_days", 7))

    start_dt = timezone.make_aware(datetime.combine(period_start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(period_end, datetime.max.time()))

    # 已解决/已关闭/已发布 且 resolved_at 落在周期内
    resolved_qs = (
        Issue.objects.filter(
            assignee=user,
            status__in=RESOLVED_STATUSES,
            resolved_at__gte=start_dt,
            resolved_at__lte=end_dt,
        )
        .order_by("resolved_at")
    )
    resolved_issues = list(resolved_qs)

    # 计件：按 resolved_at 顺序应用价格梯度
    small_count = medium_count = large_count = 0
    medium_label = "中型"
    large_label = "大型"
    for br in hour_brackets:
        if (br.get("min_hours") or 0) >= 16:
            large_label = br.get("label", large_label)
        else:
            medium_label = br.get("label", medium_label)

    total_earnings = 0
    small_cumulative_idx = 0
    breakdown_items: list[dict] = []

    # 拖延度统计:实际工时相对预计工时的偏差
    delay_ratios: list[float] = []
    over_estimate_count = 0
    total_delay_hours = 0.0    # 仅累计超出部分 (max(0, actual - est))
    total_overrun_hours = 0.0  # 净偏差 (actual - est),可为负

    for issue in resolved_issues:
        # 优先用结算快照 (已冻结的价格/规模/预计工时不受后续配置影响)
        settlement = issue.settlement or None

        if settlement:
            price = int(settlement.get("price", 0))
            size_label = settlement.get("size", "小型")
            est_hours = float(settlement.get("estimated_hours") or 0)
            settled = True
        else:
            settled = False
            est_hours = _issue_estimated_hours(issue)
            bracket_price = _price_for_hours(est_hours, hour_brackets)

            if bracket_price is not None:
                price = bracket_price
                if est_hours > 16:
                    size_label = large_label
                else:
                    size_label = medium_label
            else:
                price = _price_at_index(small_cumulative_idx, count_tiers)
                small_cumulative_idx += 1
                size_label = "小型"

        if size_label == "小型":
            small_count += 1
        elif size_label == "大型" or size_label == large_label:
            large_count += 1
        else:
            medium_count += 1

        total_earnings += price

        # 拖延度: 实际工时取 settlement 中的 (若有),否则取当前 issue.actual_hours
        if settlement and settlement.get("actual_hours") is not None:
            actual = float(settlement["actual_hours"])
        else:
            actual = _issue_actual_hours(issue)

        if actual is not None and est_hours > 0:
            ratio = actual / est_hours
            delay_ratios.append(ratio)
            delta = actual - est_hours
            total_overrun_hours += delta
            if ratio > 1:
                over_estimate_count += 1
                total_delay_hours += delta

        breakdown_items.append({
            "issue_id": issue.pk,
            "title": issue.title,
            "estimated_hours": round(est_hours, 2),
            "actual_hours": round(actual, 2) if actual is not None else None,
            "size": size_label,
            "price": price,
            "delay_ratio": round(actual / est_hours, 2) if (actual is not None and est_hours > 0) else None,
            "delay_hours": round(actual - est_hours, 2) if (actual is not None and est_hours > 0) else None,
            "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
            "priority": issue.priority,
            "settled": settled,
        })

    avg_delay_ratio = (
        round(sum(delay_ratios) / len(delay_ratios), 2) if delay_ratios else 0.0
    )

    # 首次响应时间：从 issue.created_at 到该 issue 上 assignee 的首次 Activity
    assigned_in_period = Issue.objects.filter(
        assignee=user,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    )
    response_hours_list: list[float] = []
    for issue in assigned_in_period.only("id", "created_at"):
        first_act = (
            Activity.objects.filter(issue_id=issue.pk, user=user)
            .order_by("created_at")
            .first()
        )
        if first_act and first_act.created_at and issue.created_at:
            delta = (first_act.created_at - issue.created_at).total_seconds() / 3600
            if delta >= 0:
                response_hours_list.append(delta)
    avg_first_response_hours = (
        round(sum(response_hours_list) / len(response_hours_list), 2)
        if response_hours_list else 0.0
    )

    # 重修：用户在周期内将 Issue 标记为 已解决/已关闭，之后 protection_days 内
    # 同 Issue 的状态又变回未解决（任意用户操作均计数，按 Issue 去重）
    resolve_acts = (
        Activity.objects.filter(
            user=user,
            action__in=RESOLVED_ACTIONS,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        )
        .order_by("created_at")
    )
    rework_issue_ids: set[int] = set()
    rework_window = timedelta(days=protection_days)
    for act in resolve_acts:
        if act.issue_id in rework_issue_ids:
            continue
        window_end = act.created_at + rework_window
        regression = Activity.objects.filter(
            issue_id=act.issue_id,
            action="updated",
            created_at__gt=act.created_at,
            created_at__lte=window_end,
            detail__contains="改为",
        )
        for r in regression:
            # detail 形如 "状态从 已解决 改为 进行中"
            if any(f"改为 {s}" in (r.detail or "") for s in NON_RESOLVED_STATUSES):
                rework_issue_ids.add(act.issue_id)
                break
    rework_count = len(rework_issue_ids)

    # 保护期协助：用户在保护期内协助修复他人 issue 的次数
    protection_helper_count = Issue.objects.filter(
        helpers=user,
        resolved_at__gte=start_dt,
        resolved_at__lte=end_dt,
    ).exclude(assignee=user).distinct().count()

    return {
        "completed_count": len(resolved_issues),
        "small_count": small_count,
        "medium_count": medium_count,
        "large_count": large_count,
        "estimated_earnings": total_earnings,
        "avg_first_response_hours": avg_first_response_hours,
        "avg_delay_ratio": avg_delay_ratio,
        "over_estimate_count": over_estimate_count,
        "total_delay_hours": round(total_delay_hours, 2),
        "total_overrun_hours": round(total_overrun_hours, 2),
        "rework_count": rework_count,
        "protection_days": protection_days,
        "protection_helper_count": protection_helper_count,
        "size_distribution": {
            "small": small_count,
            "medium": medium_count,
            "large": large_count,
        },
        "breakdown": breakdown_items,
    }


def _empty_workload_metrics(protection_days: int = 7) -> dict:
    return {
        "completed_count": 0,
        "small_count": 0,
        "medium_count": 0,
        "large_count": 0,
        "estimated_earnings": 0,
        "avg_first_response_hours": 0.0,
        "avg_delay_ratio": 0.0,
        "over_estimate_count": 0,
        "total_delay_hours": 0.0,
        "total_overrun_hours": 0.0,
        "rework_count": 0,
        "protection_days": protection_days,
        "protection_helper_count": 0,
        "size_distribution": {"small": 0, "medium": 0, "large": 0},
        "breakdown": [],
    }
