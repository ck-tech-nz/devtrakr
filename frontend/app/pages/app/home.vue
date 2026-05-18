<template>
  <div class="space-y-6">
    <!-- AI 问题向导 -->
    <AiIssueWizard @created="onIssueCreated" />

    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <template v-else>
      <!-- 数据概览：四列卡片（点击跳转到对应状态的 Issue 列表） -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <DashboardStatCard
          label="本周已解决"
          :value="stats.resolved_this_week"
          icon="i-heroicons-check-circle"
          tone="success"
          :delta="resolvedDelta"
          delta-label="较上周"
          delta-unit="percent"
          positive-direction="up"
          to="/app/issues?status=已解决"
        />
        <DashboardStatCard
          label="待分配"
          :value="stats.pending"
          icon="i-heroicons-clock"
          tone="warning"
          :delta="pendingDelta"
          delta-label="较昨日"
          delta-unit="absolute"
          positive-direction="down"
          to="/app/issues?status=待分配"
        />
        <DashboardStatCard
          label="进行中"
          :value="stats.in_progress"
          icon="i-heroicons-arrow-path"
          tone="info"
          :delta="null"
          to="/app/issues?status=进行中"
        />
        <DashboardStatCard
          label="总 Issue 数"
          :value="stats.total"
          icon="i-heroicons-bug-ant"
          tone="primary"
          :delta="totalAddedDelta"
          delta-label="本周新增"
          delta-unit="absolute"
          positive-direction="up"
          to="/app/issues"
        />
      </div>

      <!-- 我的待办 + 提及我的（任一为空时另一张卡占满，全为空时整行隐藏） -->
      <div
        v-if="hasTodos || hasMentions"
        class="grid grid-cols-1 gap-4"
        :class="{ 'lg:grid-cols-2': hasTodos && hasMentions }"
      >
        <!-- 我的待办 -->
        <div v-if="hasTodos" class="section-card">
          <div class="section-header">
            <h3 class="section-title">
              我的待办
              <span class="section-badge">{{ myIssues.length }}</span>
            </h3>
            <NuxtLink to="/app/issues?assignee=me" class="section-link">查看全部</NuxtLink>
          </div>
          <div class="todo-list">
            <NuxtLink
              v-for="issue in myIssues"
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

        <!-- 提及我的 -->
        <div v-if="hasMentions" class="section-card">
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
      </div>

      <!-- 我的提升计划 + 最近动态（同样的折叠规则） -->
      <div
        v-if="hasPlan || hasActivity"
        class="grid grid-cols-1 gap-4"
        :class="{ 'lg:grid-cols-2': hasPlan && hasActivity }"
      >
        <!-- 我的提升计划 -->
        <div v-if="hasPlan" class="section-card">
          <div class="section-header">
            <h3 class="section-title">我的提升计划</h3>
            <NuxtLink to="/app/ai/my-plan" class="section-link">查看全部</NuxtLink>
          </div>
          <div class="plan-summary">
            <span class="plan-summary-item">{{ planData.done }}/{{ planData.total }} 已完成</span>
            <span class="plan-summary-dot">·</span>
            <span class="plan-summary-item">{{ planData.earned }} / {{ planData.total_points }} 分</span>
          </div>
          <UProgress :value="planData.total > 0 ? planData.done / planData.total * 100 : 0" size="xs" class="plan-progress" />
          <div class="plan-items">
            <div v-for="item in planData.pending_items" :key="item.id" class="plan-item">
              <span class="plan-item-title">{{ item.title }}</span>
              <span class="plan-item-points">{{ item.points }}分</span>
            </div>
          </div>
        </div>

        <!-- 最近动态 -->
        <div v-if="hasActivity" class="section-card">
          <button
            class="section-header section-toggle"
            :class="{ 'section-toggle--collapsed': !showActivity }"
            type="button"
            @click="showActivity = !showActivity"
          >
            <h3 class="section-title">
              最近动态
              <span class="section-badge">{{ recentActivity.length }}</span>
            </h3>
            <div class="section-toggle-right">
              <NuxtLink to="/app/issues" class="section-link" @click.stop>查看全部</NuxtLink>
              <UIcon :name="showActivity ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
            </div>
          </button>
          <div v-if="showActivity" class="activity-list">
            <NuxtLink
              v-for="item in recentActivity"
              :key="item.id"
              :to="item.issue_id ? `/app/issues/${item.issue_id}` : '#'"
              class="activity-row"
            >
              <div class="activity-avatar" :style="{ backgroundColor: avatarColor(item.user_name) }">
                {{ avatarInitial(item.user_name) }}
              </div>
              <span class="activity-message">{{ item.message }}</span>
              <span class="activity-time">{{ item.time }}</span>
            </NuxtLink>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const { user, hasGroup } = useAuth()

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
const showActivity = ref(false)
const planData = ref<any>(null)
const isTester = computed(() => hasGroup('测试'))

