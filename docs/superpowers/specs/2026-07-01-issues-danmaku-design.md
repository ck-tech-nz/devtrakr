# Issues Danmaku (问题动态弹幕) — Design Spec

**Date:** 2026-07-01
**Status:** Approved for planning
**Area:** `apps/issues` (backend) · `frontend/app` (Issues page)

## 1. Goal

Add an opt-in, real-time "弹幕" (bullet-screen) activity strip to the top of the
Issues page (`/app/issues`). It shows a live, scrolling stream of two kinds of
issue activity:

- **新建** — an issue is created.
- **完成** — an issue enters a terminal status (已解决 / 已发布 / 已关闭) for the
  current cycle.

The strip is decorative/ambient team-activity — read-only, per-account
toggleable, off by default.

## 2. Locked product decisions

| Dimension | Decision |
|---|---|
| Placement | Issues page top, below `<MyPendingTasks/>`, above the toolbar |
| Visibility scope | Global; shown only to users with `issues.view_issue` permission (coarse — no per-project scoping) |
| Event types | ① issue **created** ② issue **first entry into a terminal status** this cycle = **completed** |
| Backfill | On enable, load the most recent **2 hours**, capped at **50** events (both tunable constants), then stream live |
| Motion form | **Sparse multi-lane danmaku** (right→left scrolling bullets, glassmorphism); 新建 = crystal purple, 完成 = green |
| Toggle | Per-account preference `danmaku_enabled`, **default off** |
| Transport | Live via existing Django Channels WebSocket infra; backfill via a REST endpoint |

## 3. Terminal-status semantics (`resolved_at` invariant)

This feature formalizes a `resolved_at` invariant and fixes an existing
inconsistency (the dedicated close endpoint never set `resolved_at`).

**Terminal statuses:** `已解决`, `已发布`, `已关闭`.
Define a single constant `TERMINAL_STATUSES` in `apps/issues/models.py` (next to
`Issue.save()`, which consumes it) and reuse it everywhere below. Note this is a *different* set from
the existing `CLOSED_STATUSES = ("已关闭", "已发布")` in `services.py:17`
(used for duplicate-detection) — do **not** conflate them.

**Invariant:** `Issue.resolved_at` is non-null **if and only if** the issue is
currently in a terminal status. It holds the timestamp of the *current* cycle's
completion.

State machine, derivable from `(current status, current resolved_at)` alone — no
previous-status tracking required:

| Current status | `resolved_at` | Meaning | Action |
|---|---|---|---|
| terminal | null | first completion this cycle | stamp `resolved_at = now()`; broadcast **完成** |
| terminal | set | already counted (e.g. 已解决→已发布) | none |
| non-terminal | set | reopened | clear `resolved_at = null` (no broadcast — reopen is out of scope) |
| non-terminal | null | ordinary in-progress | none |

Consequences (accepted):
- A reopen→re-complete cycle produces a **new** 完成 event — this is a genuinely
  new completion and should be shown.
- Live and backfill stay consistent because both key off `resolved_at`
  transitions.
- **KPI note:** `resolved_this_week` (in `apps/issues/views.py`) counts by
  `resolved_at`, so directly-closed issues now count as resolved-this-week. This
  is intended ("close = completed work"). `avg_resolution_hours` filters on
  `status="已解决"` and is unaffected.

## 4. Backend design (`apps/issues`)

### 4.1 `resolved_at` maintenance + event detection — `Issue.save()` override

Implement the invariant as a **`save()` override on the `Issue` model** (not a
`pre_save` signal). Reason — the **`update_fields` gotcha**: the close endpoint
calls `issue.save(update_fields=["status"])` (`views.py:912`). A `pre_save`
signal that sets `resolved_at` would be silently discarded because `resolved_at`
isn't in `update_fields`. Overriding `save()` lets us *amend* `update_fields`:

```python
def save(self, *args, update_fields=None, **kwargs):
    is_terminal = self.status in TERMINAL_STATUSES
    self._danmaku_completed = False
    if is_terminal and self.resolved_at is None:
        self.resolved_at = timezone.now()
        self._danmaku_completed = True          # flag for post_save broadcast
        if update_fields is not None:
            update_fields = set(update_fields) | {"resolved_at"}
    elif not is_terminal and self.resolved_at is not None:
        self.resolved_at = None                 # reopen; no broadcast
        if update_fields is not None:
            update_fields = set(update_fields) | {"resolved_at"}
    super().save(*args, update_fields=update_fields, **kwargs)
```

- `Issue` currently has **no** `save()` override (verified) — safe to add.
- Runs for **all** `.save()` paths (serializer, close endpoint, uptime
  auto-resolve, admin, shell), and correctly persists `resolved_at` even under
  partial `update_fields` saves.
- Remove the now-duplicate stamping in `apps/issues/serializers.py:466-468`
  (redundant once `save()` owns the invariant).

Broadcast in a **new** `post_save` receiver in `signals.py`, kept **separate**
from the existing `trigger_ai_analysis` receiver (both fire; do not modify the AI
one). Broadcast on commit so a rolled-back transaction never emits a phantom
event:

