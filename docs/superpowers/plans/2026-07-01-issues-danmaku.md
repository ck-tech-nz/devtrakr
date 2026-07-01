# Issues Danmaku (问题动态弹幕) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in, real-time scrolling "弹幕" activity strip to the top of the Issues page that streams issue **created** and **completed** (first entry into a terminal status) events.

**Architecture:** Reuse the existing Django Channels WebSocket stack for live push (single global group `danmaku`, permission-gated at connect), plus a REST endpoint for the 2-hour backfill on enable. A new `Issue.save()` override maintains a `resolved_at` invariant (non-null ⟺ terminal), which both fixes an existing inconsistency and powers accurate backfill. A `post_save` signal broadcasts events. Frontend adds a per-account toggle, a data composable (`useIssueDanmaku`), and a multi-lane bullet component (`IssueDanmakuBar.vue`).

**Tech Stack:** Django 5 / DRF, Django Channels 4 + Redis (prod) / InMemoryChannelLayer (tests), pytest + pytest-asyncio + factory-boy; Nuxt 4 SPA, Nuxt UI 3, TypeScript, Tailwind 4.

## Global Constraints

- Backend package manager is `uv`; run tests with `uv run python -m pytest` (plain `uv run pytest` fails to spawn in this repo).
- Terminal statuses are exactly `已解决`, `已发布`, `已关闭` (verbatim). Do not conflate with the existing `CLOSED_STATUSES = ("已关闭", "已发布")` in `services.py`.
- Never edit an existing Django migration; if a schema change is needed, `makemigrations`. (This plan needs **no** migration — no fields are added.)
- UI text and code comments in Chinese (zh-hans); identifiers/docs in English.
- Frontend has **no** unit-test harness — frontend task verification is `npx nuxi typecheck` plus explicit manual QA. Do not scaffold a new test framework.
- Every git commit message ends with the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- All work is on branch `feat/issues-danmaku` (already created).
- Do not silence warnings; resolve only via upstream/dep fixes (project rule).

## File Structure

**Backend (`backend/apps/issues/`)**
- `models.py` — add `TERMINAL_STATUSES` constant + `Issue.save()` override (resolved_at invariant). *[modify]*
- `serializers.py` — remove the now-duplicate resolved_at stamping at lines 466-468. *[modify]*
- `services_danmaku.py` — `build_payload()` + `broadcast_issue_event()`. *[create]*
- `signals.py` — add `broadcast_danmaku` post_save receiver (keep `trigger_ai_analysis`). *[modify]*
- `consumers.py` — add `DanmakuConsumer`. *[modify]*
- `ws_urls.py` — register `ws/danmaku/`. *[modify]*
- `views.py` — add `DanmakuRecentView` + `DANMAKU_WINDOW`/`DANMAKU_MAX`. *[modify]*
- `urls.py` — register `danmaku/recent/`. *[modify]*

**Backend tests (`backend/tests/`)**
- `test_issue_resolved_at.py` *[create]* · `test_danmaku.py` *[create]* · `test_danmaku_ws.py` *[create]*

**Frontend (`frontend/app/`)**
- `composables/useUserSettings.ts` — add `danmaku_enabled`. *[modify]*
- `composables/useIssueDanmaku.ts` — data source (backfill + WS + dedup). *[create]*
- `components/IssueDanmakuBar.vue` — multi-lane bullet renderer. *[create]*
- `pages/app/issues/index.vue` — mount bar + toolbar toggle + enable/disable wiring. *[modify]*

---

## Task 1: `resolved_at` invariant (`Issue.save()` override)

**Files:**
- Modify: `backend/apps/issues/models.py` (add constant after `SYSTEM_ASSIGNED_STATUSES` ~line 32; add `save()` to `Issue` class; add `timezone` import)
- Modify: `backend/apps/issues/serializers.py:466-468` (remove duplicate stamping)
- Test: `backend/tests/test_issue_resolved_at.py`

**Interfaces:**
- Produces: `apps.issues.models.TERMINAL_STATUSES: tuple[str, str, str]`; `Issue.save()` maintains invariant *resolved_at non-null ⟺ status ∈ TERMINAL_STATUSES* and sets transient `instance._danmaku_completed: bool` (True only on the save that first stamps resolved_at this cycle).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_issue_resolved_at.py`:

```python
import pytest

from apps.issues.models import Issue
from tests.factories import IssueFactory


@pytest.mark.django_db
def test_resolved_at_set_on_entering_terminal():
    issue = IssueFactory(status="进行中")
    assert issue.resolved_at is None
    issue.status = "已解决"
    issue.save()
    issue.refresh_from_db()
    assert issue.resolved_at is not None


@pytest.mark.django_db
def test_resolved_at_cleared_on_reopen():
    issue = IssueFactory(status="已解决")
    issue.refresh_from_db()
    assert issue.resolved_at is not None
    issue.status = "进行中"
    issue.save()
    issue.refresh_from_db()
    assert issue.resolved_at is None


