# Design: Disable-able Issue Statuses + Raw-JSON Widget Escape Hatch

Date: 2026-06-16
Status: Approved (pending spec review)

## Problem

DevTrack's `SiteSettings.issue_statuses` is a fixed list of seven statuses
(`未计划 / 待分配 / 待确认 / 进行中 / 已解决 / 已发布 / 已关闭`). Admins can edit each
status's display name, color, and order, but cannot stop using one. Some teams do
not use every status and want to hide the unused ones from the UI.

Status `value`s are hardcoded across the system — the Issue model's `IssueStatus`
TextChoices, the state-transition logic in `apps/issues/services.py`, list ordering
in `apps/issues/views.py`, and frontend constants in `app/constants/issueStatus.ts`.
Therefore "disabling" a status **cannot remove it from the system**. It can only hide
the status from the places where a user *picks* or *views* statuses, while every
existing issue keeps its status and continues to render normally.

Separately, the admin's color-option widget (`ColorOptionListWidget`) is a structured
row editor with no way to bulk-edit or repair the underlying JSON. We add a toggle to
edit the raw JSON directly as a power-user escape hatch.

## Decisions (from brainstorming)

1. **Disable semantics** — a disabled status is hidden *everywhere a user picks or
   views it*: the create-issue status select, list/project filter dropdowns, the batch
   status update, the detail-page status chips, and kanban columns. Existing issues
   retain their status and display it normally (label + color still resolve, because
   the disabled status stays in the config list — it is only flagged, not removed).
2. **Locked set** — any status a code path assigns *outside the status picker* cannot
   be disabled, otherwise an issue can land in a UI-invisible status. From an exhaustive
   grep of `issue.status = …` / `status=…` assignments: `待分配` (initial status of
   every new issue — `services.create_issue` and `uptime.create_incident`), `待确认`
   (assign/transfer/confirm targets), `进行中` (claim/confirm targets), `已解决`
   (`uptime.fire_recovery` auto-resolves an incident issue when a monitor recovers — a
   fully automatic Celery path), and `已关闭` (`IssueCloseWithGitHubView` close action).
   The only two statuses **no** code path ever assigns are `未计划` and `已发布`, so those
   are the sole disable-able statuses. (Revised after code review — the original spec
   listed only the first three and missed the uptime/close paths.)
3. **Kanban orphans** — a disabled status's column is never shown, even if historical
   issues still have that status. Those issues remain visible in the list view; they
   simply do not appear on the board.
4. **Raw-JSON escape hatch** — the raw editor can bypass the UI value-lock and
   disable-lock. Server-side `clean()` enforces only the *new* invariant (a locked
   status may not be flagged disabled) plus JSON validity. Changing a `value` via raw
   JSON remains possible and unguarded — consistent with today's behavior, where values
   are only UI-locked, not validated server-side. The raw editor is explicitly a
   "you take responsibility" power tool.

## Data Model

Each issue-status object gains an optional boolean `disabled`:

```json
{"value": "已发布", "label": "已发布", "background": "#14b8a6", "disabled": true}
```

- Absent / falsy `disabled` ⇒ enabled. All readers default missing to `false`, so the
  feature is backward-compatible with rows that predate it.
- `priorities` is **not** given a `disabled` flag — out of scope (YAGNI).

### Locked-set constant

Add to `apps/issues/models.py`, next to `IssueStatus`:

```python
# 由「状态选择器以外的代码路径」赋值的状态,不可在站点设置中禁用,
# 否则 Issue 会被置入一个 UI 不可见的状态,形成"看不到的工单"
SYSTEM_ASSIGNED_STATUSES = (
    IssueStatus.UNASSIGNED.value,            # create_issue / uptime 建单初始状态
    IssueStatus.PENDING_CONFIRMATION.value,  # assign / transfer / confirm 目标
    IssueStatus.IN_PROGRESS.value,           # claim / confirm 目标
    IssueStatus.RESOLVED.value,              # uptime fire_recovery 监控恢复自动置为已解决
    IssueStatus.CLOSED.value,                # IssueCloseWithGitHubView 关闭动作
)
```

`settings` imports this constant (settings already depends on issues conceptually;
verify no import cycle — if one exists, import lazily inside `clean()` / admin setup).

## Backend Changes

### `apps/settings/models.py`
- `default_issue_statuses()` — add `"disabled": False` to each object (tidy defaults for
  any future fresh row; the singleton already exists in every environment).
- `SiteSettings.clean()` — for each `issue_statuses` entry, if
  `entry.get("disabled")` is truthy **and** `entry["value"] in SYSTEM_ASSIGNED_STATUSES`,
  raise `ValidationError`. This is the safety net behind the UI gray-out and the raw
  editor. (If `clean()` does not yet exist on the model, add one; ensure admin save
  invokes `full_clean()` — django-solo / ModelAdmin save path runs form validation,
  which calls the field/clean validators.)

### `apps/settings/widgets.py` — `ColorOptionListWidget`
- `__init__` gains `allow_disable=False, locked_values=()`.
- `get_context`:
  - When rebuilding each item, **preserve `disabled`** (only when `allow_disable`),
    e.g. `"disabled": bool(p.get("disabled", False))`. Without this the existing
    rebuild at lines 41-48 drops the flag on every render and the checkbox would always
    show enabled.
  - Pass `allow_disable` and `locked_values` (as a JSON-encoded list, same escaping as
    `items_json`) into the template context.