```python
@receiver(post_save, sender=Issue)
def broadcast_danmaku(sender, instance, created, **kwargs):
    if created:
        payload = build_payload(instance, "created")
    elif getattr(instance, "_danmaku_completed", False):
        payload = build_payload(instance, "completed")
    else:
        return
    transaction.on_commit(lambda: broadcast_issue_event(payload))
```

`build_payload`/`broadcast_issue_event` must never call `instance.save()`
(no re-entrancy).

### 4.2 Live broadcast service — `services_danmaku.py` (new)

Mirror `services_chat.py`:

```python
def build_payload(issue, kind):   # kind: "created" | "completed"
    return {
        "kind": kind,
        "issue_id": issue.id,
        "issue_number": f"ISS-{issue.id:03d}",     # matches ISS-001 display
        "title": issue.title,
        "status": issue.status,
        "actor_name": _actor_name(issue, kind),
        "occurred_at": (issue.created_at if kind == "created"
                        else issue.resolved_at).isoformat(),
    }

def broadcast_issue_event(payload):
    layer = get_channel_layer()
    if layer is None:                 # e.g. tests without channel layer
        return
    async_to_sync(layer.group_send)(
        "danmaku", {"type": "issue.event", "payload": payload}
    )
```

- `_actor_name`: for `created` → `created_by`; for `completed` → `assignee`
  (fallback `updated_by`), then `None`. (Approach 2 stores no per-event actor;
  the assignee is the responsible party proxy.)
- Single group `"danmaku"` — no per-user fan-out (visibility is coarse; the
  permission gate is at connect time, §4.3).

### 4.3 WebSocket consumer — `consumers.py` + `ws_urls.py`

Add `DanmakuConsumer(AsyncJsonWebsocketConsumer)`:

- `connect()`: require an authenticated user **and** `issues.view_issue`
  (checked via `database_sync_to_async(user.has_perm)("issues.view_issue")`).
  On success `group_add("danmaku")` and `accept()`; otherwise `close(code=4003)`.
- `disconnect()`: `group_discard("danmaku")`.
- `issue_event(event)`: `await self.send_json(event["payload"])`.
- No inbound messages are processed (read-only feed).

Register in `ws_urls.py` by appending
`path("ws/danmaku/", DanmakuConsumer.as_asgi())` to `chat_ws_urlpatterns` — it
inherits `JWTAuthMiddleware` from `config/asgi.py` automatically. No `asgi.py`
change needed.

### 4.4 REST backfill endpoint — `views.py` + `urls.py`

`GET /api/issues/danmaku/recent/`

- Permission: `IsAuthenticated` + `issues.view_issue`
  (`FullDjangoModelPermissions` with `queryset = Issue.objects` gives GET→view_issue).
- Constants: `DANMAKU_WINDOW = timedelta(hours=2)`, `DANMAKU_MAX = 50`
  (module-level, easy to tune).
- Query (uses `Issue.objects`, which excludes `is_deleted=True`):
  - created = `Issue.objects.filter(created_at__gte=cutoff)`
  - completed = `Issue.objects.filter(status__in=TERMINAL_STATUSES, resolved_at__gte=cutoff)`
  - Build a payload per row (`build_payload`), merge, sort by `occurred_at`
    descending, take `DANMAKU_MAX`.
- Returns a JSON array of the §4.2 payload objects (newest first). The frontend
  reverses for oldest→newest playback.

### 4.5 Backend edge cases

- **Bulk `.update()` bypasses `save()` and signals.** `resolved_at` won't be
  maintained and no live event fires for issues mutated via
  `QuerySet.update()`/`bulk_update`.
  During planning, enumerate issue status-mutation paths; the known batch path
  (`views.py:196`) only resets *unassigned* issues (non-terminal), so it is
  unaffected. Any future bulk terminal transition must call the maintenance +
  broadcast explicitly, or run per-instance `.save()`.
- **Soft delete** is handled for free by `IssueManager` (`objects` filters
  `is_deleted=False`). Deleting an issue does not emit an event (out of scope).
- **Channel layer absent** (tests) → `broadcast_issue_event` no-ops.

## 5. Frontend design (`frontend/app`)

### 5.1 Preference — `composables/useUserSettings.ts`

- Add `danmaku_enabled?: boolean` to the `UserSettings` interface, default
  `false`. Read via `settings.value.danmaku_enabled`; write via
  `update('danmaku_enabled', v)` (server-synced, debounced — existing behavior).

### 5.2 Data composable — `composables/useIssueDanmaku.ts` (new)

Responsibilities:

- `enable()`: `GET /api/issues/danmaku/recent/` → seed the event queue
  (oldest→newest); then open WebSocket.
- WebSocket: connect to `` `${wsBase}/ws/danmaku/?token=${getToken()}` `` (reuse
  the dev/prod base + token logic from `useChat.ts`), with auto-reconnect
  (exponential backoff). On message → enqueue.
- **Dedup**: keep a short-lived `Set` of recent `` `${kind}:${issue_id}` `` keys so
  a backfilled event and an immediately-following live event don't double up.
