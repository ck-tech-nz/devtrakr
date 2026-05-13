"""
Back-fill Issue.settlement for already-resolved issues using the current
KPIScoringConfig.piece_rate_config.

Idempotent: only fills rows where settlement IS NULL.
Order: (assignee, resolved_at, id) so per-month 小型 工单 tier_index reflects
the historical resolve order.
"""
from django.db import migrations
from django.db.models import Q


RESOLVED_STATUSES = ("已解决", "已发布", "已关闭")


def _season_key(dt) -> str:
    return dt.strftime("%Y-%m")


def _price_for_hours(hours, hour_brackets):
    for br in hour_brackets:
        min_h = br.get("min_hours") or 0
        max_h = br.get("max_hours")
        if hours > min_h and (max_h is None or hours <= max_h):
            return int(br.get("price", 0))
    return None


def _price_at_index(idx, count_tiers):
    cum = 0
    for tier in count_tiers:
        cap = tier.get("max_count")
        if cap is None or idx < cum + cap:
            return int(tier.get("price", 0))
        cum += cap
    return int(count_tiers[-1].get("price", 0)) if count_tiers else 0


def _resolve_size_label(est_hours, hour_brackets):
    for br in hour_brackets:
        min_h = br.get("min_hours") or 0
        max_h = br.get("max_hours")
        if est_hours > min_h and (max_h is None or est_hours <= max_h):
            return br.get("label") or ("大型" if (max_h is None or max_h > 16) else "中型")
    return "小型"


def backfill(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    KPIScoringConfig = apps.get_model("kpi", "KPIScoringConfig")

    cfg_row = KPIScoringConfig.objects.first()
    if cfg_row is None or not cfg_row.piece_rate_config:
        from apps.kpi.models import _default_piece_rate_config
        cfg = _default_piece_rate_config()
    else:
        cfg = cfg_row.piece_rate_config

    count_tiers = cfg.get("count_tiers", [])
    hour_brackets = cfg.get("hour_brackets", [])

    from django.utils import timezone

    qs = (
        Issue.objects.filter(is_deleted=False)
        .filter(
            Q(status="已解决") | Q(status="已发布") | Q(status="已关闭")
        )
        .filter(settlement__isnull=True)
        .filter(assignee__isnull=False)
        .order_by("assignee_id", "resolved_at", "id")
    )

    for issue in qs.iterator():
        resolved_dt = issue.resolved_at or issue.created_at or timezone.now()
        season = _season_key(resolved_dt)

        est_hours = float(issue.estimated_hours) if issue.estimated_hours is not None else 4.0
        if issue.actual_hours is not None:
            actual_hours = float(issue.actual_hours)
        elif issue.resolved_at and issue.created_at:
            actual_hours = (issue.resolved_at - issue.created_at).total_seconds() / 3600
        else:
            actual_hours = None

        bracket_price = _price_for_hours(est_hours, hour_brackets)
        small_tier_index = None
        if bracket_price is not None:
            price = bracket_price
            size = _resolve_size_label(est_hours, hour_brackets)
        else:
            small_tier_index = (
                Issue.objects
                .filter(assignee_id=issue.assignee_id, settlement__size="小型", settlement__season=season)
                .exclude(pk=issue.pk)
                .count()
            )
            price = _price_at_index(small_tier_index, count_tiers)
            size = "小型"

        issue.settlement = {
            "price": int(price),
            "size": size,
            "estimated_hours": round(est_hours, 2),
            "actual_hours": round(actual_hours, 2) if actual_hours is not None else None,
            "season": season,
            "small_tier_index": small_tier_index,
            "rule_snapshot": cfg,
            "settled_at": timezone.now().isoformat(),
            "backfilled": True,
        }
        issue.save(update_fields=["settlement"])


def reverse(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    Issue.objects.filter(settlement__backfilled=True).update(settlement=None)


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0007_add_settlement"),
        ("kpi", "0006_add_piece_rate_config"),
    ]

    operations = [
        migrations.RunPython(backfill, reverse),
    ]
