# 工作台个性化 + 服务器资源卡片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让工作台首页(`/app/home`)的区块可由用户显隐/上下排序(持久化到用户 settings),并新增一张通过 iframe 嵌入的「服务器资源」基础设施监控卡片。

**Architecture:** 把 `home.vue` 从 600+ 行全能页面瘦身为编排者:取数后按用户布局有序渲染一组小型展示型区块组件,每个区块由 `DashboardBlock` 包装提供「编辑布局」模式下的上移/下移/显隐控件。布局状态(顺序 + 可见性)存于 `settings.dashboard_layout`(已有的 `useUserSettings` 自动 PATCH 持久化,**无后端改动**)。排序/合并纯逻辑抽到 `utils/dashboardLayout.ts` 并用 Vitest 单测。嵌入地址来自运行时环境变量 `NUXT_PUBLIC_SERVER_MONITOR_URL`。

**Tech Stack:** Nuxt 4 (SPA, `ssr:false`, Nitro node server)、Vue 3 `<script setup>`、`@nuxt/ui`、Vitest(本计划新引入,仅测纯逻辑)。

**设计依据:** `docs/superpowers/specs/2026-06-04-dashboard-customization-design.md`

---

## File Structure

**新增**

| 文件 | 职责 |
|---|---|
| `frontend/vitest.config.ts` | 最小 Vitest 配置(node 环境,测纯 TS) |
| `frontend/tests/dashboardLayout.test.ts` | 纯逻辑单测 |
| `frontend/app/utils/dashboardLayout.ts` | 区块注册表 + 合并/移位/显隐纯函数(无 Nuxt 依赖) |
| `frontend/app/utils/timeAgo.ts` | `timeAgo()` 时间格式化(Mentions/Activity 共用) |
| `frontend/app/composables/useDashboardLayout.ts` | 把纯逻辑接到响应式 state + 持久化 + 编辑开关 |
| `frontend/app/components/dashboard/Block.vue` | `DashboardBlock` 包装:渲染门控 + 编辑控件条 |
| `frontend/app/components/dashboard/ServerResource.vue` | `DashboardServerResource` 新卡片(iframe) |
| `frontend/app/components/dashboard/StatsRow.vue` | `DashboardStatsRow` 四个统计卡一组 |
| `frontend/app/components/dashboard/Todos.vue` | `DashboardTodos` 我的待办 |
| `frontend/app/components/dashboard/Mentions.vue` | `DashboardMentions` 提及我的 |
| `frontend/app/components/dashboard/Tasks.vue` | `DashboardTasks` 我的任务 |
| `frontend/app/components/dashboard/Activity.vue` | `DashboardActivity` 最近动态 |

**修改**

| 文件 | 改动 |
|---|---|
| `frontend/package.json` | 加 `vitest` devDep + `"test"` 脚本 |
| `frontend/app/composables/useUserSettings.ts` | `UserSettings` 增加 `dashboard_layout` 字段 + 默认值 |
| `frontend/nuxt.config.ts` | `runtimeConfig.public.serverMonitorUrl: ''` |
| `frontend/.env` | 追加 `NUXT_PUBLIC_SERVER_MONITOR_URL`(本地) |
| `docker-compose.yml` | `frontend` 服务新增 `environment:` 段 |
| `frontend/app/pages/app/home.vue` | 瘦身为编排者 |

**无后端改动、无数据库迁移。**

## 测试策略说明

前端**当前无任何测试设施**。本计划只为**纯逻辑**(`utils/dashboardLayout.ts`)引入最小 Vitest(node 环境,不引入 `@nuxt/test-utils`/DOM)。Vue 组件正确性通过 `npx nuxi typecheck` + 手动 QA(`/browse`)验证 —— 这与 spec 的「单测仅覆盖纯逻辑」一致,避免为展示型组件搭建重量级组件测试栈。

---

## Task 1: 引入最小 Vitest 设施

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/tests/smoke.test.ts`(临时冒烟测试,Task 2 末尾删除)

- [ ] **Step 1: 安装 vitest(devDependency)**

Run(在 `frontend/` 下):
```bash
npm install -D vitest
```
Expected: `package.json` 出现 `"devDependencies": { "vitest": "^x" }`,无报错。

- [ ] **Step 2: 增加 test 脚本**

修改 `frontend/package.json` 的 `scripts`,在 `"postinstall"` 行后加入 `"test"`:
```jsonc
  "scripts": {
    "build": "nuxt build",
    "dev": "nuxt dev",
    "generate": "nuxt generate",
    "preview": "nuxt preview",
    "postinstall": "nuxt prepare",
    "test": "vitest run"
  },
```

- [ ] **Step 3: 写最小 vitest 配置**

Create `frontend/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config'

// 仅用于测试纯 TS 逻辑(utils),不加载 Nuxt 运行时
export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
  },
})
```

- [ ] **Step 4: 写冒烟测试验证设施可用**

Create `frontend/tests/smoke.test.ts`:
```ts
import { describe, it, expect } from 'vitest'

