# Uptime Monitors Design

**Date**: 2026-05-18
**Status**: Approved (brainstorming complete, pending implementation plan)
**Scope**: Add per-project URL uptime monitoring to DevTrack, displayed inline on the project detail page.

## Goals

Let project administrators add HTTP health checks for their project's services (e.g., `https://outcall-staging.matrixai.xin/health/`), see at-a-glance status on the project detail page, and automatically open Issues when a service goes down so the existing issue-tracking workflow handles the incident.

## Non-Goals

- No monitor detail page in the frontend (Django admin covers deep inspection)
- No external integration (GlitchTip / Uptime Kuma) — fully self-hosted in DevTrack
- No email / webhook / SMS alerts in v1 (in-app notification + auto-created Issue is the only channel)
- No SLA reports, no response-time alerting, no monitor grouping/tags, no maintenance windows
- No POST/HEAD methods, no custom request headers in v1 (`method` field exists for future expansion but only `GET` is allowed)

## Architecture Overview

```
┌─────────────────┐    every 60s    ┌──────────────────────┐
│ Celery Beat     │ ──────────────> │ tick_uptime_monitors │
└─────────────────┘                 └──────────┬───────────┘
                                               │  queries DB for
                                               │  next_check_at <= now()
                                               ▼
                                    ┌──────────────────────┐
                                    │  check_monitor(id)   │  (one task per due monitor)
                                    │  - HTTP GET          │
                                    │  - write UptimeCheck │
                                    │  - apply state machine
                                    └──────────┬───────────┘
                                               │  on threshold breach / recovery
                                               ▼
                                    ┌──────────────────────┐
                                    │  Issue created /     │
                                    │  closed + comment    │
                                    │  in-app notification │
                                    └──────────────────────┘
```

A new Django app `apps/uptime` owns the models, tasks, serializers, views, and URL routes. Frontend gets a new section component on `pages/app/projects/[id].vue` and a popup modal for create/edit.

## Data Model

New app: `apps/uptime/` with two tables.

### `UptimeMonitor` — configuration + current state

| Field | Type | Notes |
|---|---|---|
| `id` | auto PK | |
| `project` | FK → `projects.Project` (CASCADE) | `related_name="uptime_monitors"` |
| `name` | CharField(100) | User-supplied label, no uniqueness constraint |
| `url` | URLField(500) | Must include protocol (`http://` or `https://`) |
| `method` | CharField(10, default=`"GET"`) | Enum; v1 only `"GET"` allowed at serializer layer |
| `expected_status` | CharField(50, default=`"200"`) | Single or comma-separated, e.g. `"200"` or `"200,204"` |
| `expected_body` | CharField(200, blank=True) | If non-empty, response body must contain this substring |
| `interval_minutes` | PositiveIntegerField(default=1) | Min 1, max 1440. UI exposes 1/5/10/30/60 |
| `timeout_secs` | PositiveIntegerField(default=20) | Min 1, max 60 |
| `is_enabled` | BooleanField(default=True) | Disabled monitors are skipped by tick |
| `next_check_at` | DateTimeField(null=True, db_index=True) | Scheduling cursor; tick selects on this |
| `last_check_at` | DateTimeField(null=True) | Set after each check |
| `last_status` | CharField(20, default=`"unknown"`) | `"up"` / `"down"` / `"unknown"` |
| `last_up_at` | DateTimeField(null=True) | Updated only on `down → up` transition; drives "Up for X" display |
| `outage_started_at` | DateTimeField(null=True) | Set when failure threshold trips (the moment `last_status` becomes `down`); cleared on recovery. Drives "Down for X" display |
| `consecutive_failures` | PositiveIntegerField(default=0) | Reset to 0 on any successful check |
| `active_incident_issue` | FK → `issues.Issue` (SET_NULL, null=True) | Points at the currently open auto-generated Issue; cleared on recovery |
| `created_at` / `updated_at` | auto | |

### `UptimeCheck` — single check result

| Field | Type | Notes |
|---|---|---|
| `id` | auto PK | |
| `monitor` | FK → `UptimeMonitor` (CASCADE) | `related_name="checks"` |
| `checked_at` | DateTimeField(db_index=True) | |
| `is_up` | BooleanField | |
| `status_code` | PositiveIntegerField(null=True) | `null` when no response received (timeout, DNS) |
| `response_ms` | PositiveIntegerField(null=True) | |
| `error` | CharField(200, blank=True) | Short reason: `"timeout"`, `"DNS error"`, `"status 500"`, `"body mismatch"` |

Index: `(monitor, -checked_at)` for "latest N checks per monitor" queries and pruning.

## Check Execution

### Tick (master heartbeat)
Registered via static `CELERY_BEAT_SCHEDULE` in `apps/uptime/tasks.py` (loaded by Django at startup), not via `django_celery_beat` DB rows. Runs every 60s.

