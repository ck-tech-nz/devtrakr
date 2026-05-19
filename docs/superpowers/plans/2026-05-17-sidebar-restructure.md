# Sidebar restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the AI sidebar group to `团队效能` (admin-only), move `我的提升计划` to the header dropdown, add a `我的待办` sidebar panel, and reflow the sidebar chrome to a Manus-style layout (top-bar auto-collapse, compact bottom service-status + MATRIX AI brand).

**Architecture:** Backend `PAGE_PERMS.SEED_ROUTES` edits drive the route table (synced via `sync_page_perms`); frontend reads it through `/api/page-perms/routes/`. Admin gating uses a new `meta.adminOnly` flag enforced in `useNavigation.ts` filter and `auth.global.ts` middleware. The "我的待办" panel shares data with the existing home-page card through a new `useMyTasks()` composable using Nuxt's `useState`. Sidebar layout changes are template-only inside `AppSidebar.vue`.

**Tech Stack:** Django 5.x + django-page-perms package, Nuxt 4 SPA, Vue 3 Composition API, Nuxt UI 3 (`UTooltip`, `UDropdownMenu`), Heroicons, Tailwind CSS, pytest-django.

---

## File Structure

**Create:**
- `frontend/app/composables/useMyTasks.ts` — Shared pending-tasks fetcher / state.
- `frontend/app/components/MyTasksSidebar.vue` — Sidebar bottom panel rendering up to 5 tasks.
- `frontend/app/assets/images/matrix-ai-logo.svg` — Word-mark variant (fetched from matrixai.xin).
- `frontend/app/assets/images/matrix-ai-mark.svg` — Icon-only variant for collapsed sidebar.

**Modify:**
- `backend/config/settings.py` — `PAGE_PERMS.SEED_ROUTES` rows for `/app/ai/team-analysis`, `/app/ai/my-plan`, `/app/ai/plans`.
- `backend/tests/test_page_perms_sync.py` — Add an assertion exercising the new meta/show_in_nav shape.
- `frontend/app/composables/useNavigation.ts` — Rename group `AI 分析` → `团队效能`; add `adminOnly` filter parallel to `superuserOnly`.
- `frontend/app/middleware/auth.global.ts` — Add `meta.adminOnly` redirect check.
- `frontend/app/components/AppHeader.vue` — Insert `我的提升计划` dropdown entry.
- `frontend/app/components/MyPendingTasks.vue` — Refactor to consume `useMyTasks()`.
- `frontend/app/components/AppSidebar.vue` — Move auto-collapse to header; replace two footer blocks with a single compact footer; embed `<MyTasksSidebar />` after the nav loop.

---

## Task 1: Backend PAGE_PERMS edits + sync

**Files:**
- Modify: `backend/config/settings.py:178-180`
- Modify: `backend/tests/test_page_perms_sync.py` (append a new test method)

- [ ] **Step 1: Write the failing test**

Append this test method inside `class TestSyncPagePerms` in `backend/tests/test_page_perms_sync.py`:

```python
    def test_seed_supports_meta_and_show_in_nav_false(self, settings):
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "/app/admin-only", "label": "AdminOnly", "sort_order": 0,
                 "meta": {"adminOnly": True}},
                {"path": "/app/hidden", "label": "Hidden", "sort_order": 1,
                 "show_in_nav": False},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        admin_route = PageRoute.objects.get(path="/app/admin-only")
        assert admin_route.meta == {"adminOnly": True}
        hidden_route = PageRoute.objects.get(path="/app/hidden")
        assert hidden_route.show_in_nav is False
```

- [ ] **Step 2: Run test to verify it passes**

From `backend/`:

```bash
uv run pytest tests/test_page_perms_sync.py::TestSyncPagePerms::test_seed_supports_meta_and_show_in_nav_false -v
```

Expected: PASS. (The `sync_page_perms` command already supports `meta` and `show_in_nav` defaults — this test pins that contract before we rely on it.)

- [ ] **Step 3: Update `settings.py` SEED_ROUTES**

In `backend/config/settings.py`, replace lines 178–180:

```python
        {"path": "/app/ai/team-analysis", "label": "团队分析", "icon": "i-heroicons-cpu-chip", "permission": "ai.view_analysis", "sort_order": 4, "meta": {"serviceKey": "ai", "adminOnly": True}},
        {"path": "/app/ai/my-plan", "label": "我的提升计划", "icon": "i-heroicons-clipboard-document-check", "permission": None, "sort_order": 5, "show_in_nav": False},
        {"path": "/app/ai/plans", "label": "团队计划管理", "icon": "i-heroicons-clipboard-document-list", "permission": "kpi.change_improvementplan", "sort_order": 6, "meta": {"adminOnly": True}},
```

- [ ] **Step 4: Sync to DB**

From `backend/`:

```bash
uv run python manage.py sync_page_perms
```

Expected output includes:
```
  Updated: /app/ai/team-analysis
  Updated: /app/ai/my-plan
  Updated: /app/ai/plans
```

- [ ] **Step 5: Verify DB state**

From `backend/`:

```bash
uv run python manage.py shell -c "
from page_perms.models import PageRoute
for p in ['/app/ai/team-analysis', '/app/ai/my-plan', '/app/ai/plans']:
    r = PageRoute.objects.get(path=p)
    print(f'{p}: meta={r.meta} show_in_nav={r.show_in_nav}')
"
```

Expected:
```
/app/ai/team-analysis: meta={'serviceKey': 'ai', 'adminOnly': True} show_in_nav=True
/app/ai/my-plan: meta={} show_in_nav=False
/app/ai/plans: meta={'adminOnly': True} show_in_nav=True
```

- [ ] **Step 6: Commit**

```bash
git add backend/config/settings.py backend/tests/test_page_perms_sync.py
git commit -m "feat(perms): mark 团队效能 routes adminOnly, hide my-plan from nav"
```

---

## Task 2: Frontend nav group rename + `adminOnly` filter

**Files:**
- Modify: `frontend/app/composables/useNavigation.ts:25` (group rename)
- Modify: `frontend/app/composables/useNavigation.ts:49-57` (filter)

- [ ] **Step 1: Rename the GROUP_DEFS entry**

In `frontend/app/composables/useNavigation.ts`, replace line 25:

```ts
  { label: '团队效能', icon: 'i-heroicons-chart-bar', paths: ['/app/ai/team-analysis', '/app/ai/plans'] },
```

(Group icon changes from `cpu-chip` to `chart-bar`; the `团队分析` child keeps its own `cpu-chip` icon from the route seed.)

- [ ] **Step 2: Add `hasGroup` to the destructure and add `isAdmin`**

Replace line 31:

```ts
  const { can, hasGroup, user } = useAuth()
```

After line 32 (`const { routes, loaded } = usePagePerms()`), add:

```ts
  const isAdmin = computed(() => user.value?.is_superuser || hasGroup('管理员'))
```

- [ ] **Step 3: Add `adminOnly` to the filter**

In `filteredNavItems` (lines 49–57), insert one line so the block reads:

```ts
  const filteredNavItems = computed(() => {
    if (!user.value) return []
    const items = navItems.value.filter(item => {
      if (item.meta?.superuserOnly && !user.value?.is_superuser) return false
      if (item.meta?.adminOnly && !isAdmin.value) return false
      if (item.permission && !can(item.permission)) return false
      return true
    })
    return [homeItem, ...items]
  })
```

- [ ] **Step 4: Manual smoke test**

Restart the dev server from `frontend/`:

```bash
npm run dev
```

Log in as a 管理员 user. In the sidebar, verify:
- Group label reads `团队效能` (not `AI 分析`).
- Group contains exactly `团队分析` and `团队计划管理`.
- `我的提升计划` is NOT in the sidebar.