@pytest.mark.django_db
def test_resolved_at_restamped_on_recomplete():
    issue = IssueFactory(status="已解决")
    issue.refresh_from_db()
    first = issue.resolved_at
    issue.status = "进行中"
    issue.save()
    issue.status = "已关闭"
    issue.save()
    issue.refresh_from_db()
    assert issue.resolved_at is not None
    assert issue.resolved_at >= first


@pytest.mark.django_db
def test_resolved_at_not_rewritten_terminal_to_terminal():
    issue = IssueFactory(status="已解决")
    issue.refresh_from_db()
    first = issue.resolved_at
    issue.status = "已发布"
    issue.save()
    issue.refresh_from_db()
    assert issue.resolved_at == first


@pytest.mark.django_db
def test_resolved_at_persists_under_partial_update_fields():
    # 关闭端点用 save(update_fields=["status"]);override 必须把 resolved_at 补进去
    issue = IssueFactory(status="进行中")
    issue.status = "已关闭"
    issue.save(update_fields=["status"])
    issue.refresh_from_db()
    assert issue.resolved_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_issue_resolved_at.py -v`
Expected: FAIL (e.g. `test_resolved_at_cleared_on_reopen` — resolved_at stays set; `test_resolved_at_persists_under_partial_update_fields` — resolved_at is None).

- [ ] **Step 3: Add the `timezone` import and `TERMINAL_STATUSES` constant**

In `backend/apps/issues/models.py`, add to the imports at the top:

```python
from django.utils import timezone
```

After the `SYSTEM_ASSIGNED_STATUSES = (...)` block (~line 32), add:

```python
# 终态集合:进入其一即视为「完成」。区别于 services.CLOSED_STATUSES(仅关闭/发布,
# 用于查重),此处含「已解决」,供 resolved_at 不变式与动态弹幕使用。
TERMINAL_STATUSES = (
    IssueStatus.RESOLVED.value,
    IssueStatus.PUBLISHED.value,
    IssueStatus.CLOSED.value,
)
```

- [ ] **Step 4: Add the `save()` override to the `Issue` model**

In `backend/apps/issues/models.py`, inside `class Issue`, add this method (e.g. right after `__str__`):

```python
    def save(self, *args, update_fields=None, **kwargs):
        # resolved_at 不变式:非空 ⟺ 当前处于终态。仅靠 (状态, resolved_at) 推导,
        # 无需记录旧状态。override 而非 pre_save 信号:关闭端点用 update_fields=["status"]
        # 部分保存,信号改字段不在 update_fields 中会被静默丢弃,这里可补入。
        is_terminal = self.status in TERMINAL_STATUSES
        self._danmaku_completed = False
        if is_terminal and self.resolved_at is None:
            self.resolved_at = timezone.now()
            self._danmaku_completed = True  # 供 post_save 广播「完成」
            if update_fields is not None:
                update_fields = set(update_fields) | {"resolved_at"}
        elif not is_terminal and self.resolved_at is not None:
            self.resolved_at = None  # 重开:清空,不广播
            if update_fields is not None:
                update_fields = set(update_fields) | {"resolved_at"}
        super().save(*args, update_fields=update_fields, **kwargs)
```

- [ ] **Step 5: Remove the duplicate stamping in the serializer**

In `backend/apps/issues/serializers.py`, delete these three lines (currently 466-468); leave the settlement block that follows intact:

```python
            if new_status in ("已解决", "已发布", "已关闭") and not issue.resolved_at:
                issue.resolved_at = timezone.now()
                issue.save(update_fields=["resolved_at"])
```

(If `timezone` is now unused in `serializers.py`, that is harmless; leave other imports untouched.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_issue_resolved_at.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Run the issues regression suite (guard against settlement/KPI fallout)**

Run: `cd backend && uv run python -m pytest tests/test_issues.py -q`
Expected: PASS (no regressions from moving resolved_at into `save()`).

- [ ] **Step 8: Commit**

```bash
git add backend/apps/issues/models.py backend/apps/issues/serializers.py backend/tests/test_issue_resolved_at.py
git commit -m "feat(issues): resolved_at 不变式(save override,重开清空/再完成重记)"
```

---

## Task 2: Danmaku payload + broadcast service

**Files:**
- Create: `backend/apps/issues/services_danmaku.py`
- Test: `backend/tests/test_danmaku.py`

**Interfaces:**
- Produces: `build_payload(issue, kind: str) -> dict` with keys `kind, issue_id, issue_number, title, status, actor_name, occurred_at`; `broadcast_issue_event(payload: dict) -> None` (group_send to `DANMAKU_GROUP`, no-op if channel layer absent); `DANMAKU_GROUP = "danmaku"`.
- Consumes: `Issue` instance fields `created_by`, `assignee`, `updated_by` (each a User with `.name`), `created_at`, `resolved_at`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_danmaku.py`:

