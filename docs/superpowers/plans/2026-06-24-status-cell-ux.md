# 状态单元格 UX 改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现详情页/列表的五处 UX 改进:进行中自动认领弹窗、消除「接单」一词、去掉状态徽章筛选点击、修复并改造变更历史卡、三张侧栏卡默认收起。

**Architecture:** 纯前端为主(Nuxt 4 SPA + Nuxt UI 组件库),仅 Item 2 涉及后端字符串与一条 `AlterField` 迁移。变更历史复用既有 `GET /api/issues/{id}/history/` 端点。唯一的纯逻辑(`changeSummary`)抽到 `app/utils/` 并用 Vitest 单测;其余为模板/交互改动,以 `npx nuxi typecheck` + 手动验证为门禁。

**Tech Stack:** Nuxt 4 (Vue 3 `<script setup>`)、Nuxt UI(`UModal`/`UButton`/`UIcon`/`USelect`)、Tailwind、Vitest(`@nuxt/test-utils`)、Django REST Framework、django-simple-history、`uv`。

## Global Constraints

- 前端语言为简体中文:所有 UI 文案与代码注释用中文。
- 「认领」替换「接单」;存储值 `claim` 不变。
- 前端类型门禁:`frontend/` 下 `npx nuxi typecheck` 必须通过。
- 前端单测:`frontend/` 下 `npm test`(= `vitest run`)。
- 后端用 `uv`(非 pip):`uv run pytest`、`uv run python manage.py …`。
- 迁移:用 `makemigrations` 生成;**绝不手改已存在的迁移文件**(如 `0010_assignment_workflow.py`);需要数据/无法生成时才手写 `RunPython`。
- `进行中` 自动认领弹窗仅在「目标状态为进行中且当前无负责人」时出现;取消/关闭 = 不做任何变更。
- 变更历史卡仅管理员可见(后端 `_is_manager` 已 403 兜底)。
- 不改动看板 `IssueCard.vue`;不改后端 `/history/` 响应结构与权限;不动其它侧栏卡默认展开态。

---

### Task 1: 消除「接单」一词 → 「认领」(前端 3 处 + 后端字符串 + 枚举迁移)

**Files:**
- Modify: `frontend/app/components/issue/StatusCell.vue`(按钮文案)
- Modify: `frontend/app/pages/app/issues/[id].vue`(审计标签映射)
- Modify: `frontend/app/pages/app/issues/index.vue`(创建后 toast)
- Modify: `backend/apps/issues/services.py`(错误信息 + 活动详情 + docstring,共 6 处)
- Modify: `backend/apps/issues/models.py`(`AssignmentAction.CLAIM` 标签)
- Modify: `backend/tests/test_assignment_api.py`(docstring,2 处)
- Create(自动生成): `backend/apps/issues/migrations/0017_*.py`(`makemigrations` 产出,勿手写)

- [ ] **Step 1: 前端 StatusCell 按钮文案**

`frontend/app/components/issue/StatusCell.vue` —— 找到接单按钮(约 78–83 行):

```vue
      <UButton
        v-if="issue.can_claim"
        size="xs" color="primary" variant="soft"
        icon="i-lucide-plus" :loading="busy"
        @click.stop="onClaim"
      >接单</UButton>
```

把 `>接单</UButton>` 改为 `>认领</UButton>`。

- [ ] **Step 2: 前端详情页审计标签映射**

`frontend/app/pages/app/issues/[id].vue`,`assignmentActionLabel` 内(约 1694 行):把

```ts
    claim: '接单',
```

改为

```ts
    claim: '认领',
```

- [ ] **Step 3: 前端创建后 toast 文案**

`frontend/app/pages/app/issues/index.vue`(约 766 行),把

```ts
      : '已创建，等待人工接单'
```

改为

```ts
      : '已创建，等待人工认领'
```

- [ ] **Step 4: 后端 services.py 全部 6 处替换**

`backend/apps/issues/services.py` 中,把全部 `接单` 替换为 `认领`(6 处,全部为有意替换):

