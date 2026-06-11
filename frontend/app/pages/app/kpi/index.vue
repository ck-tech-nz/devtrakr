<template>
  <div class="space-y-6">
    <!-- 头部 -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div class="flex items-baseline gap-3 flex-wrap">
        <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">KPI 分析</h1>
        <span class="text-sm text-gray-500 dark:text-gray-400">{{ period.label.value }}</span>
        <span v-if="data?.summary" class="text-sm text-gray-500 dark:text-gray-400 flex items-baseline gap-3">
          <span>·</span>
          <span>活跃 <strong class="text-gray-800 dark:text-gray-100 font-semibold tabular-nums">{{ data.summary.active_count ?? 0 }}</strong> 人</span>
          <span>综合分 <strong class="text-gray-800 dark:text-gray-100 font-semibold tabular-nums">{{ data.summary.avg_overall_score != null ? Number(data.summary.avg_overall_score).toFixed(1) : '-' }}</strong></span>
        </span>
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

        <!-- 自定义日期 (兼显示当前区间) -->
        <UPopover v-model:open="popoverOpen">
          <UButton size="sm" variant="outline" color="neutral" icon="i-heroicons-calendar-days" :title="isCustom ? '自定义区间' : '点击自定义区间'">
            {{ range.start }} ~ {{ range.end }}
          </UButton>
          <template #content>
            <div class="p-3 space-y-3">
              <div class="space-y-1">
                <label class="text-xs text-gray-500 dark:text-gray-400">开始日期</label>
                <UInput v-model="draftStart" type="date" size="sm" />
              </div>
              <div class="space-y-1">
                <label class="text-xs text-gray-500 dark:text-gray-400">结束日期</label>
                <UInput v-model="draftEnd" type="date" size="sm" />
              </div>
              <UButton size="sm" block @click="applyCustomRange">应用</UButton>
            </div>
          </template>
        </UPopover>

        <!-- 角色筛选 -->
        <USelect
          :model-value="selectedRole || '_all'"
          :items="roleOptions"
          size="sm"
          class="w-32"
          @update:model-value="(v: string) => selectedRole = v === '_all' ? '' : v"
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
      <!-- 效能洞察 -->
      <section class="space-y-4">
        <!-- 趋势曲线 -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 relative overflow-hidden">
          <div class="absolute -top-32 -right-32 w-[28rem] h-[28rem] bg-gradient-to-br from-crystal-200/40 via-crystal-100/20 to-transparent dark:from-crystal-900/30 dark:via-crystal-900/10 rounded-full blur-3xl pointer-events-none" />
          <div class="relative">
            <div class="flex items-start justify-between mb-5 flex-wrap gap-3">
              <div>
                <div class="flex items-center gap-2">
                  <UIcon name="i-heroicons-chart-bar-square" class="w-5 h-5 text-crystal-500" />
                  <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">问题解决趋势</h2>
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ trendWindowLabel }} · 按{{ granularityLabel }}统计</div>
              </div>
              <UButtonGroup>
                <UButton
                  v-for="g in granularityOptions"
                  :key="g.value"
                  size="xs"
                  :variant="granularity === g.value ? 'solid' : 'outline'"
                  :color="granularity === g.value ? 'primary' : 'neutral'"
                  :loading="trendLoading && granularity === g.value"
                  @click="granularity = g.value"
                >
                  {{ g.label }}
                </UButton>
              </UButtonGroup>
            </div>
            <div class="grid grid-cols-3 gap-6 mb-5">
              <div>
                <div class="text-[11px] uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-1">累计解决</div>
                <div class="text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">{{ trendStats.total }}</div>
              </div>
              <div>
                <div class="text-[11px] uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-1">{{ granularityLabel }}均值</div>
                <div class="text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">{{ trendStats.avg }}</div>
              </div>
              <div>
                <div class="text-[11px] uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-1">峰值</div>
                <div class="text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">
                  {{ trendStats.peak }}
                  <span v-if="trendStats.peakLabel" class="text-xs text-gray-400 font-normal ml-1">{{ trendStats.peakLabel }}</span>
                </div>
              </div>
            </div>
            <ChartsLineChart :x-data="trendChart.xData" :series="trendChart.series" :height="240" />
          </div>
        </div>

        <!-- 两列: 耗时分布 + 开发者对比 -->
        <div class="grid grid-cols-1 lg:grid-cols-5 gap-4">
          <!-- 耗时分布 -->
          <div class="lg:col-span-2 bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
            <div class="flex items-center gap-2 mb-1">
              <UIcon name="i-heroicons-clock" class="w-5 h-5 text-amber-500" />
              <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">解决耗时分布</h2>
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-5">从创建到解决的时长分布</div>

            <div class="flex items-baseline gap-2 mb-6">
              <div class="text-3xl font-bold tabular-nums text-gray-900 dark:text-gray-100">{{ avgResolutionDisplay }}</div>
              <div class="text-sm text-gray-500 dark:text-gray-400">小时 · 团队平均</div>
            </div>

            <div class="space-y-3">
              <div
                v-for="b in distributionBuckets"
                :key="b.key"
                class="flex items-center gap-3 text-xs"
              >
                <div class="w-14 text-gray-500 dark:text-gray-400 tabular-nums">{{ b.label }}</div>
                <div class="flex-1 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-500 ease-out"
                    :style="{ width: b.pct + '%', background: b.color }"
                  />
                </div>
                <div class="w-8 text-right tabular-nums font-medium text-gray-900 dark:text-gray-100">{{ b.count }}</div>
              </div>
              <div v-if="totalDistribution === 0" class="text-center text-xs text-gray-400 py-4">本周期暂无已解决问题</div>
            </div>
          </div>

          <!-- 开发者效能对比 -->
          <div class="lg:col-span-3 bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
            <div class="flex items-center justify-between mb-1 flex-wrap gap-2">
              <div class="flex items-center gap-2">
                <UIcon name="i-heroicons-user-group" class="w-5 h-5 text-crystal-500" />
                <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">开发者效能对比</h2>
              </div>
              <div class="text-[11px] text-gray-400 dark:text-gray-500">解决数 × 平均耗时</div>
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mb-5">仅显示本周期有解决记录的成员</div>

            <div class="space-y-3">
              <div
                v-for="dev in developerComparison"
                :key="dev.user_id"
                class="grid grid-cols-12 items-center gap-3 text-sm"
              >
                <NuxtLink
                  :to="`/app/kpi/${dev.user_id}`"
                  class="col-span-3 flex items-center gap-2 min-w-0 hover:text-crystal-600 dark:hover:text-crystal-400"
                >
                  <img
                    v-if="dev.avatar"
                    :src="resolveAvatarUrl(dev.avatar)"
                    class="w-6 h-6 rounded-full flex-shrink-0"
                  />
                  <div
                    v-else
                    class="w-6 h-6 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center text-xs font-semibold text-crystal-600 dark:text-crystal-400 flex-shrink-0"
                  >
                    {{ (dev.user_name || '?').slice(0, 1) }}
                  </div>
                  <span class="truncate text-gray-700 dark:text-gray-200">{{ dev.user_name }}</span>
                </NuxtLink>
                <div class="col-span-7 flex items-center gap-2">
                  <div class="flex-1 h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                    <div
                      class="h-full rounded-full transition-all duration-500 ease-out"
                      :style="{
                        width: dev.countPct + '%',
                        background: 'linear-gradient(90deg, #8b5cf6, #c4b5fd)',
                      }"
                    />
                  </div>
                  <span class="text-xs tabular-nums w-8 text-right font-medium text-gray-900 dark:text-gray-100">{{ dev.resolved_count }}</span>
                </div>
                <div class="col-span-2 text-right text-xs tabular-nums">
                  <span v-if="dev.avg_resolution_hours" class="text-gray-500 dark:text-gray-400">{{ dev.avg_resolution_hours.toFixed(1) }}h</span>
                  <span v-else class="text-gray-300 dark:text-gray-600">—</span>
                </div>
              </div>
              <div v-if="developerComparison.length === 0" class="text-center text-xs text-gray-400 py-4">本周期暂无解决记录</div>
            </div>
          </div>
        </div>
      </section>

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
          <component
            :is="card.to ? 'NuxtLink' : 'div'"
            v-for="card in arenaCards"
            :key="card.label"
            :to="card.to"
            class="bg-white/80 dark:bg-gray-900/60 backdrop-blur rounded-lg border border-gray-100 dark:border-gray-800 p-3 block"
            :class="card.to && 'hover:border-amber-300 dark:hover:border-amber-700 transition-colors'"
          >
            <div class="text-xs text-gray-400 dark:text-gray-500">{{ card.label }}</div>
            <div class="text-xl font-bold mt-1" :class="card.colorClass">{{ card.value }}</div>
            <div v-if="card.subUser" class="flex items-center gap-1.5 mt-1">
              <img
                v-if="card.subUser.avatar"
                :src="resolveAvatarUrl(card.subUser.avatar)"
                class="w-4 h-4 rounded-full"
              />
              <div
                v-else
                class="w-4 h-4 rounded-full bg-amber-100 dark:bg-amber-900 flex items-center justify-center text-[10px] font-semibold text-amber-700 dark:text-amber-300"
              >
                {{ (card.subUser.user_name || '?').slice(0, 1) }}
              </div>
              <span class="text-xs text-gray-700 dark:text-gray-200 font-medium truncate">{{ card.subUser.user_name }}</span>
              <span class="text-xs text-gray-400 tabular-nums">{{ Number(card.subUser.overall).toFixed(1) }}</span>
            </div>
            <div v-else-if="card.sub" class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ card.sub }}</div>
          </component>
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
            <span class="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
              <UIcon name="i-heroicons-banknotes" class="w-3.5 h-3.5" />
              <span class="tabular-nums">{{ r(row).estimated_earnings }}</span>
            </span>
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
const { activePeriod, customStart, customEnd, isCustom, periodOffset, range } = period

