/**
 * KPI 周期范围管理: 周/月/季度 + 偏移量 + 自定义日期。
 *
 * - activePeriod: 'week' | 'month' | 'quarter' | ''   (空 = 自定义模式)
 * - offset: 0 = 当前周期, -1 = 上一个, +1 = 下一个
 * - customStart / customEnd: 自定义模式下的起止日期
 *
 * 输出 range = { start, end } (YYYY-MM-DD)。
 * 偏移量 != 0 或在自定义模式时,后端按 ?start=&end= 解析;
 * 偏移量 == 0 且无自定义时,后端按 ?period= 解析。
 */

export type PeriodKey = 'week' | 'month' | 'quarter' | ''

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function formatDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function startOfWeek(d: Date): Date {
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  const m = new Date(d)
  m.setDate(d.getDate() + diff)
  m.setHours(0, 0, 0, 0)
  return m
}

export function computePeriodRange(period: PeriodKey, offset: number): { start: string; end: string } {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  let start: Date
  let end: Date

  if (period === 'week') {
    const monday = startOfWeek(today)
    monday.setDate(monday.getDate() + offset * 7)
    start = monday
    end = new Date(monday)
    end.setDate(monday.getDate() + 6)
  } else if (period === 'quarter') {
    const qIdx = Math.floor(today.getMonth() / 3)
    const target = qIdx + offset
    // Math.floor already handles negative wrap correctly: floor(-1/4) = -1
    const yearDelta = Math.floor(target / 4)
    const localQ = ((target % 4) + 4) % 4
    const year = today.getFullYear() + yearDelta
    start = new Date(year, localQ * 3, 1)
    end = new Date(year, localQ * 3 + 3, 0)
  } else {
    // month (default)
    const year = today.getFullYear()
    const month = today.getMonth() + offset
    start = new Date(year, month, 1)
    end = new Date(year, month + 1, 0)
  }

  // 当前周期截断到今天
  if (offset === 0 && end > today) end = today

  return { start: formatDate(start), end: formatDate(end) }
}

export function formatPeriodLabel(period: PeriodKey, range: { start: string; end: string }): string {
  if (!period) return `${range.start} ~ ${range.end}`
  if (period === 'week') return `${range.start} ~ ${range.end}`
  if (period === 'month') return range.start.slice(0, 7)
  if (period === 'quarter') {
    const [y, m] = range.start.split('-')
    const qIdx = Math.floor((Number(m) - 1) / 3) + 1
    return `${y} Q${qIdx}`
  }
  return `${range.start} ~ ${range.end}`
}

export function usePeriodRange(initialPeriod: PeriodKey = 'month') {
  const activePeriod = ref<PeriodKey>(initialPeriod)
  const periodOffset = ref(0)
  const customStart = ref('')
  const customEnd = ref('')

  const isCustom = computed(() => !!customStart.value && !!customEnd.value)

  const range = computed(() => {
    if (isCustom.value) {
      return { start: customStart.value, end: customEnd.value }
    }
    return computePeriodRange(activePeriod.value, periodOffset.value)
  })

  const label = computed(() => {
    if (isCustom.value) return `${customStart.value} ~ ${customEnd.value}`
    return formatPeriodLabel(activePeriod.value, range.value)
  })

  function setPeriod(p: PeriodKey) {
    activePeriod.value = p
    periodOffset.value = 0
    customStart.value = ''
    customEnd.value = ''
  }

  function shift(delta: number) {
    customStart.value = ''
    customEnd.value = ''
    if (!activePeriod.value) activePeriod.value = 'month'
    periodOffset.value += delta
  }

  function applyCustom() {
    if (!customStart.value || !customEnd.value) return
    activePeriod.value = ''
    periodOffset.value = 0
  }

  /** 序列化为查询参数 — 始终用 start/end 以支持偏移量。 */
  function toQuery(extra?: Record<string, string>): string {
    const params = new URLSearchParams()
    params.set('start', range.value.start)
    params.set('end', range.value.end)
    if (extra) {
      for (const [k, v] of Object.entries(extra)) {
        if (v) params.set(k, v)
      }
    }
    return params.toString()
  }

  return {
    activePeriod,
    periodOffset,
    customStart,
    customEnd,
    isCustom,
    range,
    label,
    setPeriod,
    shift,
    applyCustom,
    toQuery,
  }
}
