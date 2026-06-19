"""ASGI config: HTTP(Django) + WebSocket(Channels)."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# get_asgi_application() 必须在 settings 就绪后、且在导入任何用到 ORM 的
# 模块(consumers / ws_auth)之前调用。
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from apps.issues.ws_auth import JWTAuthMiddleware  # noqa: E402
from apps.issues.ws_urls import chat_ws_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(URLRouter(chat_ws_urlpatterns)),
})