```python
import pytest

from apps.issues.services_danmaku import build_payload
from tests.factories import IssueFactory, UserFactory


@pytest.mark.django_db
def test_build_payload_created():
    issue = IssueFactory(status="进行中")
    p = build_payload(issue, "created")
    assert p["kind"] == "created"
    assert p["issue_id"] == issue.id
    assert p["issue_number"] == f"ISS-{issue.id:03d}"
    assert p["status"] == "进行中"
    assert p["actor_name"] == issue.created_by.name
    assert p["occurred_at"] is not None


@pytest.mark.django_db
def test_build_payload_completed_uses_assignee_and_resolved_at():
    user = UserFactory()
    issue = IssueFactory(status="已解决", assignee=user)
    issue.refresh_from_db()
    p = build_payload(issue, "completed")
    assert p["kind"] == "completed"
    assert p["actor_name"] == user.name
    assert p["occurred_at"] == issue.resolved_at.isoformat()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_danmaku.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.issues.services_danmaku'`.

- [ ] **Step 3: Create the service**

Create `backend/apps/issues/services_danmaku.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_danmaku.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services_danmaku.py backend/tests/test_danmaku.py
git commit -m "feat(issues): 动态弹幕事件载荷与广播服务"
```

---

## Task 3: `post_save` broadcast signal

**Files:**
- Modify: `backend/apps/issues/signals.py` (add receiver + imports; keep `trigger_ai_analysis`)
- Test: `backend/tests/test_danmaku.py` (append)

**Interfaces:**
- Consumes: `build_payload`, `broadcast_issue_event` (Task 2); `Issue._danmaku_completed` (Task 1).
- Produces: on Issue save, registers a `transaction.on_commit` callback that calls `broadcast_issue_event` with a `created` payload (on insert) or `completed` payload (when `_danmaku_completed`), else nothing.

- [ ] **Step 1: Write the failing tests (append to `backend/tests/test_danmaku.py`)**

```python
from unittest.mock import patch


@pytest.mark.django_db
def test_signal_broadcasts_created(django_capture_on_commit_callbacks):
    with patch("apps.issues.signals.broadcast_issue_event") as mock_bcast:
        with django_capture_on_commit_callbacks(execute=True):
            IssueFactory(status="待分配")
    kinds = [c.args[0]["kind"] for c in mock_bcast.call_args_list]
    assert kinds == ["created"]


@pytest.mark.django_db
def test_signal_broadcasts_completed_once(django_capture_on_commit_callbacks):
    issue = IssueFactory(status="进行中")
    with patch("apps.issues.signals.broadcast_issue_event") as mock_bcast:
        with django_capture_on_commit_callbacks(execute=True):
            issue.status = "已解决"
            issue.save()
    kinds = [c.args[0]["kind"] for c in mock_bcast.call_args_list]
    assert kinds == ["completed"]


@pytest.mark.django_db
def test_signal_no_broadcast_on_reopen(django_capture_on_commit_callbacks):
    issue = IssueFactory(status="已解决")
    with patch("apps.issues.signals.broadcast_issue_event") as mock_bcast:
        with django_capture_on_commit_callbacks(execute=True):
            issue.status = "进行中"
            issue.save()
    assert mock_bcast.call_count == 0


@pytest.mark.django_db
def test_signal_rebroadcasts_on_recomplete(django_capture_on_commit_callbacks):
    issue = IssueFactory(status="已解决")
    issue.status = "进行中"
    issue.save()
    with patch("apps.issues.signals.broadcast_issue_event") as mock_bcast:
        with django_capture_on_commit_callbacks(execute=True):
            issue.status = "已发布"
            issue.save()
    kinds = [c.args[0]["kind"] for c in mock_bcast.call_args_list]
    assert kinds == ["completed"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_danmaku.py -k signal -v`
Expected: FAIL (broadcast never called — `assert [] == ["created"]`).

- [ ] **Step 3: Add the receiver to `signals.py`**

In `backend/apps/issues/signals.py`, extend the imports at the top:

```python
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Issue
from .services_danmaku import broadcast_issue_event, build_payload
```

Then add a new receiver (leave `trigger_ai_analysis` and `_maybe_analyze` unchanged):

```python
@receiver(post_save, sender=Issue)
def broadcast_danmaku(sender, instance, created, **kwargs):
    # 新建 → created;首次进入终态(save override 置的标志)→ completed;其余不推。
    # on_commit:事务回滚时不发幽灵事件。
    if created:
        payload = build_payload(instance, "created")
    elif getattr(instance, "_danmaku_completed", False):
        payload = build_payload(instance, "completed")
    else:
        return
    transaction.on_commit(lambda: broadcast_issue_event(payload))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_danmaku.py -v`
Expected: PASS (all in file).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/signals.py backend/tests/test_danmaku.py
git commit -m "feat(issues): post_save 广播新建/完成动态(on_commit)"
```

---

## Task 4: `DanmakuConsumer` + WebSocket route

**Files:**
- Modify: `backend/apps/issues/consumers.py` (add `DanmakuConsumer`)
- Modify: `backend/apps/issues/ws_urls.py` (register route)
- Test: `backend/tests/test_danmaku_ws.py`

**Interfaces:**
- Consumes: `scope["user"]` set by `JWTAuthMiddleware`; the `danmaku` group fed by Task 2's `broadcast_issue_event`.
- Produces: WS endpoint `ws/danmaku/`. Rejects unauthenticated (close 4401) and users lacking `issues.view_issue` (close 4403). On a `{"type": "issue.event", "payload": {...}}` group message, sends `payload` as JSON to the client.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_danmaku_ws.py`:

```python
import pytest
from asgiref.sync import sync_to_async
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_danmaku_ws.py -v`
Expected: FAIL with `ImportError: cannot import name 'DanmakuConsumer'`.

- [ ] **Step 3: Add `DanmakuConsumer` to `consumers.py`**

In `backend/apps/issues/consumers.py`, add the import and class:

```python
from channels.db import database_sync_to_async


class DanmakuConsumer(AsyncJsonWebsocketConsumer):
    """问题动态弹幕:只推送。连接校验 view_issue,加入全局组 danmaku。"""

    group_name = "danmaku"

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not await self._can_view(user):
            await self.close(code=4403)
            return
        self._joined = True
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "_joined", False):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def _can_view(self, user):
        return user.has_perm("issues.view_issue")

    # group_send type "issue.event" → 此方法
    async def issue_event(self, event):
        await self.send_json(event["payload"])
```

- [ ] **Step 4: Register the route in `ws_urls.py`**

Edit `backend/apps/issues/ws_urls.py`:

```python
from django.urls import path

from .consumers import ChatConsumer, DanmakuConsumer

# WebSocket 路由(挂在 asgi.py 的 websocket 协议下)。
chat_ws_urlpatterns = [
    path("ws/chat/", ChatConsumer.as_asgi()),
    path("ws/danmaku/", DanmakuConsumer.as_asgi()),
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_danmaku_ws.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/issues/consumers.py backend/apps/issues/ws_urls.py backend/tests/test_danmaku_ws.py
git commit -m "feat(issues): DanmakuConsumer + ws/danmaku 路由(连接校验 view_issue)"
```

---

## Task 5: REST backfill endpoint

**Files:**
- Modify: `backend/apps/issues/views.py` (add constants + `DanmakuRecentView`)
- Modify: `backend/apps/issues/urls.py` (register + import)
- Test: `backend/tests/test_danmaku.py` (append)

**Interfaces:**
- Produces: `GET /api/issues/danmaku/recent/` → JSON array of `build_payload` objects (newest-first), created within `DANMAKU_WINDOW` and completed (terminal + `resolved_at` within window), capped at `DANMAKU_MAX`. Requires `issues.view_issue` (403 without). Excludes soft-deleted (via `Issue.objects`).

- [ ] **Step 1: Write the failing tests (append to `backend/tests/test_danmaku.py`)**

```python
from datetime import timedelta

from django.utils import timezone

from apps.issues.models import Issue

DANMAKU_URL = "/api/issues/danmaku/recent/"


@pytest.mark.django_db
def test_recent_requires_view_issue(regular_client):
    resp = regular_client.get(DANMAKU_URL)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_recent_returns_created_and_completed(auth_client):
    IssueFactory(status="进行中")
    IssueFactory(status="已解决")
    resp = auth_client.get(DANMAKU_URL)
    assert resp.status_code == 200
    kinds = {e["kind"] for e in resp.json()}
    assert kinds == {"created", "completed"}


@pytest.mark.django_db
def test_recent_excludes_old(auth_client):
    old = IssueFactory(status="进行中")
    Issue.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=3))
    resp = auth_client.get(DANMAKU_URL)
    assert old.id not in [e["issue_id"] for e in resp.json()]


@pytest.mark.django_db
def test_recent_excludes_soft_deleted(auth_client):
    issue = IssueFactory(status="进行中")
    issue.is_deleted = True
    issue.save(update_fields=["is_deleted"])
    resp = auth_client.get(DANMAKU_URL)
    assert issue.id not in [e["issue_id"] for e in resp.json()]


@pytest.mark.django_db
def test_recent_caps_at_50(auth_client):
    IssueFactory.create_batch(60, status="进行中")
    resp = auth_client.get(DANMAKU_URL)
    assert len(resp.json()) == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_danmaku.py -k recent -v`
Expected: FAIL (404 — route not defined).

- [ ] **Step 3: Add the view to `views.py`**