| 行 | 改前 | 改后 |
|---|---|---|
| 183 | `"""任何项目成员可接单「待分配」→「进行中」,自动成为负责人。"""` | `…可认领「待分配」…` |
| 186 | `f"只有「待分配」可被接单,当前 {issue.status}"` | `f"只有「待分配」可被认领,当前 {issue.status}"` |
| 189 | `raise PermissionDenied("仅项目成员可接单")` | `raise PermissionDenied("仅项目成员可认领")` |
| 205 | `detail=f"{actor.name or actor.username} 接单"` | `detail=f"{actor.name or actor.username} 认领"` |
| 218 | `raise PermissionDenied("仅当前负责人可确认接单")` | `raise PermissionDenied("仅当前负责人可确认认领")` |
| 233 | `detail="确认接单"` | `detail="确认认领"` |

- [ ] **Step 5: 后端枚举标签**

`backend/apps/issues/models.py` 第 36 行:

```python
    CLAIM = 'claim', '接单'
```

改为

```python
    CLAIM = 'claim', '认领'
```

- [ ] **Step 6: 后端测试 docstring(2 处)**

`backend/tests/test_assignment_api.py` 第 10、22 行 docstring 里的「接单」改为「认领」(纯注释,无断言依赖)。

- [ ] **Step 7: 生成迁移**

Run（在 `backend/`）：`uv run python manage.py makemigrations issues`
Expected: 新建 `0017_*.py`,内容为对 `issueassignment.action` 的 `AlterField`(choices 标签变化)。**不要手改它,也不要改 0010。**

- [ ] **Step 8: 应用迁移**

Run（在 `backend/`）：`uv run python manage.py migrate`
Expected: `Applying issues.0017_… OK`

- [ ] **Step 9: 后端回归 + 全局确认无残留**

Run（在 `backend/`）：`uv run pytest tests/test_assignment_api.py -q`
Expected: PASS(claim/confirm 流程不受影响)

Run（仓库根）：`rg -n "接单" --glob '!*.lock' --glob '!docs/**' --glob '!**/migrations/**'`
Expected: 无输出(`dashboardLayout.ts` 的「直接单测」是子串误匹配,已被你确认无关;若它仍出现,**忽略**——不要改它)。
> 说明:`migrations/0010_assignment_workflow.py` 里的 `("claim","接单")` 是冻结历史,被 glob 排除,保持原样。

- [ ] **Step 10: 前端类型检查**

Run（在 `frontend/`）：`npx nuxi typecheck`
Expected: 无新增报错。

- [ ] **Step 11: Commit**

```bash
git add frontend/app/components/issue/StatusCell.vue frontend/app/pages/app/issues/[id].vue frontend/app/pages/app/issues/index.vue backend/apps/issues/services.py backend/apps/issues/models.py backend/tests/test_assignment_api.py backend/apps/issues/migrations/0017_*.py
git commit -m "feat(issues): 「接单」改为「认领」(前后端所有用户可见处)"
```

---

### Task 2: 去掉状态徽章的「点击筛选处理人」(消除点击冲突)

**Files:**
- Modify: `frontend/app/components/issue/StatusCell.vue`(移除 filter emit/computed/handler + 徽章点击)
- Modify: `frontend/app/pages/app/issues/index.vue`(移除 `@filter-assignee` + `filterByAssignee`)

- [ ] **Step 1: StatusCell 移除 emit 声明**

`StatusCell.vue` 的 `defineEmits` 中删除 `filter-assignee` 这一行:

```ts
const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'request-transfer'): void
  (e: 'request-assign'): void
  (e: 'filter-assignee'): void   // ← 删除这一行
}>()
```

- [ ] **Step 2: StatusCell 移除 filter 计算属性与函数**

删除这段(约 32–36 行):

```ts
// 状态徽章上若有处理人，点击可按该处理人筛选
const canFilterAssignee = computed(() => !!props.issue.assignee)
function onFilterAssignee() {
  if (canFilterAssignee.value) emit('filter-assignee')
}
```

- [ ] **Step 3: StatusCell 第一个徽章去掉点击/光标/title**

