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
