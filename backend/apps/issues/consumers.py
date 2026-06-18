"""聊天 WebSocket consumer:仅推送。

连接时校验用户并加入个人组 chat_user_<id>。回复走 REST,故忽略入站消息。
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.group_name = f"chat_user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    # group_send type "comment.new" → 此方法
    async def comment_new(self, event):
        await self.send_json({
            "type": "comment.new",
            "issue_id": event["issue_id"],
            "issue_title": event["issue_title"],
            "unread_count": event["unread_count"],
            "comment": event["comment"],
        })