「待确认/进行中: 别人的」分支里的徽章,改前:

```vue
      <UBadge
        :color="statusColor(issue.status)" variant="subtle" size="sm"
        :class="canFilterAssignee ? 'cursor-pointer hover:opacity-80' : ''"
        :title="canFilterAssignee ? `筛选处理人：${issue.assignee_name}` : undefined"
        @click.stop="onFilterAssignee"
      >
        {{ badgeLabel }}
      </UBadge>
```

改后:

```vue
      <UBadge
        :color="statusColor(issue.status)" variant="subtle" size="sm"
      >
        {{ badgeLabel }}
      </UBadge>
```

- [ ] **Step 4: StatusCell「进行中: 自己的」徽章去掉点击**

改前:

```vue
      <UBadge
        :color="statusColor(issue.status)" variant="subtle" size="sm"
        class="cursor-pointer hover:opacity-80"
        title="筛选处理人：我"
        @click.stop="onFilterAssignee"
      >
        我 处理中
      </UBadge>
```

改后:

```vue
      <UBadge
        :color="statusColor(issue.status)" variant="subtle" size="sm"
      >
        我 处理中
      </UBadge>
```

- [ ] **Step 5: StatusCell「已解决/已发布/已关闭/未计划」徽章去掉点击**

改前:

```vue
      <UBadge
        :color="statusColor(issue.status)" variant="subtle" size="sm"
        :class="canFilterAssignee ? 'cursor-pointer hover:opacity-80' : ''"
        :title="canFilterAssignee ? `筛选处理人：${issue.assignee_name}` : undefined"
        @click.stop="onFilterAssignee"
      >
        {{ badgeLabel }}
      </UBadge>
```

改后:

```vue
      <UBadge
        :color="statusColor(issue.status)" variant="subtle" size="sm"
      >
        {{ badgeLabel }}
      </UBadge>
```

- [ ] **Step 6: index.vue 移除事件处理**

`frontend/app/pages/app/issues/index.vue` 的 `<StatusCell>` 上删除这一行(约 340 行):

```vue
            @filter-assignee="filterByAssignee(row.original)"
```

- [ ] **Step 7: index.vue 删除 filterByAssignee 函数**

删除现已无引用的函数(约 477–482 行)。**注意只删 `filterByAssignee`,保留紧随其后的 `filterByPriority`(优先级徽章仍用)**:

```ts
// 点击有处理人的状态：以独立标签按该处理人(assignee)筛选；同时清空负责人下拉，避免双重筛选
function filterByAssignee(issue: any) {
  if (!issue.assignee) return
  filterAssignee.value = ''
  filterHandler.value = { id: String(issue.assignee), label: issue.assignee_name || '处理人' }
}
```

- [ ] **Step 8: 确认无残留 + 类型检查**

Run（仓库根）：`rg -n "filter-assignee|filterByAssignee" frontend/`
Expected: 无输出。

Run（在 `frontend/`）：`npx nuxi typecheck`
Expected: 无新增报错。

- [ ] **Step 9: 手动验证(`bot`/`password123`,`/browse` 或 `/qa`)**

进问题列表:点击状态徽章不再触发「按处理人筛选」;`认领`/`接受`/`转单`/`指派` 按钮点击正常;列表顶部「负责人」下拉筛选仍可用。

- [ ] **Step 10: Commit**

```bash
git add frontend/app/components/issue/StatusCell.vue frontend/app/pages/app/issues/index.vue
git commit -m "fix(issues): 状态徽章去掉点击筛选，消除与操作按钮的点击冲突"
```

---

### Task 3: 「进行中」自动认领弹窗(详情页)

**Files:**
- Modify: `frontend/app/pages/app/issues/[id].vue`(新增 refs + 改 `handleStatusClick` + 新增保存函数 + 新增 `UModal`)

**Interfaces:**
- Consumes: 已有 `selfUserId`(computed, number)、`form.value.assignee`(string,空为 `'_none'`)、`issue.value`、`route.params.id`、`api`、`populateForm`、`updateField`、`closeWithGitHub`。
- Produces: 无对外接口(同文件内自洽)。

