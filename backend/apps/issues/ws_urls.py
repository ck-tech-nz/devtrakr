from django.urls import path

from .consumers import ChatConsumer, DanmakuConsumer

# WebSocket 路由(挂在 asgi.py 的 websocket 协议下)。
chat_ws_urlpatterns = [
    path("ws/chat/", ChatConsumer.as_asgi()),
    path("ws/danmaku/", DanmakuConsumer.as_asgi()),
]
