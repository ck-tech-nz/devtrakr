<template>
  <div class="space-y-6">
    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <template v-else-if="summary">
      <!-- 个人 Hero 卡片 -->
      <div class="relative overflow-hidden rounded-xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900">
        <!-- 顶部段位色带 -->
        <div class="h-1.5 w-full" :class="tierStripClass(summary.scores?.tier?.key)" />
        <!-- 背景光斑 -->
        <div class="absolute -top-24 -right-24 w-96 h-96 bg-gradient-to-br from-crystal-200/30 via-amber-100/20 to-transparent dark:from-crystal-900/30 dark:via-amber-900/10 rounded-full blur-3xl pointer-events-none" />
        <div class="relative p-6">
          <div class="flex items-center gap-5 flex-wrap">
            <div class="relative">
              <img
                v-if="summary.avatar"
                :src="resolveAvatarUrl(summary.avatar)"
                class="w-20 h-20 rounded-full ring-4 ring-white dark:ring-gray-900 shadow-md"
              />
              <div
                v-else
                class="w-20 h-20 rounded-full bg-crystal-100 dark:bg-crystal-900 ring-4 ring-white dark:ring-gray-900 shadow-md flex items-center justify-center text-2xl font-semibold text-crystal-600 dark:text-crystal-400"
              >
                {{ (summary.user_name || '?').slice(0, 1) }}
              </div>
              <div
                v-if="summary.scores?.tier?.key"
                class="absolute -bottom-1 -right-1 w-7 h-7 rounded-full flex items-center justify-center shadow"
                :class="tierBadgeBgClass(summary.scores.tier.key)"
              >
                <UIcon name="i-heroicons-trophy" class="w-4 h-4 text-white" />
              </div>
            </div>

            <div class="flex-1 min-w-0">
              <div class="flex items-baseline gap-2 flex-wrap">
                <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">{{ summary.user_name }}</h1>
                <span class="text-sm text-gray-500 dark:text-gray-400">的 KPI · {{ period.label.value }}</span>
              </div>
              <div class="flex gap-1.5 mt-2 flex-wrap items-center">
                <UBadge
                  v-for="g in (summary.groups || [])"
                  :key="g"
                  color="neutral"
                  variant="subtle"
                  size="xs"
                >
                  {{ g }}
                </UBadge>
                <UBadge
                  v-if="summary.scores?.tier?.label"
                  :class="tierBadgeClass(summary.scores.tier.key)"
                  variant="subtle"
                  size="xs"
                >
                  <UIcon name="i-heroicons-trophy" class="w-3 h-3 mr-0.5" />
                  {{ summary.scores.tier.label }}
                </UBadge>
              </div>
              <div class="flex items-center gap-3 mt-3 flex-wrap text-sm">
                <NuxtLink
                  v-if="canViewTeam"
                  :to="`/app/kpi/${summary.user_id}`"
                  class="inline-flex items-center gap-1 text-crystal-600 dark:text-crystal-400 hover:underline"
                >
                  详细报告 <UIcon name="i-heroicons-arrow-top-right-on-square" class="w-3.5 h-3.5" />
                </NuxtLink>
                <NuxtLink
                  v-if="can('kpi.view_own_plan')"
                  to="/app/ai/my-plan"
                  class="inline-flex items-center gap-1 text-crystal-600 dark:text-crystal-400 hover:underline"
                >
                  我的提升计划 <UIcon name="i-heroicons-arrow-top-right-on-square" class="w-3.5 h-3.5" />
                </NuxtLink>
              </div>
            </div>

            <div class="text-right">
              <div class="text-[11px] uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-1">综合评分</div>
              <div class="flex items-baseline justify-end gap-2">
                <div class="text-5xl font-bold tabular-nums bg-gradient-to-br from-crystal-500 to-violet-500 bg-clip-text text-transparent">
                  {{ summary.scores?.overall != null ? Number(summary.scores.overall).toFixed(1) : '-' }}
                </div>
                <div v-if="trendDelta != null" class="text-sm tabular-nums" :class="trendDeltaClass">
                  {{ trendDelta > 0 ? '↑' : trendDelta < 0 ? '↓' : '—' }} {{ Math.abs(trendDelta).toFixed(1) }}
                </div>
              </div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">较上期</div>
            </div>
          </div>

          <!-- 段位进度 -->
          <div v-if="summary.scores?.tier" class="mt-5 pt-5 border-t border-gray-100 dark:border-gray-800">
            <div class="flex items-center justify-between text-xs mb-2">
              <span class="text-gray-500 dark:text-gray-400">
                当前 <strong class="text-gray-800 dark:text-gray-100 font-medium">{{ summary.scores.tier.label }}</strong>
                <span v-if="summary.scores.tier.next_label">
                  · 距 <strong class="text-gray-800 dark:text-gray-100 font-medium">{{ summary.scores.tier.next_label }}</strong>
                  还差 <strong class="text-amber-600 dark:text-amber-400 font-medium tabular-nums">{{ tierGap }}</strong> 分
                </span>
                <span v-else class="text-amber-600 dark:text-amber-400">已抵达最高段位 🎉</span>
              </span>
              <span class="text-gray-400 tabular-nums">{{ Number(summary.scores.overall ?? 0).toFixed(0) }} / {{ summary.scores.tier.next_threshold ?? 100 }}</span>
            </div>
            <div class="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
              <div
                class="h-full transition-all duration-700 ease-out"
                :class="tierStripClass(summary.scores.tier.key)"
                :style="{ width: tierProgressPct + '%' }"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 周期选择 -->
      <div class="flex items-center gap-2 flex-wrap">
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
      </div>

      <!-- 我的解决趋势 -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 relative overflow-hidden">
        <div class="absolute -top-32 -right-32 w-[28rem] h-[28rem] bg-gradient-to-br from-crystal-200/40 via-crystal-100/20 to-transparent dark:from-crystal-900/30 dark:via-crystal-900/10 rounded-full blur-3xl pointer-events-none" />
        <div class="relative">
          <div class="flex items-start justify-between mb-5 flex-wrap gap-3">
            <div>
              <div class="flex items-center gap-2">
                <UIcon name="i-heroicons-chart-bar-square" class="w-5 h-5 text-crystal-500" />
                <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">我的解决趋势</h2>
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

      <!-- 两列: 耗时分布 + 能力雷达 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- 我的耗时分布 -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
          <div class="flex items-center gap-2 mb-1">
            <UIcon name="i-heroicons-clock" class="w-5 h-5 text-amber-500" />
            <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">我的耗时分布</h2>
          </div>
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-5">本期工单从创建到解决的时长</div>

          <div class="flex items-baseline gap-2 mb-6">
            <div class="text-3xl font-bold tabular-nums text-gray-900 dark:text-gray-100">{{ avgResolutionDisplay }}</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">小时 · 我的平均</div>
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

        <!-- 能力雷达 -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
          <div class="flex items-center gap-2 mb-1">
            <UIcon name="i-heroicons-sparkles" class="w-5 h-5 text-violet-500" />
            <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">能力雷达</h2>
          </div>
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-3">5 维评分,满分 100</div>
          <ChartsRadarChart
            :indicators="radarIndicators"
            :values="radarValues"
            :height="280"
          />
        </div>
      </div>

      <!-- 代码竞技场: 我的本期成绩 -->
      <div class="bg-gradient-to-r from-violet-50 via-crystal-50 to-amber-50 dark:from-violet-950/40 dark:via-crystal-950/40 dark:to-amber-950/40 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
        <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-trophy" class="w-5 h-5 text-amber-500" />
            <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">本期成绩</h2>
          </div>
          <div class="text-xs text-gray-500 dark:text-gray-400">{{ period.label.value }}</div>
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

      <!-- 最近完成工单 -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
        <div class="px-5 py-3 border-b border-gray-50 dark:border-gray-800 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-document-text" class="w-5 h-5 text-emerald-500" />
            <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">最近完成工单</h2>
          </div>
          <span v-if="recentBreakdown.length" class="text-xs text-gray-400">显示前 {{ recentBreakdown.length }} 条</span>
        </div>
        <div v-if="recentBreakdown.length" class="divide-y divide-gray-50 dark:divide-gray-800">
          <NuxtLink
            v-for="b in recentBreakdown"
            :key="b.issue_id"
            :to="`/app/issues/${b.issue_id}`"
            class="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
          >
            <span class="text-xs font-mono text-gray-400 tabular-nums w-16 flex-shrink-0">ISS-{{ String(b.issue_id).padStart(3, '0') }}</span>
            <UBadge :class="sizeBadgeClass(b.size)" variant="subtle" size="xs" class="flex-shrink-0">{{ b.size }}</UBadge>
            <span class="text-sm text-gray-900 dark:text-gray-100 truncate flex-1">{{ b.title }}</span>
            <span v-if="b.actual_hours != null" class="text-xs text-gray-500 dark:text-gray-400 tabular-nums flex-shrink-0">{{ Number(b.actual_hours).toFixed(1) }}h</span>
            <span class="text-xs text-emerald-600 dark:text-emerald-400 font-medium tabular-nums flex-shrink-0 w-12 text-right">¥{{ b.price }}</span>
          </NuxtLink>
        </div>
        <div v-else class="px-5 py-12 text-center text-sm text-gray-400">本期暂无完成工单</div>
      </div>

      <!-- 改进建议 -->
      <div v-if="suggestionItems.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
        <div class="flex items-center gap-2 mb-3">
          <UIcon name="i-heroicons-light-bulb" class="w-5 h-5 text-amber-500" />
          <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">改进建议</h2>
          <span v-if="suggestions?.profile" class="text-xs text-gray-500 dark:text-gray-400">· {{ suggestions.profile }}</span>
        </div>
        <div class="space-y-2.5">
          <div
            v-for="(s, i) in suggestionItems"
            :key="i"
            class="flex items-start gap-3 text-sm"
          >
            <div class="w-1.5 h-1.5 rounded-full bg-amber-400 mt-2 flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="text-gray-900 dark:text-gray-100">{{ s.title }}</div>
              <div v-if="s.detail" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ s.detail }}</div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 无数据 -->
    <div
      v-else
      class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center"
    >
      <UIcon name="i-heroicons-chart-bar" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
      <p class="text-gray-500 dark:text-gray-400">暂无 KPI 数据</p>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const { resolveAvatarUrl } = useAvatars()