- [ ] **Step 1: 新增弹窗状态 ref**

在 `[id].vue` 的 `<script setup>` 中,紧挨现有 `handleStatusClick` 之前新增:

```ts
// 「进行中」自动认领弹窗状态
const showSelfAssignPrompt = ref(false)
const pendingStatus = ref('')
```

- [ ] **Step 2: 改写 handleStatusClick**

把现有(约 1437–1447 行):

```ts
// 状态胶囊点击处理（已解决 -> 已关闭 时检查 GitHub）
function handleStatusClick(newStatus: string) {
  if (newStatus === '已关闭') {
    const hasOpenGH = issue.value?.github_issues?.some((gh: any) => gh.state === 'open')
    if (hasOpenGH) {
      closeWithGitHub()
      return
    }
  }
  updateField('status', newStatus)
}
```

改为:

```ts
// 状态胶囊点击处理（已解决 -> 已关闭 时检查 GitHub；进行中且无负责人时询问认领）
function handleStatusClick(newStatus: string) {
  if (newStatus === '已关闭') {
    const hasOpenGH = issue.value?.github_issues?.some((gh: any) => gh.state === 'open')
    if (hasOpenGH) {
      closeWithGitHub()
      return
    }
  }
  // 改为「进行中」且当前无负责人 → 询问是否同时把负责人设为自己
  if (newStatus === '进行中' && form.value.assignee === '_none') {
    pendingStatus.value = newStatus
    showSelfAssignPrompt.value = true
    return
  }
  updateField('status', newStatus)
}
```

- [ ] **Step 3: 新增确认保存函数**

在 `handleStatusClick` 之后新增:

```ts
// 弹窗确认:alsoAssign 为 true 时同时把负责人设为当前用户
async function confirmSelfAssign(alsoAssign: boolean) {
  const targetStatus = pendingStatus.value
  showSelfAssignPrompt.value = false
  pendingStatus.value = ''
  if (!issue.value || !targetStatus) return
  const body: Record<string, any> = { status: targetStatus }
  if (alsoAssign) body.assignee = selfUserId.value
  try {
    await api(`/api/issues/${issue.value.id}/`, { method: 'PATCH', body })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
  } catch (e) {
    console.error('Self-assign status change failed:', e)
  }
}
```

- [ ] **Step 4: 新增弹窗模板**

在模板里其它 `UModal`(如「删除附件确认弹窗」)旁边新增(放在 `</UModal>` 之后、同级):

```vue
    <!-- 「进行中」自动认领弹窗 -->
    <UModal v-model:open="showSelfAssignPrompt">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>设为进行中</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showSelfAssignPrompt = false" />
          </div>
          <div class="modal-body">
            <p class="text-sm text-gray-700 dark:text-gray-300">该问题还没有负责人，要同时把负责人设为你自己吗？</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="confirmSelfAssign(false)">仅修改状态</UButton>
            <UButton color="primary" @click="confirmSelfAssign(true)">是，由我处理</UButton>
          </div>
        </div>
      </template>
    </UModal>
```

- [ ] **Step 5: 类型检查**

Run（在 `frontend/`）：`npx nuxi typecheck`
Expected: 无新增报错。

- [ ] **Step 6: 手动验证(`bot`/`password123`)**

1. 打开一个**无负责人**的问题 → 点「进行中」→ 弹窗出现。
2. 点「是，由我处理」→ 状态变进行中,负责人变为「我」。
3. 再开一个无负责人问题 → 点「进行中」→ 点「仅修改状态」→ 状态变进行中,负责人仍为「无」。
4. 取消(关闭弹窗/点 X)→ 状态、负责人都不变。
5. 打开一个**已有负责人**的问题 → 点「进行中」→ 不弹窗,直接生效。

- [ ] **Step 7: Commit**

```bash
git add frontend/app/pages/app/issues/[id].vue
git commit -m "feat(issues): 进行中且无负责人时弹窗询问是否同时认领"
```

---

### Task 4: 变更摘要纯函数 `changeSummary` + 单测

