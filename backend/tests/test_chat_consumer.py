import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db(transaction=True)


def _ws(token):
    url = f"/ws/chat/?token={token}" if token else "/ws/chat/"
    return WebsocketCommunicator(application, url)


@pytest.mark.asyncio
async def test_anonymous_is_rejected():
    comm = _ws(None)
    connected, _ = await comm.connect()
    assert connected is False


@pytest.mark.asyncio
async def test_authed_connects_and_receives_push():
    from channels.db import database_sync_to_async
    user = await database_sync_to_async(UserFactory)()
    token = str(AccessToken.for_user(user))

    comm = _ws(token)
    connected, _ = await comm.connect()
    assert connected is True

    layer = get_channel_layer()
    await layer.group_send(f"chat_user_{user.id}", {
        "type": "comment.new",
        "issue_id": 7, "issue_title": "T", "unread_count": 2,
        "comment": {"id": 1, "content": "hi"},
    })
    msg = await comm.receive_json_from(timeout=2)
    assert msg["issue_id"] == 7 and msg["unread_count"] == 2
    await comm.disconnect()
