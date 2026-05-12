<template>
  <div class="space-y-6">
    <!-- 头部 -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div class="flex items-baseline gap-3 flex-wrap">
        <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">KPI 分析</h1>
        <span class="text-sm text-gray-500 dark:text-gray-400">{{ period.label.value }}</span>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <!-- 周期选择 (← 周/月/季度 →) -->
        <div class="flex items-center gap-1">
          <UButton
            size="sm"
            variant="outline"
            color="neutral"
            icon="i-heroicons-chevron-left"
            :disabled="isCustom"
            :title="`上一${periodUnitLabel}`"
            @click="period.shift(-1)"
          />
          <UButtonGroup>
            <UButton
              v-for="p in periods"
              :key="p.value"
              size="sm"
              :variant="activePeriod === p.value ? 'solid' : 'outline'"
              :color="activePeriod === p.value ? 'primary' : 'neutral'"
              @click="period.setPeriod(p.value)"
            >
              {{ p.label }}
            </UButton>
          </UButtonGroup>
          <UButton
            size="sm"
            variant="outline"
            color="neutral"
            icon="i-heroicons-chevron-right"
            :disabled="isCustom || periodOffset >= 0"
            :title="`下一${periodUnitLabel}`"
            @click="period.shift(1)"
          />
        </div>

        <!-- 自定义日期 -->
        <UPopover>
          <UButton size="sm" variant="outline" color="neutral" icon="i-heroicons-calendar-days">
            {{ isCustom ? `${customStart} ~ ${customEnd}` : '自定义' }}
          </UButton>
          <template #content>
            <div class="p-3 space-y-3">
              <div class="space-y-1">
                <label class="text-xs text-gray-500 dark:text-gray-400">开始日期</label>
                <UInput v-model="customStart" type="date" size="sm" />
              </div>
              <div class="space-y-1">
                <label class="text-xs text-gray-500 dark:text-gray-400">结束日期</label>
                <UInput v-model="customEnd" type="date" size="sm" />
              </div>
              <UButton size="sm" block @click="applyCustomRange">应用</UButton>
            </div>
          </template>
        </UPopover>

        <!-- 角色筛选 -->
        <USelect
          v-model="selectedRole"
          :items="roleOptions"
          size="sm"
          class="w-32"
        />

        <!-- 刷新 -->
        <UButton
          size="sm"
          variant="outline"
          color="neutral"
          icon="i-heroicons-arrow-path"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新
        </UButton>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <template v-else-if="data">
      <!-- 汇总卡片 -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          v-for="card in summaryCards"
          :key="card.label"
          class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5"
        >
          <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ card.label }}</div>
          <div class="text-2xl font-bold text-gray-900 dark:text-gray-100">{{ card.value }}</div>
          <div v-if="card.sub" class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ card.sub }}</div>
        </div>
      </div>

      <!-- Code Arena 工作量统计 -->
      <div class="bg-gradient-to-r from-violet-50 via-crystal-50 to-amber-50 dark:from-violet-950/40 dark:via-crystal-950/40 dark:to-amber-950/40 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
        <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-trophy" class="w-5 h-5 text-amber-500" />
            <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">代码竞技场 · 本期赛况</h2>
          </div>
          <div class="text-xs text-gray-500 dark:text-gray-400">数据用于未来对接 AI 计件 / 段位 / 重修惩罚等机制</div>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div
            v-for="card in arenaCards"
            :key="card.label"
            class="bg-white/80 dark:bg-gray-900/60 backdrop-blur rounded-lg border border-gray-100 dark:border-gray-800 p-3"
          >
            <div class="text-xs text-gray-400 dark:text-gray-500">{{ card.label }}</div>
            <div class="text-xl font-bold mt-1" :class="card.colorClass">{{ card.value }}</div>
            <div v-if="card.sub" class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ card.sub }}</div>
          </div>
        </div>
      </div>

      <!-- 排名表格 -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
        <UTable
          :data="tableRows"
          :columns="columns"
          :ui="{ th: 'text-xs', td: 'text-sm', tr: 'hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-pointer' }"
          @select="onRowSelect"
        >
          <template #rank-cell="{ row }">
            <span
              class="inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold"
              :class="rankClass(r(row).rank)"
            >
              {{ r(row).rank }}
            </span>
          </template>
          <template #developer-cell="{ row }">
            <NuxtLink
              :to="`/app/kpi/${r(row).user_id}`"
              class="flex items-center gap-2 text-crystal-500 dark:text-crystal-400 hover:text-crystal-700 dark:hover:text-crystal-300 font-medium"
            >
              <img
                v-if="r(row).avatar"
                :src="resolveAvatarUrl(r(row).avatar)"
                class="w-6 h-6 rounded-full"
              />
              <div
                v-else
                class="w-6 h-6 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center text-xs font-semibold text-crystal-600 dark:text-crystal-400"
              >
                {{ (r(row).user_name || '?').slice(0, 1) }}
              </div>
              {{ r(row).user_name }}
            </NuxtLink>
          </template>
          <template #tier-cell="{ row }">
            <UBadge
              v-if="r(row).tier_label"
              :class="tierBadgeClass(r(row).tier_key)"
              variant="subtle"
              size="xs"
            >
              {{ r(row).tier_label }}
            </UBadge>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template #tickets-cell="{ row }">
            <span class="font-medium text-gray-900 dark:text-gray-100">{{ r(row).completed_count }}</span>
            <span v-if="r(row).large_count || r(row).medium_count" class="text-xs text-gray-400 ml-1">
              ({{ r(row).large_count }}大/{{ r(row).medium_count }}中)
            </span>
          </template>
          <template #earnings-cell="{ row }">
            <span class="text-emerald-600 dark:text-emerald-400 font-medium">¥{{ r(row).estimated_earnings }}</span>
          </template>
          <template #rework-cell="{ row }">
            <span :class="r(row).rework_count > 0 ? 'text-red-500 font-medium' : 'text-gray-400'">
              {{ r(row).rework_count }}
            </span>
          </template>
          <template #delay_hours-cell="{ row }">
            <span v-if="r(row).total_delay_hours > 0" class="text-red-500 font-medium">
              {{ r(row).total_delay_hours.toFixed(1) }}h
            </span>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template #delay-cell="{ row }">
            <span v-if="r(row).avg_delay_ratio" :class="delayCellClass(r(row).avg_delay_ratio)">
              {{ r(row).avg_delay_ratio.toFixed(2) }}×
            </span>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template #response-cell="{ row }">
            <span v-if="r(row).avg_first_response_hours" class="text-sm">
              {{ r(row).avg_first_response_hours.toFixed(1) }}h
            </span>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template #overall-cell="{ row }">
            <span class="font-semibold text-gray-900 dark:text-gray-100">{{ formatScore(r(row).overall) }}</span>
          </template>
          <template #efficiency-cell="{ row }">
            {{ formatScore(r(row).efficiency) }}
          </template>
          <template #output-cell="{ row }">
            {{ formatScore(r(row).output) }}
          </template>
          <template #quality-cell="{ row }">
            {{ formatScore(r(row).quality) }}
          </template>
          <template #capability-cell="{ row }">
            {{ formatScore(r(row).capability) }}
          </template>
          <template #growth-cell="{ row }">
            {{ formatScore(r(row).growth) }}
          </template>
          <template #trend-cell="{ row }">
            <span v-if="r(row).trend > 0" class="text-emerald-500">+{{ r(row).trend.toFixed(1) }}</span>
            <span v-else-if="r(row).trend < 0" class="text-red-500">{{ r(row).trend.toFixed(1) }}</span>
            <span v-else class="text-gray-400">-</span>
          </template>
        </UTable>
        <div class="flex items-center justify-between px-4 py-3 border-t border-gray-50 dark:border-gray-800">
          <span class="text-xs text-gray-400 dark:text-gray-500">共 {{ tableRows.length }} 位开发者</span>
        </div>
      </div>
    </template>

    <!-- 无数据 -->
    <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center">
      <UIcon name="i-heroicons-chart-bar" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
      <p class="text-gray-500 dark:text-gray-400">暂无 KPI 数据</p>
      <UButton class="mt-4" size="sm" @click="handleRefresh">立即生成</UButton>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const { resolveAvatarUrl } = useAvatars()