**Files:**
- Create: `frontend/app/utils/issueHistory.ts`
- Test: `frontend/tests/issueHistory.test.ts`

**Interfaces:**
- Produces: `export type HistoryChange = { field: string; label: string; before: any; after: any }`;`export type HistoryEntry = { id: number; type: '+' | '~' | '-'; date: string; user: string | null; changes: HistoryChange[] }`;`export function changeSummary(entry: HistoryEntry): string` —— Task 5 的变更历史卡消费它。

- [ ] **Step 1: 写失败测试**

`frontend/tests/issueHistory.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { changeSummary, type HistoryEntry } from '../app/utils/issueHistory'

function entry(partial: Partial<HistoryEntry>): HistoryEntry {
  return { id: 1, type: '~', date: '2026-06-24T00:00:00Z', user: '凯歌', changes: [], ...partial }
}

describe('changeSummary', () => {
  it('创建记录显示「创建」', () => {
    expect(changeSummary(entry({ type: '+', changes: [{ field: '_created', label: '创建', before: null, after: null }] }))).toBe('创建')
  })

  it('首个变更字段为 _created 时也显示「创建」', () => {
    expect(changeSummary(entry({ type: '~', changes: [{ field: '_created', label: '创建', before: null, after: null }] }))).toBe('创建')
  })

  it('删除记录显示「删除」', () => {
    expect(changeSummary(entry({ type: '-', changes: [{ field: 'is_deleted', label: '已删除', before: false, after: true }] }))).toBe('删除')
  })

  it('更新记录用「、」连接变更字段名', () => {
    expect(changeSummary(entry({
      changes: [
        { field: 'status', label: '状态', before: '进行中', after: '已解决' },
        { field: 'description', label: '描述', before: 'a', after: 'b' },
      ],
    }))).toBe('状态、描述')
  })

  it('无变更字段时兜底「更新」', () => {
    expect(changeSummary(entry({ changes: [] }))).toBe('更新')
  })
})
```

- [ ] **Step 2: 运行,确认失败**

Run（在 `frontend/`）：`npm test -- issueHistory`
Expected: FAIL —— 找不到模块 `../app/utils/issueHistory`。

- [ ] **Step 3: 实现**

`frontend/app/utils/issueHistory.ts`:

```ts
// 问题变更历史的纯逻辑(无 Nuxt 依赖,可被 Vitest 直接单测)。
// 数据来源:GET /api/issues/{id}/history/(django-simple-history diff)。

export type HistoryChange = { field: string; label: string; before: any; after: any }
export type HistoryEntry = {
  id: number
  type: '+' | '~' | '-'
  date: string
  user: string | null
  changes: HistoryChange[]
}

// 每行「变更内容」:仅显示变动的字段名(用顿号连接);创建/删除单独成词。
export function changeSummary(entry: HistoryEntry): string {
  if (entry.type === '+' || entry.changes[0]?.field === '_created') return '创建'
  if (entry.type === '-') return '删除'
  const labels = entry.changes.map(c => c.label).filter(Boolean)
  return labels.length ? labels.join('、') : '更新'
}
```

- [ ] **Step 4: 运行,确认通过**

Run（在 `frontend/`）：`npm test -- issueHistory`
Expected: PASS(5 个用例全过)。

- [ ] **Step 5: Commit**

```bash
git add frontend/app/utils/issueHistory.ts frontend/tests/issueHistory.test.ts
git commit -m "feat(issues): 抽出变更历史摘要纯函数 changeSummary + 单测"
```

---

### Task 5: 修复并改造「更新历史」卡为「变更历史」卡

**Files:**
- Modify: `frontend/app/pages/app/issues/[id].vue`(移动卡片位置、改可见性/默认展开、进页加载、用 `changeSummary` 渲染、删除 `formatValue`)

**Interfaces:**
- Consumes: Task 4 的 `changeSummary` 与类型;已有 `isManager`、`history`、`historyLoading`、`showHistory`、`loadHistory`、`toggleHistory`、`formatRelative`、`onMounted`。