In `backend/apps/issues/views.py`, add near the top (with the other imports — reuse whatever `Response`/`APIView`/`IsAuthenticated`/`FullDjangoModelPermissions` imports already exist in this file; add only what's missing):

```python
from datetime import timedelta

from django.utils import timezone

from .models import TERMINAL_STATUSES
from .services_danmaku import build_payload

DANMAKU_WINDOW = timedelta(hours=2)  # 回放时间窗(可调)
DANMAKU_MAX = 50                     # 回放条数上限(可调)
```

Then add the view (anywhere among the class-based views):

```python
class DanmakuRecentView(APIView):
    """动态弹幕回放:最近 DANMAKU_WINDOW 内的新建 + 完成事件,倒序,上限 DANMAKU_MAX。"""
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    queryset = Issue.objects.all()  # 供 FullDjangoModelPermissions 推导 view_issue

    def get(self, request):
        cutoff = timezone.now() - DANMAKU_WINDOW
        created = Issue.objects.filter(created_at__gte=cutoff)
        completed = Issue.objects.filter(
            status__in=TERMINAL_STATUSES, resolved_at__gte=cutoff
        )
        events = [build_payload(i, "created") for i in created]
        events += [build_payload(i, "completed") for i in completed]
        events.sort(key=lambda e: e["occurred_at"], reverse=True)
        return Response(events[:DANMAKU_MAX])
```

> Note: `Issue`, `APIView`, `Response`, `IsAuthenticated`, `FullDjangoModelPermissions` are already imported and used in `views.py`; do not duplicate their imports.

- [ ] **Step 4: Register the URL**

In `backend/apps/issues/urls.py`, add `DanmakuRecentView` to the `from .views import (...)` block, and add this path **before** the `path("<int:pk>/", ...)` line (keep it with the other non-pk routes, e.g. right after the `chat/...` paths):

```python
    path("danmaku/recent/", DanmakuRecentView.as_view(), name="issue-danmaku-recent"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_danmaku.py -v`
Expected: PASS (all in file).

- [ ] **Step 6: Full backend suite sanity check**

Run: `cd backend && uv run python -m pytest -q`
Expected: PASS (no regressions across the suite).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/issues/views.py backend/apps/issues/urls.py backend/tests/test_danmaku.py
git commit -m "feat(issues): 动态弹幕回放端点 /danmaku/recent/(最近2h·上限50·view_issue)"
```

---

## Task 6: Frontend preference `danmaku_enabled`

**Files:**
- Modify: `frontend/app/composables/useUserSettings.ts`

**Interfaces:**
- Produces: `UserSettings.danmaku_enabled: boolean` (default `false`), readable via `settings.value.danmaku_enabled`, writable via `update('danmaku_enabled', v)`.

- [ ] **Step 1: Add the field to the interface**

In `frontend/app/composables/useUserSettings.ts`, add to the `interface UserSettings` block (after `system_alert_dismissed`):

```typescript
  // 问题动态弹幕开关(Issues 页顶部滚动活动流),默认关闭
  danmaku_enabled: boolean
```

- [ ] **Step 2: Add the default**

In the same file, add to the `defaults` object (after `system_alert_dismissed: ''`):

```typescript
  danmaku_enabled: false,
```

- [ ] **Step 3: Verify types**

Run: `cd frontend && npx nuxi typecheck`
Expected: PASS (no type errors introduced).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/composables/useUserSettings.ts
git commit -m "feat(issues): 用户偏好增加 danmaku_enabled(默认关)"
```

---

## Task 7: `useIssueDanmaku` composable

**Files:**
- Create: `frontend/app/composables/useIssueDanmaku.ts`

**Interfaces:**
- Consumes: `useApi().api`; `GET /api/issues/danmaku/recent/`; WS `${wsBase}/ws/danmaku/?token=<access_token>` (or same-origin `/ws/danmaku/`).
- Produces: `useIssueDanmaku()` → `{ queue: Ref<DanmakuEvent[]>, enable(): Promise<void>, disable(): void }`. `queue` is a FIFO the renderer drains; `enable()` seeds backfill (oldest→newest) then opens the WS; `disable()` closes the WS and clears state. `DanmakuEvent` = `{ kind: 'created'|'completed'; issue_id: number; issue_number: string; title: string; status: string; actor_name: string | null; occurred_at: string | null }`.

- [ ] **Step 1: Create the composable**

Create `frontend/app/composables/useIssueDanmaku.ts`:

```typescript
// 问题动态弹幕数据源:开启时先 REST 回放最近 2h,再开 WebSocket 接实时。
// 广播为单一全局组(后端按 view_issue 鉴权),前端只读。连接/去重为模块级单例
// (全应用至多一条弹幕连接),queue 经 useState 跨组件共享,由弹幕栏组件消费。
export interface DanmakuEvent {
  kind: 'created' | 'completed'
  issue_id: number
  issue_number: string
  title: string
  status: string
  actor_name: string | null
  occurred_at: string | null
}

let ws: WebSocket | null = null
let retry = 0
let closedByUs = false
const seen = new Set<string>()

export function useIssueDanmaku() {
  const { api } = useApi()
  const queue = useState<DanmakuEvent[]>('danmaku-queue', () => [])

  function enqueue(e: DanmakuEvent) {
    const k = `${e.kind}:${e.issue_id}`
    if (seen.has(k)) return  // 回放项与随后的实时项去重
    seen.add(k)
    queue.value = [...queue.value, e]
    // 缓冲上限:标签页隐藏、渲染暂停时避免无界增长
    if (queue.value.length > 200) queue.value = queue.value.slice(-200)
    if (seen.size > 400) seen.clear()
  }

  async function loadBackfill() {
    try {
      const data = await api<DanmakuEvent[]>('/api/issues/danmaku/recent/')
      // 后端倒序返回;按时间正序(旧→新)灌入,滚动顺序符合直觉
      for (const e of [...data].reverse()) enqueue(e)
    } catch {
      /* 回放失败不影响实时 */
    }
  }

  function wsUrl() {
    const token = (typeof localStorage !== 'undefined' && localStorage.getItem('access_token')) || ''
    const base = (useRuntimeConfig().public.wsBase as string) || ''
    if (base) return `${base.replace(/\/$/, '')}/ws/danmaku/?token=${token}`
    const proto = (typeof location !== 'undefined' && location.protocol === 'https:') ? 'wss' : 'ws'
    const host = typeof location !== 'undefined' ? location.host : ''
    return `${proto}://${host}/ws/danmaku/?token=${token}`
  }

  function connect() {
    if (typeof WebSocket === 'undefined') return
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    closedByUs = false
    ws = new WebSocket(wsUrl())
    ws.onopen = () => { retry = 0 }
    ws.onmessage = (e: MessageEvent) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev?.kind === 'created' || ev?.kind === 'completed') enqueue(ev as DanmakuEvent)
      } catch { /* 忽略格式错误的消息 */ }
    }
    ws.onclose = () => {
      if (closedByUs) return
      retry = Math.min(retry + 1, 6)
      setTimeout(connect, Math.min(1000 * 2 ** retry, 30000))
    }
  }

  async function enable() {
    queue.value = []
    seen.clear()
    await loadBackfill()
    connect()
  }

  function disable() {
    closedByUs = true
    ws?.close()
    ws = null
    queue.value = []
    seen.clear()
  }

  return { queue, enable, disable }
}
```

- [ ] **Step 2: Verify types**

Run: `cd frontend && npx nuxi typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/composables/useIssueDanmaku.ts
git commit -m "feat(issues): useIssueDanmaku 组合式(回放+WebSocket+去重)"
```

---

## Task 8: `IssueDanmakuBar.vue` component

**Files:**
- Create: `frontend/app/components/IssueDanmakuBar.vue`

**Interfaces:**
- Consumes: `useIssueDanmaku().queue` (drains it); `useUserSettings().update('danmaku_enabled', false)` for the close button; `navigateTo` for bullet clicks.
- Produces: a self-contained bar. Reduced-motion → static recent list. Desktop 3 lanes / mobile 1 lane. Bullets scroll right→left, click navigates to the issue.

- [ ] **Step 1: Create the component**

Create `frontend/app/components/IssueDanmakuBar.vue`:

```vue
<template>
  <div
    class="danmaku-bar relative w-full overflow-hidden rounded-xl border border-black/5"
    role="log"
    aria-label="问题动态"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
  >
    <span class="danmaku-tag">动态</span>

    <!-- 减少动态效果:静态展示最近若干条 -->
    <div v-if="reduced" class="reduced-list">
      <button
        v-for="e in recent"
        :key="`${e.kind}:${e.issue_id}`"
        class="bullet"
        type="button"
        @click="go(e)"
      >
        <span class="pill" :class="e.kind">{{ e.kind === 'created' ? '新建' : '完成' }}</span>
        <span class="iss">{{ e.issue_number }}</span>
        <span class="ttl">{{ e.title }}</span>
        <span v-if="e.actor_name" class="who">· {{ e.actor_name }}</span>
      </button>
    </div>

    <!-- 多轨弹幕 -->
    <div v-else class="lanes" :style="{ height: `${lanes * LANE_H}px` }">
      <div v-for="(laneBullets, li) in laneModel" :key="li" class="lane" :style="{ height: `${LANE_H}px` }">
        <button
          v-for="b in laneBullets"
          :key="b.id"
          class="bullet flying"
          :class="{ paused }"
          type="button"
          :style="{ animationDuration: `${b.duration}s` }"
          @click="go(b.event)"
          @animationend="removeBullet(li, b.id)"
        >
          <span class="pill" :class="b.event.kind">{{ b.event.kind === 'created' ? '新建' : '完成' }}</span>
          <span class="iss">{{ b.event.issue_number }}</span>
          <span class="ttl">{{ b.event.title }}</span>
          <span v-if="b.event.actor_name" class="who">· {{ b.event.actor_name }}</span>
        </button>
      </div>
    </div>

    <button class="danmaku-close" type="button" aria-label="关闭动态弹幕" @click="close">
      <UIcon name="i-heroicons-x-mark" class="w-3.5 h-3.5" />
    </button>
  </div>