const toast = useToast()

const loading = ref(true)
const refreshing = ref(false)
const data = ref<any>(null)
const selectedRole = ref('开发者')

const period = usePeriodRange('month')
const { activePeriod, customStart, customEnd, isCustom, periodOffset } = period

const periods = [
  { label: '周', value: 'week' as const },
  { label: '月', value: 'month' as const },
  { label: '季度', value: 'quarter' as const },
]

const periodUnitLabel = computed(() => {
  if (activePeriod.value === 'week') return '周'
  if (activePeriod.value === 'quarter') return '季度'
  return '月'
})

const roleOptions = [
  { label: '开发者', value: '开发者' },
  { label: '全部', value: '' },
]

const columns = [
  { accessorKey: 'rank', header: '排名' },
  { accessorKey: 'developer', header: '开发者' },
  { accessorKey: 'tier', header: '段位' },
  { accessorKey: 'tickets', header: '完成工单' },
  { accessorKey: 'earnings', header: '估算收入' },
  { accessorKey: 'rework', header: '重修' },
  { accessorKey: 'delay_hours', header: '延期(h)' },
  { accessorKey: 'delay', header: '倍数' },
  { accessorKey: 'response', header: '首响' },
  { accessorKey: 'overall', header: '综合分' },
  { accessorKey: 'efficiency', header: '效率' },
  { accessorKey: 'output', header: '产出' },
  { accessorKey: 'quality', header: '质量' },
  { accessorKey: 'capability', header: '能力' },
  { accessorKey: 'growth', header: '成长' },
  { accessorKey: 'trend', header: '趋势' },
]