Log in as a non-admin (e.g. 开发者). Verify:
- `团队效能` group is NOT rendered at all.
- `我的提升计划` is NOT in the sidebar (header dropdown comes in Task 4).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/composables/useNavigation.ts
git commit -m "feat(nav): rename AI 分析 to 团队效能, gate via meta.adminOnly"
```

---

## Task 3: Route middleware `adminOnly` guard

**Files:**
- Modify: `frontend/app/middleware/auth.global.ts`

- [ ] **Step 1: Add the adminOnly check**

Replace the contents of `frontend/app/middleware/auth.global.ts` with:

```ts
export default defineNuxtRouteMiddleware(async (to) => {
  if (to.path === '/' || to.path === '/login' || to.path === '/register') return
  if (to.path === '/app/forbidden') return

  const { getToken } = useApi()
  if (!getToken()) {
    return navigateTo('/login')
  }

  const { user, fetchMe, can } = useAuth()
  const { loaded, fetchRoutes, routePermissions, routes, error } = usePagePerms()

  if (!user.value) {
    await fetchMe()
  }

  if (!user.value) {
    return navigateTo('/login')
  }

  if (!loaded.value) {
    await fetchRoutes()
  }

  if (error.value && to.path.startsWith('/app/')) {
    return navigateTo('/app/forbidden')
  }

  // Permission code check (existing)
  const perms = routePermissions.value
  for (const [prefix, perm] of Object.entries(perms)) {
    if (to.path === prefix || to.path.startsWith(prefix + '/')) {
      if (!can(perm)) {
        return navigateTo('/app/forbidden')
      }
      break
    }
  }

  // meta.adminOnly check
  const isAdmin = user.value.is_superuser || user.value.groups.includes('管理员')
  for (const route of routes.value) {
    if (to.path === route.path || to.path.startsWith(route.path + '/')) {
      if (route.meta?.adminOnly && !isAdmin) {
        return navigateTo('/app/forbidden')
      }
      break
    }
  }
})
```

- [ ] **Step 2: Manual smoke test**

With dev server running, log in as a non-admin (e.g. 开发者 — they hold `ai.view_analysis` but not 管理员 group). In the browser address bar, type `/app/ai/team-analysis` and hit Enter.

Expected: redirected to `/app/forbidden`.

Type `/app/ai/plans`. Expected: redirected to `/app/forbidden`.

Log in as 管理员. Type `/app/ai/team-analysis`. Expected: page loads normally.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/middleware/auth.global.ts
git commit -m "feat(middleware): block adminOnly routes for non-admins"
```

---

## Task 4: Header dropdown entry for `我的提升计划`

**Files:**
- Modify: `frontend/app/components/AppHeader.vue:71-92`

- [ ] **Step 1: Insert the dropdown item**

In `frontend/app/components/AppHeader.vue`, replace the `userMenuItems` block (lines 71–92) with:

```ts
const userMenuItems = computed(() => {
  const items: any[][] = [
    [
      {
        label: '个人资料',
        icon: 'i-heroicons-user-circle',
        onSelect: () => navigateTo('/app/profile'),
      },
      {
        label: '我的提升计划',
        icon: 'i-heroicons-clipboard-document-check',
        onSelect: () => navigateTo('/app/ai/my-plan'),
      },
    ],
  ]
  if (user.value?.is_superuser) {
    items.push([{
      label: '系统管理',
      icon: 'i-heroicons-cog-6-tooth',
      onSelect: () => openAdmin(),
    }])
  }
  items.push([{
    label: '退出登录',
    icon: 'i-heroicons-arrow-right-on-rectangle',
    onSelect: () => logout(),
  }])
  return items
})
```

- [ ] **Step 2: Manual smoke test**

Log in (any role). Click the avatar in the top-right corner.

Expected dropdown contents (top to bottom):
- 个人资料
- 我的提升计划
- (only if superuser) 系统管理
- 退出登录

Click `我的提升计划`. Expected: navigates to `/app/ai/my-plan` and the page renders.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/AppHeader.vue
git commit -m "feat(header): add 我的提升计划 to user dropdown"
```

---

## Task 5: `useMyTasks()` composable + refactor `MyPendingTasks`

**Files:**
- Create: `frontend/app/composables/useMyTasks.ts`
- Modify: `frontend/app/components/MyPendingTasks.vue:67-133`

- [ ] **Step 1: Create the composable**

Create `frontend/app/composables/useMyTasks.ts` with:

```ts
interface MyTask {
  id: number
  title: string
  status: string
  priority?: number
  project_name?: string
}