const periods = [
  { label: '周', value: 'week' as const },
  { label: '月', value: 'month' as const },
  { label: '季度', value: 'quarter' as const },
  { label: '年', value: 'year' as const },
]

const periodUnitLabel = computed(() => {
  if (activePeriod.value === 'week') return '周'
  if (activePeriod.value === 'quarter') return '季度'
  if (activePeriod.value === 'year') return '年'
  return '月'
})

// 自定义日期弹窗:本地草稿,打开时用当前区间预填,点"应用"才写入 period
const popoverOpen = ref(false)
const draftStart = ref('')
const draftEnd = ref('')
watch(popoverOpen, (open) => {
  if (open) {
    draftStart.value = customStart.value || range.value.start
    draftEnd.value = customEnd.value || range.value.end
  }
})

// SelectItem 不允许空字符串 value，「全部」用 '_all' 哨兵在模板里映射回 ''
const roleOptions = [
  { label: '开发者', value: '开发者' },
  { label: '全部', value: '_all' },
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
      subUser: s.top_tier_user ?? undefined,
      sub: s.top_tier_user ? undefined : (s.top_tier?.threshold != null ? `≥ ${s.top_tier.threshold} 分` : undefined),
      to: s.top_tier_user?.user_id ? `/app/kpi/${s.top_tier_user.user_id}` : undefined,
    },
  ]
})