### `templates/widgets/color_option_list.html`
- Add a **toggle button** at the top: `编辑原始 JSON` ⇄ `返回可视化编辑`.
- Two view containers sharing the single hidden `<input>` as submission source of truth:
  - **Rich view** (existing rows box). When `allow_disable`, each row gains a `禁用`
    checkbox bound to `item.disabled`; for rows whose `value` is in `locked_values` the
    checkbox is rendered `disabled` and grayed (title: e.g. `流程关键状态不可禁用`).
  - **Raw view** — a `<textarea>` (monospace, ~10 rows) prefilled with
    `JSON.stringify(items, null, 2)`.
- Mode state machine (`mode` = `'rich' | 'raw'`, starts `'rich'`):
  - rich → raw: set textarea to pretty JSON of current `items`; swap visibility.
  - raw → rich: `JSON.parse(textarea.value)`; if it parses to an **array**, set
    `items`, `render()`, `sync()`, swap; otherwise show an inline error (red text) and
    stay in raw.
  - while in raw, on textarea `input`: try parse; if a valid array, `items = parsed;
    sync()` (live), clear error, normal border; if invalid, red border + inline error
    and **do not** update the hidden input.
  - **submit guard**: a `submit` listener on the enclosing admin form
    (`hidden.form`) calls `preventDefault()` when `mode === 'raw'` and the textarea
    JSON is invalid, surfacing the error and focusing the textarea. This prevents the
    silent-data-loss footgun where an invalid raw edit would otherwise let the form
    save the last-valid hidden value while the admin believes their edits were saved.
    (Added after code review.)
- The `禁用` checkbox column renders only when `allow_disable` is true, so the
  `priorities` widget instance is visually unchanged.

### `apps/settings/admin.py`
- Instantiate the `issue_statuses` widget with
  `allow_disable=True, locked_values=SYSTEM_ASSIGNED_STATUSES`.
- The `priorities` widget instance keeps defaults (`allow_disable=False`) but **does**
  get the raw-JSON toggle, since the toggle is unconditional on the widget.

### Migration
- A data migration (`RunPython`) backfilling `disabled: False` into each existing
  `SiteSettings.issue_statuses` object, mirroring the precedent in
  `0011_issue_statuses_to_objects.py`. Forward backfills; reverse strips the key (or is
  a no-op). Pure-Python, no schema change (JSONField). Low risk; keeps stored data
  explicit rather than relying solely on read-time defaults.

### No change needed
- `SiteSettingsSerializer` already returns the raw `issue_statuses` JSON, so `disabled`
  flows to the frontend automatically.
- `IssueCreateUpdateSerializer.validate_status` checks only `IssueStatus.values`, not
  site settings — so a PATCH that retains an existing (now-disabled) status still
  validates. This is desired; do **not** tighten it.

## Frontend Changes

### `app/composables/useStatus.ts`
- `StatusItem` interface: add `disabled?: boolean`.
- `setStatusesFromSettings`: read `s.disabled` (`Boolean(s.disabled)`), default `false`.
- New helper `isStatusDisabled(value: string): boolean` — looks up the configured item
  and returns its `disabled` flag (missing ⇒ `false`).

### Hide points (exclude disabled statuses)
- `app/pages/app/issues/index.vue`
  - `createStatusOptions` (create-issue select) — filter out disabled.
  - `filterStatusOptions` (list filter) — filter out disabled. `batchStatusItems`
    derives from it and inherits the exclusion.
  - `kanbanStatusKeys` / `kanbanColumns` — drop disabled keys (column not shown).
- `app/pages/app/projects/[id].vue`
  - `statusOptions` (filter) — filter out disabled (keep the leading "all" entry).
  - `kanbanColumns` — drop disabled keys.
- `app/pages/app/issues/[id].vue`
  - `statusItems` (detail-page status chips) — filter out disabled, **except always
    keep the issue's current status** even if disabled, so historical data displays
    correctly and editing other fields does not force a status change. This reuses the
    existing "keep current assignee option for 历史数据" pattern at `[id].vue:1245`.

### Edge-case rule
"Always keep the current value visible" applies only to the detail-page status chips
(the one place tied to a specific issue's current status). Create-issue starts at the
locked `待分配`, and filter dropdowns have no per-issue "current" value, so plain
exclusion is correct there.

## Components / Boundaries

- **`isStatusDisabled` (useStatus.ts)** — single source of truth for "is this status
  hidden from pickers?" Every frontend hide point calls it; no page reimplements the
  rule.
- **`SYSTEM_ASSIGNED_STATUSES` (issues/models.py)** — single source of truth for the
  locked set, consumed by the admin widget (gray-out) and `clean()` (enforcement).
- **`ColorOptionListWidget`** — gains two independent, opt-in behaviors: a `禁用` column
  (`allow_disable`) and an always-on raw-JSON toggle. Priorities get the toggle but not
  the column.

## Testing

Backend (pytest):
- `SiteSettings.clean()` rejects disabling a locked status (e.g. `进行中`) and accepts
  disabling a non-locked one (e.g. `已发布`).
- An issue whose status is disabled can still be PATCHed (status retained) without a
  validation error.
- Data migration: a pre-existing settings row gains `disabled: False` on each status.

Frontend (manual / typecheck):
- `npx nuxi typecheck` passes with the new `StatusItem.disabled` field.
- With `已发布` disabled: it is absent from create/filter/detail pickers and from both
  kanban boards; an issue already in `已发布` still shows its badge in the list and its
  highlighted chip on the detail page.

Admin (manual):
- The `禁用` checkbox appears for issue_statuses, is grayed for locked rows, and
  round-trips on save (flag persists after reload).
- The raw-JSON toggle round-trips items, blocks toggle-back on invalid JSON, and the
  `priorities` widget shows the toggle but no `禁用` column.

## Out of Scope

- `disabled` for priorities or labels.
- Server-side validation of status `value` integrity (the raw editor can still change
  values; this matches the status quo and is the escape hatch's purpose).
- Removing or reordering the kanban's hardcoded base columns.