</template>

<script setup lang="ts">
import type { DanmakuEvent } from '~/composables/useIssueDanmaku'

interface Bullet { id: number; event: DanmakuEvent; duration: number }

const LANE_H = 34            // 每轨高度(px)
const DURATION = 14          // 单条滚过时长(s),恒定速度感
const MIN_GAP_MS = 3500      // 同轨两条最小间隔,避免重叠
const TICK_MS = 400          // 调度间隔

const { queue, disable } = useIssueDanmaku()
const { update } = useUserSettings()

const reduced = ref(false)
const paused = ref(false)
const lanes = ref(3)
const recent = ref<DanmakuEvent[]>([])
const laneModel = ref<Bullet[][]>([[], [], []])
const laneNextFree = [0, 0, 0]
let bulletSeq = 0
let timer: ReturnType<typeof setInterval> | null = null
let mql: MediaQueryList | null = null
let mobileMql: MediaQueryList | null = null

function go(e: DanmakuEvent) {
  navigateTo(`/app/issues/${e.issue_id}`)
}

function close() {
  update('danmaku_enabled', false)  // 页面 watcher 会随之 disable()
}

function removeBullet(laneIndex: number, id: number) {
  const lane = laneModel.value[laneIndex]
  if (lane) laneModel.value[laneIndex] = lane.filter(b => b.id !== id)
}