const { can } = useAuth()

const canViewTeam = computed(() => can('kpi.view_kpisnapshot'))

const loading = ref(true)
const summary = ref<any>(null)
const workload = ref<any>(null)
const issues = ref<any>(null)
const suggestions = ref<any>(null)
const trendsHistory = ref<any[]>([])

const period = usePeriodRange('month')
const { activePeriod, isCustom, periodOffset, range } = period

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

// ---------- 趋势图 (独立滚动窗口) ----------
type Granularity = 'day' | 'week' | 'month'

const granularity = ref<Granularity>('week')
const trendData = ref<any>(null)
const trendLoading = ref(false)

const granularityOptions: { label: string; value: Granularity }[] = [
  { label: '日', value: 'day' },
  { label: '周', value: 'week' },
  { label: '月', value: 'month' },
]

const granularityLabel = computed(() =>
  granularity.value === 'day' ? '日' : granularity.value === 'week' ? '周' : '月'
)

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

async function fetchTrend() {
  trendLoading.value = true
  try {
    const params = new URLSearchParams({ granularity: granularity.value })
    params.set('anchor', range.value.end)
    trendData.value = await api<any>(`/api/kpi/me/resolution-trend/?${params.toString()}`)
  } catch (e) {
    console.error('Failed to load trend', e)
    trendData.value = null
  } finally {
    trendLoading.value = false
  }
}

