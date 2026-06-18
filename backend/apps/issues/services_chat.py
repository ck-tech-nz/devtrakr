"""聊天会话服务:参与者计算 + 评论广播。

与通知铃铛独立(不写 Notification 表)。接收走 WebSocket,
发送复用现有 REST POST .../comments/(由视图调用 broadcast_comment)。
"""
import logging

from django.contrib.auth import get_user_model

from apps.notifications.services import extract_mentioned_user_ids
from .models import IssueChatParticipant

logger = logging.getLogger(__name__)
User = get_user_model()


def participants_for_comment(comment) -> set:
    """该评论应触达的聊天参与者(不含作者过滤,由调用方决定)。

    并集:负责人 ∪ 协助人 ∪ 被@者 ∪ 已在会话中的成员;仅活跃用户。
    """
    issue = comment.issue
    users = set()
    if issue.assignee_id:
        users.add(issue.assignee)
    users.update(issue.helpers.all())
    mentioned_ids = extract_mentioned_user_ids(comment.content or "")
    if mentioned_ids:
        users.update(User.objects.filter(id__in=mentioned_ids))
    existing_ids = IssueChatParticipant.objects.filter(issue=issue).values_list("user_id", flat=True)
    if existing_ids:
        users.update(User.objects.filter(id__in=list(existing_ids)))
    return {u for u in users if u.is_active}