export function useMyTasks() {
  const { api } = useApi()
  const { user, hasGroup } = useAuth()

  const tasks = useState<MyTask[]>('my-tasks', () => [])
  const totalCount = useState<number>('my-tasks-count', () => 0)
  const loading = useState<boolean>('my-tasks-loading', () => false)

  const isTester = computed(() => hasGroup('测试'))

  async function load() {
    if (!user.value) return
    loading.value = true
    try {
      const uid = user.value.id
      const fetches: Promise<any>[] = [
        api<any>(`/api/issues/?assignee=${uid}&status=待处理&page_size=8`),
        api<any>(`/api/issues/?assignee=${uid}&status=进行中&page_size=8`),
        api<any>(`/api/issues/?helpers=${uid}&status=待处理&page_size=8`),
        api<any>(`/api/issues/?helpers=${uid}&status=进行中&page_size=8`),
      ]
      if (isTester.value) {
        fetches.push(api<any>(`/api/issues/?status=已发布&page_size=8`))
      }
      const results = await Promise.all(fetches)
      const seen = new Set<number>()
      const merged: MyTask[] = []
      let total = 0
      for (const res of results) {
        const items = res.results || res || []
        const prevSize = seen.size
        for (const item of items) {
          if (!seen.has(item.id)) { seen.add(item.id); merged.push(item) }
        }
        const batchNew = seen.size - prevSize
        const batchDup = items.length - batchNew
        total += (res.count ?? items.length) - batchDup
      }
      totalCount.value = total
      tasks.value = merged.slice(0, 8)
    } catch (e) {
      console.error('Failed to load my tasks:', e)
    } finally {
      loading.value = false
    }
  }

  async function closeIssue(task: MyTask) {
    await api(`/api/issues/${task.id}/close-with-github/`, { method: 'POST' })
    await load()
  }

  return { tasks, totalCount, loading, isTester, load, closeIssue }
}
```

- [ ] **Step 2: Refactor `MyPendingTasks.vue` to use the composable**

In `frontend/app/components/MyPendingTasks.vue`, replace lines 67–133 (the entire `<script setup>` block) with:

```ts
<script setup lang="ts">
const { tasks, totalCount, load, closeIssue, isTester } = useMyTasks()
const collapsed = ref(false)
const closingId = ref<number | null>(null)

function statusColor(status: string) {
  if (status === '待处理') return 'warning'
  if (status === '进行中') return 'info'
  if (status === '已解决') return 'success'
  if (status === '已发布') return 'success'
  return 'neutral'
}

async function onClose(task: any) {
  closingId.value = task.id
  try {
    await closeIssue(task)
  } catch (e) {
    console.error('Failed to close issue:', e)
  } finally {
    closingId.value = null
  }
}

onMounted(() => { load() })
</script>
```

Then update the `closeIssue` reference in the template. In the template section, find the line containing `@click.stop.prevent="closeIssue(task)"` (around line 54) and change it to:

```html
                @click.stop.prevent="onClose(task)"
```

(`priorityColor` and `priorityLabel` are top-level exports from `frontend/app/composables/usePriority.ts`, not properties of a `usePriority()` hook. Nuxt auto-imports them by name from the `composables/` directory, so the template references will keep working without any new import line.)

- [ ] **Step 3: Verify the auto-imports still resolve**

```bash
grep -n "priorityColor\|priorityLabel" frontend/app/composables/usePriority.ts
```

Expected: two `export function` lines (one per name). If both exist, no further action.

- [ ] **Step 4: Manual smoke test**

Reload the home page. Expected:
- `MyPendingTasks` card renders identically to before (same count, same tasks, same colors).
- Clicking "关闭" (as tester) still closes an issue and refreshes the list.
- Toggling collapsed state still works.

- [ ] **Step 5: Typecheck**

From `frontend/`:

```bash
npx nuxi typecheck
```

Expected: no new type errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/composables/useMyTasks.ts frontend/app/components/MyPendingTasks.vue
git commit -m "refactor(tasks): extract useMyTasks composable, share state via useState"
```

---

## Task 6: Fetch MATRIX AI brand assets