- **Visibility-aware**: pause consumption / animation when `document.hidden`
  (like `useBulletins.ts`); resume on visible.
- `disable()`: close the socket, clear the queue and dedup set.
- Reacts to `settings.danmaku_enabled` — enabling/disabling drives connect/teardown.
- Exposes: `{ events, enabled, enable, disable }` (or a queue API the bar drains).

### 5.3 Presentation — `components/IssueDanmakuBar.vue` (new)

Style **B — sparse multi-lane**:

- **Lanes**: 3 on desktop, **1 on mobile** (`< md`), via a responsive constant.
- **Scheduler** (prevents overlap): track each lane's `nextFreeAt`. To emit a
  queued bullet, pick a lane where `now >= nextFreeAt`; if none is free, wait.
  On assign, set that lane's `nextFreeAt = now + MIN_GAP`.
- **Animation**: bullet element CSS-animates `translateX` from just off the right
  edge to fully past the left edge. Duration is normalized to bullet width so
  travel speed is constant across bullets. Remove the node on `animationend`.
- **Bullet content**: event-type pill (新建 purple / 完成 green) + `ISS-xxx`
  (tabular-nums) + title (truncated) + actor name.
- **Interactions**: click a bullet → `navigateTo(\`/app/issues/${issue_id}\`)`
  (matches the list's row navigation at `index.vue:1131`); hover → pause the lane
  (`animation-play-state: paused`).
- **Accessibility**: `role="log"` / `aria-label="问题动态"`; respect
  `prefers-reduced-motion` → render a **static** list of the most recent few
  events with no motion.
- **Styling**: glassmorphism consistent with app tokens (`--glass-*`,
  `crystal` brand, green for done), matching the approved mockup.
- A small `×` in the corner → `update('danmaku_enabled', false)`.

### 5.4 Wiring — `pages/app/issues/index.vue`

- Mount `<IssueDanmakuBar v-if="settings.danmaku_enabled" />` directly below
  `<MyPendingTasks/>` (top of content, above the toolbar).
- Add a compact toggle to the toolbar labeled **动态弹幕**, bound to
  `update('danmaku_enabled', v)`, so users can discover and turn it on (default
  off).

### 5.5 Proxy note

`nuxt.config.ts` already proxies `/ws/**` (prod, same-origin) and `useChat`
handles dev direct-connect; no config change is expected. Confirm `/ws/danmaku/`
works in both dev and prod during QA.

## 6. Testing

Backend (`pytest`, `InMemoryChannelLayer` per `tests/conftest.py`):

- `resolved_at`: set on entering a terminal status; cleared on reopen; re-stamped
  on re-complete; **not** rewritten on terminal→terminal (已解决→已发布).
- Recent endpoint: only events within the 2h window; cap at 50; soft-deleted
  issues excluded; 403 without `issues.view_issue`; created+completed merged and
  ordered newest-first.
- Broadcast: `created` fires once on creation; `completed` fires exactly once per
  completion cycle; no broadcast on reopen; a reopen→re-complete fires a second
  `completed`.
- Consumer: connect rejected (close 4003) without `view_issue`; accepted with it;
  receives a broadcast payload.

Frontend:

- `npx nuxi typecheck`.
- Manual `/qa` with the `bot` account: toggle on/off persists per account; backfill
  appears then live events stream; bullets scroll without overlap; click navigates
  to the issue; mobile shows a single lane; reduced-motion shows a static list.

## 7. Out of scope (YAGNI)

Per-project visibility scoping; bullet reactions/emoji; user-authored danmaku
(this is a read-only activity feed, not comments); history beyond the 2h window;
sound; in-UI density/speed controls (kept as tunable constants); reopen/other
status-change event types.

Known limitation (deferred): uptime auto-recovery (`apps/uptime/services.py`) sets
`resolved_at` explicitly before save, so the `save()` stamping branch is skipped and
no 完成 danmaku fires for monitor auto-resolves; the invariant is still satisfied. A
clean follow-up would let `save()` own the stamping there.

## 8. File touch-list

**Backend (new):** `apps/issues/services_danmaku.py`
**Backend (modified):** `apps/issues/models.py` (`Issue.save()` override for the
`resolved_at` invariant + `TERMINAL_STATUSES` constant),
`apps/issues/signals.py` (new `broadcast_danmaku` post_save receiver, alongside
the existing `trigger_ai_analysis`), `apps/issues/consumers.py` (DanmakuConsumer),
`apps/issues/ws_urls.py` (route), `apps/issues/views.py` + `apps/issues/urls.py`
(recent endpoint), `apps/issues/serializers.py` (remove duplicate `resolved_at`
stamping at lines 466-468).
**Frontend (new):** `app/composables/useIssueDanmaku.ts`,
`app/components/IssueDanmakuBar.vue`
**Frontend (modified):** `app/composables/useUserSettings.ts` (`danmaku_enabled`),
`app/pages/app/issues/index.vue` (mount + toolbar toggle).
**Tests (new):** danmaku endpoint/signal/consumer tests under `backend/tests/`.
