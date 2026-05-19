import logging
from datetime import timedelta
from enum import Enum
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


class TransitionAction(Enum):
    NONE = "none"
    FIRE_FAILURE = "fire_failure"
    FIRE_RECOVERY = "fire_recovery"


def decide_transition(monitor, *, is_up: bool) -> TransitionAction:
    """决定给定当前监控状态和最新检查结果应触发的副作用。

    纯函数 — 不修改监控对象。调用方负责应用状态更新
    （last_status、consecutive_failures 等）并分发对应动作。
    """
    threshold = settings.UPTIME_FAILURE_THRESHOLD

    if is_up:
        if monitor.last_status == "down":
            return TransitionAction.FIRE_RECOVERY
        return TransitionAction.NONE

    # is_up = False
    if monitor.last_status == "down":
        return TransitionAction.NONE
    # last_status is up or unknown
    if monitor.consecutive_failures + 1 >= threshold:
        return TransitionAction.FIRE_FAILURE
    return TransitionAction.NONE


def _get_bot_user():
    """Resolve the system bot user. Returns None and logs if the user is missing,
    so callers can degrade gracefully rather than retry-looping on DoesNotExist."""
    try:
        return User.objects.get(username=settings.UPTIME_SYSTEM_BOT_USERNAME)
    except User.DoesNotExist:
        logger.error(
            "UPTIME_SYSTEM_BOT_USERNAME=%r does not exist. "
            "Cannot create monitoring Issue/Notification — create the user or update settings.",
            settings.UPTIME_SYSTEM_BOT_USERNAME,
        )
        return None


def _build_failure_description(monitor, latest_error: str) -> str:
    return (
        f"**监控**: {monitor.name}\n\n"
        f"**URL**: {monitor.url}\n\n"
        f"**首次失败时间**: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"**连续失败次数**: {settings.UPTIME_FAILURE_THRESHOLD}\n\n"
        f"**最近一次错误**: {latest_error}\n"
    )


def fire_failure(monitor, *, latest_error: str):
    """Create an Issue for this monitor going down, link it, and notify project members."""
    from apps.issues.models import Issue, IssueStatus
    from apps.notifications.models import Notification, NotificationRecipient
    from apps.projects.models import ProjectMember

    bot = _get_bot_user()
    now = timezone.now()

    if bot is None:
        # Degrade gracefully: still flip the monitor into "down" so we don't fire
        # the same threshold breach on every subsequent check, but skip Issue +
        # notification creation. Operator will see the row turn red.
        monitor.last_status = "down"
        monitor.outage_started_at = now
        monitor.save(update_fields=["last_status", "outage_started_at", "updated_at"])
        return

    issue = Issue.objects.create(
        project=monitor.project,
        title=f"[监控告警] {monitor.name} 不可达",
        description=_build_failure_description(monitor, latest_error),
        priority="P1",
        status=IssueStatus.UNASSIGNED.value,
        created_by=bot,
        reporter="",
    )

    monitor.active_incident_issue = issue
    monitor.last_status = "down"
    monitor.outage_started_at = now
    monitor.save(update_fields=["active_incident_issue", "last_status", "outage_started_at", "updated_at"])

    notification = Notification.objects.create(
        notification_type=Notification.Type.SYSTEM,
        title=f"监控 {monitor.name} 不可达",
        content=f"已创建 Issue #{issue.pk}",
        source_user=bot,
        source_issue=issue,
        target_type=Notification.TargetType.USER,
    )
    member_ids = list(
        ProjectMember.objects.filter(project=monitor.project).values_list("user_id", flat=True)
    )
    for user_id in member_ids:
        NotificationRecipient.objects.create(notification=notification, user_id=user_id)

    logger.info("Uptime monitor %s went down. Issue #%s created.", monitor.pk, issue.pk)


def _format_duration_zh(delta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds} 秒"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} 分钟"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时 {minutes % 60} 分钟"
    days = hours // 24
    return f"{days} 天 {hours % 24} 小时"


def fire_recovery(monitor):
    """Close the active incident Issue (if any), add an Activity row, notify project members."""
    from apps.issues.models import Issue, IssueStatus, Activity
    from apps.notifications.models import Notification, NotificationRecipient
    from apps.projects.models import ProjectMember

    bot = _get_bot_user()
    now = timezone.now()
    duration = now - monitor.outage_started_at if monitor.outage_started_at else timedelta()
    duration_human = _format_duration_zh(duration)

    issue = monitor.active_incident_issue
    closed_states = (IssueStatus.RESOLVED.value, IssueStatus.CLOSED.value)
    if bot is not None and issue is not None and issue.status not in closed_states:
        issue.status = IssueStatus.RESOLVED.value
        issue.resolved_at = now
        issue.save(update_fields=["status", "resolved_at", "updated_at"])
        Activity.objects.create(
            user=bot, issue=issue, action="resolved",
            detail=f"监控已恢复,故障持续 {duration_human}",
        )

    monitor.active_incident_issue = None
    monitor.outage_started_at = None
    monitor.last_status = "up"
    monitor.last_up_at = now
    monitor.consecutive_failures = 0
    monitor.save(update_fields=[
        "active_incident_issue", "outage_started_at", "last_status",
        "last_up_at", "consecutive_failures", "updated_at",
    ])

    if bot is None:
        # Without a bot user we can't author the notification. Monitor state was
        # already updated above so we exit cleanly; operator sees the green dot.
        return

    notification = Notification.objects.create(
        notification_type=Notification.Type.SYSTEM,
        title=f"监控 {monitor.name} 已恢复",
        content=f"故障持续 {duration_human}",
        source_user=bot,
        source_issue=issue,
        target_type=Notification.TargetType.USER,
    )
    member_ids = list(
        ProjectMember.objects.filter(project=monitor.project).values_list("user_id", flat=True)
    )
    for user_id in member_ids:
        NotificationRecipient.objects.create(notification=notification, user_id=user_id)

    logger.info("Uptime monitor %s recovered after %s.", monitor.pk, duration_human)