interface SummaryCard {
  label: string
  value: string | number
  sub?: string
}

const summaryCards = computed<SummaryCard[]>(() => {
  if (!data.value?.summary) return []
  const s = data.value.summary
  return [
    { label: '活跃人数', value: s.active_count ?? 0 },
    { label: '已解决问题', value: s.resolved_count ?? 0 },
    { label: '平均解决时间', value: s.avg_resolution_hours != null ? `${s.avg_resolution_hours.toFixed(1)}h` : '-' },
    { label: '团队综合分', value: s.avg_overall_score != null ? s.avg_overall_score.toFixed(1) : '-' },
  ]
})

const arenaCards = computed(() => {
  if (!data.value?.summary) return []
  const s = data.value.summary
  return [
    {
      label: '本期工单总量',
      value: s.total_tickets ?? 0,
      colorClass: 'text-violet-600 dark:text-violet-400',
      sub: '所有完成工单数',
    },
    {
      label: '估算计件总额',
      value: `¥${s.total_earnings ?? 0}`,
      colorClass: 'text-emerald-600 dark:text-emerald-400',
      sub: '按梯度+工时分级',
    },
    {
      label: '保护期重修',
      value: s.total_rework ?? 0,
      colorClass: (s.total_rework ?? 0) > 0 ? 'text-red-500' : 'text-gray-700 dark:text-gray-300',
      sub: '关联惩罚候选',
    },
    {
      label: '最高段位',
      value: s.top_tier?.label ?? '-',
      colorClass: 'text-amber-600 dark:text-amber-400',
      sub: s.top_tier?.threshold != null ? `≥ ${s.top_tier.threshold} 分` : undefined,
    },
  ]
})