// ---------- 效能洞察 ----------
type Granularity = 'day' | 'week' | 'month'

const granularity = ref<Granularity>('week')
const trendData = ref<any>(null)
const trendLoading = ref(false)

const granularityOptions: { label: string; value: Granularity }[] = [
  { label: '日', value: 'day' },
  { label: '周', value: 'week' },
  { label: '月', value: 'month' },
]

const granularityLabel = computed(() => {
  return granularity.value === 'day' ? '日' : granularity.value === 'week' ? '周' : '月'
})

const trendWindowLabel = computed(() => {
  if (granularity.value === 'day') return '最近 30 天'
  if (granularity.value === 'week') return '最近 12 周'
  return '最近 12 个月'
})

interface TrendBucket {
  key: string
  label: string
  resolved: number
}

const trendChart = computed(() => {
  const buckets = (trendData.value?.buckets as TrendBucket[] | undefined) || []
  return {
    xData: buckets.map((b) => b.label),
    series: [{ name: '已解决', data: buckets.map((b) => b.resolved) }],
  }
})

async function fetchTrend() {
  trendLoading.value = true
  try {
    const params = new URLSearchParams({ granularity: granularity.value })
    if (selectedRole.value) params.set('role', selectedRole.value)
    params.set('anchor', range.value.end)
    trendData.value = await api<any>(`/api/kpi/team/trend/?${params.toString()}`)
  } catch (e) {
    console.error('Failed to load trend data', e)
    trendData.value = null
  } finally {
    trendLoading.value = false
  }
}