// 空内容折叠：单卡内容为空时让相邻卡占满整行，两张都为空则整行隐藏
const hasTodos = computed(() => myIssues.value.length > 0)
const hasMentions = computed(() => mentions.value.length > 0)
const hasPlan = computed(() => Boolean(planData.value))
const hasActivity = computed(() => recentActivity.value.length > 0)

// 已解决环比：(本周 - 上周) / 上周 * 100
const resolvedDelta = computed<number | null>(() => {
  const cur = stats.value.resolved_this_week
  const prev = stats.value.resolved_prev_week
  if (!prev) return cur > 0 ? 100 : null
  return Math.round(((cur - prev) / prev) * 100)
})

// 待分配日环比：当前总数 - 昨日之前留存数（绝对差）
const pendingDelta = computed<number | null>(() => {
  const cur = stats.value.pending
  const prev = stats.value.pending_yesterday
  const diff = cur - prev
  if (diff === 0) return null
  return diff
})

// 总数本周新增（绝对值）
const totalAddedDelta = computed<number | null>(() => {
  const added = stats.value.total_added_this_week
  return added > 0 ? added : null
})

async function onIssueCreated(_issueId: number) {
  // 创建后刷新"我的待办"
  if (isTester.value) {
    myIssues.value = await fetchTesterTodos()
  } else {
    myIssues.value = await fetchDefaultTodos()
  }
}

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

