"""问题动态弹幕:事件载荷构造 + WebSocket 广播。

单一全局组 danmaku(可见性为粗粒度 view_issue,权限校验在 DanmakuConsumer.connect
完成,故无需按人扇出)。与聊天广播独立。
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

DANMAKU_GROUP = "danmaku"


def _actor_name(issue, kind):
    if kind == "created":
        return issue.created_by.name if issue.created_by else None
    # completed:方案 2 不存逐事件操作者,用负责人作「责任人」代理,回退更新人
    who = issue.assignee or issue.updated_by
    return who.name if who else None


def build_payload(issue, kind):  # kind: "created" | "completed"
    occurred = issue.created_at if kind == "created" else issue.resolved_at
    return {
        "kind": kind,
        "issue_id": issue.id,
        "issue_number": f"ISS-{issue.id:03d}",  # 与前端 ISS-001 展示一致
        "title": issue.title,
        "status": issue.status,
        "actor_name": _actor_name(issue, kind),
        "occurred_at": occurred.isoformat() if occurred else None,
    }


def broadcast_issue_event(payload) -> None:
    """向全局组推送一条动态;通道层不可用或失败时静默跳过(不得影响主流程)。"""
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            DANMAKU_GROUP,
            {"type": "issue.event", "payload": payload},  # → DanmakuConsumer.issue_event
        )
    except Exception:  # noqa: BLE001 — 推送失败不得影响问题保存
        logger.warning("danmaku ws push failed", exc_info=True)
