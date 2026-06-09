# Design — Header Bulletin Carousel & Issues Filter-Bar Enhancements

**Date:** 2026-06-09
**Status:** Approved (design)
**Scope:** Two independent UX enhancements. Feature A is full-stack; Feature B is frontend-only. They can ship as separate PRs.

---

## Feature A — Header Bulletin Carousel (走马灯)

A rotating banner in the empty center of the global app header. Content is **backend-managed** so admins (and non-technical staff) can edit it without a deploy.

### Naming & placement decision

The content is broadcast-style (shown to everyone, **no per-user read tracking**) — unlike `Notification`, which is built around fan-out + read state (`NotificationRecipient.is_read/read_at`). So it is a **separate model**, not a reuse of `Notification`.

It lives in the existing **`apps.notifications`** app (the messaging domain) rather than a new app. The model is named **`Bulletin`** — deliberately *not* `Broadcast`, because `Notification.Type.BROADCAST` already exists in that app (a tracked all-users notification); a second meaning of "broadcast" in the same app would be confusing. `Bulletin` (公告栏) keeps the namespace unambiguous: `notifications.Bulletin` = ambient/untracked, `Notification.Type.BROADCAST` = inbox/tracked.

### Categories
Five content categories, all surfaced through one carousel:
- `quote` — 编程大神名言
- `prompt` — 最新最火提示词
- `pitfall` — 最新避坑指南
- `value` — 公司价值观
- `announcement` — 重大提醒公告

### A1. Backend — `Bulletin` model in `apps.notifications`

No new app, no new `INSTALLED_APPS` entry, no new URL include (the notifications app is already mounted at `/api/notifications/`).

**`Bulletin` model** (added to `apps/notifications/models.py`):

| field | type | notes |
|---|---|---|
| `id` | AutoField (default pk) | |
| `category` | `CharField(choices=Category.choices)` | TextChoices: `quote` 名言 / `prompt` 提示词 / `pitfall` 避坑 / `value` 价值观 / `announcement` 公告 |
| `content` | `TextField` | the bulletin / announcement text |
| `source` | `CharField(blank=True)` | optional attribution (e.g. quote author) |
| `link_url` | `URLField(blank=True)` | optional "查看详情" link (mainly announcements) |
| `is_active` | `BooleanField(default=True)` | admin on/off toggle |
| `sort_order` | `IntegerField(default=0)` | admin ordering |
| `starts_at` | `DateTimeField(null=True, blank=True)` | optional auto-show start |
| `ends_at` | `DateTimeField(null=True, blank=True)` | optional auto-expire |
| `created_by` | `FK(AUTH_USER_MODEL, on_delete=SET_NULL, null=True, blank=True)` | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |
| `updated_at` | `DateTimeField(auto_now=True)` | |

`Meta`: `ordering = ["sort_order", "-created_at"]`, `verbose_name = "走马灯公告"`. `__str__` returns a truncated `content`.

**Helper** — a queryset/manager method `Bulletin.objects.currently_active()` returning `is_active=True` AND (`starts_at` is null or `<= now`) AND (`ends_at` is null or `>= now`).

### A2. API — two tiers

Added to `apps/notifications/urls.py` (after the existing notification routes), mirroring the user-facing-vs-manage split already used there.

**Public read (carousel)** — `GET /api/notifications/bulletins/active/`
- Permission: `IsAuthenticated` only (every logged-in user, no model perm).
- Returns `Bulletin.objects.currently_active()` via a lean public serializer: `id, category, content, source, link_url`.
- Returns a flat list ordered by `sort_order` (unpaginated — the active set is small); the client groups by category and applies pinning logic (A5).

**Admin manage** — gated by `IsAuthenticated, FullDjangoModelPermissions`:
- `GET  /api/notifications/bulletins/manage/` — list all (admin serializer: all fields + `created_by_name`).
- `POST /api/notifications/bulletins/manage/create/` — create.
- `GET  /api/notifications/bulletins/manage/<pk>/` — detail.
- `PATCH /api/notifications/bulletins/manage/<pk>/update/` — update.
- `DELETE /api/notifications/bulletins/manage/<pk>/` — delete.

`FullDjangoModelPermissions` maps GET→`notifications.view_bulletin`, POST→`notifications.add_bulletin`, PATCH→`notifications.change_bulletin`, DELETE→`notifications.delete_bulletin`.

### A3. Permission + nav wiring (DB-driven)

Navigation and route guards are built from DB `PageRoute` records synced from `backend/page_perms.json`, so **no manual edits** to `useNavigation.ts` or `auth.global.ts` are required.

- Add to `seed_routes` in `page_perms.json`:
  ```json
  {
    "path": "/app/settings/bulletins",
    "label": "走马灯管理",
    "icon": "i-heroicons-megaphone",
    "permission": "notifications.view_bulletin",
    "parent": "#group:system",
    "is_group": false,
    "sort_order": 18,
    "show_in_nav": true,
    "is_active": true,
    "meta": {},
    "source": "seed"
  }
  ```
  (`sort_order` to be reconciled with siblings under `#group:system` so it slots sensibly.)
- Add `notifications.add_bulletin`, `notifications.change_bulletin`, `notifications.delete_bulletin`, `notifications.view_bulletin` to the `管理员` group in `seed_groups`.
- Run `uv run python manage.py sync_page_perms` after `migrate`.

