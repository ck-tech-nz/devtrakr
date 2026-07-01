import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import Permission

from apps.issues.consumers import DanmakuConsumer
from tests.factories import UserFactory


@database_sync_to_async
def _make_user(with_perm):
    user = UserFactory()
    if with_perm:
        perm = Permission.objects.get(
            content_type__app_label="issues", codename="view_issue"
        )
        user.user_permissions.add(perm)
    return user


@pytest.mark.django_db(transaction=True)
async def test_consumer_rejects_without_view_issue():
    user = await _make_user(with_perm=False)
    communicator = WebsocketCommunicator(DanmakuConsumer.as_asgi(), "/ws/danmaku/")
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_consumer_accepts_and_receives_event():
    user = await _make_user(with_perm=True)
    communicator = WebsocketCommunicator(DanmakuConsumer.as_asgi(), "/ws/danmaku/")
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected is True
    layer = get_channel_layer()
    await layer.group_send(
        "danmaku",
        {"type": "issue.event", "payload": {"kind": "created", "issue_id": 1}},
    )
    msg = await communicator.receive_json_from(timeout=2)
    assert msg["kind"] == "created"
    assert msg["issue_id"] == 1
    await communicator.disconnect()