interface TableRow {
  user_id: number
  user_name: string
  avatar: string
  rank: number
  overall: number
  efficiency: number
  output: number
  quality: number
  capability: number
  growth: number
  trend: number
  tier_key: string
  tier_label: string
  completed_count: number
  medium_count: number
  large_count: number
  estimated_earnings: number
  rework_count: number
  avg_delay_ratio: number
  total_delay_hours: number
  avg_first_response_hours: number
}

const tableRows = computed<TableRow[]>(() => {
  if (!data.value?.developers) return []
  return data.value.developers.map((d: any, i: number) => ({
    user_id: d.user_id,
    user_name: d.user_name ?? '',
    avatar: d.avatar ?? '',
    rank: d.rankings?.overall_rank ?? i + 1,
    overall: d.scores?.overall ?? 0,
    efficiency: d.scores?.efficiency ?? 0,
    output: d.scores?.output ?? 0,
    quality: d.scores?.quality ?? 0,
    capability: d.scores?.capability ?? 0,
    growth: d.scores?.growth ?? 0,
    trend: d.scores?.trend_delta ?? 0,
    tier_key: d.scores?.tier?.key ?? '',
    tier_label: d.scores?.tier?.label ?? '',
    completed_count: d.workload?.completed_count ?? 0,
    medium_count: d.workload?.medium_count ?? 0,
    large_count: d.workload?.large_count ?? 0,
    estimated_earnings: d.workload?.estimated_earnings ?? 0,
    rework_count: d.workload?.rework_count ?? 0,
    avg_delay_ratio: d.workload?.avg_delay_ratio ?? 0,
    total_delay_hours: d.workload?.total_delay_hours ?? 0,
    avg_first_response_hours: d.workload?.avg_first_response_hours ?? 0,
  }))
})

function delayCellClass(ratio: number) {
  if (ratio > 1.5) return 'text-red-500 font-medium'
  if (ratio > 1.1) return 'text-amber-500'
  if (ratio < 0.9 && ratio > 0) return 'text-emerald-500'
  return ''
}

function tierBadgeClass(key: string) {
  const map: Record<string, string> = {
    bronze: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
    silver: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
    gold: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    platinum: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
    diamond: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
    master: 'bg-gradient-to-r from-violet-200 to-pink-200 text-violet-800 dark:from-violet-900/60 dark:to-pink-900/60 dark:text-violet-200',
  }
  return map[key] || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'
}

function formatScore(v: any) {
  return v != null ? Number(v).toFixed(1) : '-'
}

function r(row: any): TableRow {
  return row.original as TableRow
}

function onRowSelect(row: any, e?: Event) {
  if (!e) return
  const target = e.target as HTMLElement
  if (target.closest('a, button, input')) return
  navigateTo(`/app/kpi/${r(row).user_id}`)
}

function rankClass(rank: number) {
  if (rank === 1) return 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300'
  if (rank === 2) return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
  if (rank === 3) return 'bg-orange-100 text-orange-600 dark:bg-orange-900 dark:text-orange-300'
  return 'text-gray-400 dark:text-gray-500'
}

function buildQuery() {
  return period.toQuery(selectedRole.value ? { role: selectedRole.value } : undefined)
}

function applyCustomRange() {
  period.applyCustom()
  fetchData()
}

async function fetchData() {
  loading.value = true
  try {
    data.value = await api<any>(`/api/kpi/team/?${buildQuery()}`)
  } catch (e: any) {
    console.error('Failed to load KPI data:', e)
    data.value = null
  } finally {
    loading.value = false
  }
}

async function handleRefresh() {
  refreshing.value = true
  try {
    await api('/api/kpi/refresh/', { method: 'POST' })
    toast.add({ title: 'KPI 数据已刷新', color: 'success' })
    await fetchData()
  } catch (e: any) {
    toast.add({ title: '刷新失败', description: e?.data?.detail || e?.response?._data?.detail || '请稍后重试', color: 'error' })
  } finally {
    refreshing.value = false
  }
}

watch([activePeriod, periodOffset, selectedRole], () => {
  fetchData()
})

onMounted(fetchData)
</script>
