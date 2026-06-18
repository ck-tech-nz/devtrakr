"""聊天会话服务:参与者计算 + 评论广播。

与通知铃铛独立(不写 Notification 表)。接收走 WebSocket,
发送复用现有 REST POST .../comments/(由视图调用 broadcast_comment)。
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

from apps.notifications.services import extract_mentioned_user_ids
from .models import IssueChatParticipant
from .serializers import IssueCommentSerializer

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


def _push_comment_ws(user_id: int, comment, unread_count: int) -> None:
    """向某用户的 WS 组推送一条新评论事件;通道层不可用时静默跳过。"""
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            f"chat_user_{user_id}",
            {
                "type": "comment.new",  # → ChatConsumer.comment_new
                "issue_id": comment.issue_id,
                "issue_title": comment.issue.title,
                "unread_count": unread_count,
                "comment": IssueCommentSerializer(comment).data,
            },
        )
    except Exception:  # noqa: BLE001 — 推送失败不得影响评论保存
        logger.warning("chat ws push failed for user %s", user_id, exc_info=True)


def broadcast_comment(comment) -> None:
    """评论创建后调用:upsert 成员行 + 作者自动已读 + 推送给其余参与者。"""
    recipients = participants_for_comment(comment)
    author = comment.author
    everyone = recipients | ({author} if author else set())

    # 第一遍:upsert 所有参与者行；缓存到 dict 供推送遍历复用，避免重复查询
    parts: dict[int, IssueChatParticipant] = {}
    for user in everyone:
        part, _ = IssueChatParticipant.objects.get_or_create(issue=comment.issue, user=user)
        if author and user.id == author.id:
            part.last_read_comment = comment   # 自己发的自动已读
            part.save(update_fields=["last_read_comment", "updated_at"])
        else:
            part.save(update_fields=["updated_at"])  # bump 排序
        parts[user.id] = part

    # 推送给所有参与者(含作者本人)。作者自己的消息 unread_count=0(已自动已读),
    # 前端据此不弹预览条/不计未读,仅让作者本人的会话列表与线程实时回显自己的发言。
    for user in everyone:
        part = parts[user.id]  # 复用第一遍已获取的行
        _push_comment_ws(user.id, comment, part.unread_count())