- [ ] **Step 1: 导入 changeSummary**

在 `[id].vue` `<script setup>` 顶部的 import 区新增:

```ts
import { changeSummary } from '~/utils/issueHistory'
```

> 现有的本地 `type HistoryChange`/`type HistoryEntry`(约 872–873 行)保留即可,与 util 的结构一致;无需改动 `history`/`loadHistory`/`toggleHistory`。

- [ ] **Step 2: 默认展开**

把(约 875 行):

```ts
const showHistory = ref(false)
```

改为:

```ts
const showHistory = ref(true)
```

- [ ] **Step 3: 进页即加载(管理员)**

在 `onMounted(async () => { … })` 末尾(现有 `fetchAnalyses()` 之后)新增一行:

```ts
  loadHistory()
```

> `loadHistory` 内部已 `if (!isManager.value) return`,非管理员不会发请求。

- [ ] **Step 4: 删除旧「更新历史」卡块**

删除现有整段(约 612–654 行,`<!-- 更新历史 … -->` 到对应 `</div>`):

```vue
        <!-- 更新历史 (仅管理员; 内容为空 + 已加载完成时整张卡隐藏) -->
        <div v-if="isManager && (historyLoading || history.length)" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          ... (整块,含逐字段 before→after 明细) ...
        </div>
```

- [ ] **Step 5: 在「分配流转」卡之后插入新「变更历史」卡**

找到「分配流转」卡(`<!-- 分配流转 -->` … 到它的 `</div>`,约 656–668 行),在其**结束 `</div>` 之后**插入:

```vue
        <!-- 变更历史 (仅管理员) -->
        <div v-if="isManager" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="toggleHistory">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">变更历史</h3>
            <UIcon :name="showHistory ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <div v-if="showHistory" class="space-y-3">
            <div v-if="historyLoading" class="text-xs text-gray-400 dark:text-gray-500">加载中...</div>
            <p v-else-if="!history.length" class="text-xs text-gray-400 dark:text-gray-500">暂无历史记录</p>
            <div v-else class="space-y-3 max-h-96 overflow-y-auto -mx-1 px-1">
              <div
                v-for="entry in history"
                :key="entry.id"
                class="border-l-2 pl-3 py-1"
                :class="entry.type === '+' ? 'border-emerald-400' : entry.type === '-' ? 'border-rose-400' : 'border-crystal-300 dark:border-crystal-700'"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs font-medium text-gray-700 dark:text-gray-300">{{ entry.user || '系统' }}</span>
                  <time class="text-[11px] text-gray-400 dark:text-gray-500" :title="entry.date">{{ formatRelative(entry.date) }}</time>
                </div>
                <div class="mt-1 text-xs text-gray-600 dark:text-gray-400">{{ changeSummary(entry) }}</div>
              </div>
            </div>
          </div>
        </div>
```

- [ ] **Step 6: 删除现已无用的 formatValue**

旧明细块删除后,`formatValue`(约 897–903 行)不再被任何地方引用。删除该函数:

```ts
function formatValue(v: any): string {
  ...
}
```

- [ ] **Step 7: 确认无残留引用 + 类型检查**

Run（仓库根）：`rg -n "formatValue|更新历史" frontend/app/pages/app/issues/\[id\].vue`
Expected: 无输出。

Run（在 `frontend/`）：`npx nuxi typecheck`
Expected: 无新增报错。

- [ ] **Step 8: 手动验证(管理员账号 `bot`/`password123`)**

1. 打开任一问题详情 → 侧栏最底部出现「变更历史」卡,且**默认展开**、进页即显示历史(无需点击)。
2. 每行:左修改人、右相对时间(悬停看完整时间),下一行为变更字段名(如「状态、描述」);最早一条显示「创建」。
3. 卡头可点击折叠/再展开。
4. (若有非管理员账号)用其登录 → 不出现「变更历史」卡。

- [ ] **Step 9: Commit**

```bash
git add frontend/app/pages/app/issues/[id].vue
git commit -m "fix(issues): 修复变更历史卡(原从不显示)，移到分配流转下、默认展开、仅显字段名"
```