```python
CELERY_BEAT_SCHEDULE["uptime-tick"] = {
    "task": "apps.uptime.tasks.tick_uptime_monitors",
    "schedule": 60.0,
}
```

The tick task is lightweight: it selects monitor IDs where `is_enabled=True AND (next_check_at IS NULL OR next_check_at <= now())`, then calls `check_monitor.delay(id)` for each.

### Per-monitor check (`check_monitor`)
Steps:
1. `SELECT ... FOR UPDATE SKIP LOCKED` on the monitor row to prevent duplicate execution.
2. Set `next_check_at = now() + interval_minutes` and save **before** the HTTP call, so a slow worker doesn't get re-dispatched by the next tick.
3. Perform HTTP GET using `requests` (already a dependency). Apply `timeout_secs`. Capture response time.
4. Determine `is_up`:
   - Got response AND `response.status_code` matches one of `expected_status` (parsed as comma-separated int list), AND
   - If `expected_body` is non-empty, response text contains it as substring.
   - Otherwise `is_up = False` with an `error` summary (`"timeout"`, `"connection error"`, `"status 500"`, `"body mismatch"`, etc.).
5. Insert `UptimeCheck` row.
6. Apply state transition (next section).

### Failure threshold and state machine

`UPTIME_FAILURE_THRESHOLD = 3` in settings (configurable, not hard-coded).

Transition rules applied after every check:

| Before (`last_status`) | This check | New `consecutive_failures` | Side effect |
|---|---|---|---|
| `up` or `unknown` | up | 0 | None |
| `up` or `unknown` | down | +1 | If reaches threshold → **fire failure** |
| `down` | down | +1 | None (already in outage) |
| `down` | up | 0 | **Fire recovery** |

After applying, update `last_status`, `last_check_at`. Set `last_up_at = now()` only on `down → up` transition.

### Failure action
1. Create an `issues.Issue` in `monitor.project`:
   - `title = f"[监控告警] {monitor.name} 不可达"`
   - `description` (Markdown): monitor name, URL, first-failed-at timestamp, consecutive failure count (3), latest error message
   - `priority = "P1"`
   - `status = IssueStatus.PENDING` (`"待处理"`)
   - `created_by`: system bot user (see "System bot user" below)
   - `reporter`: empty string (the `reporter` field is freeform text in `Issue`)
   - `assignee`: null (left for human triage)
2. Set `monitor.active_incident_issue = issue`, `last_status = "down"`, `outage_started_at = now()`.
3. Send in-app notification (`Notification` with `notification_type=SYSTEM`, `target_type=USER`, `source_issue=issue`) to all `ProjectMember` users of the project. Title: `"监控 {name} 不可达"`, content: `"已创建 Issue #{id}"`.

### Recovery action
1. Locate `monitor.active_incident_issue`. If it's null or already closed (status `已关闭` or `已解决`), skip the close step but still send notification.
2. Compute outage duration: `now() - monitor.outage_started_at`.
3. Append a system comment on the issue authored by the system bot user: `"监控已于 {recovered_at} 恢复,故障持续 {duration_human}。"` (Implementation reads the existing comment model + creation path in `apps/issues` and reuses it.)
4. Set issue `status = IssueStatus.RESOLVED` (`"已解决"`) and `resolved_at = now()`.
5. Clear `monitor.active_incident_issue = None`, `outage_started_at = None`, set `last_up_at = now()`, `last_status = "up"`, `consecutive_failures = 0`.
6. In-app notification to project members: `"监控 {name} 已恢复,持续 {duration_human}"`, linking to the same Issue.

### Edge cases
- **Monitor deleted while issue open**: `active_incident_issue` foreign key uses `SET_NULL`, the Issue is untouched (manual cleanup).
- **Monitor disabled (`is_enabled=False`) while in outage**: tick skips it. `active_incident_issue` stays as-is. Re-enabling resumes checks; recovery flow runs normally on the next up result.
- **Manually closed Issue followed by new outage**: when firing failure, if `active_incident_issue` is null OR refers to an already-closed Issue, create a brand new Issue and update the pointer. Never reopen a closed Issue.

### System bot user
The project already has a `bot` user (visible as a project member in the UI). The implementation will:
1. Add `UPTIME_SYSTEM_BOT_USERNAME = "bot"` to `config/settings.py`.
2. Resolve it via `User.objects.get(username=settings.UPTIME_SYSTEM_BOT_USERNAME)` when creating Issues / comments / notifications.
3. If the user doesn't exist, the failure handler raises and logs; deployment must create the user first.

## API

URL routes registered under `apps/uptime/urls.py`, mounted in `apps/urls.py` at `uptime/`. The project-scoped list/create lives under the existing `projects/` namespace.