function timeAgo(isoDate: string): string {
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

// 根据用户名生成稳定的头像背景色
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

async function fetchPlanSummary() {
  try {
    const res = await api<any>('/api/kpi/plans/me/')
    if (res.current) {
      const items = res.current.action_items || []
      const done = items.filter((i: any) => i.status === 'verified').length
      const earned = items.reduce((s: number, i: any) => s + (i.earned_points || 0), 0)
      const total_points = items.reduce((s: number, i: any) => s + i.points, 0)
      const pending_items = items
        .filter((i: any) => !['verified', 'not_achieved'].includes(i.status))
        .slice(0, 3)
      planData.value = { done, total: items.length, earned, total_points, pending_items }
    }
  } catch { /* 没有提升计划时跳过 */ }
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

    recentActivity.value = (activityData || []).slice(0, 10).map((item: any) => ({
      id: item.id,
      issue_id: item.issue_id,
      user_name: item.user_name,
      message: activityMessage(item),
      time: item.created_at ? timeAgo(item.created_at) : '',
    }))
  } catch (e) {
    console.error('Failed to load home data:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
/* 通用 section 卡片 */
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
.section-badge {
  font-size: 0.75rem;
  font-weight: 500;
  color: #9ca3af;
}
.section-link {
  font-size: 0.75rem;
  color: #7c3aed;
  transition: color 0.15s;
}
.section-link:hover { color: #6d28d9; }

/* 可折叠 section header（按钮形态） */
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
.section-toggle-right { display: flex; align-items: center; gap: 0.625rem; }

/* 待办 / 提及行 */
.todo-list {
  display: flex;
  flex-direction: column;
}
.todo-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem 0.5rem;
  margin: 0 -0.5rem;
  border-radius: 0.375rem;
  transition: background-color 0.15s;
}
.todo-row:not(:last-child) {
  border-bottom: 1px solid #f3f4f6;
  border-radius: 0;
  margin-bottom: 0;
}
:root.dark .todo-row:not(:last-child) {
  border-bottom-color: rgba(255, 255, 255, 0.04);
}
.todo-row:hover { background-color: #f9fafb; }
:root.dark .todo-row:hover { background-color: rgba(255, 255, 255, 0.03); }

.todo-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.6875rem;
  color: #9ca3af;
  flex-shrink: 0;
}
.todo-title {
  flex: 1;
  font-size: 0.8125rem;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:root.dark .todo-title { color: #d1d5db; }

.dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 9999px;
  flex-shrink: 0;
}
.dot--urgent { background-color: #ef4444; }
.dot--high { background-color: #f59e0b; }
.dot--mid { background-color: #3b82f6; }
.dot--low { background-color: #9ca3af; }
.dot--info { background-color: #8b5cf6; }

.todo-priority {
  font-size: 0.6875rem;
  padding: 0.0625rem 0.4375rem;
  border-radius: 0.25rem;
  flex-shrink: 0;
  font-weight: 500;
}
.todo-priority--urgent {
  background-color: #fef2f2; color: #dc2626;
}
:root.dark .todo-priority--urgent {
  background-color: rgba(239, 68, 68, 0.15); color: #fca5a5;
}
.todo-priority--high {
  background-color: #fffbeb; color: #d97706;
}
:root.dark .todo-priority--high {
  background-color: rgba(245, 158, 11, 0.15); color: #fcd34d;
}
.todo-priority--mid {
  background-color: #eff6ff; color: #2563eb;
}
:root.dark .todo-priority--mid {
  background-color: rgba(59, 130, 246, 0.15); color: #93c5fd;
}
.todo-priority--low {
  background-color: #f9fafb; color: #6b7280;
}
:root.dark .todo-priority--low {
  background-color: rgba(255, 255, 255, 0.05); color: #9ca3af;
}
.todo-priority--verify {
  background-color: #ecfdf5; color: #059669;
}
:root.dark .todo-priority--verify {
  background-color: rgba(16, 185, 129, 0.15); color: #6ee7b7;
}

/* 最近动态 */
.activity-list {
  display: flex;
  flex-direction: column;
  max-height: 24rem;
  overflow-y: auto;
}
.activity-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.5rem;
  margin: 0 -0.5rem;
  border-radius: 0.375rem;
  transition: background-color 0.15s;
}
.activity-row:not(:last-child) {
  border-bottom: 1px solid #f3f4f6;
  border-radius: 0;
}
:root.dark .activity-row:not(:last-child) {
  border-bottom-color: rgba(255, 255, 255, 0.04);
}
.activity-row:hover { background-color: #f9fafb; }
:root.dark .activity-row:hover { background-color: rgba(255, 255, 255, 0.03); }
.activity-avatar {
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 9999px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-size: 0.6875rem;
  font-weight: 600;
  flex-shrink: 0;
}
.activity-message {
  flex: 1;
  font-size: 0.8125rem;
  color: #4b5563;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:root.dark .activity-message { color: #9ca3af; }
.activity-time {
  font-size: 0.6875rem;
  color: #9ca3af;
  flex-shrink: 0;
  white-space: nowrap;
}

/* 我的提升计划 */
.plan-summary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: #6b7280;
  margin-bottom: 0.75rem;
}
:root.dark .plan-summary { color: #9ca3af; }
.plan-summary-dot { color: #d1d5db; }
.plan-progress {
  margin-bottom: 1rem;
}
.plan-items {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.plan-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.8125rem;
}
.plan-item-title {
  color: #374151;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 0.5rem;
}
:root.dark .plan-item-title { color: #d1d5db; }
.plan-item-points {
  color: #9ca3af;
  font-size: 0.75rem;
  flex-shrink: 0;
}
</style>