describe('vitest setup', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 5: 运行测试验证通过**

Run(在 `frontend/` 下):
```bash
npm test
```
Expected: PASS,1 个测试通过(`tests/smoke.test.ts`)。

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/tests/smoke.test.ts
git commit -m "test(frontend): add minimal vitest setup for pure-logic unit tests"
```

---

## Task 2: 区块布局纯逻辑 + TDD 单测

**Files:**
- Create: `frontend/app/utils/dashboardLayout.ts`
- Test: `frontend/tests/dashboardLayout.test.ts`
- Delete: `frontend/tests/smoke.test.ts`

- [ ] **Step 1: 写失败的测试**

Create `frontend/tests/dashboardLayout.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import {
  DASHBOARD_BLOCKS,
  defaultLayout,
  mergeLayout,
  moveBlock,
  toggleBlock,
} from '../app/utils/dashboardLayout'

describe('defaultLayout', () => {
  it('returns one entry per registry block in order, all visible', () => {
    const layout = defaultLayout()
    expect(layout.map(e => e.id)).toEqual(DASHBOARD_BLOCKS.map(b => b.id))
    expect(layout.every(e => e.visible)).toBe(true)
  })
  it('puts server block last (after activity)', () => {
    const ids = defaultLayout().map(e => e.id)
    expect(ids[ids.length - 1]).toBe('server')
    expect(ids.indexOf('server')).toBeGreaterThan(ids.indexOf('activity'))
  })
})

describe('mergeLayout', () => {
  it('returns default layout for null/undefined', () => {
    expect(mergeLayout(null)).toEqual(defaultLayout())
    expect(mergeLayout(undefined)).toEqual(defaultLayout())
  })
  it('returns default layout for empty array', () => {
    expect(mergeLayout([])).toEqual(defaultLayout())
  })
  it('appends registry blocks missing from saved layout, in registry order, at the end', () => {
    const saved = [
      { id: 'activity', visible: true },
      { id: 'stats', visible: false },
    ]
    const merged = mergeLayout(saved)
    // 已存的保序在前
    expect(merged[0]).toEqual({ id: 'activity', visible: true })
    expect(merged[1]).toEqual({ id: 'stats', visible: false })
    // 其余按注册表顺序补到末尾
    const rest = merged.slice(2).map(e => e.id)
    expect(rest).toEqual(['uptime', 'todos', 'mentions', 'tasks', 'server'])
    expect(merged).toHaveLength(DASHBOARD_BLOCKS.length)
  })
  it('drops unknown ids', () => {
    const merged = mergeLayout([{ id: 'ghost', visible: true }, { id: 'stats', visible: true }])
    expect(merged.find(e => e.id === 'ghost')).toBeUndefined()
    expect(merged.map(e => e.id)).toContain('stats')
    expect(merged).toHaveLength(DASHBOARD_BLOCKS.length)
  })
  it('preserves saved order and visible:false', () => {
    const saved = DASHBOARD_BLOCKS.map(b => ({ id: b.id, visible: false })).reverse()
    const merged = mergeLayout(saved)
    expect(merged.map(e => e.id)).toEqual(DASHBOARD_BLOCKS.map(b => b.id).reverse())
    expect(merged.every(e => e.visible === false)).toBe(true)
  })
  it('dedups repeated ids, keeping first occurrence', () => {
    const merged = mergeLayout([
      { id: 'stats', visible: false },
      { id: 'stats', visible: true },
    ])
    const statsEntries = merged.filter(e => e.id === 'stats')
    expect(statsEntries).toHaveLength(1)
    expect(statsEntries[0]!.visible).toBe(false)
  })
})

describe('moveBlock', () => {
  const base = defaultLayout()
  it('moves a block up (direction -1)', () => {
    const moved = moveBlock(base, 'uptime', -1) // uptime 在 index 1 -> 0
    expect(moved.map(e => e.id).slice(0, 2)).toEqual(['uptime', 'stats'])
  })
  it('moves a block down (direction +1)', () => {
    const moved = moveBlock(base, 'stats', 1) // stats 0 -> 1
    expect(moved.map(e => e.id).slice(0, 2)).toEqual(['uptime', 'stats'])
  })
  it('returns same order when moving first block up', () => {
    expect(moveBlock(base, 'stats', -1)).toEqual(base)
  })
  it('returns same order when moving last block down', () => {
    expect(moveBlock(base, 'server', 1)).toEqual(base)
  })
  it('returns same order for unknown id', () => {
    expect(moveBlock(base, 'ghost', 1)).toEqual(base)
  })
  it('does not mutate the input array', () => {
    const copy = base.slice()
    moveBlock(base, 'stats', 1)
    expect(base).toEqual(copy)
  })
})

describe('toggleBlock', () => {
  it('flips visible for the matching id only', () => {
    const layout = defaultLayout()
    const toggled = toggleBlock(layout, 'todos')
    expect(toggled.find(e => e.id === 'todos')!.visible).toBe(false)
    expect(toggled.filter(e => e.id !== 'todos').every(e => e.visible)).toBe(true)
  })
  it('does not mutate the input array', () => {
    const layout = defaultLayout()
    const copy = layout.map(e => ({ ...e }))
    toggleBlock(layout, 'todos')
    expect(layout).toEqual(copy)
  })
})
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `npm test`
Expected: FAIL —— 无法解析 `../app/utils/dashboardLayout`(模块不存在)。

- [ ] **Step 3: 实现纯逻辑模块**

Create `frontend/app/utils/dashboardLayout.ts`:
```ts
// 工作台区块布局纯逻辑 —— 无 Nuxt 依赖,可被 Vitest 直接单测。

export interface DashboardBlockMeta {
  id: string
  title: string
  defaultVisible: boolean
}

export interface LayoutEntry {
  id: string
  visible: boolean
}

// 规范注册表 + 默认顺序(服务器资源卡落在最近动态之后)
export const DASHBOARD_BLOCKS: DashboardBlockMeta[] = [
  { id: 'stats', title: '数据概览', defaultVisible: true },
  { id: 'uptime', title: '生产环境监控', defaultVisible: true },
  { id: 'todos', title: '我的待办', defaultVisible: true },
  { id: 'mentions', title: '提及我的', defaultVisible: true },
  { id: 'tasks', title: '我的任务', defaultVisible: true },
  { id: 'activity', title: '最近动态', defaultVisible: true },
  { id: 'server', title: '服务器资源', defaultVisible: true },
]

export function defaultLayout(): LayoutEntry[] {
  return DASHBOARD_BLOCKS.map(b => ({ id: b.id, visible: b.defaultVisible }))
}

// 合并已存布局与注册表:已存且仍在注册表中的条目去重保序在前;
// 注册表里有、已存没有的,按注册表顺序补到末尾;未知 id 丢弃。
export function mergeLayout(
  saved: LayoutEntry[] | null | undefined,
  registry: DashboardBlockMeta[] = DASHBOARD_BLOCKS,
): LayoutEntry[] {
  const known = new Set(registry.map(b => b.id))
  const savedArr = Array.isArray(saved) ? saved : []
  const seen = new Set<string>()
  const result: LayoutEntry[] = []
  for (const entry of savedArr) {
    if (entry && known.has(entry.id) && !seen.has(entry.id)) {
      result.push({ id: entry.id, visible: entry.visible !== false })
      seen.add(entry.id)
    }
  }
  for (const b of registry) {
    if (!seen.has(b.id)) {
      result.push({ id: b.id, visible: b.defaultVisible })
      seen.add(b.id)
    }
  }
  return result
}

// 移动区块:direction = -1 上移 / +1 下移;越界或未知 id 返回原数组(不报错)。返回新数组,不改入参。
export function moveBlock(layout: LayoutEntry[], id: string, direction: -1 | 1): LayoutEntry[] {
  const idx = layout.findIndex(e => e.id === id)
  if (idx === -1) return layout
  const target = idx + direction
  if (target < 0 || target >= layout.length) return layout
  const next = layout.slice()
  const [item] = next.splice(idx, 1)
  next.splice(target, 0, item!)
  return next
}

// 切换某区块显隐,返回新数组,不改入参。
export function toggleBlock(layout: LayoutEntry[], id: string): LayoutEntry[] {
  return layout.map(e => (e.id === id ? { ...e, visible: !e.visible } : e))
}
```

- [ ] **Step 4: 运行测试,确认通过**

Run: `npm test`
Expected: PASS —— `dashboardLayout.test.ts` 全部通过。

- [ ] **Step 5: 删除冒烟测试**

```bash
rm frontend/tests/smoke.test.ts
```
Run: `npm test`
Expected: PASS —— 仅 `dashboardLayout.test.ts` 运行并通过。

- [ ] **Step 6: Commit**

```bash
git add frontend/app/utils/dashboardLayout.ts frontend/tests/dashboardLayout.test.ts
git rm frontend/tests/smoke.test.ts
git commit -m "feat(home): dashboard layout pure logic (registry/merge/move/toggle) + tests"
```

---

## Task 3: 扩展 useUserSettings 支持 dashboard_layout

**Files:**
- Modify: `frontend/app/composables/useUserSettings.ts`

- [ ] **Step 1: 在接口与默认值中加入 dashboard_layout**

把 `frontend/app/composables/useUserSettings.ts` 顶部的接口与 `defaults` 改为:
```ts
interface UserSettings {
  sidebar_auto_collapse: boolean
  issues_view_mode: 'kanban' | 'table'
  project_view_mode: 'kanban' | 'table'
  theme: 'light' | 'dark' | 'auto'
  // 工作台区块布局:有序的 {id, visible} 数组(空数组 = 用默认布局)
  dashboard_layout: { id: string; visible: boolean }[]
}

const defaults: UserSettings = {
  sidebar_auto_collapse: false,
  issues_view_mode: 'table',
  project_view_mode: 'kanban',
  theme: 'light',
  dashboard_layout: [],
}
```
其余(`load`/`save`/`update`)不变 —— `update('dashboard_layout', …)` 会被 `update<K extends keyof UserSettings>` 自动接受。

- [ ] **Step 2: 类型检查**

Run(在 `frontend/` 下):
```bash
npx nuxi typecheck
```
Expected: 通过(无新增错误)。

- [ ] **Step 3: Commit**

```bash
git add frontend/app/composables/useUserSettings.ts
git commit -m "feat(home): add dashboard_layout to user settings"
```

---

## Task 4: useDashboardLayout 组合式函数

**Files:**
- Create: `frontend/app/composables/useDashboardLayout.ts`

- [ ] **Step 1: 实现组合式函数**

Create `frontend/app/composables/useDashboardLayout.ts`:
```ts
import {
  DASHBOARD_BLOCKS,
  defaultLayout,
  mergeLayout,
  moveBlock,
  toggleBlock,
  type LayoutEntry,
} from '~/utils/dashboardLayout'

export function useDashboardLayout() {
  const { settings, update } = useUserSettings()
  // 编辑模式开关:仅运行时,不持久化;useState 保证 home 与各 Block 共享同一实例
  const editing = useState<boolean>('dashboard_editing', () => false)

  // 合并后的有序区块(含 title),随 settings 变化
  const orderedBlocks = computed(() =>
    mergeLayout(settings.value.dashboard_layout).map((entry) => {
      const meta = DASHBOARD_BLOCKS.find(b => b.id === entry.id)!
      return { id: entry.id, visible: entry.visible, title: meta.title }
    }),
  )

  function current(): LayoutEntry[] {
    return mergeLayout(settings.value.dashboard_layout)
  }
  function persist(next: LayoutEntry[]) {
    update('dashboard_layout', next)
  }

  function moveUp(id: string) {
    persist(moveBlock(current(), id, -1))
  }
  function moveDown(id: string) {
    persist(moveBlock(current(), id, 1))
  }
  function toggleVisible(id: string) {
    persist(toggleBlock(current(), id))
  }
  function reset() {
    persist(defaultLayout())
  }

  return { orderedBlocks, editing, moveUp, moveDown, toggleVisible, reset }
}
```

- [ ] **Step 2: 类型检查**

Run: `npx nuxi typecheck`
Expected: 通过。

- [ ] **Step 3: Commit**

```bash
git add frontend/app/composables/useDashboardLayout.ts
git commit -m "feat(home): useDashboardLayout composable (order/visibility/edit + persistence)"
```

---

## Task 5: 接线运行时环境变量(嵌入地址)

**Files:**
- Modify: `frontend/nuxt.config.ts`
- Modify: `frontend/.env`
- Modify: `docker-compose.yml`

- [ ] **Step 1: 在 runtimeConfig.public 增加 serverMonitorUrl**

修改 `frontend/nuxt.config.ts` 的 `runtimeConfig.public`,在末尾加一行(空串 → 运行时由 `NUXT_PUBLIC_SERVER_MONITOR_URL` 覆盖):
```ts
  runtimeConfig: {
    public: {
      version: buildInfo.version,
      gitHash: buildInfo.gitHash || '',
      buildDate: buildInfo.buildDate || '',
      nuxtVersion,
      vueVersion,
      serverMonitorUrl: '',
    },
  },
```

- [ ] **Step 2: 本地 .env 追加变量**

修改 `frontend/.env`,追加一行(保留已有的 `NUXT_API_BASE`):
```bash
NUXT_API_BASE=http://localhost:8100
NUXT_PUBLIC_SERVER_MONITOR_URL=http://localhost:9300/embed?key=smk_-jNiwEc4r9Im9IfsA9uEaxp0GqxqUxYW
```

- [ ] **Step 3: docker-compose frontend 服务增加运行时 env**

修改 `docker-compose.yml` 的 `frontend` 服务,新增 `environment:` 段(注意是运行时 env,不是 `build.args`):
```yaml
  frontend:
    build:
      context: ./frontend
      args:
        NUXT_API_BASE: http://backend:8000
    environment:
      - NUXT_PUBLIC_SERVER_MONITOR_URL=${NUXT_PUBLIC_SERVER_MONITOR_URL:-}
    ports:
      - "3000:3000"
    depends_on:
      - backend
```
(各环境服务器在 compose 读取的 `.env` 中给出实际 `NUXT_PUBLIC_SERVER_MONITOR_URL`;未设置时默认为空串 → 卡片隐藏。)

- [ ] **Step 4: 类型检查**

Run: `npx nuxi typecheck`
Expected: 通过。

- [ ] **Step 5: Commit**

```bash
git add frontend/nuxt.config.ts frontend/.env docker-compose.yml
git commit -m "feat(home): wire NUXT_PUBLIC_SERVER_MONITOR_URL runtime config"
```

---

## Task 6: DashboardServerResource 卡片

**Files:**
- Create: `frontend/app/components/dashboard/ServerResource.vue`

- [ ] **Step 1: 实现组件**

Create `frontend/app/components/dashboard/ServerResource.vue`:
```vue
<template>
  <div v-if="url" class="section-card">
    <button
      class="section-header section-toggle"
      :class="{ 'section-toggle--collapsed': !expanded }"
      type="button"
      @click="expanded = !expanded"
    >
      <h3 class="section-title">服务器资源</h3>
      <UIcon :name="expanded ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
    </button>
    <iframe
      v-if="expanded"
      :src="url"
      loading="lazy"
      class="server-frame"
    />
  </div>
</template>

<script setup lang="ts">
// 基础设施资源监控:嵌入地址来自运行时环境变量,留空则整卡不渲染。
const url = computed(() => useRuntimeConfig().public.serverMonitorUrl as string)
const expanded = ref(true)
</script>

<style scoped>
.section-card {
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 1.25rem;
}
:root.dark .section-card {
  background-color: #1f2937;
  border-color: #374151;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.section-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
:root.dark .section-title { color: #f3f4f6; }
.section-toggle {
  width: 100%;
  background: transparent;
  border: 0;
  cursor: pointer;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: left;
}
.section-toggle--collapsed { margin-bottom: 0; }
.section-toggle:hover .section-title { color: #7c3aed; }
:root.dark .section-toggle:hover .section-title { color: #c4b5fd; }
.server-frame {
  width: 100%;
  height: 640px;
  border: 0;
  border-radius: 0.5rem;
}
</style>
```

- [ ] **Step 2: 类型检查**

Run: `npx nuxi typecheck`
Expected: 通过。

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/dashboard/ServerResource.vue
git commit -m "feat(home): server resource iframe card (DashboardServerResource)"
```

---

## Task 7: 抽取展示型区块组件

把 `home.vue` 中现有的区块内容抽到独立组件。每个组件为纯展示型,数据经 props 传入,自带所需的 scoped 样式(`.dot` 等类名在其他组件也用到,故必须 scoped,不可全局化)。

**Files:**
- Create: `frontend/app/utils/timeAgo.ts`
- Create: `frontend/app/components/dashboard/StatsRow.vue`
- Create: `frontend/app/components/dashboard/Todos.vue`
- Create: `frontend/app/components/dashboard/Mentions.vue`
- Create: `frontend/app/components/dashboard/Tasks.vue`
- Create: `frontend/app/components/dashboard/Activity.vue`

- [ ] **Step 1: 共用 timeAgo 工具**

Create `frontend/app/utils/timeAgo.ts`:
```ts
// 相对时间格式化(中文),Mentions / Activity 共用。
export function timeAgo(isoDate: string): string {
  const now = new Date()
  const then = new Date(isoDate)
  const diffMs = now.getTime() - then.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} 小时前`
  const diffDay = Math.floor(diffHour / 24)
  return `${diffDay} 天前`
}
```

- [ ] **Step 2: DashboardStatsRow(数据概览)**

Create `frontend/app/components/dashboard/StatsRow.vue`:
```vue
<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
    <DashboardStatCard
      label="本周已解决" :value="stats.resolved_this_week" icon="i-heroicons-check-circle"
      tone="success" :delta="resolvedDelta" delta-label="较上周" delta-unit="percent"
      positive-direction="up" to="/app/issues?status=已解决"
    />
    <DashboardStatCard
      label="待分配" :value="stats.pending" icon="i-heroicons-clock"
      tone="warning" :delta="pendingDelta" delta-label="较昨日" delta-unit="absolute"
      positive-direction="down" to="/app/issues?status=待分配"
    />
    <DashboardStatCard
      label="进行中" :value="stats.in_progress" icon="i-heroicons-arrow-path"
      tone="info" :delta="null" to="/app/issues?status=进行中"
    />
    <DashboardStatCard
      label="总 Issue 数" :value="stats.total" icon="i-heroicons-bug-ant"
      tone="primary" :delta="totalAddedDelta" delta-label="本周新增" delta-unit="absolute"
      positive-direction="up" to="/app/issues"
    />
  </div>
</template>

<script setup lang="ts">
interface Stats {
  total: number
  pending: number
  in_progress: number
  resolved_this_week: number
  resolved_prev_week: number
  pending_yesterday: number
  total_added_this_week: number
}
const props = defineProps<{ stats: Stats }>()

// 已解决环比:(本周 - 上周) / 上周 * 100
const resolvedDelta = computed<number | null>(() => {
  const cur = props.stats.resolved_this_week
  const prev = props.stats.resolved_prev_week
  if (!prev) return cur > 0 ? 100 : null
  return Math.round(((cur - prev) / prev) * 100)
})
// 待分配日环比(绝对差)
const pendingDelta = computed<number | null>(() => {
  const diff = props.stats.pending - props.stats.pending_yesterday
  return diff === 0 ? null : diff
})
// 总数本周新增(绝对值)
const totalAddedDelta = computed<number | null>(() =>
  props.stats.total_added_this_week > 0 ? props.stats.total_added_this_week : null,
)
</script>
```

- [ ] **Step 3: DashboardTodos(我的待办)**

Create `frontend/app/components/dashboard/Todos.vue`:
```vue
<template>
  <div class="section-card">
    <button
      class="section-header section-toggle"
      :class="{ 'section-toggle--collapsed': !show }"
      type="button"
      @click="show = !show"
    >
      <h3 class="section-title">
        我的待办
        <span class="section-badge">{{ issues.length }}</span>
      </h3>
      <div class="section-toggle-right">
        <NuxtLink to="/app/issues?assignee=me" class="section-link" @click.stop>查看全部</NuxtLink>
        <UIcon :name="show ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
      </div>
    </button>
    <div v-if="show" class="todo-list">
      <NuxtLink
        v-for="issue in issues"
        :key="issue.id"
        :to="`/app/issues/${issue.id}`"
        class="todo-row"
      >
        <span class="dot" :class="priorityDotClass(issue.priority)" />
        <span class="todo-id">{{ formatIssueId(issue.id) }}</span>
        <span class="todo-title">{{ issue.title }}</span>
        <span
          v-if="isTester && issue.status === '已解决'"
          class="todo-priority todo-priority--verify"
        >待验证</span>
        <span class="todo-priority" :class="priorityPillClass(issue.priority)">{{ issue.priority }}</span>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ issues: any[]; isTester: boolean }>()
const show = ref(false)

function formatIssueId(id: number): string {
  return `ISS-${String(id).padStart(3, '0')}`
}
function priorityDotClass(priority: string): string {
  switch (priority) {
    case '紧急': return 'dot--urgent'
    case '高': return 'dot--high'
    case '中': return 'dot--mid'
    case '低': return 'dot--low'
    default: return 'dot--low'
  }
}
function priorityPillClass(priority: string): string {
  switch (priority) {
    case '紧急': return 'todo-priority--urgent'
    case '高': return 'todo-priority--high'
    case '中': return 'todo-priority--mid'
    case '低': return 'todo-priority--low'
    default: return 'todo-priority--low'
  }
}
</script>

<style scoped>
.section-card { background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 1.25rem; }
:root.dark .section-card { background-color: #1f2937; border-color: #374151; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
.section-title { font-size: 0.875rem; font-weight: 600; color: #111827; display: flex; align-items: center; gap: 0.5rem; }
:root.dark .section-title { color: #f3f4f6; }
.section-badge { font-size: 0.75rem; font-weight: 500; color: #9ca3af; }
.section-link { font-size: 0.75rem; color: #7c3aed; transition: color 0.15s; }
.section-link:hover { color: #6d28d9; }
.section-toggle { width: 100%; background: transparent; border: 0; cursor: pointer; padding: 0; font: inherit; color: inherit; text-align: left; }
.section-toggle--collapsed { margin-bottom: 0; }
.section-toggle:hover .section-title { color: #7c3aed; }
:root.dark .section-toggle:hover .section-title { color: #c4b5fd; }
.section-toggle-right { display: flex; align-items: center; gap: 0.625rem; }
.todo-list { display: flex; flex-direction: column; }
.todo-row { display: flex; align-items: center; gap: 0.625rem; padding: 0.5rem 0.5rem; margin: 0 -0.5rem; border-radius: 0.375rem; transition: background-color 0.15s; }
.todo-row:not(:last-child) { border-bottom: 1px solid #f3f4f6; border-radius: 0; margin-bottom: 0; }
:root.dark .todo-row:not(:last-child) { border-bottom-color: rgba(255, 255, 255, 0.04); }
.todo-row:hover { background-color: #f9fafb; }
:root.dark .todo-row:hover { background-color: rgba(255, 255, 255, 0.03); }
.todo-id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.6875rem; color: #9ca3af; flex-shrink: 0; }
.todo-title { flex: 1; font-size: 0.8125rem; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .todo-title { color: #d1d5db; }
.dot { width: 0.5rem; height: 0.5rem; border-radius: 9999px; flex-shrink: 0; }
.dot--urgent { background-color: #ef4444; }
.dot--high { background-color: #f59e0b; }
.dot--mid { background-color: #3b82f6; }
.dot--low { background-color: #9ca3af; }
.todo-priority { font-size: 0.6875rem; padding: 0.0625rem 0.4375rem; border-radius: 0.25rem; flex-shrink: 0; font-weight: 500; }
.todo-priority--urgent { background-color: #fef2f2; color: #dc2626; }
:root.dark .todo-priority--urgent { background-color: rgba(239, 68, 68, 0.15); color: #fca5a5; }
.todo-priority--high { background-color: #fffbeb; color: #d97706; }
:root.dark .todo-priority--high { background-color: rgba(245, 158, 11, 0.15); color: #fcd34d; }
.todo-priority--mid { background-color: #eff6ff; color: #2563eb; }
:root.dark .todo-priority--mid { background-color: rgba(59, 130, 246, 0.15); color: #93c5fd; }
.todo-priority--low { background-color: #f9fafb; color: #6b7280; }
:root.dark .todo-priority--low { background-color: rgba(255, 255, 255, 0.05); color: #9ca3af; }
.todo-priority--verify { background-color: #ecfdf5; color: #059669; }
:root.dark .todo-priority--verify { background-color: rgba(16, 185, 129, 0.15); color: #6ee7b7; }
</style>
```

- [ ] **Step 4: DashboardMentions(提及我的)**

Create `frontend/app/components/dashboard/Mentions.vue`:
```vue
<template>
  <div class="section-card">
    <div class="section-header">
      <h3 class="section-title">
        提及我的
        <span class="section-badge">{{ mentions.length }}</span>
      </h3>
      <NuxtLink to="/app/notifications" class="section-link">查看全部</NuxtLink>
    </div>
    <div class="todo-list">
      <NuxtLink
        v-for="n in mentions"
        :key="n.id"
        :to="n.source_issue_id ? `/app/issues/${n.source_issue_id}` : `/app/notifications/${n.id}`"
        class="todo-row"
      >
        <span class="dot dot--info" />
        <span class="todo-title">{{ n.title }}</span>
        <span class="activity-time">{{ timeAgo(n.created_at) }}</span>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { timeAgo } from '~/utils/timeAgo'
defineProps<{ mentions: any[] }>()
</script>

<style scoped>
.section-card { background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 1.25rem; }
:root.dark .section-card { background-color: #1f2937; border-color: #374151; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
.section-title { font-size: 0.875rem; font-weight: 600; color: #111827; display: flex; align-items: center; gap: 0.5rem; }
:root.dark .section-title { color: #f3f4f6; }
.section-badge { font-size: 0.75rem; font-weight: 500; color: #9ca3af; }
.section-link { font-size: 0.75rem; color: #7c3aed; transition: color 0.15s; }
.section-link:hover { color: #6d28d9; }
.todo-list { display: flex; flex-direction: column; }
.todo-row { display: flex; align-items: center; gap: 0.625rem; padding: 0.5rem 0.5rem; margin: 0 -0.5rem; border-radius: 0.375rem; transition: background-color 0.15s; }
.todo-row:not(:last-child) { border-bottom: 1px solid #f3f4f6; border-radius: 0; margin-bottom: 0; }
:root.dark .todo-row:not(:last-child) { border-bottom-color: rgba(255, 255, 255, 0.04); }
.todo-row:hover { background-color: #f9fafb; }
:root.dark .todo-row:hover { background-color: rgba(255, 255, 255, 0.03); }
.todo-title { flex: 1; font-size: 0.8125rem; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .todo-title { color: #d1d5db; }
.dot { width: 0.5rem; height: 0.5rem; border-radius: 9999px; flex-shrink: 0; }
.dot--info { background-color: #8b5cf6; }
.activity-time { font-size: 0.6875rem; color: #9ca3af; flex-shrink: 0; white-space: nowrap; }
</style>
```

- [ ] **Step 5: DashboardTasks(我的任务)**

Create `frontend/app/components/dashboard/Tasks.vue`:
```vue
<template>
  <div class="section-card">
    <div class="section-header">
      <h3 class="section-title">
        我的任务
        <span class="section-badge">{{ tasks.length }}</span>
      </h3>
      <NuxtLink to="/app/ai/my-plan" class="section-link">查看全部</NuxtLink>
    </div>
    <div class="todo-list">
      <NuxtLink
        v-for="t in tasks"
        :key="t.id"
        to="/app/ai/my-plan"
        class="todo-row"
      >
        <span class="dot" :class="taskDotClass(t.priority)" />
        <span class="todo-title">{{ t.title }}</span>
        <span
          v-if="t.due_date"
          class="todo-priority"
          :class="taskOverdue(t) ? 'todo-priority--urgent' : 'todo-priority--low'"
        >截止 {{ t.due_date }}</span>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ tasks: any[] }>()

function taskDotClass(priority: string): string {
  if (priority === 'high') return 'dot--high'
  if (priority === 'medium') return 'dot--mid'
  return 'dot--low'
}
function taskOverdue(t: any): boolean {
  if (!t.due_date) return false
  const d = new Date()
  const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return t.due_date < today
}
</script>

<style scoped>
.section-card { background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 1.25rem; }
:root.dark .section-card { background-color: #1f2937; border-color: #374151; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
.section-title { font-size: 0.875rem; font-weight: 600; color: #111827; display: flex; align-items: center; gap: 0.5rem; }
:root.dark .section-title { color: #f3f4f6; }
.section-badge { font-size: 0.75rem; font-weight: 500; color: #9ca3af; }
.section-link { font-size: 0.75rem; color: #7c3aed; transition: color 0.15s; }
.section-link:hover { color: #6d28d9; }
.todo-list { display: flex; flex-direction: column; }
.todo-row { display: flex; align-items: center; gap: 0.625rem; padding: 0.5rem 0.5rem; margin: 0 -0.5rem; border-radius: 0.375rem; transition: background-color 0.15s; }
.todo-row:not(:last-child) { border-bottom: 1px solid #f3f4f6; border-radius: 0; margin-bottom: 0; }
:root.dark .todo-row:not(:last-child) { border-bottom-color: rgba(255, 255, 255, 0.04); }
.todo-row:hover { background-color: #f9fafb; }
:root.dark .todo-row:hover { background-color: rgba(255, 255, 255, 0.03); }
.todo-title { flex: 1; font-size: 0.8125rem; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .todo-title { color: #d1d5db; }
.dot { width: 0.5rem; height: 0.5rem; border-radius: 9999px; flex-shrink: 0; }
.dot--high { background-color: #f59e0b; }
.dot--mid { background-color: #3b82f6; }
.dot--low { background-color: #9ca3af; }
.todo-priority { font-size: 0.6875rem; padding: 0.0625rem 0.4375rem; border-radius: 0.25rem; flex-shrink: 0; font-weight: 500; }
.todo-priority--urgent { background-color: #fef2f2; color: #dc2626; }
:root.dark .todo-priority--urgent { background-color: rgba(239, 68, 68, 0.15); color: #fca5a5; }
.todo-priority--low { background-color: #f9fafb; color: #6b7280; }
:root.dark .todo-priority--low { background-color: rgba(255, 255, 255, 0.05); color: #9ca3af; }
</style>
```

- [ ] **Step 6: DashboardActivity(最近动态)**

Create `frontend/app/components/dashboard/Activity.vue`(接收**原始** activity 数组,自行计算文案/时间/头像):
```vue
<template>
  <div class="section-card">
    <button
      class="section-header section-toggle"
      :class="{ 'section-toggle--collapsed': !show }"
      type="button"
      @click="show = !show"
    >
      <h3 class="section-title">
        最近动态
        <span class="section-badge">{{ items.length }}</span>
      </h3>
      <div class="section-toggle-right">
        <NuxtLink to="/app/issues" class="section-link" @click.stop>查看全部</NuxtLink>
        <UIcon :name="show ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
      </div>
    </button>
    <div v-if="show" class="activity-list">
      <NuxtLink
        v-for="item in items"
        :key="item.id"
        :to="item.issue_id ? `/app/issues/${item.issue_id}` : '#'"
        class="activity-row"
      >
        <div class="activity-avatar" :style="{ backgroundColor: avatarColor(item.user_name) }">
          {{ avatarInitial(item.user_name) }}
        </div>
        <span class="activity-message">{{ activityMessage(item) }}</span>
        <span class="activity-time">{{ item.created_at ? timeAgo(item.created_at) : '' }}</span>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { timeAgo } from '~/utils/timeAgo'
defineProps<{ items: any[] }>()
const show = ref(false)

function activityMessage(item: any): string {
  const name = item.user_name || '未知用户'
  const issueRef = item.issue_id ? `#${item.issue_id}` : ''
  const title = item.issue_title ? `「${item.issue_title}」` : ''
  switch (item.action) {
    case 'created': return `${name} 创建了 ${issueRef}${title}`
    case 'resolved': return `${name} 解决了 ${issueRef}${title}`
    case 'status_changed': return `${name} 更新了 ${issueRef} 的状态${item.detail ? '：' + item.detail : ''}`
    case 'assigned': return `${name} 分配了 ${issueRef}${item.detail ? ' 给 ' + item.detail : ''}`
    case 'priority_changed': return `${name} 修改了 ${issueRef} 的优先级${item.detail ? '：' + item.detail : ''}`
    default: return `${name} ${item.action} ${issueRef} ${item.detail || ''}`.trim()
  }
}

