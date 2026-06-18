# Issue Chat (评论弹窗 + 可聊天) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an issue gets a new comment, its assignee, helpers, and any `@`-mentioned users see a real-time right-bottom chat bubble and can reply inline (= add a comment).

**Architecture:** Django Channels adds a WebSocket push channel on top of the already-ASGI (uvicorn) backend. A new `IssueChatParticipant` table doubles as conversation membership + per-user read pointer (Fork A1). Replies are sent over the existing REST `POST .../comments/` (Fork B1); after a comment is created the server broadcasts it to each participant's `chat_user_<id>` group. A Nuxt `useChat` composable holds a WebSocket + conversation state and drives a global `ChatBubble` component.

**Tech Stack:** Django 6 / DRF / SimpleJWT / Django Channels + channels-redis / Redis (existing Celery broker, DB `/1`) / uvicorn (prod) + daphne (dev runserver) / Nuxt 4 SPA / `@nuxt/ui` v3 / Vitest + `@nuxt/test-utils`.

## Global Constraints

- Backend package manager is `uv` (run `uv run …`, never `pip`). Python `>=3.14`, Django `>=6.0,<7.0`.
- **Migrations:** use `makemigrations` (never hand-write generated migrations; never edit an existing one — add a new one).
- Frontend language is Chinese (zh-hans); skills/docs in English, code comments + UI text in Chinese.
- Frontend gate is `npm run test` (vitest). `npx nuxi typecheck` is already red on `main` from a Nuxt UI bump — do not treat pre-existing typecheck errors as new.
- Chat is **independent of the notification bell**: it does **not** write `Notification`/`NotificationRecipient` rows. The existing `create_comment_mention_notifications` call stays untouched (mentions still hit the bell in parallel).
- Comment `id` is monotonic; "newer than X" == `id__gt=X`. Issues have **no** `number` field — display id as `ISS-{id}`.
- `broadcast_comment` must **degrade gracefully**: if the channel layer is unavailable, the comment is still saved and the request still succeeds.
- **Compat risk (verify early):** Python 3.14 + Django 6 + Channels/daphne/twisted is bleeding-edge. Task 1 installs and boots; if resolution/boot fails, STOP and report — do not silently drop WebSockets.

**Spec:** `docs/superpowers/specs/2026-06-18-issue-chat-design.md`. **Visual reference (canonical for styling/CSS values):** `docs/superpowers/specs/2026-06-18-issue-chat-mockup.html`.

---

## File Structure

**Backend**
- `backend/pyproject.toml` — add `channels[daphne]`, `channels-redis`; dev `pytest-asyncio`.
- `backend/config/settings.py` — `daphne` (top of INSTALLED_APPS) + `channels`; `ASGI_APPLICATION`; `CHANNEL_LAYERS`.
- `backend/config/asgi.py` — `ProtocolTypeRouter` (http + websocket).
- `backend/apps/issues/ws_auth.py` — **create** — `JWTAuthMiddleware` (query-string token → `scope["user"]`).
- `backend/apps/issues/consumers.py` — **create** — `ChatConsumer` (join `chat_user_<id>`, push-only).
- `backend/apps/issues/ws_urls.py` — **create** — `chat_ws_urlpatterns` (`ws/chat/`).
- `backend/apps/issues/models.py` — **modify** — `IssueChatParticipant` + `unread_count()`.
- `backend/apps/issues/services_chat.py` — **create** — `participants_for_comment`, `broadcast_comment`, `conversations_for`, `_push_comment_ws`.
- `backend/apps/issues/serializers.py` — **modify** — `ChatConversationSerializer`.
- `backend/apps/issues/views.py` — **modify** — `ChatConversationsView`, `ChatUnreadTotalView`, `ChatMarkReadView`; hook `broadcast_comment` into `IssueCommentsView.post`.
- `backend/apps/issues/urls.py` — **modify** — chat routes.
- `backend/tests/conftest.py` — **modify** — autouse in-memory channel-layer fixture.
- `backend/tests/test_issue_chat.py` — **create** — model/services/endpoints.
- `backend/tests/test_chat_consumer.py` — **create** — consumer + auth.

**Frontend**
- `frontend/app/composables/useChat.ts` — **create** — WS + REST + state.
- `frontend/app/components/chat/ChatBubble.vue` — **create** — FAB + panel + list.
- `frontend/app/components/chat/ChatThread.vue` — **create** — thread + `@`-mention composer.
- `frontend/app/components/chat/ChatPreviewToast.vue` — **create** — preview bar + ding.
- `frontend/app/app.vue` — **modify** — mount `<ChatBubble>` when authenticated.
- `frontend/nuxt.config.ts` — **modify** — `/ws/` proxy (devProxy + routeRules).
- `frontend/tests/useChat.test.ts` — **create**.
- `frontend/tests/chatBubble.test.ts` — **create**.

---

## Task 1: Channels infrastructure (deps, settings, ASGI routing)

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/config/settings.py:21-51` (INSTALLED_APPS), after `WSGI_APPLICATION` (line 83)
- Modify: `backend/config/asgi.py`
- Create: `backend/apps/issues/ws_urls.py`
- Test: `backend/tests/test_chat_consumer.py` (smoke part)

**Interfaces:**
- Produces: `config.asgi.application` is a `ProtocolTypeRouter` with `"http"` and `"websocket"` keys; `chat_ws_urlpatterns` (list) importable from `apps.issues.ws_urls`; `settings.CHANNEL_LAYERS["default"]`.

- [ ] **Step 1: Install dependencies**

```bash
cd backend
uv add 'channels[daphne]>=4.1,<5.0' 'channels-redis>=4.2,<5.0'
uv add --dev 'pytest-asyncio>=0.24,<1.0'
```
Expected: `uv` resolves and writes `pyproject.toml` + `uv.lock`. If resolution fails on Python 3.14, STOP and report (see Global Constraints compat risk).

- [ ] **Step 2: Register apps + ASGI settings**

In `backend/config/settings.py`, make `daphne` the **first** entry of `INSTALLED_APPS` (so `manage.py runserver` serves ASGI/WebSocket in dev) and add `channels`:

```python
INSTALLED_APPS = [
    "daphne",   # 必须在最前:让 runserver 走 ASGI 以支持 WebSocket(dev)
    # ... existing entries ...
    "channels",
]
```

After the `WSGI_APPLICATION = "config.wsgi.application"` line, add:

```python
ASGI_APPLICATION = "config.asgi.application"