watch(granularity, fetchTrend)
watch([() => range.value.end, selectedRole], fetchTrend)
onMounted(fetchTrend)

const trendStats = computed(() => {
  const xs = trendChart.value.xData
  const ys = trendChart.value.series[0]?.data || []
  if (ys.length === 0) return { total: 0, avg: '0', peak: 0, peakLabel: '' }
  const total = ys.reduce((a, b) => a + b, 0)
  const avg = (total / ys.length).toFixed(1)
  let peakIdx = 0
  for (let i = 1; i < ys.length; i++) {
    if ((ys[i] ?? 0) > (ys[peakIdx] ?? 0)) peakIdx = i
  }
  return {
    total,
    avg,
    peak: ys[peakIdx] ?? 0,
    peakLabel: (ys[peakIdx] ?? 0) > 0 ? (xs[peakIdx] || '') : '',
  }
})

const avgResolutionDisplay = computed(() => {
  const v = data.value?.summary?.avg_resolution_hours
  return v != null ? Number(v).toFixed(1) : '—'
})

const distributionBuckets = computed(() => {
  const raw = (data.value?.summary?.resolution_buckets || {}) as Record<string, number>
  const defs: { key: string; label: string; color: string }[] = [
    { key: 'lt4h', label: '< 4h', color: '#10b981' },
    { key: 'h4_8', label: '4-8h', color: '#22d3ee' },
    { key: 'h8_24', label: '8-24h', color: '#8b5cf6' },
    { key: 'd1_3', label: '1-3天', color: '#f59e0b' },
    { key: 'gt3d', label: '> 3天', color: '#ef4444' },
  ]
  const total = defs.reduce((sum, d) => sum + (raw[d.key] || 0), 0)
  const max = Math.max(1, ...defs.map((d) => raw[d.key] || 0))
  return defs.map((d) => ({
    ...d,
    count: raw[d.key] || 0,
    pct: total > 0 ? ((raw[d.key] || 0) / max) * 100 : 0,
  }))
})

const totalDistribution = computed(() =>
  distributionBuckets.value.reduce((sum, b) => sum + b.count, 0)
)

interface DevComparison {
  user_id: number
  user_name: string
  avatar: string
  resolved_count: number
  avg_resolution_hours: number
  countPct: number
}

const developerComparison = computed<DevComparison[]>(() => {
  const devs = (data.value?.developers || []) as any[]
  const items = devs
    .map((d) => ({
      user_id: d.user_id,
      user_name: d.user_name || '',
      avatar: d.avatar || '',
      resolved_count: d.issue_summary?.resolved_count || 0,
      avg_resolution_hours: d.issue_summary?.avg_resolution_hours || 0,
    }))
    .filter((d) => d.resolved_count > 0)
    .sort((a, b) => b.resolved_count - a.resolved_count)
  const max = Math.max(1, ...items.map((i) => i.resolved_count))
  return items.map((i) => ({ ...i, countPct: (i.resolved_count / max) * 100 }))
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
  if (!draftStart.value || !draftEnd.value) return
  customStart.value = draftStart.value
  customEnd.value = draftEnd.value
  period.applyCustom()
  popoverOpen.value = false
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