**Files:**
- Create: `frontend/app/assets/images/matrix-ai-logo.svg`
- Create: `frontend/app/assets/images/matrix-ai-mark.svg`

- [ ] **Step 1: Inspect matrixai.xin for brand assets**

Use WebFetch on `https://matrixai.xin/` with the prompt:

> List every image asset visible on the homepage — particularly any logo, brand-mark, or icon files. For each, give the absolute URL, the file extension, and whether it's a word-mark (text + icon) or icon-only.

- [ ] **Step 2: Download the chosen assets**

Based on the WebFetch result, pick:
- One word-mark variant (text + mark) → save to `frontend/app/assets/images/matrix-ai-logo.svg`
- One icon-only mark → save to `frontend/app/assets/images/matrix-ai-mark.svg`

If both variants are SVG, fetch via:

```bash
curl -L --fail -o frontend/app/assets/images/matrix-ai-logo.svg "<word-mark-url>"
curl -L --fail -o frontend/app/assets/images/matrix-ai-mark.svg "<icon-only-url>"
```

If the site only ships PNG, change the extensions to `.png` accordingly (and update the `<img src>` references in Task 9). If only one variant exists, save it to both filenames (the mark file will be used for the collapsed sidebar).

- [ ] **Step 3: Verify the files**

```bash
ls -lh frontend/app/assets/images/matrix-ai-*.*
file frontend/app/assets/images/matrix-ai-*.*
```

Expected: both files exist, both are valid SVG or PNG.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/assets/images/matrix-ai-logo.svg frontend/app/assets/images/matrix-ai-mark.svg
git commit -m "chore(assets): add MATRIX AI brand mark assets"
```

---

## Task 7: `MyTasksSidebar` component

**Files:**
- Create: `frontend/app/components/MyTasksSidebar.vue`

- [ ] **Step 1: Create the component**

Create `frontend/app/components/MyTasksSidebar.vue` with:

```vue
<template>
  <div v-if="visible" class="pt-2">
    <button
      class="relative flex items-center w-full h-10 px-2 rounded-lg transition-colors"
      :class="open
        ? 'text-crystal-600 dark:text-crystal-400'
        : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'"
      @click="toggle"
    >
      <UIcon name="i-heroicons-inbox-stack" class="w-5 h-5 flex-shrink-0" />
      <transition name="fade">
        <span v-if="expanded" class="ml-3 text-sm font-medium whitespace-nowrap flex-1 text-left flex items-center gap-2">
          我的待办
          <span
            v-if="totalCount > 0"
            class="text-[10px] bg-crystal-50 dark:bg-crystal-950 text-crystal-600 dark:text-crystal-400 px-1.5 py-0.5 rounded-full"
          >{{ totalCount }}</span>
        </span>
      </transition>
      <transition name="fade">
        <UIcon
          v-if="expanded"
          :name="open ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
          class="w-3.5 h-3.5 flex-shrink-0 opacity-50"
        />
      </transition>
      <span
        v-if="!expanded && totalCount > 0"
        class="absolute right-2 top-2 text-[10px] bg-crystal-500 text-white rounded-full px-1.5 leading-tight"
      >{{ totalCount }}</span>
    </button>

    <template v-if="expanded && open">
      <NuxtLink
        v-for="task in displayTasks"
        :key="task.id"
        :to="`/app/issues/${task.id}`"
        class="flex items-center h-9 pl-9 pr-2 rounded-lg transition-colors text-xs text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200"
      >
        <span class="font-mono text-gray-400 dark:text-gray-600 mr-2">#{{ task.id }}</span>
        <span class="truncate flex-1">{{ task.title }}</span>
        <span class="w-1.5 h-1.5 rounded-full ml-2 flex-shrink-0" :class="dotColor(task.status)" />
      </NuxtLink>

      <div v-if="displayTasks.length === 0" class="pl-9 pr-2 py-1.5 text-xs text-gray-400 dark:text-gray-600">
        暂无待办
      </div>

      <NuxtLink
        v-if="totalCount > 0"
        :to="`/app/issues?assignee=${userId}`"
        class="flex items-center h-8 pl-9 pr-2 rounded-lg text-xs text-crystal-600 dark:text-crystal-400 hover:bg-crystal-50 dark:hover:bg-crystal-950"
      >
        查看全部 →
      </NuxtLink>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{ expanded: boolean }>()