const AVATAR_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899']
function avatarColor(name?: string): string {
  const text = name || '?'
  let hash = 0
  for (const c of text) hash = (hash + c.charCodeAt(0)) % AVATAR_COLORS.length
  return AVATAR_COLORS[hash] ?? AVATAR_COLORS[0]!
}
function avatarInitial(name?: string): string {
  const text = (name || '?').trim()
  return text.slice(0, 1) || '?'
}
</script>

<style scoped>
.section-card { background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 1.25rem; }
:root.dark .section-card { background-color: #1f2937; border-color: #374151; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
.section-title { font-size: 0.875rem; font-weight: 600; color: #111827; display: flex; align-items: center; gap: 0.5rem; }
:root.dark .section-title { color: #f3f4f6; }
.section-badge { font-size: 0.75rem; font-weight: 500; color: #9ca3af; }
.section-link { font-size: 0.75rem; color: #7c3aed; transition: color 0.15s; }
.section-link:hover { color: #6d28d9; }
.section-toggle { width: 100%; background: transparent; border: 0; cursor: pointer; padding: 0; font: inherit; color: inherit; text-align: left; }
.section-toggle--collapsed { margin-bottom: 0; }
.section-toggle:hover .section-title { color: #7c3aed; }
:root.dark .section-toggle:hover .section-title { color: #c4b5fd; }
.section-toggle-right { display: flex; align-items: center; gap: 0.625rem; }
.activity-list { display: flex; flex-direction: column; max-height: 24rem; overflow-y: auto; }
.activity-row { display: flex; align-items: center; gap: 0.75rem; padding: 0.625rem 0.5rem; margin: 0 -0.5rem; border-radius: 0.375rem; transition: background-color 0.15s; }
.activity-row:not(:last-child) { border-bottom: 1px solid #f3f4f6; border-radius: 0; }
:root.dark .activity-row:not(:last-child) { border-bottom-color: rgba(255, 255, 255, 0.04); }
.activity-row:hover { background-color: #f9fafb; }
:root.dark .activity-row:hover { background-color: rgba(255, 255, 255, 0.03); }
.activity-avatar { width: 1.75rem; height: 1.75rem; border-radius: 9999px; display: flex; align-items: center; justify-content: center; color: #ffffff; font-size: 0.6875rem; font-weight: 600; flex-shrink: 0; }
.activity-message { flex: 1; font-size: 0.8125rem; color: #4b5563; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .activity-message { color: #9ca3af; }
.activity-time { font-size: 0.6875rem; color: #9ca3af; flex-shrink: 0; white-space: nowrap; }
</style>
```

- [ ] **Step 7: 类型检查**

Run: `npx nuxi typecheck`
Expected: 通过(组件此时尚未被 home.vue 引用,但应能独立通过类型检查)。

- [ ] **Step 8: Commit**

```bash
git add frontend/app/utils/timeAgo.ts frontend/app/components/dashboard/StatsRow.vue frontend/app/components/dashboard/Todos.vue frontend/app/components/dashboard/Mentions.vue frontend/app/components/dashboard/Tasks.vue frontend/app/components/dashboard/Activity.vue
git commit -m "refactor(home): extract dashboard blocks into presentational components"
```

---

## Task 8: DashboardBlock 包装组件

**Files:**
- Create: `frontend/app/components/dashboard/Block.vue`

- [ ] **Step 1: 实现包装组件**

Create `frontend/app/components/dashboard/Block.vue`:
```vue
<template>
  <!-- 普通模式:仅当可见且有内容时渲染插槽内容(根级条件,不加包裹 div,避免隐藏区块在 gap 列中留空位) -->
  <slot v-if="!editing && visible && available" />

  <!-- 编辑模式:渲染所有区块(含占位),叠加控件条 -->
  <div v-else-if="editing" class="db-edit" :class="{ 'db-edit--hidden': !visible }">
    <div class="db-edit-bar">
      <span class="db-edit-title">{{ title }}</span>
      <span v-if="!visible" class="db-edit-flag">已隐藏</span>
      <div class="db-edit-actions">
        <button type="button" class="db-btn" :disabled="isFirst" title="上移" @click="moveUp(id)">
          <UIcon name="i-heroicons-arrow-up" class="db-icon" />
        </button>
        <button type="button" class="db-btn" :disabled="isLast" title="下移" @click="moveDown(id)">
          <UIcon name="i-heroicons-arrow-down" class="db-icon" />
        </button>
        <button type="button" class="db-btn" :title="visible ? '隐藏' : '显示'" @click="toggleVisible(id)">
          <UIcon :name="visible ? 'i-heroicons-eye' : 'i-heroicons-eye-slash'" class="db-icon" />
        </button>
      </div>
    </div>
    <div v-if="available" class="db-edit-body">
      <slot />
    </div>
    <div v-else class="db-edit-placeholder">{{ emptyText }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  id: string
  title: string
  available: boolean
  visible: boolean
  isFirst: boolean
  isLast: boolean
  emptyText: string
}>()
const { editing, moveUp, moveDown, toggleVisible } = useDashboardLayout()
</script>

<style scoped>
.db-edit { border: 1px dashed #c4b5fd; border-radius: 0.75rem; padding: 0.5rem; }
:root.dark .db-edit { border-color: #6d28d9; }
.db-edit--hidden { opacity: 0.55; }
.db-edit-bar { display: flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0.5rem 0.5rem; }
.db-edit-title { font-size: 0.8125rem; font-weight: 600; color: #6d28d9; }
:root.dark .db-edit-title { color: #c4b5fd; }
.db-edit-flag { font-size: 0.6875rem; color: #9ca3af; }
.db-edit-actions { margin-left: auto; display: flex; align-items: center; gap: 0.25rem; }
.db-btn { display: inline-flex; align-items: center; justify-content: center; width: 1.75rem; height: 1.75rem; border-radius: 0.375rem; border: 1px solid #e5e7eb; background: #fff; cursor: pointer; transition: background-color 0.15s; }
:root.dark .db-btn { background: #1f2937; border-color: #374151; }
.db-btn:hover:not(:disabled) { background: #f5f3ff; }
:root.dark .db-btn:hover:not(:disabled) { background: rgba(124, 58, 237, 0.15); }
.db-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.db-icon { width: 1rem; height: 1rem; color: #6b7280; }
:root.dark .db-icon { color: #9ca3af; }
/* 编辑模式下内容仅供预览,屏蔽交互,避免误点跳转 */
.db-edit-body { pointer-events: none; }
.db-edit-placeholder { padding: 1.25rem; text-align: center; font-size: 0.8125rem; color: #9ca3af; background: #f9fafb; border-radius: 0.5rem; }
:root.dark .db-edit-placeholder { background: rgba(255, 255, 255, 0.03); }
</style>
```

- [ ] **Step 2: 类型检查**

Run: `npx nuxi typecheck`
Expected: 通过。

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/dashboard/Block.vue
git commit -m "feat(home): DashboardBlock wrapper with edit-mode reorder/visibility controls"
```

---

## Task 9: 重写 home.vue 为编排者

把 `frontend/app/pages/app/home.vue` 整体替换为下面内容:保留取数与 `loading`,按 `orderedBlocks` 有序渲染包装后的区块,顶部加「编辑布局」工具条。

**Files:**
- Modify: `frontend/app/pages/app/home.vue`(整体替换)

- [ ] **Step 1: 整体替换 home.vue**

将 `frontend/app/pages/app/home.vue` 全部内容替换为:
```vue
<template>
  <div class="space-y-6">
    <!-- AI 问题向导(固定置顶,不可移动/隐藏) -->
    <AiIssueWizard @created="onIssueCreated" />

    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <template v-else>
      <!-- 工具条:编辑布局 -->
      <div class="dash-toolbar">
        <template v-if="editing">
          <button type="button" class="dash-link" @click="reset">重置默认</button>
          <button type="button" class="dash-btn dash-btn--primary" @click="editing = false">完成</button>
        </template>
        <button v-else type="button" class="dash-btn" @click="editing = true">
          <UIcon name="i-heroicons-squares-2x2" class="w-4 h-4" />
          编辑布局
        </button>
      </div>

      <!-- 区块:单列全宽,按用户布局有序渲染 -->
      <div class="dash-blocks">
        <DashboardBlock
          v-for="(block, i) in orderedBlocks"
          :key="block.id"
          :id="block.id"
          :title="block.title"
          :visible="block.visible"
          :available="availability[block.id] ?? false"
          :is-first="i === 0"
          :is-last="i === orderedBlocks.length - 1"
          :empty-text="block.id === 'server' ? '未配置监控地址' : '暂无内容'"
        >
          <component :is="blockComponents[block.id]" v-bind="propsFor(block.id)" />
        </DashboardBlock>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import UptimeMonitorsHomeWidget from '~/components/UptimeMonitorsHomeWidget.vue'
import DashboardStatsRow from '~/components/dashboard/StatsRow.vue'
import DashboardTodos from '~/components/dashboard/Todos.vue'
import DashboardMentions from '~/components/dashboard/Mentions.vue'
import DashboardTasks from '~/components/dashboard/Tasks.vue'
import DashboardActivity from '~/components/dashboard/Activity.vue'
import DashboardServerResource from '~/components/dashboard/ServerResource.vue'

definePageMeta({ layout: 'default' })

const { api } = useApi()
const { user, hasGroup } = useAuth()
// home 只用 orderedBlocks/editing/reset;移位与显隐由各 DashboardBlock 内部调用 useDashboardLayout 处理
const { orderedBlocks, editing, reset } = useDashboardLayout()
const { monitors } = useUptimeMonitors()
const serverMonitorUrl = computed(() => useRuntimeConfig().public.serverMonitorUrl as string)

const loading = ref(true)
const myIssues = ref<any[]>([])
const mentions = ref<any[]>([])
const stats = ref({
  total: 0,
  pending: 0,
  in_progress: 0,
  resolved_this_week: 0,
  resolved_prev_week: 0,
  pending_yesterday: 0,
  total_added_this_week: 0,
})
const recentActivity = ref<any[]>([])
const myTasks = ref<any[]>([])
const isTester = computed(() => hasGroup('测试'))

// 各区块「是否有内容/已配置」—— 普通模式下与 visible 一起决定是否渲染
const availability = computed<Record<string, boolean>>(() => ({
  stats: true,
  uptime: monitors.value.some(m => m.environment === 'production'),
  todos: myIssues.value.length > 0,
  mentions: mentions.value.length > 0,
  tasks: myTasks.value.length > 0,
  activity: recentActivity.value.length > 0,
  server: !!serverMonitorUrl.value,
}))

// id -> 组件
const blockComponents: Record<string, Component> = {
  stats: DashboardStatsRow,
  uptime: UptimeMonitorsHomeWidget,
  todos: DashboardTodos,
  mentions: DashboardMentions,
  tasks: DashboardTasks,
  activity: DashboardActivity,
  server: DashboardServerResource,
}

// id -> 该组件所需 props(uptime / server 自取数据,无 props)
function propsFor(id: string): Record<string, any> {
  switch (id) {
    case 'stats': return { stats: stats.value }
    case 'todos': return { issues: myIssues.value, isTester: isTester.value }
    case 'mentions': return { mentions: mentions.value }
    case 'tasks': return { tasks: myTasks.value }
    case 'activity': return { items: recentActivity.value }
    default: return {}
  }
}

async function onIssueCreated(_issueId: number) {
  // 创建后刷新"我的待办"
  myIssues.value = isTester.value ? await fetchTesterTodos() : await fetchDefaultTodos()
}

async function fetchPlanSummary() {
  try {
    const res = await api<any>('/api/kpi/plans/me/')
    const items = res.current?.action_items || []
    myTasks.value = items
      .filter((i: any) => !['verified', 'not_achieved'].includes(i.status))
      .slice(0, 8)
  } catch { /* 无计划时跳过 */ }
}

async function fetchTesterTodos(): Promise<any[]> {
  const userId = user.value?.id
  const [assignedData, resolvedData] = await Promise.all([
    api<any>(`/api/issues/?assignee=${userId}&exclude_statuses=已关闭&ordering=-priority&page_size=10`),
    api<any>('/api/issues/?status=已解决&ordering=-priority&page_size=20'),
  ])
  const assigned = (assignedData.results || assignedData || []) as any[]
  const resolved = (resolvedData.results || resolvedData || []) as any[]
  const assignedIds = new Set(assigned.map((i: any) => i.id))
  const merged = [...assigned, ...resolved.filter((i: any) => !assignedIds.has(i.id))]
  return merged.slice(0, 15)
}

async function fetchDefaultTodos(): Promise<any[]> {
  const userId = user.value?.id
  const data = await api<any>(`/api/issues/?assignee=${userId}&exclude_statuses=已解决,已关闭&ordering=-priority&page_size=10`)
  return (data.results || data || []).slice(0, 10)
}

onMounted(async () => {
  try {
    const [issueResults, notifData, statsData, activityData] = await Promise.all([
      isTester.value ? fetchTesterTodos() : fetchDefaultTodos(),
      api<any[]>('/api/notifications/?is_read=false'),
      api<any>('/api/dashboard/stats/'),
      api<any[]>('/api/dashboard/recent-activity/'),
    ])
    fetchPlanSummary()

    myIssues.value = issueResults

    const notifResults = Array.isArray(notifData) ? notifData : (notifData as any).results || []
    mentions.value = notifResults.slice(0, 5)

    stats.value = {
      total: statsData.total ?? 0,
      pending: statsData.pending ?? 0,
      in_progress: statsData.in_progress ?? 0,
      resolved_this_week: statsData.resolved_this_week ?? 0,
      resolved_prev_week: statsData.resolved_prev_week ?? 0,
      pending_yesterday: statsData.pending_yesterday ?? 0,
      total_added_this_week: statsData.total_added_this_week ?? 0,
    }

    // 传原始动态数组(文案/时间/头像由 DashboardActivity 内部计算)
    recentActivity.value = (activityData || []).slice(0, 10)
  } catch (e) {
    console.error('Failed to load home data:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dash-toolbar { display: flex; align-items: center; justify-content: flex-end; gap: 0.625rem; }
.dash-blocks { display: flex; flex-direction: column; gap: 1.5rem; }
.dash-btn { display: inline-flex; align-items: center; gap: 0.375rem; font-size: 0.8125rem; color: #4b5563; background: #fff; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 0.375rem 0.75rem; cursor: pointer; transition: background-color 0.15s, color 0.15s; }
:root.dark .dash-btn { background: #1f2937; border-color: #374151; color: #d1d5db; }
.dash-btn:hover { background: #f5f3ff; color: #6d28d9; }
:root.dark .dash-btn:hover { background: rgba(124, 58, 237, 0.15); color: #c4b5fd; }
.dash-btn--primary { background: #7c3aed; color: #fff; border-color: #7c3aed; }
.dash-btn--primary:hover { background: #6d28d9; color: #fff; }
.dash-link { font-size: 0.8125rem; color: #7c3aed; background: transparent; border: 0; cursor: pointer; }
.dash-link:hover { color: #6d28d9; }
</style>
```

- [ ] **Step 2: 类型检查**

Run: `npx nuxi typecheck`
Expected: 通过。

- [ ] **Step 3: 运行已有单测确认未回归**

Run: `npm test`
Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pages/app/home.vue
git commit -m "feat(home): orchestrate dashboard via ordered customizable blocks"
```

---

## Task 10: 手动 QA + 收尾

**Files:** 无(验证 + 必要修复)

- [ ] **Step 1: 启动前后端**

Run(两个终端):
```bash
# backend/
uv run python manage.py runserver
# frontend/
npm run dev
```
确保 `frontend/.env` 已含 `NUXT_PUBLIC_SERVER_MONITOR_URL`(Task 5),且本机 `localhost:9300` 监控服务可访问。

- [ ] **Step 2: 用 /browse 走查 `http://localhost:3004/app/home`**

逐项确认:
1. 默认布局正常显示:数据概览 → 生产环境监控 → 我的待办 → 提及我的 → 我的任务 → 最近动态 → 服务器资源(iframe)。
2. 空内容区块(如无待办/无提及)普通模式自动隐藏。
3. 点「编辑布局」→ 所有 7 个区块均显示(空的显示「暂无内容」占位),出现 ↑/↓/眼睛 控件;首区块 ↑ 禁用、末区块 ↓ 禁用。
4. 上移/下移某区块顺序即时变化;隐藏某区块标记「已隐藏」并灰显。
5. 点「完成」退出编辑;**刷新页面**,顺序与显隐保持(已持久化到后端)。
6. 点「重置默认」恢复初始顺序与全部可见。
7. 服务器资源卡片 iframe 正常加载;把 `frontend/.env` 的该变量置空并重启 `npm run dev`,普通模式下该卡片消失、编辑模式显示「未配置监控地址」。

- [ ] **Step 3: 修复 QA 中发现的问题(若有)**

针对走查发现的问题做最小修复;每修一处后重跑 `npx nuxi typecheck` 与 `npm test`。

- [ ] **Step 4: 最终类型检查 + 单测**

Run:
```bash
npx nuxi typecheck
npm test
```
Expected: 均通过。

- [ ] **Step 5: Commit(若有修复)**

```bash
git add -A
git commit -m "fix(home): QA fixes for dashboard customization"
```

---

## Self-Review(计划编写者已核对)

- **Spec 覆盖**:服务器资源卡片(Task 5/6)、个性化显隐排序(Task 2/3/4/8/9)、单列布局(Task 9)、env var 接线含 compose(Task 5)、纯逻辑单测(Task 2)、手动 QA(Task 10)—— 均有对应任务。
- **类型一致**:`LayoutEntry`/`DashboardBlockMeta` 在 util 定义并贯穿 composable;`useUserSettings.dashboard_layout` 类型(`{id;visible}[]`)与 `LayoutEntry[]` 结构兼容;`mergeLayout/moveBlock/toggleBlock/defaultLayout` 名称在 util、测试、composable 中一致;`DashboardBlock` props(`id/title/available/visible/isFirst/isLast/emptyText`)与 home.vue 传参一致;`blockComponents` 键与 `DASHBOARD_BLOCKS` id 一致。
- **无占位符**:每个改代码的步骤均含完整代码与确切命令/预期。