---

### Task 6: 「分配流转」「分析记录」「关联仓库」三卡默认收起

**Files:**
- Modify: `frontend/app/pages/app/issues/[id].vue`(三个折叠 ref + 三处卡头改可点击 + body 包 `v-if`)

- [ ] **Step 1: 新增三个折叠状态 ref**

在 `<script setup>` 中(可放在 `showHistory` 附近)新增,默认收起:

```ts
// 侧栏卡默认收起
const showAnalysis = ref(false)
const showRepo = ref(false)
const showAssignments = ref(false)
```

- [ ] **Step 2: 「分析记录」卡头改可点击 + body 包裹**

把(约 291–293 行):

```vue
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">分析记录</h3>
          <div class="space-y-4">
```

改为:

```vue
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="showAnalysis = !showAnalysis">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">分析记录</h3>
            <UIcon :name="showAnalysis ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <div v-if="showAnalysis" class="space-y-4">
```

> 该卡 body(三个 `form-row`)与外层 `</div>` 结构不变;新增的 `v-if` div 替换原 `<div class="space-y-4">` 开标签,闭合标签数量不变。

- [ ] **Step 3: 「关联仓库」卡头改可点击 + body 包裹**

把(约 358–361 行):

```vue
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">关联仓库</h3>

          <div class="space-y-2">
```

改为:

```vue
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="showRepo = !showRepo">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">关联仓库</h3>
            <UIcon :name="showRepo ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>

          <div v-if="showRepo" class="space-y-2">
```

> 注意:`关联仓库` 卡里在 `.space-y-2` 之后还有一个 `<div v-if="issueRepo" …>`(仓库链接块,约 391–399 行)。也要把它纳入折叠。做法:把该 `v-if="issueRepo"` 改为 `v-if="showRepo && issueRepo"`:

```vue
          <div v-if="showRepo && issueRepo" class="flex items-center gap-2 pt-1">
```

- [ ] **Step 4: 「分配流转」卡头改可点击 + body 包裹**

把(约 657–659 行):

```vue
        <div v-if="issue?.assignments?.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">分配流转</h3>
          <ol class="space-y-1.5 text-sm">
```

改为:

```vue
        <div v-if="issue?.assignments?.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="showAssignments = !showAssignments">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">分配流转</h3>
            <UIcon :name="showAssignments ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <ol v-if="showAssignments" class="space-y-1.5 text-sm">
```

- [ ] **Step 5: 类型检查**

Run（在 `frontend/`）：`npx nuxi typecheck`
Expected: 无新增报错。

- [ ] **Step 6: 手动验证(`bot`/`password123`)**

1. 打开问题详情:「分配流转」「分析记录」「关联仓库」三卡**默认收起**(只见标题 + chevron)。
2. 逐个点击卡头 → 展开;再点 → 收起。
3. 展开「分析记录」后,备注/原因分析/解决方案可编辑、失焦保存正常。
4. 展开「关联仓库」后,项目/仓库下拉可改,已关联仓库链接与克隆状态徽章正常显示。

- [ ] **Step 7: Commit**

```bash
git add frontend/app/pages/app/issues/[id].vue
git commit -m "feat(issues): 分配流转/分析记录/关联仓库三卡默认收起"
```

---

## 验收(对照 spec §5)

- [ ] 无负责人问题点「进行中」→ 弹窗;是→进行中+负责人为我;仅改状态→进行中+负责人空;取消→无变更;有负责人→不弹窗。
- [ ] 列表/详情/创建 toast/活动详情/错误信息中均无「接单」,显示为「认领」。
- [ ] 状态徽章点击不再筛选;操作按钮正常;顶部负责人下拉筛选仍可用。
- [ ] 管理员进详情:变更历史卡默认展开且进页即显示,每行有修改人/相对时间/变更字段名,首条「创建」;非管理员不可见。
- [ ] 三卡默认收起,可展开/收起,展开后功能正常。
- [ ] `npx nuxi typecheck` 通过;`npm test` 通过;`uv run pytest tests/test_assignment_api.py` 通过。