const { user, can } = useAuth()
const { tasks, totalCount, load } = useMyTasks()

const visible = computed(() => !!user.value && can('issues.view_issue'))
const userId = computed(() => user.value?.id)
const open = ref(false)

const displayTasks = computed(() => tasks.value.slice(0, 5))

function toggle() {
  open.value = !open.value
  if (open.value && tasks.value.length === 0) load()
}

function dotColor(status: string) {
  if (status === '待处理') return 'bg-amber-400'
  if (status === '进行中') return 'bg-blue-400'
  if (status === '已发布') return 'bg-emerald-400'
  return 'bg-gray-300'
}

onMounted(() => { if (visible.value) load() })
</script>

<style scoped>
.fade-enter-active { transition: opacity 0.2s ease 0.1s; }
.fade-leave-active { transition: opacity 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
```

- [ ] **Step 2: Embed the component in `AppSidebar.vue`**

In `frontend/app/components/AppSidebar.vue`, find the closing `</template>` of the nav loop (currently around line 75). Replace lines 15–75 so the `<nav>` block ends with the new component:

```html
    <nav class="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
      <template v-for="entry in groupedNavItems" :key="isNavGroup(entry) ? entry.label : entry.to">
        <!-- Group header -->
        <template v-if="isNavGroup(entry)">
          <button
            class="flex items-center w-full h-10 px-2 rounded-lg transition-colors"
            :class="isGroupActive(entry)
              ? 'text-crystal-600 dark:text-crystal-400'
              : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'"
            @click="toggleGroup(entry.label)"
          >
            <UIcon :name="entry.icon" class="w-5 h-5 flex-shrink-0" />
            <transition name="fade">
              <span v-if="expanded" class="ml-3 text-sm font-medium whitespace-nowrap flex-1 text-left">{{ entry.label }}</span>
            </transition>
            <transition name="fade">
              <UIcon
                v-if="expanded"
                :name="openGroups.has(entry.label) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                class="w-3.5 h-3.5 flex-shrink-0 opacity-50"
              />
            </transition>
          </button>
          <template v-if="expanded && openGroups.has(entry.label)">
            <NuxtLink
              v-for="child in entry.children"
              :key="child.to"
              :to="child.to!"
              class="flex items-center h-9 pl-9 pr-2 rounded-lg transition-colors text-sm"
              :class="isChildActive(child)
                ? 'bg-crystal-50 dark:bg-crystal-950 text-crystal-600 dark:text-crystal-400'
                : 'text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200'"
            >
              {{ child.label }}
            </NuxtLink>
          </template>
        </template>

        <NuxtLink
          v-else
          :to="entry.to!"
          class="flex items-center h-10 px-2 rounded-lg transition-colors group"
          :class="isChildActive(entry)
            ? 'bg-crystal-50 dark:bg-crystal-950 text-crystal-600 dark:text-crystal-400'
            : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'"
        >
          <UIcon :name="entry.icon" class="w-5 h-5 flex-shrink-0" />
          <transition name="fade">
            <span v-if="expanded" class="ml-3 text-sm font-medium whitespace-nowrap flex items-center gap-2">
              {{ entry.label }}
              <ServiceStatusDot
                v-if="entry.meta?.serviceKey"
                :online="isOnline(entry.meta.serviceKey)"
              />
            </span>
          </transition>
        </NuxtLink>
      </template>

      <MyTasksSidebar :expanded="expanded" />
    </nav>
```

- [ ] **Step 3: Manual smoke test**

Reload the app. With assigned issues:
- Scroll to the bottom of the sidebar nav. Verify `我的待办` appears as the last entry with the count badge.
- Click to expand. Verify up to 5 rows render with `#ID` + title + status dot.
- Click a row. Verify it navigates to `/app/issues/<id>`.
- Click `查看全部 →`. Verify it navigates to `/app/issues?assignee=<my-id>`.
- Without assigned issues: badge is hidden, expanding shows `暂无待办`.
- Collapsed sidebar mode (auto-collapse on, mouse not over): only the icon + count badge are visible.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/MyTasksSidebar.vue frontend/app/components/AppSidebar.vue
git commit -m "feat(sidebar): add 我的待办 panel sharing state with home card"
```

---

## Task 8: Sidebar header reflow — auto-collapse to top

**Files:**
- Modify: `frontend/app/components/AppSidebar.vue` (top header `<div>`, lines 8–13)
- Modify: `frontend/app/components/AppSidebar.vue` (remove the old footer auto-collapse block, lines 90–104)

- [ ] **Step 1: Replace the header row**

In `frontend/app/components/AppSidebar.vue`, replace the header `<div>` (lines 8–13) with:

```html
    <div class="h-16 flex items-center px-4 border-b border-gray-50 dark:border-gray-800 gap-2">
      <img src="~/assets/images/logo-icon.svg" alt="DevTrakr" class="w-8 h-8 flex-shrink-0" />
      <transition name="fade">
        <span v-if="expanded" class="font-semibold text-gray-900 dark:text-gray-100 whitespace-nowrap">DevTrakr</span>
      </transition>
      <div class="flex-1" />
      <button
        class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 flex-shrink-0 p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
        :title="autoCollapse ? '取消自动收起' : '启用自动收起'"
        @click.stop="autoCollapse = !autoCollapse"
      >
        <UIcon
          :name="autoCollapse ? 'i-heroicons-chevron-double-left' : 'i-heroicons-chevron-double-right'"
          class="w-4 h-4"
        />
      </button>
    </div>
```

- [ ] **Step 2: Remove the old auto-collapse footer block**

In the same file, delete the entire `<div>` block currently at lines 90–104 (the `<div class="border-t ..."><button @click="autoCollapse = ...">`).

After this step the bottom of `<aside>` should end with only the service-status block (which we'll restructure in Task 9).

- [ ] **Step 3: Manual smoke test**

Reload the app. Verify:
- The auto-collapse `«` / `»` chevron is in the top-right of the sidebar header.
- Clicking it toggles auto-collapse persistence (settings save).
- The old footer auto-collapse button is gone.
- Sidebar still hover-expands when auto-collapse is on.
- Collapsed state (w-16): the header shows the logo icon centered-ish and the chevron button next to it; clicking still works.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/AppSidebar.vue
git commit -m "feat(sidebar): move auto-collapse toggle to header top-right"
```

---

## Task 9: Sidebar footer reflow — compact service status + MATRIX AI brand

**Files:**
- Modify: `frontend/app/components/AppSidebar.vue` (old service-status `<div>`, lines 77–88 of the original file — now the only remaining footer block after Task 8)

- [ ] **Step 1: Replace the footer block**

In `frontend/app/components/AppSidebar.vue`, locate the remaining footer `<div v-if="expanded" class="border-t ...">` block (the service-status block) and replace it with a single new footer that always renders, branching layout on `expanded`:

```html
    <div class="border-t border-gray-50 dark:border-gray-800 py-3 px-3" :class="expanded ? 'flex items-center justify-between gap-2' : 'flex flex-col items-center gap-2'">
      <div :class="expanded ? 'flex items-center gap-2' : 'flex flex-col items-center gap-2'">
        <UTooltip
          v-for="key in ['github', 'ai']"
          :key="key"
          :text="getLabel(key) + (isOnline(key) ? ' · 在线' : ' · 离线')"
        >
          <button class="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800" @click="toggle(key)">
            <ServiceStatusDot :online="isOnline(key)" />
          </button>
        </UTooltip>
      </div>
      <a
        href="https://matrixai.xin/"
        target="_blank"
        rel="noopener"
        class="flex items-center hover:opacity-80 transition-opacity"
        title="MATRIX AI"
      >
        <img
          v-if="expanded"
          src="~/assets/images/matrix-ai-logo.svg"
          alt="MATRIX AI"
          class="h-5 w-auto"
        />
        <img
          v-else
          src="~/assets/images/matrix-ai-mark.svg"
          alt="MATRIX AI"
          class="h-5 w-auto"
        />
      </a>
    </div>
```

(If the brand assets you fetched in Task 6 are PNG instead of SVG, change both `src` extensions to `.png`.)

- [ ] **Step 2: Manual smoke test**

Reload the app. Verify (sidebar expanded):
- Bottom row shows two `ServiceStatusDot`s on the left and the MATRIX AI word-mark on the right.
- Hovering each dot shows a tooltip with the label (`GitHub · 在线`, `AI 服务 · 在线`).
- Clicking a dot toggles its online state (demo behaviour preserved).
- Clicking the MATRIX AI mark opens `https://matrixai.xin/` in a new tab.

Verify (sidebar collapsed via auto-collapse, mouse not over):
- The two dots stack vertically.
- The MATRIX AI brand collapses to the icon-only `matrix-ai-mark.svg` underneath.

- [ ] **Step 3: Typecheck**

From `frontend/`:

```bash
npx nuxi typecheck
```

Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/AppSidebar.vue
git commit -m "feat(sidebar): compact service-status dots + MATRIX AI brand footer"
```

---

## Task 10: End-to-end smoke test

**Files:** none modified.

- [ ] **Step 1: Run full backend test suite**

From `backend/`:

```bash
uv run pytest
```

Expected: all green. If any test broke, investigate before proceeding.

- [ ] **Step 2: Run frontend typecheck**

From `frontend/`:

```bash
npx nuxi typecheck
```

Expected: no errors.

- [ ] **Step 3: Manual end-to-end checklist**

With dev servers running:

**As 管理员:**
- [ ] Sidebar shows `团队效能` group containing `团队分析` and `团队计划管理`.
- [ ] Sidebar does NOT show `我的提升计划` anywhere.
- [ ] Header dropdown shows `我的提升计划` between `个人资料` and `退出登录`.
- [ ] Clicking the dropdown item navigates to `/app/ai/my-plan` and the page renders.
- [ ] Sidebar shows `我的待办` panel at the bottom with the right count.
- [ ] Top-right of sidebar has the auto-collapse chevron.
- [ ] Bottom of sidebar has two service dots + MATRIX AI brand mark.
- [ ] Auto-collapse on → mouse off sidebar → sidebar collapses; dots stack vertically; brand mark becomes icon-only.

**As 开发者 (or any non-admin):**
- [ ] `团队效能` group is NOT visible in the sidebar.
- [ ] Manually navigating to `/app/ai/team-analysis` redirects to `/app/forbidden`.
- [ ] Manually navigating to `/app/ai/plans` redirects to `/app/forbidden`.
- [ ] `我的提升计划` is reachable from the header dropdown and loads.
- [ ] `我的待办` panel is visible and functional.

**Issue close flow propagation (as 测试):**
- [ ] On `/app/home`, the `MyPendingTasks` card lists at least one `已发布` issue.
- [ ] Click "关闭" on one item; it disappears from the card.
- [ ] Without reloading, scroll to the `我的待办` sidebar panel and verify the same item is gone (shared state).

- [ ] **Step 4: Final commit (if any cleanup)**

If the manual checklist surfaced anything, commit fixes. Otherwise no commit needed.

```bash
git status
```

Expected: clean working tree.

---

## Self-Review Notes

- Spec coverage: every section maps to a task — backend perms (1), nav rename + filter (2), middleware (3), header dropdown (4), composable + home refactor (5), brand assets (6), sidebar panel (7), header reflow (8), footer reflow (9), end-to-end (10).
- No placeholders, no "TBD". Asset filename extensions branch on what `matrixai.xin` actually serves — Task 6 handles that explicitly and Task 9 references both paths.
- Type / name consistency: `useMyTasks` returns `{ tasks, totalCount, loading, isTester, load, closeIssue }`; `MyPendingTasks` consumes `{ tasks, totalCount, load, closeIssue, isTester }`; `MyTasksSidebar` consumes `{ tasks, totalCount, load }`. All consistent.
- Edge case: `usePriority` import in `MyPendingTasks.vue` is handled in Task 5 Step 3.
- Task 9 deliberately removes the `v-if="expanded"` from the old service-status block — the new footer always renders so the brand mark and dots survive in collapsed mode.
