import re
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from .models import Notification, NotificationRecipient

User = get_user_model()

MENTION_RE = re.compile(r'@\[([^\]]+)\]\(user:(\d+)\)')

REMOTE_PUBLISH_TIMEOUT = 30


class RemotePublishError(Exception):
    """Raised when the remote DevTrakr server rejects the publish request."""


def publish_notification_to_remote(notification: Notification, *, env: str) -> dict:
    """POST the notification to a remote DevTrakr server.

    is_draft is forced by env: test=True, prod=False.
    """
    if env not in ("test", "prod"):
        raise ValueError(f"env must be 'test' or 'prod', got {env!r}")

    url_setting = f"DEVTRAKR_{env.upper()}_URL"
    key_setting = f"DEVTRAKR_{env.upper()}_KEY"
    url = getattr(settings, url_setting, "")
    key = getattr(settings, key_setting, "")
    if not url:
        raise ImproperlyConfigured(f"{url_setting} is not set")
    if not key:
        raise ImproperlyConfigured(f"{key_setting} is not set")

    payload = {
        "title": notification.title,
        "content": notification.content,
        "target_type": notification.target_type,
        "is_draft": env == "test",
    }
    resp = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {key}"},
        timeout=REMOTE_PUBLISH_TIMEOUT,
    )
    if not resp.ok:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        raise RemotePublishError(f"remote returned {resp.status_code}: {detail}")
    return resp.json()


def extract_mentioned_user_ids(text: str) -> set[int]:
    return {int(m.group(2)) for m in MENTION_RE.finditer(text)}


def generate_recipients(notification) -> int:
    """Generate NotificationRecipient rows based on target_type. Idempotent."""
    if notification.target_type == Notification.TargetType.ALL:
        users = User.objects.filter(is_active=True)
    elif notification.target_type == Notification.TargetType.GROUP and notification.target_group:
        users = notification.target_group.user_set.filter(is_active=True)
    elif notification.target_type == Notification.TargetType.USER:
        users = notification.target_users.filter(is_active=True)
    else:
        return 0
    recipients = [NotificationRecipient(notification=notification, user=u) for u in users]
    NotificationRecipient.objects.bulk_create(recipients, ignore_conflicts=True)
    return len(recipients)


def create_broadcast_notification(
    *,
    title: str,
    content: str = "",
    target_type: str = "all",
    target_group_id=None,
    target_user_ids=None,
    is_draft: bool = False,
    source_user=None,
):
    """Create a broadcast notification and (unless draft) materialize recipients.

    Returns (notification, recipient_count).
    """
    notification = Notification.objects.create(
        notification_type=Notification.Type.BROADCAST,
        title=title,
        content=content,
        source_user=source_user,
        target_type=target_type,
        target_group_id=target_group_id or None,
        is_draft=is_draft,
    )
    if target_type == Notification.TargetType.USER and target_user_ids:
        notification.target_users.set(target_user_ids)

    recipient_count = 0 if is_draft else generate_recipients(notification)
    return notification, recipient_count


def create_comment_mention_notifications(*, comment, old_content: str, new_content: str, actor):
    """评论中 @提及 的站内通知。只对本次新增的提及发，@自己不发。

    新增提及只对比上一版内容,反复编辑(删 @ 再加回)本可无限重发;
    故加一层短窗口去重:同一 actor 在同一 issue 上 10 分钟内对同一用户只发一次。
    """
    old_ids = extract_mentioned_user_ids(old_content)
    new_ids = extract_mentioned_user_ids(new_content)
    added_ids = new_ids - old_ids - {actor.id}
    if not added_ids:
        return

    issue = comment.issue
    users = User.objects.filter(id__in=added_ids, is_active=True)
    recently_notified = set(
        NotificationRecipient.objects.filter(
            user__in=users,
            notification__notification_type=Notification.Type.MENTION,
            notification__source_user=actor,
            notification__source_issue=issue,
            notification__created_at__gte=timezone.now() - timedelta(minutes=10),
        ).values_list("user_id", flat=True)
    )
    for user in users:
        if user.id in recently_notified:
            continue
        notification = Notification.objects.create(
            notification_type=Notification.Type.MENTION,
            title=f"{actor.name or actor.username} 在 #{issue.pk} 的评论中提到了你",
            content=MENTION_RE.sub(r"@\1", new_content)[:100],
            source_user=actor,
            source_issue=issue,
            target_type=Notification.TargetType.USER,
        )
        NotificationRecipient.objects.create(notification=notification, user=user)


def create_mention_notifications(*, issue, old_description: str, new_description: str, actor):
    old_ids = extract_mentioned_user_ids(old_description)
    new_ids = extract_mentioned_user_ids(new_description)
    added_ids = new_ids - old_ids - {actor.id}

    if not added_ids:
        return

    users = User.objects.filter(id__in=added_ids, is_active=True)
    for user in users:
        notification = Notification.objects.create(
            notification_type=Notification.Type.MENTION,
            title=f"{actor.name or actor.username} 在 #{issue.pk} 中提到了你",
            content=f"问题: {issue.title}",
            source_user=actor,
            source_issue=issue,
            target_type=Notification.TargetType.USER,
        )
        NotificationRecipient.objects.create(
            notification=notification,
            user=user,
        )