| Method | URL | Purpose |
|---|---|---|
| `GET` | `/api/projects/{project_id}/monitors/` | List monitors for a project |
| `POST` | `/api/projects/{project_id}/monitors/` | Create monitor (project bound from URL) |
| `GET` | `/api/uptime/monitors/{id}/` | Retrieve a single monitor |
| `PATCH` | `/api/uptime/monitors/{id}/` | Update |
| `DELETE` | `/api/uptime/monitors/{id}/` | Delete |
| `GET` | `/api/uptime/monitors/{id}/checks/?limit=60` | Recent checks, newest first |

The nested list/create routes will be added to `apps/projects/urls.py` (following the same pattern as `/api/projects/{id}/issues/`).

### Serializers

**`UptimeMonitorSerializer`** (used by list/retrieve/create/update):
- Writable: `name`, `url`, `method`, `expected_status`, `expected_body`, `interval_minutes`, `timeout_secs`, `is_enabled`
- Read-only: `id`, `last_status`, `last_check_at`, `last_up_at`, `outage_started_at`, `active_incident_issue_id`

Validation:
- `url` must pass `URLValidator` (Django built-in) and start with `http://` or `https://`
- `name` 1–100 chars, no uniqueness check
- `expected_status` regex `^\d{3}(,\d{3})*$`
- `method` must equal `"GET"` (raise on anything else in v1)
- `interval_minutes` ∈ [1, 1440]
- `timeout_secs` ∈ [1, 60]

**`UptimeCheckSerializer`** (read-only):
- `checked_at`, `is_up`, `status_code`, `response_ms`, `error`

### Permissions
New `apps/uptime/permissions.py`:

```python
class IsSuperUserOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_superuser
```

Applied to all monitor + check views. Authenticated non-superusers can read; only superusers can create/update/delete. No Django group/role setup needed, so `sync_page_perms` is unaffected.

## Frontend

### Section placement
On `frontend/app/pages/app/projects/[id].vue`, insert a new section `<UptimeMonitorsSection :project-id="..." />` between "项目成员" and the Issues block. Section styling matches the surrounding cards (`bg-white dark:bg-gray-900 rounded-xl border ... p-5`).

Header: `系统监控 (N)` on the left, `+ 添加监控` button on the right (visible only when `useAuth().user.is_superuser` is true).

### Per-monitor row (GlitchTip-style)
Each row contains:
- **Status dot** (left, 8px circle): green / red / gray for `up` / `down` / `unknown`
- **Name** (bold) above **URL** (small, muted, with link affordance)
- **Timeline** (center): a horizontal strip of up to 60 small bars, each ~4px wide with 1px gap. Color = `is_up` of that check. Oldest left, newest right. Hover on a bar shows a tooltip: `"已恢复 - 2026-05-18 10:54"` for up, `"宕机 - 2026-05-18 10:54 (timeout)"` for down.
- **Right-aligned status text**:
  - `up`: green `"已稳定运行 X 天/小时/分钟"` (computed from `last_up_at`)
  - `down`: red `"已宕机 X 分钟"` (computed from `outage_started_at` — a new read-only field on the monitor serializer that the backend exposes; set to the timestamp of the failure that triggered the outage, cleared on recovery)
  - `unknown`: gray `"等待首次检查"`
- **Hover actions** (superuser only): edit pencil + delete trash icons appear on the right end. Edit opens the same modal in edit mode. Delete shows a `UAlertDialog` confirm.

### Add/Edit modal
Component `UptimeMonitorFormModal.vue`. Fields:
- 监控名称 * (text)
- URL * (text, placeholder `https://...`)
- 期望状态码 (text, default `200`)
- 期望响应体关键字 (text, optional)
- 检查间隔 (select: 1 / 5 / 10 / 30 / 60 分钟)
- 超时 (number input, seconds, default 20)
- Buttons: 取消 / 创建 (or 保存 in edit mode)

Submit calls `POST /api/projects/{id}/monitors/` or `PATCH /api/uptime/monitors/{id}/`. On success, close modal and refresh the section's monitor list.

### Component tree
```
frontend/app/components/projects/
  UptimeMonitorsSection.vue       # owns data fetch + polling + modal trigger
  UptimeMonitorRow.vue            # single row, hover actions
  UptimeMonitorTimeline.vue       # pure presentational, props: checks[]
  UptimeMonitorFormModal.vue      # create/edit form
```

### Data fetching + auto-refresh
On mount, `UptimeMonitorsSection.vue`:
1. `GET /api/projects/{id}/monitors/` → list of monitors
2. For each monitor, `GET /api/uptime/monitors/{id}/checks/?limit=60` → timeline data (parallel)

