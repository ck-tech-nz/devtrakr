# Sidebar restructure: 团队效能 group, header dropdown, All tasks panel, Manus-style chrome

## Problem

The current `/app` shell has three rough edges that this work addresses together:

1. The "AI 分析" sidebar group mixes a personal page (`我的提升计划`) with two admin-only pages (`团队分析`, `团队计划管理`). Non-admins see a group titled "AI 分析" that only contains their own plan view, which is misleading. The label "AI 分析" also no longer reflects what the group is for — it has drifted into a team-performance toolset.
2. Users have no way to see their open issues without leaving the page they are on. `MyPendingTasks.vue` exists on the home page but disappears as soon as they navigate away.
3. The sidebar chrome (auto-collapse toggle, service status, branding) is dated next to peer tools like Manus. The auto-collapse button sits at the bottom and competes with the service status, and there is no company brand mark.

## Goal

- Rename the misnamed group to `团队效能`, move the personal page out to the header user-menu, and hide the entire group from non-administrators.
- Surface the user's open issues in the sidebar itself ("我的待办" panel) using the same logic as the existing `MyPendingTasks` home-page card.
- Restructure the sidebar chrome to a Manus-style layout: auto-collapse on top, compact service-status + MATRIX AI brand mark on the bottom.

## Non-goals

- Re-permission backend API calls. `ai.view_analysis` / `kpi.change_improvementplan` codes are not redistributed across groups; the new admin gate is a frontend-nav + middleware concern. Users who happen to hold those perms outside the 管理员 group still get blocked at the URL.
- Real-time push for the new "我的待办" sidebar panel. It is a lazy/refetch-on-demand list, not a websocket subscription. Out of scope for this round.
- Reworking the existing home-page `MyPendingTasks` card visually. We extract its data logic into a composable but do not redesign the card itself.
- Generalising the "dynamic-children nav group" concept. The All-tasks panel is implemented as a one-off sidebar component, not a new entry in the route schema. If a second dynamic panel ever appears, that's when generalisation pays for itself.
- Touching `superuserOnly` middleware gaps. Currently `meta.superuserOnly` is only enforced in the nav filter, not in `auth.global.ts`. Tightening that is out of scope; this spec only introduces `meta.adminOnly` enforcement.

## User flow

### Admin (member of 管理员 group or superuser)
1. Opens the sidebar. Sees the new `团队效能` group containing `团队分析` and `团队计划管理`.
2. Clicks their avatar at the top-right. The dropdown now has `我的提升计划` between `个人资料` and `退出登录`.
3. Scrolls to the bottom of the sidebar. Sees `我的待办` panel with their open issues (count badge in the header). Expanding shows up to 5 issue rows + a `查看全部 →` link.
4. Sees auto-collapse `«` button in the top-right of the sidebar header. Sees compact service-status dots on the bottom-left and MATRIX AI brand mark on the bottom-right.