# Channels 通道层:复用 Celery 的 Redis,另用 DB /1。
# 测试经 conftest 改用 InMemoryChannelLayer(无需 Redis)。
CHANNEL_REDIS_URL = os.environ.get("CHANNEL_REDIS_URL", "redis://127.0.0.1:6379/1")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [CHANNEL_REDIS_URL]},
    }
}
```

- [ ] **Step 3: Create the WebSocket URL router**

Create `backend/apps/issues/ws_urls.py`:

```python
from django.urls import path

from .consumers import ChatConsumer

# WebSocket 路由(挂在 asgi.py 的 websocket 协议下)。
chat_ws_urlpatterns = [
    path("ws/chat/", ChatConsumer.as_asgi()),
]
```

- [ ] **Step 4: Wire ASGI ProtocolTypeRouter**

Replace the body of `backend/config/asgi.py` with:

```python
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
```

(`JWTAuthMiddleware` and `ChatConsumer` are created in Task 5; this file will not import cleanly until then. That is expected — Task 5 closes the loop. Do Tasks 2–5 before running the Step 6 smoke test.)

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/config/settings.py backend/config/asgi.py backend/apps/issues/ws_urls.py
git commit -m "feat(chat): add Channels deps + ASGI websocket routing scaffold"
```

- [ ] **Step 6: Deferred smoke test** — covered by Task 5 Step (consumer test imports `config.asgi.application`). No standalone run here.

---

## Task 2: `IssueChatParticipant` model + unread count

**Files:**
- Modify: `backend/apps/issues/models.py` (after `IssueComment`, ~line 214)
- Create: migration via `makemigrations`
- Test: `backend/tests/test_issue_chat.py`

**Interfaces:**
- Produces: `IssueChatParticipant(issue, user, last_read_comment, created_at, updated_at)`; method `unread_count() -> int`; reverse names `issue.chat_participants`, `user.issue_chats`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_issue_chat.py`:

```python
import pytest

from apps.issues.models import IssueChatParticipant
from tests.factories import IssueFactory, IssueCommentFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_unread_count_excludes_own_and_counts_newer():
    issue = IssueFactory()
    me = UserFactory()
    other = UserFactory()
    c1 = IssueCommentFactory(issue=issue, author=other)
    part = IssueChatParticipant.objects.create(issue=issue, user=me, last_read_comment=c1)
    # 一条别人的新评论 + 一条自己的评论
    IssueCommentFactory(issue=issue, author=other)   # 未读 +1
    IssueCommentFactory(issue=issue, author=me)       # 自己的不计
    assert part.unread_count() == 1


def test_unread_count_none_pointer_counts_all_others():
    issue = IssueFactory()
    me = UserFactory()
    other = UserFactory()
    IssueCommentFactory(issue=issue, author=other)
    IssueCommentFactory(issue=issue, author=other)
    part = IssueChatParticipant.objects.create(issue=issue, user=me, last_read_comment=None)
    assert part.unread_count() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -v`
Expected: FAIL — `ImportError: cannot import name 'IssueChatParticipant'`.

- [ ] **Step 3: Add the model**

In `backend/apps/issues/models.py`, after the `IssueComment` class:

```python
class IssueChatParticipant(models.Model):
    """聊天会话成员 + 已读指针。一行 = 某用户参与某问题的评论会话。"""
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="chat_participants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="issue_chats"
    )
    last_read_comment = models.ForeignKey(
        IssueComment, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("issue", "user")]
        indexes = [models.Index(fields=["user", "-updated_at"])]

    def unread_count(self) -> int:
        """该会话对本用户的未读评论数:比指针更新、且非本人所发。"""
        qs = self.issue.comments.exclude(author_id=self.user_id)
        if self.last_read_comment_id:
            qs = qs.filter(id__gt=self.last_read_comment_id)
        return qs.count()
```

Confirm `from django.conf import settings` is already imported in this file (it is — `assignee` uses `settings.AUTH_USER_MODEL`).

- [ ] **Step 4: Generate + apply migration**

Run:
```bash
cd backend && uv run python manage.py makemigrations issues && uv run python manage.py migrate
```
Expected: a new `issues/migrations/00XX_issuechatparticipant.py`; migrate OK.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/issues/models.py backend/apps/issues/migrations/ backend/tests/test_issue_chat.py
git commit -m "feat(chat): IssueChatParticipant model with unread_count"
```

---

## Task 3: `participants_for_comment` service

**Files:**
- Create: `backend/apps/issues/services_chat.py`
- Test: `backend/tests/test_issue_chat.py`

**Interfaces:**
- Consumes: `apps.notifications.services.extract_mentioned_user_ids`; `IssueChatParticipant`.
- Produces: `participants_for_comment(comment) -> set[User]` — assignee ∪ helpers ∪ mentioned ∪ existing chat participants, active users only (author NOT filtered out here; callers decide).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_issue_chat.py`:

```python
from apps.issues.services_chat import participants_for_comment


def test_participants_union_assignee_helpers_mentions():
    assignee = UserFactory()
    helper = UserFactory()
    mentioned = UserFactory()
    author = UserFactory()
    issue = IssueFactory(assignee=assignee)
    issue.helpers.add(helper)
    content = f"看下 @[{mentioned.name}](user:{mentioned.id})"
    comment = IssueCommentFactory(issue=issue, author=author, content=content)

    result = participants_for_comment(comment)
    assert {assignee, helper, mentioned}.issubset(result)


def test_participants_includes_existing_participants_and_skips_inactive():
    issue = IssueFactory(assignee=None)
    existing = UserFactory()
    inactive = UserFactory(is_active=False)
    IssueChatParticipant.objects.create(issue=issue, user=existing)
    IssueChatParticipant.objects.create(issue=issue, user=inactive)
    comment = IssueCommentFactory(issue=issue)

    result = participants_for_comment(comment)
    assert existing in result
    assert inactive not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -k participants -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.issues.services_chat'`.

- [ ] **Step 3: Create the service**

Create `backend/apps/issues/services_chat.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -k participants -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services_chat.py backend/tests/test_issue_chat.py
git commit -m "feat(chat): participants_for_comment service"
```

---

## Task 4: `broadcast_comment` (upsert membership + read pointer + push)

**Files:**
- Modify: `backend/apps/issues/services_chat.py`
- Modify: `backend/tests/conftest.py` (autouse in-memory channel layer)
- Test: `backend/tests/test_issue_chat.py`

**Interfaces:**
- Consumes: `participants_for_comment`; `channels.layers.get_channel_layer`; `asgiref.sync.async_to_sync`; `IssueCommentSerializer` (Task uses it for the WS payload).
- Produces: `broadcast_comment(comment) -> None`; `_push_comment_ws(user_id, comment, unread_count) -> None`; group name convention `chat_user_{id}`; WS event dict shape (below).

- [ ] **Step 1: Add the autouse channel-layer fixture**

In `backend/tests/conftest.py`, append:

```python
@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings):
    """所有测试用进程内通道层,避免依赖 Redis。"""
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
```

(Confirm `import pytest` is present at the top of conftest — it is.)

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_issue_chat.py`:

```python
from apps.issues.services_chat import broadcast_comment


def test_broadcast_creates_rows_and_marks_author_read():
    assignee = UserFactory()
    author = UserFactory()
    issue = IssueFactory(assignee=assignee)
    comment = IssueCommentFactory(issue=issue, author=author)

    broadcast_comment(comment)

    # 作者与负责人都有成员行
    author_row = IssueChatParticipant.objects.get(issue=issue, user=author)
    assignee_row = IssueChatParticipant.objects.get(issue=issue, user=assignee)
    # 作者自己的评论自动已读;负责人未读=1
    assert author_row.last_read_comment_id == comment.id
    assert author_row.unread_count() == 0
    assert assignee_row.unread_count() == 1


def test_broadcast_is_safe_when_channel_layer_missing(settings):
    settings.CHANNEL_LAYERS = {}  # get_channel_layer() -> None
    issue = IssueFactory(assignee=UserFactory())
    comment = IssueCommentFactory(issue=issue)
    # 不应抛异常
    broadcast_comment(comment)
    assert IssueChatParticipant.objects.filter(issue=issue).exists()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -k broadcast -v`
Expected: FAIL — `ImportError: cannot import name 'broadcast_comment'`.

- [ ] **Step 4: Implement broadcast**

Append to `backend/apps/issues/services_chat.py`:

```python
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .serializers import IssueCommentSerializer


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

    for user in everyone:
        part, _ = IssueChatParticipant.objects.get_or_create(issue=comment.issue, user=user)
        if author and user.id == author.id:
            part.last_read_comment = comment   # 自己发的自动已读
            part.save(update_fields=["last_read_comment", "updated_at"])
        else:
            part.save(update_fields=["updated_at"])  # bump 排序

    for user in recipients:
        if author and user.id == author.id:
            continue
        part = IssueChatParticipant.objects.get(issue=comment.issue, user=user)
        _push_comment_ws(user.id, comment, part.unread_count())
```

Note the `comment.new` → handler `comment_new` mapping is implemented in Task 5's consumer.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -k broadcast -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/issues/services_chat.py backend/tests/conftest.py backend/tests/test_issue_chat.py
git commit -m "feat(chat): broadcast_comment upserts membership, marks author read, pushes WS"
```

---

## Task 5: WebSocket auth middleware + ChatConsumer

**Files:**
- Create: `backend/apps/issues/ws_auth.py`
- Create: `backend/apps/issues/consumers.py`
- Test: `backend/tests/test_chat_consumer.py`

**Interfaces:**
- Consumes: `chat_user_{id}` group convention; `comment.new` event type.
- Produces: `JWTAuthMiddleware(app)` (sets `scope["user"]` from `?token=`); `ChatConsumer` joins `chat_user_<id>`, rejects anonymous with close code 4401, forwards `comment.new` events to the socket.

- [ ] **Step 1: Create the JWT WebSocket middleware**

Create `backend/apps/issues/ws_auth.py`:

```python
"""WebSocket JWT 鉴权中间件:从 query string 的 ?token= 解析 access token。

项目认证为 JWT(非 session),故 WS 不能用 Channels 默认的 session 中间件。
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

User = get_user_model()


@database_sync_to_async
def _get_user(user_id):
    try:
        return User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError

        scope["user"] = AnonymousUser()
        qs = parse_qs(scope.get("query_string", b"").decode())
        token = (qs.get("token") or [None])[0]
        if token:
            try:
                access = AccessToken(token)
                scope["user"] = await _get_user(access["user_id"])
            except TokenError:
                pass
        return await super().__call__(scope, receive, send)
```

- [ ] **Step 2: Create the consumer**

Create `backend/apps/issues/consumers.py`:

```python
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
```

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_chat_consumer.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify behavior**

Run: `cd backend && uv run pytest tests/test_chat_consumer.py -v`
Expected: PASS (2 passed). This also confirms `config.asgi.application` (Task 1) imports cleanly now that `ws_auth`/`consumers` exist.

If `pytest-asyncio` does not pick up `@pytest.mark.asyncio`, add to `backend/pyproject.toml` under `[tool.pytest.ini_options]`: `asyncio_mode = "auto"` (and re-run).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/ws_auth.py backend/apps/issues/consumers.py backend/tests/test_chat_consumer.py backend/pyproject.toml
git commit -m "feat(chat): JWT WS middleware + push-only ChatConsumer"
```

---

## Task 6: Chat REST endpoints (conversations, unread-total, mark-read)

**Files:**
- Modify: `backend/apps/issues/serializers.py` (append)
- Modify: `backend/apps/issues/views.py` (append views; imports)
- Modify: `backend/apps/issues/urls.py`
- Test: `backend/tests/test_issue_chat.py`

**Interfaces:**
- Consumes: `IssueChatParticipant`, `IssueCommentSerializer`.
- Produces: `GET /api/issues/chat/conversations/`, `GET /api/issues/chat/unread-total/`, `POST /api/issues/chat/conversations/<issue_id>/read/`. Conversation item shape: `{issue_id, issue_title, last_comment, unread_count}`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_issue_chat.py`:

```python
def test_conversations_endpoint_lists_with_unread(auth_client, auth_user):
    issue = IssueFactory()
    other = UserFactory()
    c1 = IssueCommentFactory(issue=issue, author=other)
    IssueChatParticipant.objects.create(issue=issue, user=auth_user, last_read_comment=c1)
    IssueCommentFactory(issue=issue, author=other)  # 未读 +1

    resp = auth_client.get("/api/issues/chat/conversations/")
    assert resp.status_code == 200
    items = resp.json()["results"] if isinstance(resp.json(), dict) else resp.json()
    row = next(r for r in items if r["issue_id"] == issue.id)
    assert row["unread_count"] == 1
    assert row["issue_title"] == issue.title
    assert row["last_comment"]["content"]


def test_unread_total_endpoint(auth_client, auth_user):
    issue = IssueFactory()
    other = UserFactory()
    IssueChatParticipant.objects.create(issue=issue, user=auth_user)
    IssueCommentFactory(issue=issue, author=other)

    resp = auth_client.get("/api/issues/chat/unread-total/")
    assert resp.status_code == 200
    assert resp.json()["unread_total"] == 1


def test_mark_read_advances_pointer(auth_client, auth_user):
    issue = IssueFactory()
    other = UserFactory()
    IssueChatParticipant.objects.create(issue=issue, user=auth_user)
    latest = IssueCommentFactory(issue=issue, author=other)

    resp = auth_client.post(f"/api/issues/chat/conversations/{issue.id}/read/")
    assert resp.status_code == 200
    part = IssueChatParticipant.objects.get(issue=issue, user=auth_user)
    assert part.last_read_comment_id == latest.id
    assert part.unread_count() == 0
```