// ---------- 主数据 ----------
function buildQuery() {
  return period.toQuery()
}

async function fetchAll() {
  loading.value = true
  try {
    const q = buildQuery()
    const [s, w, i, sg, th] = await Promise.all([
      api<any>(`/api/kpi/me/summary/?${q}`).catch(() => null),
      api<any>(`/api/kpi/me/workload/?${q}`).catch(() => null),
      api<any>(`/api/kpi/me/issues/?${q}`).catch(() => null),
      api<any>(`/api/kpi/me/suggestions/?${q}`).catch(() => null),
      api<any>(`/api/kpi/me/trends/?limit=2`).catch(() => []),
    ])
    summary.value = s
    workload.value = w
    issues.value = i
    suggestions.value = sg
    trendsHistory.value = Array.isArray(th) ? th : []
  } finally {
    loading.value = false
  }
}

watch([() => range.value.end], () => { fetchAll(); fetchTrend() })
watch(granularity, fetchTrend)
onMounted(() => { fetchAll(); fetchTrend() })

// ---------- 派生 ----------
const trendDelta = computed<number | null>(() => {
  // 优先用 scores.trend_delta, 否则从历史快照算
  const td = summary.value?.scores?.trend_delta
  if (typeof td === 'number') return td
  const hist = trendsHistory.value
  if (hist.length >= 2) {
    const cur = hist[hist.length - 1]?.scores?.overall
    const prev = hist[hist.length - 2]?.scores?.overall
    if (cur != null && prev != null) return Number(cur) - Number(prev)
  }
  return null
})

