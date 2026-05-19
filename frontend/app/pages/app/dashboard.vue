<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">项目概览</h1>

    <!-- Loading State -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <template v-else>
      <!-- Active Projects Quick Access -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <NuxtLink
          v-for="p in activeProjects"
          :key="p.id"
          :to="`/app/projects/${p.id}`"
          class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 hover:shadow-sm hover:border-crystal-200 dark:hover:border-crystal-700 transition-all flex items-center gap-4 group"
        >
          <div class="w-10 h-10 rounded-lg bg-crystal-50 dark:bg-crystal-950 flex items-center justify-center flex-shrink-0 group-hover:bg-crystal-100 dark:hover:bg-crystal-900 transition-colors">
            <UIcon name="i-heroicons-folder-open" class="w-5 h-5 text-crystal-500" />
          </div>
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{{ p.name }}</p>
            <div class="flex items-center gap-3 text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              <span>{{ p.member_count }} 成员</span>
              <span>{{ p.issue_count }} Issues</span>
              <span v-if="p.estimated_completion">预计 {{ p.estimated_completion.slice(0, 10) }}</span>
            </div>
          </div>
          <UIcon name="i-heroicons-chevron-right" class="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-crystal-400 flex-shrink-0" />
        </NuxtLink>
      </div>

      <!-- Stat Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <DashboardStatCard label="总 Issue 数" :value="stats.total" icon="i-heroicons-bug-ant" icon-bg="bg-crystal-50 dark:bg-crystal-950" icon-color="text-crystal-500" />
        <DashboardStatCard label="待分配" :value="stats.pending" icon="i-heroicons-clock" icon-bg="bg-amber-50 dark:bg-amber-950" icon-color="text-amber-500" />
        <DashboardStatCard label="进行中" :value="stats.in_progress" icon="i-heroicons-arrow-path" icon-bg="bg-blue-50 dark:bg-blue-950" icon-color="text-blue-500" />
        <DashboardStatCard label="本周已解决" :value="stats.resolved_this_week" icon="i-heroicons-check-circle" icon-bg="bg-emerald-50 dark:bg-emerald-950" icon-color="text-emerald-500" />
      </div>

      <!-- Charts -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2 bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">30 日 Issue 趋势</h3>
          <ChartsLineChart
            :x-data="trendDates"
            :series="[
              { name: '新增', data: trendCreated },
              { name: '解决', data: trendResolved },
            ]"
            :height="280"
          />
        </div>
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">优先级分布</h3>
          <ChartsPieChart :data="pieData" :height="280" />
        </div>
      </div>

      <!-- Developer Leaderboard -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">开发者排行榜（本月解决数）</h3>
        <div v-if="topDevs.length" class="space-y-3">
          <div v-for="(dev, idx) in topDevs" :key="dev.user_id" class="flex items-center">
            <span class="w-6 text-sm font-medium" :class="idx < 3 ? 'text-crystal-500' : 'text-gray-400 dark:text-gray-500'">{{ idx + 1 }}</span>
            <div class="w-8 h-8 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center ml-2">
              <span class="text-crystal-600 dark:text-crystal-400 text-xs font-medium">{{ dev.user_name.slice(0, 1) }}</span>
            </div>
            <span class="ml-3 text-sm text-gray-700 dark:text-gray-300 flex-1">{{ dev.user_name }}</span>
            <span class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ dev.monthly_resolved_count }}</span>
          </div>
        </div>
        <div v-else class="text-sm text-gray-400 dark:text-gray-500">暂无数据</div>
      </div>

      <!-- Recent Activity -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">最近动态</h3>
        <div v-if="recentActivity.length" class="divide-y divide-gray-50 dark:divide-gray-800">
          <div v-for="item in recentActivity" :key="item.id" class="flex items-center py-3 first:pt-0 last:pb-0">
            <div class="w-8 h-8 rounded-lg bg-gray-50 dark:bg-gray-800 flex items-center justify-center flex-shrink-0">
              <UIcon :name="item.icon" class="w-4 h-4 text-gray-400 dark:text-gray-500" />
            </div>
            <span class="ml-3 text-sm text-gray-700 dark:text-gray-300 flex-1">{{ item.message }}</span>
            <span class="text-xs text-gray-400 dark:text-gray-500 ml-4 whitespace-nowrap">{{ item.time }}</span>
          </div>
        </div>
        <div v-else class="text-sm text-gray-400 dark:text-gray-500">暂无动态</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()