(The `auth_client` / `auth_user` fixtures already exist in `conftest.py`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -k "conversations or unread_total or mark_read" -v`
Expected: FAIL — 404 (routes not defined).

- [ ] **Step 3: Add the serializer**

Append to `backend/apps/issues/serializers.py` (it already imports `IssueComment`, `IssueChatParticipant` is new — add the import):

```python
class ChatConversationSerializer(serializers.Serializer):
    """聊天会话列表项。期望传入已 annotate 的 IssueChatParticipant 实例。"""
    issue_id = serializers.IntegerField()  # 直接读 IssueChatParticipant.issue_id
    issue_title = serializers.CharField(source="issue.title")
    unread_count = serializers.SerializerMethodField()
    last_comment = serializers.SerializerMethodField()

    def get_unread_count(self, obj):
        return obj.unread_count()

    def get_last_comment(self, obj):
        last = obj.issue.comments.select_related("author").last()
        return IssueCommentSerializer(last).data if last else None
```

- [ ] **Step 4: Add the views**

In `backend/apps/issues/views.py`, add to the model import line `IssueChatParticipant`, and to the serializer imports `ChatConversationSerializer`. Append:

```python
class ChatConversationsView(APIView):
    """GET: 我参与且有评论的会话列表(按最近活动倒序)。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        parts = (
            IssueChatParticipant.objects
            .filter(user=request.user, issue__comments__isnull=False)
            .select_related("issue")
            .distinct()
            .order_by("-updated_at")
        )
        data = ChatConversationSerializer(parts, many=True).data
        return Response({"results": data})


class ChatUnreadTotalView(APIView):
    """GET: 跨所有会话的未读总数(供气泡角标)。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        parts = IssueChatParticipant.objects.filter(user=request.user).select_related("issue")
        total = sum(p.unread_count() for p in parts)
        return Response({"unread_total": total})


class ChatMarkReadView(APIView):
    """POST: 把某会话已读指针推进到最新评论。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, issue_id):
        part = IssueChatParticipant.objects.filter(user=request.user, issue_id=issue_id).first()
        if not part:
            return Response({"detail": "会话不存在"}, status=status.HTTP_404_NOT_FOUND)
        latest = part.issue.comments.last()
        part.last_read_comment = latest
        part.save(update_fields=["last_read_comment", "updated_at"])
        return Response({"unread_count": part.unread_count()})
```

- [ ] **Step 5: Add the routes**

In `backend/apps/issues/urls.py`, import the three views and add (place **before** the `<int:pk>/` route so `chat/` is not captured as a pk):

```python
    path("chat/conversations/", ChatConversationsView.as_view(), name="chat-conversations"),
    path("chat/unread-total/", ChatUnreadTotalView.as_view(), name="chat-unread-total"),
    path("chat/conversations/<int:issue_id>/read/", ChatMarkReadView.as_view(), name="chat-mark-read"),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -v`
Expected: PASS (all chat tests).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/issues/serializers.py backend/apps/issues/views.py backend/apps/issues/urls.py backend/tests/test_issue_chat.py
git commit -m "feat(chat): conversations / unread-total / mark-read REST endpoints"
```

---

## Task 7: Hook `broadcast_comment` into comment creation

**Files:**
- Modify: `backend/apps/issues/views.py` (`IssueCommentsView.post`, ~line 598-602)
- Test: `backend/tests/test_issue_chat.py`

**Interfaces:**
- Consumes: `broadcast_comment` (Task 4).
- Produces: posting a comment creates participant rows + unread for assignee/helpers/mentioned; author auto-read.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_issue_chat.py`:

```python
def test_posting_comment_notifies_assignee(auth_client, auth_user):
    assignee = UserFactory()
    issue = IssueFactory(assignee=assignee)  # auth_user 作为作者

    resp = auth_client.post(
        f"/api/issues/{issue.id}/comments/", {"content": "请看下这个问题"}, format="json"
    )
    assert resp.status_code == 201
    assignee_row = IssueChatParticipant.objects.get(issue=issue, user=assignee)
    author_row = IssueChatParticipant.objects.get(issue=issue, user=auth_user)
    assert assignee_row.unread_count() == 1
    assert author_row.unread_count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -k posting_comment -v`
Expected: FAIL — `IssueChatParticipant.DoesNotExist` (no rows created yet).

- [ ] **Step 3: Add the broadcast call**

In `backend/apps/issues/views.py`, add the import near the other issue service imports: `from .services_chat import broadcast_comment`. Then in `IssueCommentsView.post`, immediately after the existing `create_comment_mention_notifications(...)` call and before `return Response(...)`:

```python
        broadcast_comment(comment)  # 推送聊天气泡(独立于通知铃铛)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_issue_chat.py -k posting_comment -v`
Expected: PASS.

- [ ] **Step 5: Run the full chat + comments suite (no regressions)**

Run: `cd backend && uv run pytest tests/test_issue_chat.py tests/test_chat_consumer.py -v` and `uv run pytest -k comment -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/issues/views.py backend/tests/test_issue_chat.py
git commit -m "feat(chat): broadcast new comments to participants on POST"
```

---

## Task 8: `useChat` composable — REST state (no WS yet)

**Files:**
- Create: `frontend/app/composables/useChat.ts`
- Test: `frontend/tests/useChat.test.ts`

**Interfaces:**
- Consumes: auto-imported `useApi().api`.
- Produces: `useChat()` returning `{ conversations, unreadTotal, activeIssueId, messages, loadConversations, openConversation, sendReply, markRead, handleIncoming }` (all refs/functions). `handleIncoming(event)` is the WS-event entry point (wired in Task 9).

Types:
```ts
interface ChatComment { id: number; author: number | null; author_name: string | null; author_avatar: string; content: string; created_at: string; updated_at: string; is_edited: boolean }
interface ChatConversation { issue_id: number; issue_title: string; unread_count: number; last_comment: ChatComment | null }
interface ChatIncoming { type: 'comment.new'; issue_id: number; issue_title: string; unread_count: number; comment: ChatComment }
```

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/useChat.test.ts`:

```ts
// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { useChat } from '../app/composables/useChat'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

beforeEach(() => { apiMock.mockReset() })

function conv(over = {}) {
  return { issue_id: 1, issue_title: 'T', unread_count: 2, last_comment: null, ...over }
}

describe('useChat REST', () => {
  it('loads conversations and totals unread', async () => {
    apiMock.mockResolvedValueOnce({ results: [conv({ issue_id: 1, unread_count: 2 }), conv({ issue_id: 2, unread_count: 3 })] })
    const c = useChat()
    await c.loadConversations()
    expect(c.conversations.value.length).toBe(2)
    expect(c.unreadTotal.value).toBe(5)
  })

  it('handleIncoming bumps conversation + unread when not active', async () => {
    const c = useChat()
    c.activeIssueId.value = null
    c.handleIncoming({ type: 'comment.new', issue_id: 9, issue_title: 'Z', unread_count: 1, comment: { id: 5, content: 'hi' } as any })
    expect(c.unreadTotal.value).toBe(1)
    expect(c.conversations.value[0].issue_id).toBe(9)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- useChat`
Expected: FAIL — cannot resolve `../app/composables/useChat`.

- [ ] **Step 3: Implement the composable (REST + state + handleIncoming)**

Create `frontend/app/composables/useChat.ts`:

```ts
// 聊天会话状态:会话列表、未读、当前会话消息。WebSocket 连接在 Task 9 加入。
// 回复走现有 REST POST .../comments/(Fork B1),接收走 WS(Task 9)。
export interface ChatComment {
  id: number; author: number | null; author_name: string | null; author_avatar: string
  content: string; created_at: string; updated_at: string; is_edited: boolean
}
export interface ChatConversation {
  issue_id: number; issue_title: string; unread_count: number; last_comment: ChatComment | null
}
export interface ChatIncoming {
  type: 'comment.new'; issue_id: number; issue_title: string; unread_count: number; comment: ChatComment
}

export function useChat() {
  const { api } = useApi()
  const conversations = useState<ChatConversation[]>('chat-conversations', () => [])
  const unreadTotal = useState<number>('chat-unread-total', () => 0)
  const activeIssueId = useState<number | null>('chat-active', () => null)
  const messages = useState<ChatComment[]>('chat-messages', () => [])
  const lastIncoming = useState<ChatIncoming | null>('chat-last-incoming', () => null)

  function recomputeTotal() {
    unreadTotal.value = conversations.value.reduce((s, c) => s + (c.unread_count || 0), 0)
  }

  async function loadConversations() {
    const data = await api<{ results: ChatConversation[] }>('/api/issues/chat/conversations/')
    conversations.value = data.results || []
    recomputeTotal()
  }

  async function openConversation(issueId: number) {
    activeIssueId.value = issueId
    messages.value = await api<ChatComment[]>(`/api/issues/${issueId}/comments/`)
    await markRead(issueId)
  }

  async function markRead(issueId: number) {
    await api(`/api/issues/chat/conversations/${issueId}/read/`, { method: 'POST' })
    const conv = conversations.value.find(c => c.issue_id === issueId)
    if (conv) conv.unread_count = 0
    recomputeTotal()
  }

  async function sendReply(issueId: number, content: string) {
    const created = await api<ChatComment>(`/api/issues/${issueId}/comments/`, {
      method: 'POST', body: { content },
    })
    if (activeIssueId.value === issueId) messages.value.push(created)
    return created
  }

  // WS 事件入口(Task 9 wiring 调用)。
  function handleIncoming(ev: ChatIncoming) {
    lastIncoming.value = ev
    if (activeIssueId.value === ev.issue_id) {
      messages.value.push(ev.comment)
      markRead(ev.issue_id)
      return
    }
    let conv = conversations.value.find(c => c.issue_id === ev.issue_id)
    if (!conv) {
      conv = { issue_id: ev.issue_id, issue_title: ev.issue_title, unread_count: 0, last_comment: ev.comment }
      conversations.value.unshift(conv)
    } else {
      conv.last_comment = ev.comment
      conversations.value = [conv, ...conversations.value.filter(c => c.issue_id !== ev.issue_id)]
    }
    conv.unread_count = ev.unread_count
    recomputeTotal()
  }

  return { conversations, unreadTotal, activeIssueId, messages, lastIncoming,
           loadConversations, openConversation, markRead, sendReply, handleIncoming }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- useChat`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/composables/useChat.ts frontend/tests/useChat.test.ts
git commit -m "feat(chat): useChat composable (REST state + incoming handler)"
```

---

## Task 9: WebSocket connection in `useChat`

**Files:**
- Modify: `frontend/app/composables/useChat.ts`
- Test: `frontend/tests/useChat.test.ts`

**Interfaces:**
- Consumes: `localStorage` `access_token`; `useApi` refresh (implicit). Produces: `connect()`, `disconnect()` on the `useChat` return; auto-reconnect with backoff; on `comment.new` calls `handleIncoming`.

- [ ] **Step 1: Write the failing test (mock WebSocket)**

Append to `frontend/tests/useChat.test.ts`:

```ts
describe('useChat WebSocket', () => {
  it('connect opens a socket and routes comment.new to handleIncoming', async () => {
    const sockets: any[] = []
    class FakeWS {
      url: string; onopen: any; onmessage: any; onclose: any; readyState = 1
      constructor(url: string) { this.url = url; sockets.push(this) }
      close() { this.readyState = 3 }
    }
    vi.stubGlobal('WebSocket', FakeWS as any)
    vi.stubGlobal('localStorage', { getItem: () => 'tok123' } as any)

    const c = useChat()
    c.connect()
    expect(sockets[0].url).toContain('/ws/chat/?token=tok123')

    sockets[0].onmessage({ data: JSON.stringify({ type: 'comment.new', issue_id: 3, issue_title: 'W', unread_count: 1, comment: { id: 1, content: 'x' } }) })
    expect(c.conversations.value.find(v => v.issue_id === 3)?.unread_count).toBe(1)
    c.disconnect()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- useChat`
Expected: FAIL — `c.connect is not a function`.

- [ ] **Step 3: Add connection logic**

In `frontend/app/composables/useChat.ts`, inside `useChat()` before `return`:

```ts
  let ws: WebSocket | null = null
  let retry = 0
  let closedByUs = false

  function wsUrl() {
    const token = (typeof localStorage !== 'undefined' && localStorage.getItem('access_token')) || ''
    const proto = (typeof location !== 'undefined' && location.protocol === 'https:') ? 'wss' : 'ws'
    const host = typeof location !== 'undefined' ? location.host : ''
    return `${proto}://${host}/ws/chat/?token=${token}`
  }

  function connect() {
    if (typeof WebSocket === 'undefined') return
    closedByUs = false
    ws = new WebSocket(wsUrl())
    ws.onopen = () => { retry = 0 }
    ws.onmessage = (e: MessageEvent) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev?.type === 'comment.new') handleIncoming(ev as ChatIncoming)
      } catch { /* ignore malformed */ }
    }
    ws.onclose = () => {
      if (closedByUs) return
      // 退避重连(token 可能已过期 → useApi 后续请求会刷新;此处直接用最新 token 重连)
      retry = Math.min(retry + 1, 6)
      setTimeout(connect, Math.min(1000 * 2 ** retry, 30000))
    }
  }

  function disconnect() {
    closedByUs = true
    ws?.close()
    ws = null
  }
```

Add `connect, disconnect` to the returned object.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- useChat`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/composables/useChat.ts frontend/tests/useChat.test.ts
git commit -m "feat(chat): useChat WebSocket connect/reconnect + message routing"
```

---

## Task 10: ChatBubble + ChatThread + ChatPreviewToast components

**Files:**
- Create: `frontend/app/components/chat/ChatBubble.vue`
- Create: `frontend/app/components/chat/ChatThread.vue`
- Create: `frontend/app/components/chat/ChatPreviewToast.vue`
- Test: `frontend/tests/chatBubble.test.ts`

**Interfaces:**
- Consumes: `useChat()`; `useMentionMarkdown()` (existing, for rendering); `MentionDropdown.vue` (existing). Produces: `<ChatBubble>` self-contained widget. Visual/CSS reference: copy values from `docs/superpowers/specs/2026-06-18-issue-chat-mockup.html`.

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/chatBubble.test.ts`:

```ts
// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import ChatBubble from '../app/components/chat/ChatBubble.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

beforeEach(() => { apiMock.mockReset(); apiMock.mockResolvedValue({ results: [] }) })

describe('ChatBubble', () => {
  it('shows unread badge from useChat state', async () => {
    apiMock.mockResolvedValueOnce({ results: [
      { issue_id: 1, issue_title: 'A', unread_count: 2, last_comment: null },
      { issue_id: 2, issue_title: 'B', unread_count: 1, last_comment: null },
    ] })
    const w = await mountSuspended(ChatBubble)
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('[data-test="fab-badge"]').text()).toBe('3')
  })

  it('toggles panel open on FAB click', async () => {
    const w = await mountSuspended(ChatBubble)
    expect(w.find('[data-test="chat-panel"]').exists()).toBe(false)
    await w.find('[data-test="fab"]').trigger('click')
    expect(w.find('[data-test="chat-panel"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- chatBubble`
Expected: FAIL — cannot resolve `ChatBubble.vue`.

- [ ] **Step 3: Create ChatPreviewToast.vue**

Create `frontend/app/components/chat/ChatPreviewToast.vue`:

```vue
<script setup lang="ts">
import type { ChatIncoming } from '~/composables/useChat'
const props = defineProps<{ event: ChatIncoming | null }>()
const emit = defineEmits<{ open: [issueId: number] }>()
const visible = ref(false)
let timer: any = null

// 合成"叮"提示音(无需音频资源),受浏览器自动播放策略限制(首次交互后才响)。
function ding() {
  try {
    const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext
    const ac = new Ctx(); const now = ac.currentTime
    ;[[880, 0], [1320, 0.09]].forEach(([f, t]) => {
      const o = ac.createOscillator(), g = ac.createGain()
      o.type = 'sine'; o.frequency.value = f as number
      o.connect(g); g.connect(ac.destination)
      g.gain.setValueAtTime(0, now + (t as number))
      g.gain.linearRampToValueAtTime(0.18, now + (t as number) + 0.015)
      g.gain.exponentialRampToValueAtTime(0.0001, now + (t as number) + 0.32)
      o.start(now + (t as number)); o.stop(now + (t as number) + 0.34)
    })
  } catch { /* autoplay blocked */ }
}

watch(() => props.event, (ev) => {
  if (!ev) return
  visible.value = true
  ding()
  clearTimeout(timer)
  timer = setTimeout(() => (visible.value = false), 5000)
})
</script>

<template>
  <Transition name="chat-toast">
    <div v-if="visible && event" class="chat-toast" data-test="preview-toast"
         @click="emit('open', event.issue_id); visible = false">
      <div class="ct-av">{{ (event.comment.author_name || '?').slice(0, 1) }}</div>
      <div class="ct-body">
        <div class="ct-name">{{ event.comment.author_name }}<span class="ct-iss">ISS-{{ event.issue_id }}</span></div>
        <div class="ct-msg">{{ event.comment.content }}</div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.chat-toast { position: fixed; right: 24px; bottom: 104px; z-index: 45; width: 320px; display: flex; gap: 11px;
  background: var(--ui-bg, #fff); border: 1px solid var(--ui-border, #e4e8ef); border-radius: 14px; padding: 13px 14px;
  box-shadow: 0 24px 60px -16px rgba(15,23,42,.32); cursor: pointer; }
.ct-av { width: 38px; height: 38px; border-radius: 11px; flex: none; display: grid; place-items: center;
  color: #fff; font-weight: 700; background: linear-gradient(135deg,#34d399,#0d9488); }
.ct-body { min-width: 0; }
.ct-name { font-weight: 700; font-size: 13.5px; display: flex; gap: 8px; align-items: baseline; }
.ct-iss { font-size: 11px; font-weight: 700; color: var(--ui-primary, #2f55ea); }
.ct-msg { font-size: 13px; color: #64748b; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chat-toast-enter-active, .chat-toast-leave-active { transition: all .3s ease; }
.chat-toast-enter-from, .chat-toast-leave-to { opacity: 0; transform: translateY(20px); }
</style>
```

- [ ] **Step 4: Create ChatThread.vue**

Create `frontend/app/components/chat/ChatThread.vue`. Reuse the existing `useMentionMarkdown` for rendering and `MentionDropdown` for the composer (study `frontend/app/components/MarkdownEditor.vue` for the existing `@`-trigger detection helper to import/reuse; if it is not exported, lift the minimal `detectMentionTrigger` logic here):

```vue
<script setup lang="ts">
import type { ChatComment } from '~/composables/useChat'
const props = defineProps<{ messages: ChatComment[]; meId: number | null }>()
const emit = defineEmits<{ send: [content: string] }>()
const { renderMention } = useMentionMarkdown()   // 复用现有 @[name](user:id) / #issue 渲染

const draft = ref('')
const scroller = ref<HTMLElement | null>(null)

function isMine(m: ChatComment) { return props.meId != null && m.author === props.meId }
function submit() {
  const text = draft.value.trim()
  if (!text) return
  emit('send', text)
  draft.value = ''
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
}
watch(() => props.messages.length, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
})
</script>

<template>
  <div class="ct-thread">
    <div ref="scroller" class="ct-scroll">
      <div v-for="m in messages" :key="m.id" class="ct-msg" :class="{ mine: isMine(m) }">
        <div class="ct-mav">{{ (m.author_name || '?').slice(0, 1) }}</div>
        <div class="ct-mwrap">
          <div class="ct-mname">{{ m.author_name }}</div>
          <div class="ct-bubble" v-html="renderMention(m.content)" />
        </div>
      </div>
    </div>
    <div class="ct-composer">
      <textarea v-model="draft" rows="1" placeholder="回复… 输入 @ 提及成员"
                data-test="reply-input" @keydown="onKey" />
      <button class="ct-send" :disabled="!draft.trim()" data-test="reply-send" @click="submit">发送</button>
    </div>
    <div class="ct-hint">回车发送 · @ 提及 · 回复即在该问题新增评论</div>
  </div>
</template>

<style scoped>
.ct-thread { display: flex; flex-direction: column; height: 100%; }
.ct-scroll { flex: 1; overflow-y: auto; padding: 16px 14px; background: var(--ui-bg-muted, #f7f8fb); }
.ct-msg { display: flex; gap: 9px; margin-bottom: 12px; max-width: 86%; }
.ct-msg.mine { margin-left: auto; flex-direction: row-reverse; }
.ct-mav { width: 30px; height: 30px; border-radius: 9px; flex: none; display: grid; place-items: center; color: #fff; font-size: 12px; font-weight: 700; background: linear-gradient(135deg,#34d399,#0d9488); }
.ct-bubble { padding: 9px 13px; border-radius: 14px; font-size: 14px; background: #fff; border: 1px solid #e4e8ef; }
.ct-msg.mine .ct-bubble { background: var(--ui-primary, #2f55ea); color: #fff; border: none; }
.ct-mname { font-size: 11.5px; font-weight: 700; color: #64748b; margin: 0 0 4px 3px; }
.ct-composer { display: flex; gap: 8px; padding: 11px 12px; border-top: 1px solid #e4e8ef; }
.ct-composer textarea { flex: 1; resize: none; border: 1px solid #e4e8ef; border-radius: 12px; padding: 9px 12px; font: inherit; }
.ct-send { border: none; background: var(--ui-primary, #2f55ea); color: #fff; border-radius: 10px; padding: 0 14px; cursor: pointer; }
.ct-send:disabled { background: #c3ccde; }
.ct-hint { font-size: 11px; color: #94a3b8; padding: 0 12px 10px; }
</style>
```

> Note on `@`-mention dropdown: wire `MentionDropdown.vue` to the textarea using the same trigger-detection approach as `MarkdownEditor.vue`. If `MarkdownEditor` already extracts this into a composable, import it; otherwise this step also extracts `detectMentionTrigger(text, caret)` into `frontend/app/composables/useMentionTrigger.ts` and uses it in both places (DRY). Keep this within Task 10 — it is part of the composer deliverable.

- [ ] **Step 5: Create ChatBubble.vue**

Create `frontend/app/components/chat/ChatBubble.vue`:

```vue
<script setup lang="ts">
const chat = useChat()
const { conversations, unreadTotal, activeIssueId, messages, lastIncoming } = chat
const { user } = useAuth()

const open = ref(false)
const view = ref<'list' | 'thread'>('list')
const meId = computed(() => (user.value ? Number(user.value.id) : null))
const activeTitle = computed(() => conversations.value.find(c => c.issue_id === activeIssueId.value)?.issue_title || '消息')

onMounted(() => { chat.loadConversations(); chat.connect() })
onUnmounted(() => chat.disconnect())

function toggle() { open.value = !open.value }
async function openConv(id: number) { await chat.openConversation(id); view.value = 'thread' }
function back() { view.value = 'list'; activeIssueId.value = null }
function send(content: string) { if (activeIssueId.value) chat.sendReply(activeIssueId.value, content) }
function onPreviewOpen(id: number) { open.value = true; openConv(id) }
</script>

<template>
  <ClientOnly>
    <div class="chat-root">
      <ChatPreviewToast v-if="!open" :event="lastIncoming" @open="onPreviewOpen" />

      <button class="chat-fab" data-test="fab" aria-label="聊天" @click="toggle">
        <span>{{ open ? '✕' : '💬' }}</span>
        <span v-if="unreadTotal > 0" class="chat-fab-badge" data-test="fab-badge">{{ unreadTotal }}</span>
      </button>

      <div v-if="open" class="chat-panel" data-test="chat-panel">
        <header class="chat-head">
          <button v-if="view === 'thread'" class="chat-back" @click="back">‹</button>
          <strong>{{ view === 'thread' ? activeTitle : '消息' }}</strong>
          <button class="chat-x" @click="toggle">✕</button>
        </header>

        <div v-if="view === 'list'" class="chat-list">
          <div class="chat-list-hd">有我参与且有评论的</div>
          <button v-for="c in conversations" :key="c.issue_id" class="chat-conv"
                  data-test="conv" @click="openConv(c.issue_id)">
            <div class="cc-main">
              <div class="cc-top"><span class="cc-iss">ISS-{{ c.issue_id }}</span><span class="cc-title">{{ c.issue_title }}</span></div>
              <div class="cc-snip">{{ c.last_comment?.content }}</div>
            </div>
            <span v-if="c.unread_count > 0" class="cc-unread">{{ c.unread_count }}</span>
          </button>
        </div>

        <ChatThread v-else :messages="messages" :me-id="meId" @send="send" />
      </div>
    </div>
  </ClientOnly>
</template>

<style scoped>
.chat-fab { position: fixed; right: 24px; bottom: 24px; z-index: 46; width: 60px; height: 60px; border-radius: 20px;
  border: none; cursor: pointer; color: #fff; font-size: 24px; background: linear-gradient(140deg, var(--ui-primary,#2f55ea), #5b7bff);
  box-shadow: 0 14px 30px -8px rgba(47,85,234,.55); }
.chat-fab-badge { position: absolute; top: -6px; right: -6px; min-width: 22px; height: 22px; padding: 0 6px; border-radius: 11px;
  background: #ef4444; color: #fff; font-size: 12px; font-weight: 800; display: grid; place-items: center; border: 2.5px solid #eef1f6; }
.chat-panel { position: fixed; right: 24px; bottom: 96px; z-index: 47; width: 384px; height: min(584px, calc(100vh - 132px));
  background: #fff; border: 1px solid #e4e8ef; border-radius: 16px; box-shadow: 0 24px 60px -16px rgba(15,23,42,.32);
  display: flex; flex-direction: column; overflow: hidden; }
.chat-head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid #e4e8ef; }
.chat-head strong { flex: 1; }
.chat-back, .chat-x { border: none; background: transparent; font-size: 18px; cursor: pointer; color: #64748b; }
.chat-list { overflow-y: auto; padding: 6px; }
.chat-list-hd { padding: 10px 12px 6px; font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: #94a3b8; }
.chat-conv { display: flex; gap: 11px; width: 100%; text-align: left; padding: 11px 12px; border: none; background: transparent; border-radius: 12px; cursor: pointer; }
.chat-conv:hover { background: #f7f8fb; }
.cc-main { flex: 1; min-width: 0; }
.cc-iss { font-size: 11px; font-weight: 700; color: var(--ui-primary,#2f55ea); margin-right: 8px; }
.cc-title { font-weight: 700; font-size: 13.5px; }
.cc-snip { font-size: 13px; color: #64748b; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cc-unread { align-self: center; min-width: 19px; height: 19px; padding: 0 5px; border-radius: 10px; background: var(--ui-primary,#2f55ea); color: #fff; font-size: 11px; font-weight: 800; display: grid; place-items: center; }
</style>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm run test -- chatBubble`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add frontend/app/components/chat/ frontend/tests/chatBubble.test.ts frontend/app/composables/useMentionTrigger.ts
git commit -m "feat(chat): ChatBubble + ChatThread + ChatPreviewToast components"
```

---

## Task 11: Mount globally + WebSocket proxy config

**Files:**
- Modify: `frontend/app/app.vue`
- Modify: `frontend/nuxt.config.ts`
- Test: manual (proxy is not unit-testable) + existing suite must stay green

**Interfaces:**
- Consumes: `useAuth()` for auth gating. Produces: `<ChatBubble>` rendered on authenticated app pages; `/ws/` proxied to backend in dev and prod.

- [ ] **Step 1: Mount the bubble (authenticated only)**

In `frontend/app/app.vue`, render `<ChatBubble>` when a user is logged in. Locate the existing root template (it already mounts `<AppDialog>` per earlier exploration) and add alongside it:

```vue
<ChatBubble v-if="user" />
```

Ensure `const { user } = useAuth()` is available in that `<script setup>` (add if absent). `ChatBubble` is auto-imported from `components/chat/`.

- [ ] **Step 2: Add the WebSocket proxy**

In `frontend/nuxt.config.ts`:

In `routeRules` (after the `'/api/**'` line):
```ts
    '/ws/**': { proxy: `${apiBase}/ws/**` },
```
In `nitro.devProxy` (after the `'/api/'` block):
```ts
      '/ws/': {
        target: `${apiBase}/ws/`,
        ws: true,
      },
```

- [ ] **Step 3: Run the full frontend suite (no regressions)**

Run: `cd frontend && npm run test`
Expected: PASS (all existing + new chat tests).

- [ ] **Step 4: Manual smoke (dev, two users)**

```bash
# 后端必须经 ASGI/WebSocket 启动:
cd backend && uv run python manage.py runserver   # daphne 在 INSTALLED_APPS 顶部 → runserver 走 ASGI
# 前端:
cd frontend && npm run dev    # :3004
```
Verify: log in as `bot` (and a second user in another browser); assign an issue, post a comment as the other user; confirm the chat bubble badge increments, the preview toast appears with a ding, opening the conversation shows the message, and replying posts a comment that the other session receives live.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/app.vue frontend/nuxt.config.ts
git commit -m "feat(chat): mount ChatBubble globally + proxy /ws/ (dev + prod)"
```

---

## Task 12: Deployment wiring + docs

**Files:**
- Modify: `docs/superpowers/specs/2026-06-18-issue-chat-design.md` (append a short "Deploy" note) — or a new `docs/` note
- Modify: `backend/.env.example` if present (else document)

**Interfaces:** none (operational).

- [ ] **Step 1: Document env + infra**

Record (in the spec's deploy section or a README note):
- `CHANNEL_REDIS_URL` (default `redis://127.0.0.1:6379/1`) — must point at a reachable Redis on test/prod (the same instance Celery uses; DB `/1`).
- Prod is served by `uvicorn config.asgi:application` (existing Dockerfile CMD) — already ASGI; no change.
- The reverse proxy in front of the frontend/backend (nginx/traefik) **must forward WebSocket upgrade headers** for `/ws/`. Add the upgrade config to the deploy infra.
- `daphne` is only for the dev `runserver`; prod uses uvicorn.

- [ ] **Step 2: Verify backend boots under uvicorn (prod-like)**

Run: `cd backend && uv run uvicorn config.asgi:application --port 8001`
Expected: starts without import errors; `GET http://127.0.0.1:8001/api/...` works and `ws://127.0.0.1:8001/ws/chat/?token=<valid>` connects.

- [ ] **Step 3: Commit**

```bash
git add docs/ backend/.env.example
git commit -m "docs(chat): deployment + env wiring notes for WebSocket chat"
```

---

## Self-Review

**1. Spec coverage**
- Data model A1 → Task 2. ✓
- `participants_for_comment` (assignee/helpers/mentioned/existing, active-only) → Task 3. ✓
- `broadcast_comment` (author excluded from push, auto-read, dedup, graceful degrade) → Task 4. ✓
- Channels deps + settings + ASGI + daphne-for-runserver → Task 1. ✓
- JWT WS middleware + push-only consumer → Task 5. ✓
- REST: conversations / unread-total / mark-read; reuse existing comment GET/POST → Tasks 6, 7. ✓
- Chat independent of bell (no Notification rows) → enforced; existing mention call untouched (Task 7 adds *alongside*). ✓
- Frontend: `useChat` REST+WS, `ChatBubble`/`ChatThread`/`ChatPreviewToast`, preview+ding, lightweight `@`-mention composer → Tasks 8–10. ✓
- Global mount + dev/prod `/ws/` proxy → Task 11. ✓
- Conversation scope "参与且有评论" → conversations query filters `issue__comments__isnull=False` and rows only created on comment broadcast. ✓
- Arrival = preview bar + sound + badge → ChatPreviewToast + badge in ChatBubble. ✓
- Redis `/1`, prod proxy upgrade, uvicorn already ASGI → Task 12. ✓
- Reconnect / offline re-hydrate / headless degrade → Task 9 reconnect + Task 8 `loadConversations` on mount + Task 4 graceful skip. ✓

**2. Placeholder scan:** No TBD/TODO; every code step has full code. The two prose notes (Task 10 mention-dropdown wiring; Task 12 deploy) describe concrete, bounded work folded into their task deliverable, not deferred placeholders.

**3. Type consistency:** `IssueChatParticipant` fields/`unread_count()` consistent across Tasks 2/4/6. WS event keys (`issue_id`, `issue_title`, `unread_count`, `comment`) identical in `_push_comment_ws` (Task 4), consumer `comment_new` (Task 5), and `ChatIncoming` (Task 8). Group name `chat_user_{id}` consistent (Tasks 4/5). `useChat` returned names match component usage (Tasks 8/9/10).