const trendDeltaClass = computed(() => {
  const d = trendDelta.value
  if (d == null) return 'text-gray-400'
  if (d > 0) return 'text-emerald-600 dark:text-emerald-400'
  if (d < 0) return 'text-red-500'
  return 'text-gray-400'
})

const tierGap = computed(() => {
  const next = summary.value?.scores?.tier?.next_threshold
  const overall = summary.value?.scores?.overall ?? 0
  if (next == null) return 0
  return Math.max(0, Math.ceil(Number(next) - Number(overall)))
})

const tierProgressPct = computed(() => {
  const tier = summary.value?.scores?.tier
  if (!tier) return 0
  const overall = Number(summary.value?.scores?.overall ?? 0)
  const cur = Number(tier.threshold ?? 0)
  const next = Number(tier.next_threshold ?? cur + 1)
  if (next <= cur) return 100
  const pct = ((overall - cur) / (next - cur)) * 100
  return Math.max(0, Math.min(100, pct))
})

// 雷达
const radarIndicators = [
  { name: '效率', max: 100 },
  { name: '产出', max: 100 },
  { name: '质量', max: 100 },
  { name: '能力', max: 100 },
  { name: '成长', max: 100 },
]

const radarValues = computed(() => {
  const s = summary.value?.scores
  if (!s) return [0, 0, 0, 0, 0]
  return [
    Number(s.efficiency) || 0,
    Number(s.output) || 0,
    Number(s.quality) || 0,
    Number(s.capability) || 0,
    Number(s.growth) || 0,
  ]
})

// 耗时分布 - 客户端从 breakdown 计算 (api 没暴露分桶)
interface BreakdownItem {
  issue_id: number
  title: string
  size: string
  price: number
  estimated_hours: number | null
  actual_hours: number | null
  delay_hours: number | null
  delay_ratio: number | null
  resolved_at: string | null
  priority: string
}

const breakdown = computed<BreakdownItem[]>(() => workload.value?.breakdown || [])

const distributionBuckets = computed(() => {
  const items = breakdown.value
  const buckets = { lt4h: 0, h4_8: 0, h8_24: 0, d1_3: 0, gt3d: 0 }
  for (const it of items) {
    const hrs = it.actual_hours
    if (hrs == null) continue
    if (hrs < 4) buckets.lt4h++
    else if (hrs < 8) buckets.h4_8++
    else if (hrs < 24) buckets.h8_24++
    else if (hrs < 72) buckets.d1_3++
    else buckets.gt3d++
  }
  const defs: { key: keyof typeof buckets; label: string; color: string }[] = [
    { key: 'lt4h', label: '< 4h', color: '#10b981' },
    { key: 'h4_8', label: '4-8h', color: '#22d3ee' },
    { key: 'h8_24', label: '8-24h', color: '#8b5cf6' },
    { key: 'd1_3', label: '1-3天', color: '#f59e0b' },
    { key: 'gt3d', label: '> 3天', color: '#ef4444' },
  ]
  const max = Math.max(1, ...defs.map((d) => buckets[d.key]))
  const total = defs.reduce((s, d) => s + buckets[d.key], 0)
  return defs.map((d) => ({
    ...d,
    count: buckets[d.key],
    pct: total > 0 ? (buckets[d.key] / max) * 100 : 0,
  }))
})