### A4. Admin CRUD page — `/app/settings/bulletins`

`frontend/app/pages/app/settings/bulletins.vue`, matching the `backups.vue` / `users` page pattern:
- Header with title 走马灯管理 + 新建按钮.
- `UTable`: columns = category (badge), content (truncated preview), active (`USwitch`/badge), time window, 操作 (edit/delete buttons).
- `UModal` create/edit form: category `USelect`, content textarea, source `UInput`, link `UInput`, active `USwitch`, optional `starts_at`/`ends_at`.
- Delete with confirmation.
- All calls via `useApi()` against `/api/notifications/bulletins/manage/...`.

### A5. Carousel component + composable

**`frontend/app/composables/useBulletins.ts`**
- Fetches `GET /api/notifications/bulletins/active/` on mount; refreshes every ~5 minutes, **visibility-aware** (pause polling when tab hidden), modeled on the existing `useGatewayStatus` composable.
- Exposes the active bulletins split into `announcements` (category `announcement`) and `rotating` (the other four).

**`frontend/app/components/HeaderBulletinCarousel.vue`**
- Inserted into the empty center of `AppHeader.vue`:
  ```vue
  <div class="hidden lg:flex flex-1 min-w-0 justify-center px-4">
    <HeaderBulletinCarousel />
  </div>
  ```
  Hidden at ≤md breakpoints to avoid crowding; single line with truncation.
- **Announcement pinning:** if ≥1 active announcement exists, the carousel persistently shows the announcement with distinct alert styling (amber accent + icon) and does **not** rotate the other categories. If multiple announcements are active, rotate among announcements only. When no announcement is active, rotate the four regular categories.
- **Rotation:** shuffled pool, fade/slide transition every ~8s, **pause on hover**. Each category renders a small leading icon + subtle accent color. `link_url`, when present, makes the item a click-through.
- Renders nothing (collapses gracefully) when there are no active bulletins.

### A6. Seed data

A data migration in `apps.notifications` seeds a few starter bulletins (≈one per non-announcement category) so the carousel is non-empty on first deploy. No seed announcement (announcements are event-driven).

### A7. Tests (backend, pytest)

- `BulletinFactory` added to `tests/factories.py`.
- `GET /api/notifications/bulletins/active/` returns only `is_active=True` bulletins within their time window; excludes inactive and out-of-window rows.
- `GET .../bulletins/active/` is reachable by an ordinary authenticated user (no `notifications.*_bulletin` perm).
- Manage endpoints enforce `notifications.view/add/change/delete_bulletin` (403 without perm, 200/201/204 with).

---

## Feature B — Issues Filter Bar (frontend-only)

All changes are within `frontend/app/pages/app/issues/index.vue` plus one small new component. No backend changes.

### B1. Collapsible filter bar

The filter row auto-collapses to reduce clutter, since filters are used infrequently.

- **Always visible (never collapse):** 新建问题 button, 看板/列表 view toggle, refresh button.
- **Collapsible filter controls:** 查看全部 toggle, 搜索 input, 负责人, 优先级, 状态, 只看我的.
- **Collapsed state:** a compact **「筛选 ▾」trigger** plus **active-filter chips** summarizing what's applied (e.g. `只看我的 ✓`, `中`, `进行中`, `搜索: xxx`). Each chip is ×-clearable.
- **Expand:** hover the trigger/chip area for ~400ms (hover-intent delay to avoid accidental opens) **or** click the trigger.
- **Collapse:** ~2.5s after the mouse leaves the filter region. The collapse timer is **cancelled** while any filter dropdown is open or an input is focused, and re-armed when that ends.
- **Accessibility:** the trigger is a real `<button>` (keyboard-focusable; click-to-expand works without hover). Default state is collapsed.
- State is ephemeral (a local `filtersExpanded` ref + hover/idle timers); not persisted to user settings. Filter state itself stays in `index.vue` (it drives `fetchIssues`) — no risky extraction of the existing bound refs.

### B2. 「只看我的」filter

- A toggle placed among the filter controls.
- Maps to `assignee = current user id` (`useAuth().user.id`), reusing the existing `assignee` query param — **no backend change**.
- **Mutually exclusive** with the 负责人 dropdown (both target `assignee`): turning 只看我的 on clears `filterAssignee`; selecting a 负责人 turns 只看我的 off.
- Surfaces as its own active-filter chip.

### B3. 优先级 slider

- Replaces the 优先级 `USelect` dropdown with a small custom component `frontend/app/components/PrioritySlider.vue`.
- Discrete single-pick snap positions: **全部 · 低(P3) · 中(P2) · 高(P1) · 紧急(P0)** (ordered low→urgent along the track).
- "全部" position clears the priority filter.
- Emits the existing exact-match `priority` value (`P0`–`P3`) into the current `filterPriority` ref — **zero backend change** (backend `priority` filter is exact-match).
- Uses `PRIORITY_ITEMS` from `usePriority.ts` for labels/values.

---

## Cross-cutting

- **Shipping:** Feature A (full-stack) and Feature B (frontend-only) are independent → two separate PRs/branches recommended.
- **Deploy:** No prod deploy without the user's explicit go-ahead (standing constitutional rule). After backend changes, run `migrate` + `sync_page_perms`.
- **i18n:** All UI text in Chinese (zh-hans), per project convention.
- **No new runtime warnings** introduced (project policy: fix warnings via upstream, never silence).
