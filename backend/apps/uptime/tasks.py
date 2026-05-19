import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.uptime.http_check import perform_check
from apps.uptime.models import UptimeMonitor, UptimeCheck
from apps.uptime.services import decide_transition, fire_failure, fire_recovery, TransitionAction

logger = logging.getLogger(__name__)


@shared_task
def check_monitor(monitor_id: int):
    """Execute one health check for the given monitor and apply state transitions."""
    with transaction.atomic():
        monitor = (
            UptimeMonitor.objects
            .select_for_update(skip_locked=True)
            .filter(pk=monitor_id)
            .first()
        )
        if monitor is None or not monitor.is_enabled:
            return

        now = timezone.now()
        monitor.next_check_at = now + timedelta(minutes=monitor.interval_minutes)
        monitor.last_check_at = now
        monitor.save(update_fields=["next_check_at", "last_check_at", "updated_at"])

    # HTTP call outside the txn so we don't hold a row lock during a slow request.
    result = perform_check(monitor)

    UptimeCheck.objects.create(
        monitor=monitor,
        checked_at=timezone.now(),
        is_up=result.is_up,
        status_code=result.status_code,
        response_ms=result.response_ms,
        error=result.error,
    )

    action = decide_transition(monitor, is_up=result.is_up)

    if result.is_up:
        monitor.consecutive_failures = 0
        if monitor.last_status == "unknown":
            monitor.last_status = "up"
            monitor.last_up_at = timezone.now()
            monitor.save(update_fields=["consecutive_failures", "last_status", "last_up_at", "updated_at"])
        else:
            monitor.save(update_fields=["consecutive_failures", "updated_at"])
    else:
        monitor.consecutive_failures += 1
        monitor.save(update_fields=["consecutive_failures", "updated_at"])

    if action == TransitionAction.FIRE_FAILURE:
        fire_failure(monitor, latest_error=result.error or "unknown")
    elif action == TransitionAction.FIRE_RECOVERY:
        fire_recovery(monitor)
    else:
        logger.debug("Monitor %s check: is_up=%s, no action", monitor.pk, result.is_up)


@shared_task
def tick_uptime_monitors():
    """Find all monitors due for a check and dispatch per-monitor check tasks."""
    now = timezone.now()
    due_ids = list(
        UptimeMonitor.objects
        .filter(is_enabled=True)
        .filter(Q(next_check_at__isnull=True) | Q(next_check_at__lte=now))
        .values_list("pk", flat=True)
    )
    for monitor_id in due_ids:
        check_monitor.delay(monitor_id)
    logger.info("Uptime tick dispatched %d checks", len(due_ids))


@shared_task
def prune_old_checks():
    """Hard-delete UptimeCheck rows older than UPTIME_CHECK_RETENTION_DAYS."""
    cutoff = timezone.now() - timedelta(days=settings.UPTIME_CHECK_RETENTION_DAYS)
    deleted, _ = UptimeCheck.objects.filter(checked_at__lt=cutoff).delete()
    logger.info("Pruned %d old uptime checks (cutoff=%s)", deleted, cutoff)