function now() { return Date.now() }

function spawn() {
  if (paused.value) return
  if (typeof document !== 'undefined' && document.hidden) return
  if (!queue.value.length) return
  // 找一条空闲轨道(上一条已发射足够久)
  for (let li = 0; li < lanes.value; li++) {
    if (now() < laneNextFree[li]) continue
    const event = queue.value[0]
    if (!event) return
    queue.value = queue.value.slice(1)  // 出队
    const bullet: Bullet = { id: ++bulletSeq, event, duration: DURATION }
    laneModel.value[li] = [...(laneModel.value[li] || []), bullet]
    laneNextFree[li] = now() + MIN_GAP_MS
    return  // 每 tick 至多发射一条,保持稀疏
  }
}

function pushRecent(e: DanmakuEvent) {
  recent.value = [e, ...recent.value].slice(0, 6)
}

// 减少动态效果模式:直接把队列并入静态最近列表
watch(queue, (q) => {
  if (!reduced.value || !q.length) return
  for (const e of q) pushRecent(e)
  queue.value = []
}, { deep: true })

onMounted(() => {
  if (typeof window !== 'undefined' && window.matchMedia) {
    mql = window.matchMedia('(prefers-reduced-motion: reduce)')
    reduced.value = mql.matches
    mql.addEventListener('change', ev => { reduced.value = ev.matches })

    mobileMql = window.matchMedia('(max-width: 767px)')
    const applyLanes = () => {
      lanes.value = mobileMql!.matches ? 1 : 3
      if (!laneModel.value.length) laneModel.value = Array.from({ length: lanes.value }, () => [])
    }
    applyLanes()
    mobileMql.addEventListener('change', applyLanes)
  }
  laneModel.value = Array.from({ length: lanes.value }, () => [])
  timer = setInterval(spawn, TICK_MS)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.danmaku-bar {
  background: rgba(139, 92, 246, 0.06);
  backdrop-filter: blur(10px) saturate(160%);
  -webkit-backdrop-filter: blur(10px) saturate(160%);
  padding: 8px 0;
}
.danmaku-tag {
  position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
  z-index: 3; font-size: 11px; font-weight: 700; letter-spacing: .12em;
  color: #6d28d9; padding-right: 12px;
  background: linear-gradient(90deg, rgba(255,255,255,.7) 70%, transparent);
}
.danmaku-close {
  position: absolute; right: 8px; top: 6px; z-index: 3;
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 6px; color: #9a97ab;
}
.danmaku-close:hover { background: rgba(0,0,0,.06); color: #4b5563; }
.lanes { position: relative; }
.lane { position: relative; }
.bullet {
  display: inline-flex; align-items: center; gap: 8px; white-space: nowrap;
  font-size: 13px; cursor: pointer;
}
.bullet.flying {
  position: absolute; left: 100%; top: 50%; transform: translateY(-50%);
  background: rgba(255,255,255,.78); border: 1px solid rgba(0,0,0,.06);
  padding: 4px 12px; border-radius: 999px;
  box-shadow: 0 4px 14px -8px rgba(33,29,51,.35);
  animation-name: danmaku-fly; animation-timing-function: linear; animation-iteration-count: 1;
  will-change: transform;
}
.bullet.flying.paused { animation-play-state: paused; }
@keyframes danmaku-fly {
  from { transform: translate(0, -50%); }
  to   { transform: translate(calc(-100vw - 100%), -50%); }
}
.reduced-list { display: flex; flex-wrap: wrap; gap: 8px 16px; padding: 2px 12px 2px 66px; }
.reduced-list .bullet { background: transparent; }
.pill { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
.pill.created { background: rgba(139,92,246,.12); color: #6d28d9; }
.pill.completed { background: rgba(16,185,129,.15); color: #047857; }
.iss { font-variant-numeric: tabular-nums; font-weight: 700; color: #211d33; }
.ttl { color: #211d33; max-width: 30ch; overflow: hidden; text-overflow: ellipsis; }
.who { color: #9a97ab; }
</style>
```

- [ ] **Step 2: Verify types**

Run: `cd frontend && npx nuxi typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/IssueDanmakuBar.vue
git commit -m "feat(issues): IssueDanmakuBar 多轨弹幕组件(悬停暂停/减少动态降级/移动端单轨)"
```

---

## Task 9: Wire the bar + toggle into the Issues page

**Files:**
- Modify: `frontend/app/pages/app/issues/index.vue`

**Interfaces:**
- Consumes: `useIssueDanmaku()` (Task 7), `IssueDanmakuBar` (Task 8, auto-imported), existing `settings` / `updateSettings` (`useUserSettings`) at line 631, existing `onMounted`/`onUnmounted`.
- Produces: the bar renders under `<MyPendingTasks/>` when `settings.danmaku_enabled`; a toolbar button toggles the preference; enabling/disabling drives the composable's `enable()`/`disable()`.

- [ ] **Step 1: Mount the bar under `<MyPendingTasks />`**

In `frontend/app/pages/app/issues/index.vue`, change line 4 from:

```vue
    <MyPendingTasks />
```

to:

```vue
    <MyPendingTasks />
    <IssueDanmakuBar v-if="settings.danmaku_enabled" />
```

- [ ] **Step 2: Add the toolbar toggle button**

In the same file, in the "始终可见:视图切换 / 刷新 / 新建" cluster, immediately **before** the view-switch `<div class="flex items-center bg-gray-100 ...">` (currently line 91), insert:

```vue
        <UButton
          :icon="settings.danmaku_enabled ? 'i-heroicons-bolt-solid' : 'i-heroicons-bolt'"
          size="sm"
          variant="ghost"
          :color="settings.danmaku_enabled ? 'primary' : 'neutral'"
          :aria-label="settings.danmaku_enabled ? '关闭动态弹幕' : '开启动态弹幕'"
          :title="settings.danmaku_enabled ? '关闭动态弹幕' : '开启动态弹幕'"
          @click="updateSettings('danmaku_enabled', !settings.danmaku_enabled)"
        />
```

- [ ] **Step 3: Add the enable/disable wiring in `<script setup>`**

In the same file, just after the existing `const { settings, update: updateSettings } = useUserSettings()` line (~631), add:

```typescript
// 动态弹幕:开关变化时驱动数据源连接/断开;页面卸载时断开
const danmaku = useIssueDanmaku()
watch(() => settings.value.danmaku_enabled, (on) => {
  if (on) danmaku.enable()
  else danmaku.disable()
}, { immediate: true })
```

Then add `danmaku.disable()` to the existing `onUnmounted(() => { ... })` block (~line 1368) so the WebSocket is closed when leaving the page:

```typescript
  danmaku.disable()
```

> `watch`, `onUnmounted`, `onMounted` are Nuxt auto-imported; no new import lines needed.

- [ ] **Step 4: Verify types**

Run: `cd frontend && npx nuxi typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/pages/app/issues/index.vue
git commit -m "feat(issues): Issues 页接入动态弹幕(工具栏开关+落位+连接生命周期)"
```

---

## Task 10: End-to-end manual QA

**Files:** none (verification only).

- [ ] **Step 1: Start backend (ASGI, so WS works) and frontend**

```bash
cd backend && uv run python manage.py runserver
```
In another shell:
```bash
cd frontend && TMPDIR=/tmp npm run dev
```
(Backend must be reachable so the dev WS direct-connect works; see `useChat` wsBase note.)

- [ ] **Step 2: Log in and enable the danmaku**

- Log in as `bot` / `password123`, go to `/app/issues`.
- Click the toolbar bolt (⚡) toggle. The bar appears under 我的待办.
- Confirm the preference persists: reload the page — the bar is still on. Log in as a different account — it defaults off.

- [ ] **Step 3: Verify backfill + live**

- On enable, recent (last 2h) created/completed events scroll in oldest→newest.
- In a second tab, create a new issue → within ~1s a purple 「新建」 bullet appears in the first tab.
- Change an issue's status to 已解决 (or close it) → a green 「完成」 bullet appears. Reopen then re-complete → a second 「完成」 bullet appears.

- [ ] **Step 4: Verify interactions & responsiveness**

- Hover the bar → bullets pause; leave → resume.
- Click a bullet → navigates to that issue's detail page.
- Resize to mobile width (≤767px) → a single lane.
- OS "reduce motion" on → the bar shows a static recent list, no scrolling.
- Turn the toggle off (or the bar's ×) → bar disappears; confirm in devtools Network/WS that the `ws/danmaku/` socket closed.

- [ ] **Step 5: Full backend test suite (final gate)**

Run: `cd backend && uv run python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Frontend typecheck (final gate)**

Run: `cd frontend && npx nuxi typecheck`
Expected: PASS.

- [ ] **Step 7: Commit any QA-driven tweaks**

```bash
git add -A
git commit -m "chore(issues): 动态弹幕 QA 微调"
```
(Skip if no changes were needed.)

---

## Notes for deployment (out of plan scope)

Once merged to `main`, deploy to test via `git push -f origin main:env/test` (builds frontend + backend). The WS route works in prod through the existing same-origin `/ws/` reverse-proxy path; no infra change is needed (Channels/Redis/Daphne already run).