### Non-admin (e.g. 开发者, 测试)
1. Same as admin, except the `团队效能` group is not rendered at all.
2. If they attempt to URL-navigate to `/app/ai/team-analysis` or `/app/ai/plans`, the route middleware redirects to `/app/forbidden`.
3. They still get `我的提升计划` in the header dropdown (the route's permission was already `None`).

## Architecture

### Backend — `PAGE_PERMS` config + sync

`backend/config/settings.py` `PAGE_PERMS.SEED_ROUTES` edits:

| Path | Before | After |
|---|---|---|
| `/app/ai/team-analysis` | `meta: {"serviceKey": "ai"}` | `meta: {"serviceKey": "ai", "adminOnly": True}` |
| `/app/ai/my-plan` | `show_in_nav: True` (default), no `meta` | `show_in_nav: False`, no `meta` change |
| `/app/ai/plans` | no `meta` | `meta: {"adminOnly": True}` |

After editing, run `uv run python manage.py sync_page_perms` to push the updated rows to the `page_perms_pageroute` table (the command is idempotent via `update_or_create` on `path`).

`my-plan` keeps `permission: None` (visible to everyone authenticated) so the header dropdown link works for non-admins. `show_in_nav: False` hides it from the sidebar but the page still resolves at `/app/ai/my-plan`.

No schema change. `meta` is already a `JSONField` on `PageRoute` and is already returned by `/api/page-perms/routes/`.

### Frontend — nav model & filter

`frontend/app/composables/useNavigation.ts`:

1. Rename `GROUP_DEFS[1]`:
   ```ts
   { label: '团队效能', icon: 'i-heroicons-chart-bar', paths: ['/app/ai/team-analysis', '/app/ai/plans'] },
   ```
   (icon switches from `cpu-chip` to `chart-bar` since the group is no longer AI-branded. `cpu-chip` stays as the icon for the `团队分析` child via the route's own seed.)

2. `filteredNavItems` adds an `adminOnly` filter parallel to the existing `superuserOnly`:
   ```ts
   const isAdmin = computed(
     () => user.value?.is_superuser || hasGroup('管理员')
   )
   ...
   if (item.meta?.adminOnly && !isAdmin.value) return false
   ```
   `hasGroup` is already exported from `useAuth()`.

3. `my-plan` no longer needs a child slot in `GROUP_DEFS` since `show_in_nav: False` removes it from `routes` upstream.

### Frontend — route middleware admin gate

`frontend/app/middleware/auth.global.ts` currently checks only `routePermissions` (`permission` codes). Add a second check for `meta.adminOnly`:

```ts
// after the existing perm check
const { routes } = usePagePerms()
const isAdmin = user.value.is_superuser || user.value.groups.includes('管理员')
for (const route of routes.value) {
  if (to.path === route.path || to.path.startsWith(route.path + '/')) {
    if (route.meta?.adminOnly && !isAdmin) {
      return navigateTo('/app/forbidden')
    }
    break
  }
}
```

This catches users who hold `ai.view_analysis` outside the 管理员 group (currently 开发者 / 产品经理 / 测试 do).

### Frontend — header dropdown

`frontend/app/components/AppHeader.vue` `userMenuItems`: insert one entry into the first group, after `个人资料`:

```ts
{
  label: '我的提升计划',
  icon: 'i-heroicons-clipboard-document-check',
  onSelect: () => navigateTo('/app/ai/my-plan'),
}
```

No permission guard on the entry — matches the route's existing `permission: None`.

### Frontend — `useMyTasks` composable

New file `frontend/app/composables/useMyTasks.ts`. Extracts the data-fetching half of `MyPendingTasks.vue`:

```ts
export function useMyTasks() {
  const tasks = useState<any[]>('my-tasks', () => [])
  const totalCount = useState<number>('my-tasks-count', () => 0)
  const loading = useState<boolean>('my-tasks-loading', () => false)

  async function load() { /* same 4-or-5-call Promise.all as before */ }
  async function closeIssue(task) { /* unchanged */ }

  return { tasks, totalCount, loading, load, closeIssue }
}
```

`useState` (Nuxt) gives a shared reactive instance across the two consumers (home card + sidebar panel) without extra wiring. `MyPendingTasks.vue` is rewritten to consume the composable; behaviour is unchanged.

### Frontend — `MyTasksSidebar` component

New file `frontend/app/components/MyTasksSidebar.vue`. Rendered inside `AppSidebar.vue` after the `<template v-for=... groupedNavItems>` block, gated by `can('issues.view_issue')`.

Behaviour:

- Group-style header row: icon `i-heroicons-inbox-stack`, label `我的待办`, count badge (small pill showing `totalCount`), chevron toggle.
- Expanded:
  - Up to 5 rows. Each row: `#{id}` (mono, gray-400) + title (truncate) + status dot. Click → `navigateTo('/app/issues/' + id)`.
  - Footer row: `查看全部 →` link → `/app/issues?assignee={me}`.
- Collapsed sidebar (auto-collapse mode, `expanded=false`): only the icon + count badge are visible. Click expands the sidebar (existing hover behaviour).
- Loads via `useMyTasks().load()` on mount and on group expand. No polling. After `closeIssue` from `MyPendingTasks`, `tasks` ref auto-updates because state is shared.

### Frontend — `AppSidebar.vue` layout reflow

The current sidebar template has three regions: top header (h-16), nav (flex-1), and two footer blocks (service status + auto-collapse). After this work it has three regions but shaped differently:

**1. Top header (h-16, unchanged height):**
```
[ logo-icon 8×8 ] DevTrakr [────spacer────] [«/»]
```
- Logo + brand text — unchanged.
- Auto-collapse toggle moves here: a `<button>` on the right side of the header bar. Uses `i-heroicons-chevron-double-left` when `autoCollapse=true`, `chevron-double-right` when `false`. Bound to the same `autoCollapse` computed (writes through to `useUserSettings`).
- Collapsed state (w-16): only logo + button are visible, both centered/compact.

**2. Nav (flex-1, scrollable):** existing `groupedNavItems` loop + the new `<MyTasksSidebar />` appended after.

**3. Bottom footer (single row, replaces both existing footer blocks):**
```
[● ●]                              [MATRIX AI mark]
```
- Left: two `ServiceStatusDot` instances inline (github, ai). Labels removed; wrap each in `UTooltip` showing `getLabel(key)`. Click still toggles via `useServiceStatus`. The `服务状态 (Demo)` heading is removed.
- Right: `<a href="https://matrixai.xin/" target="_blank" rel="noopener">` wrapping `<img src="~/assets/images/matrix-ai-logo.svg" class="h-5 w-auto">`. `title="MATRIX AI"`.
- Collapsed sidebar: footer reflows to a vertical stack — two dots stacked vertically, MATRIX AI shrinks to the mark-only variant (`matrix-ai-mark.svg`) below them.

### MATRIX AI brand assets

Fetch from `https://matrixai.xin/`:
- A full word-mark (text + mark variant) → `frontend/app/assets/images/matrix-ai-logo.svg`
- An icon-only mark → `frontend/app/assets/images/matrix-ai-mark.svg`

If only PNG is available on the site, use PNG. If only one variant exists, reuse it for both expanded and collapsed states.

## Data flow

```
PAGE_PERMS (settings.py)
  └─ sync_page_perms ──► page_perms_pageroute table
                          │
                          ▼ /api/page-perms/routes/
                       usePagePerms.routes
                          │
                          ├─► useNavigation.filteredNavItems
                          │      (drops adminOnly when !isAdmin)
                          │      └─► AppSidebar nav loop
                          │
                          └─► auth.global.ts middleware
                                 (redirects on meta.adminOnly mismatch)

useMyTasks (new composable)
  ├─► MyPendingTasks.vue (home card)
  └─► MyTasksSidebar.vue (sidebar bottom panel)

useUserSettings.sidebar_auto_collapse
  ├─► AppSidebar header-toggle button (NEW location)
  └─► (old footer toggle removed)

useServiceStatus
  └─► AppSidebar footer-dots (NEW compact form)
```

## Edge cases

- **Admin demoted mid-session**: A user removed from `管理员` while the SPA is open continues seeing the `团队效能` group until `/api/auth/me/` refetches (next navigation guard run). Acceptable — middleware will still block the URL on the next route.
- **No issues assigned**: `useMyTasks.totalCount === 0`. `MyTasksSidebar` still renders the group header (with `0` badge) so the user knows the panel exists. Empty state inside: a single muted line "暂无待办".
- **Hover collapse race**: The auto-collapse button at the top has a small click target. Make sure `@click` does not bubble to the `@mouseenter`/`@mouseleave` handlers on the `<aside>` (the existing handlers manage the hover-expand). Use `.stop` if needed.
- **Tooltip on collapsed sidebar**: When collapsed, the footer dots stack vertically and tooltips should still anchor correctly. Nuxt UI `UTooltip` handles positioning; verify visually.
- **`matrixai.xin` unreachable at build time**: We're saving the assets locally, so runtime doesn't need the site. WebFetch is a one-off during implementation.

## Testing

Backend:
- `tests/test_page_perms_sync.py` exercises the sync command pattern. Add a small assertion (in a new or existing test) that after sync, `/app/ai/team-analysis` and `/app/ai/plans` have `meta["adminOnly"] is True`, and `/app/ai/my-plan` has `show_in_nav is False`.

Frontend (manual smoke since no FE unit-test setup):
- Login as 管理员 → sees 团队效能 group with two children, no my-plan child, my-plan reachable from header dropdown.
- Login as 开发者 → no 团队效能 group, can still reach my-plan from header dropdown, typing `/app/ai/team-analysis` in URL → redirected to `/app/forbidden`.
- 我的待办 panel: with assigned issues, badge count matches home card; expanding shows up to 5; "查看全部" navigates correctly; close from home card propagates to sidebar (shared state).
- Auto-collapse toggle in the header: clicking flips state, persists across reload, sidebar collapses on mouseleave when on.
- Service-status dots: hover shows tooltip with label; click toggles (demo behaviour preserved).
- MATRIX AI brand: click opens `https://matrixai.xin/` in a new tab; collapsed sidebar shows icon-only variant.

## File touch list

- `backend/config/settings.py` — `PAGE_PERMS.SEED_ROUTES` edits
- `frontend/app/composables/useNavigation.ts` — group rename, adminOnly filter
- `frontend/app/middleware/auth.global.ts` — adminOnly route check
- `frontend/app/components/AppHeader.vue` — dropdown entry
- `frontend/app/composables/useMyTasks.ts` — new
- `frontend/app/components/MyPendingTasks.vue` — refactor to use composable
- `frontend/app/components/MyTasksSidebar.vue` — new
- `frontend/app/components/AppSidebar.vue` — header toggle, footer reflow, panel embed
- `frontend/app/assets/images/matrix-ai-logo.svg` — new (fetched)
- `frontend/app/assets/images/matrix-ai-mark.svg` — new (fetched)
- `backend/tests/test_page_perms_sync.py` — additional assertion (optional)