Every 60s, re-fetch only `GET /api/projects/{id}/monitors/` and patch existing rows' `last_status` / `last_check_at` / `last_up_at` / `active_incident_issue_id` in place. **Do not re-fetch timeline data on the polling cycle** — that would N× the request volume for no visual gain (timeline only changes once per minute per monitor; we can rely on the next page load to refresh it, or extend polling later if needed). Polling stops when the component unmounts.

### Uptime formatter helper
Add `frontend/app/utils/formatUptime.ts`:
```ts
export function formatUptime(lastUpAt: string | null, lastStatus: string): string
```
Returns the Chinese strings listed above.

## Data Retention & Cleanup

`UPTIME_CHECK_RETENTION_DAYS = 30` in settings.

Second Celery Beat job, runs daily at 3 AM:
```python
CELERY_BEAT_SCHEDULE["uptime-prune-checks"] = {
    "task": "apps.uptime.tasks.prune_old_checks",
    "schedule": crontab(hour=3, minute=0),
}
```

`prune_old_checks` deletes `UptimeCheck` rows where `checked_at < now() - 30 days`. Hard delete, no archive. Order-of-magnitude check: 60 monitors × 1440 checks/day × 30 days ≈ 2.6M rows steady state — within Postgres' comfort zone for this index layout.

## Settings additions

```python
# config/settings.py

# Uptime monitoring
UPTIME_TICK_SECONDS = 60
UPTIME_FAILURE_THRESHOLD = 3
UPTIME_CHECK_RETENTION_DAYS = 30
UPTIME_DEFAULT_TIMEOUT_SECS = 20
UPTIME_SYSTEM_BOT_USERNAME = "bot"
```

## Testing

All in `backend/tests/test_uptime.py`, using `pytest-django` + `factory-boy` like the existing tests.

**State machine** (highest priority, no external IO):
- up → up (no side effects)
- up → down ×1, ×2 (no Issue yet)
- up → down ×3 (Issue created, notification sent, `active_incident_issue` set)
- down → down (no duplicate Issue)
- down → up (Issue closed with comment, `active_incident_issue` cleared, `last_up_at` updated)
- `active_incident_issue` is null when firing failure → create new Issue
- `active_incident_issue` is already-closed when firing failure → create new Issue (do not reopen)

**HTTP check layer** (mock `requests` with `responses` library or `pytest-httpx`):
- 200 → up
- expected_status="200", got 204 → down with `error="status 204"`
- expected_status="200,204", got 204 → up
- expected_body="healthy", body=`'{"status":"healthy"}'` → up
- expected_body="healthy", body=`'{"status":"degraded"}'` → down with `error="body mismatch"`
- timeout → down with `error="timeout"`
- connection refused → down with `error="connection error"`

**Tasks**:
- `tick_uptime_monitors` dispatches only monitors with `next_check_at <= now()` and `is_enabled=True`
- `check_monitor` sets `next_check_at` before issuing HTTP request
- `prune_old_checks` deletes only checks older than 30 days

**API**:
- Non-superuser POST/PATCH/DELETE → 403
- Authenticated user GET → 200
- POST with malformed URL → 400
- POST with malformed `expected_status` → 400
- POST through `/api/projects/{id}/monitors/` auto-binds project

**Frontend**: no automated tests in v1 (project has no frontend test infrastructure). Verification is `npx nuxi typecheck` + manual smoke test of: add monitor → see it appear → see first check turn it green → trigger failure (point at unreachable URL) → after 3 minutes see Issue created and red status.

## Deployment

1. New app `apps/uptime/` with models, tasks, serializers, views, urls, admin.
2. `python manage.py makemigrations uptime && migrate`
3. Register routes in `apps/urls.py` (`uptime/`) and `apps/projects/urls.py` (nested `monitors/`).
4. Update `config/settings.py` with the new settings and `CELERY_BEAT_SCHEDULE` entries.
5. Restart Celery worker + Beat to load new tasks.
6. `sync_page_perms` is **not** required (no Django groups/permissions added).
7. Ensure the `bot` user exists in production (or set `UPTIME_SYSTEM_BOT_USERNAME` to a user that does).
8. Deploy: push to `env/test`, manual smoke test, then (with explicit user approval per CLAUDE.md) push to `env/prod`.

## Open Items for Implementation

These are minor details to resolve when reading the surrounding code, not new design decisions:

- How `Issue` system comments are created in the existing codebase (find by grepping `apps/issues/` for comment creation, then mimic).
- Whether the existing `apps/notifications/services.py` exposes a generic `create_system_notification(target_users, title, content, source_issue)` helper, or we need to add one.
- Verifying the `IssueStatus.RESOLVED` value is the canonical "resolved" string used elsewhere in the app, and confirming `resolved_at` should be set when transitioning to resolved.