const loading = ref(true)
const stats = ref({ total: 0, pending: 0, in_progress: 0, resolved_this_week: 0 })
const trendDates = ref<string[]>([])
const trendCreated = ref<number[]>([])
const trendResolved = ref<number[]>([])
const pieData = ref<{ name: string; value: number }[]>([])
const topDevs = ref<any[]>([])
const recentActivity = ref<any[]>([])
const activeProjects = ref<any[]>([])

function activityIcon(action: string): string {
  switch (action) {
    case 'created': return 'i-heroicons-plus-circle'
    case 'resolved': return 'i-heroicons-check-circle'
    case 'status_changed': return 'i-heroicons-arrow-path'
    case 'assigned': return 'i-heroicons-user-plus'
    case 'priority_changed': return 'i-heroicons-flag'
    default: return 'i-heroicons-information-circle'
  }
}

function activityMessage(item: any): string {
  const name = item.user_name || '未知用户'
  const issueRef = item.issue_id ? `#${item.issue_id}` : ''
  switch (item.action) {
    case 'created': return `${name} 创建了问题 ${issueRef}${item.issue_title ? '「' + item.issue_title + '」' : ''}`
    case 'resolved': return `${name} 解决了问题 ${issueRef}${item.issue_title ? '「' + item.issue_title + '」' : ''}`
    case 'status_changed': return `${name} 更新了 ${issueRef} 的状态${item.detail ? '：' + item.detail : ''}`
    case 'assigned': return `${name} 分配了问题 ${issueRef}${item.detail ? '给 ' + item.detail : ''}`
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

onMounted(async () => {
  try {
    const [statsData, trendsData, priorityData, leaderboardData, activityData, projectsData] = await Promise.all([
      api<any>('/api/dashboard/stats/'),
      api<any[]>('/api/dashboard/trends/'),
      api<any[]>('/api/dashboard/priority-distribution/'),
      api<any[]>('/api/dashboard/developer-leaderboard/'),
      api<any[]>('/api/dashboard/recent-activity/'),
      api<any>('/api/projects/'),
    ])

    stats.value = {
      total: statsData.total ?? 0,
      pending: statsData.pending ?? 0,
      in_progress: statsData.in_progress ?? 0,
      resolved_this_week: statsData.resolved_this_week ?? 0,
    }

    trendDates.value = (trendsData || []).map((d: any) => d.date?.slice(5) || '')
    trendCreated.value = (trendsData || []).map((d: any) => d.created ?? 0)
    trendResolved.value = (trendsData || []).map((d: any) => d.resolved ?? 0)

    pieData.value = (priorityData || []).map((d: any) => ({
      name: d.priority,
      value: d.count,
    }))

    topDevs.value = [...(leaderboardData || [])]
      .sort((a: any, b: any) => (b.monthly_resolved_count ?? 0) - (a.monthly_resolved_count ?? 0))
      .slice(0, 5)

    recentActivity.value = (activityData || []).map((item: any) => ({
      id: item.id,
      icon: activityIcon(item.action),
      message: activityMessage(item),
      time: item.created_at ? timeAgo(item.created_at) : '',
    }))

    const projectResults = projectsData.results || projectsData || []
    activeProjects.value = projectResults.filter((p: any) => p.status === '进行中')
  } catch (e) {
    console.error('Failed to load dashboard data:', e)
  } finally {
    loading.value = false
  }
})
</script>