const totalDistribution = computed(() =>
  distributionBuckets.value.reduce((s, b) => s + b.count, 0)
)

const avgResolutionDisplay = computed(() => {
  const v = issues.value?.avg_resolution_hours
  return v != null && Number(v) > 0 ? Number(v).toFixed(1) : '—'
})

// Code Arena
const arenaCards = computed(() => {
  const w = workload.value
  if (!w) return []
  return [
    {
      label: '完成工单',
      value: w.completed_count ?? 0,
      colorClass: 'text-violet-600 dark:text-violet-400',
      sub: `${w.small_count ?? 0} 小 / ${w.medium_count ?? 0} 中 / ${w.large_count ?? 0} 大`,
    },
    {
      label: '估算计件',
      value: `¥${w.estimated_earnings ?? 0}`,
      colorClass: 'text-emerald-600 dark:text-emerald-400',
      sub: '按预计工时分级',
    },
    {
      label: '保护期重修',
      value: w.rework_count ?? 0,
      colorClass: (w.rework_count ?? 0) > 0 ? 'text-red-500' : 'text-gray-900 dark:text-gray-100',
      sub: `${w.protection_days ?? 7} 天窗口`,
    },
    {
      label: '协助修复',
      value: w.protection_helper_count ?? 0,
      colorClass: 'text-sky-600 dark:text-sky-400',
      sub: '帮助他人解决',
    },
  ]
})

// 最近 8 条
const recentBreakdown = computed(() =>
  [...breakdown.value]
    .sort((a, b) => (b.resolved_at || '').localeCompare(a.resolved_at || ''))
    .slice(0, 8)
)

// 建议
interface SuggestionItem { title: string; detail?: string }

const dimensionLabels: Record<string, string> = {
  efficiency: '效率',
  output: '产出',
  quality: '质量',
  capability: '能力',
  growth: '成长',
}

function localizeDimension(d: string | undefined, fallback: string): string {
  if (!d) return fallback
  return dimensionLabels[d] || d
}

const suggestionItems = computed<SuggestionItem[]>(() => {
  const sg = suggestions.value
  if (!sg) return []
  const out: SuggestionItem[] = []
  for (const s of sg.shortcomings || []) {
    out.push({
      title: localizeDimension(s.dimension, s.title || '改进项'),
      detail: s.description || s.detail,
    })
  }
  for (const t of sg.trends || []) {
    out.push({
      title: localizeDimension(t.dimension, t.title || '趋势提醒'),
      detail: t.description || t.detail,
    })
  }
  return out
})

// ---------- 样式辅助 ----------
function tierStripClass(key?: string): string {
  const map: Record<string, string> = {
    bronze: 'bg-gradient-to-r from-orange-400 to-orange-300',
    silver: 'bg-gradient-to-r from-gray-400 to-gray-300',
    gold: 'bg-gradient-to-r from-amber-500 to-amber-300',
    platinum: 'bg-gradient-to-r from-cyan-400 to-cyan-300',
    diamond: 'bg-gradient-to-r from-sky-500 to-sky-300',
    master: 'bg-gradient-to-r from-violet-500 via-pink-400 to-amber-400',
  }
  return map[key ?? ''] || 'bg-gradient-to-r from-gray-300 to-gray-200'
}

function tierBadgeBgClass(key?: string): string {
  const map: Record<string, string> = {
    bronze: 'bg-orange-500',
    silver: 'bg-gray-400',
    gold: 'bg-amber-500',
    platinum: 'bg-cyan-500',
    diamond: 'bg-sky-500',
    master: 'bg-gradient-to-br from-violet-500 to-pink-500',
  }
  return map[key ?? ''] || 'bg-gray-400'
}

function tierBadgeClass(key: string): string {
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

function sizeBadgeClass(size: string): string {
  if (size === '大型' || size?.includes('大')) return 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300'
  if (size === '中型' || size?.includes('中')) return 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300'
  return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
}
</script>
