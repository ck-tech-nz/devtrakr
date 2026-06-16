export interface StatusItem {
  value: string
  label: string
  background: string // 该状态主色(hex),'' = 无底色
  disabled?: boolean // true = 管理员禁用,在各选择/展示入口隐藏(已有该状态的工单仍显示)
}

// 静态默认,与后端 default_issue_statuses 一致;站点设置加载后由 setStatusesFromSettings 覆盖
export const STATUS_ITEMS: StatusItem[] = [
  { value: '未计划', label: '未计划', background: '#8b5cf6' },
  { value: '待分配', label: '待分配', background: '#f59e0b' },
  { value: '待确认', label: '待确认', background: '#eab308' },
  { value: '进行中', label: '进行中', background: '#3b82f6' },
  { value: '已解决', label: '已解决', background: '#10b981' },
  { value: '已发布', label: '已发布', background: '#14b8a6' },
  { value: '已关闭', label: '已关闭', background: '#6b7280' },
]

// 无主色/非法主色状态在胶囊与看板圆点里的兜底色
export const STATUS_FALLBACK_COLOR = '#9ca3af'

// 管理员在站点设置配置的状态;SPA(无 SSR),模块级单例状态安全(同 usePriority)
const configured = ref<StatusItem[]>(STATUS_ITEMS.map(s => ({ ...s })))

export function useStatusItems() {
  return configured
}

// 接入 /api/settings/ 的 issue_statuses 字段;兼容旧版扁平列表 ["未计划",...]
export function setStatusesFromSettings(raw: unknown) {
  if (!Array.isArray(raw) || raw.length === 0) return
  const items: StatusItem[] = []
  for (const s of raw as any[]) {
    if (typeof s === 'string') {
      const def = STATUS_ITEMS.find(d => d.value === s)
      items.push({ value: s, label: def?.label ?? s, background: def?.background ?? '' })
    } else if (s && typeof s === 'object' && s.value) {
      items.push({
        value: String(s.value),
        label: String(s.label || s.value),
        background: typeof s.background === 'string' ? s.background : '',
        disabled: Boolean(s.disabled),
      })
    }
  }
  if (items.length) configured.value = items
}

function find(s: string): StatusItem | undefined {
  return configured.value.find(i => i.value === s)
}

export function statusLabel(s: string): string {
  return find(s)?.label ?? s
}

// 该状态是否被管理员禁用(缺省/未知状态视为未禁用)。各选择/展示入口据此隐藏。
export function isStatusDisabled(s: string): boolean {
  return find(s)?.disabled === true
}

// 状态主色(hex):详情页状态胶囊/看板列圆点用;主色只认安全 hex,否则兜底灰
export function statusMainColor(s: string): string {
  const bg = find(s)?.background
  return bg && isSafeHexColor(bg) ? bg : STATUS_FALLBACK_COLOR
}
