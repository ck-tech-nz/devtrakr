export interface PriorityItem {
  value: string
  label: string
  background: string // 该档主色(hex),'' = 无底色(基线档)
}

// 静态默认(高→低),色系低→高: 灰 → 黄 → 橙 → 红。
// badge 语义色(color)只作无主色档位的兜底,自定义档位回退 neutral;
// 卡片/行/滑块/徽章的色系走下方 configured 的动态主色(站点设置可改)。
export const PRIORITY_ITEMS = [
  { value: 'P0', label: '紧急', color: 'error',   background: '#ef4444' },
  { value: 'P1', label: '高',   color: 'warning', background: '#f97316' },
  { value: 'P2', label: '中',   color: 'warning', background: '#facc15' },
  { value: 'P3', label: '低',   color: 'neutral', background: '' },
] as const

// 无主色档位(如默认的「低」)在滑块轨道里的兜底色
export const PRIORITY_FALLBACK_COLOR = '#9ca3af' // gray-400

// 管理员在站点设置配置的优先级;SPA(无 SSR),模块级单例状态安全
const configured = ref<PriorityItem[]>(
  PRIORITY_ITEMS.map(p => ({ value: p.value, label: p.label, background: p.background })),
)

export function usePriorityItems() {
  return configured
}

// 接入 /api/settings/ 的 priorities 字段;兼容旧版扁平列表 ["P0",...]
export function setPrioritiesFromSettings(raw: unknown) {
  if (!Array.isArray(raw) || raw.length === 0) return
  const items: PriorityItem[] = []
  for (const p of raw as any[]) {
    if (typeof p === 'string') {
      const def = PRIORITY_ITEMS.find(d => d.value === p)
      items.push({ value: p, label: def?.label ?? p, background: def?.background ?? '' })
    } else if (p && typeof p === 'object' && p.value) {
      items.push({
        value: String(p.value),
        label: String(p.label || p.value),
        background: typeof p.background === 'string' ? p.background : '',
      })
    }
  }
  if (items.length) configured.value = items
}

// 主色只允许合法长度的 hex(3/4/6/8 位),防止管理员输入混入生成的 CSS;
// 5/7 位不是合法 CSS 颜色,混入 color-mix() 会让整条规则失效
export function isSafeHexColor(c: string): boolean {
  return /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(c)
}

function find(p: string): PriorityItem | undefined {
  return configured.value.find(i => i.value === p)
}

export function priorityLabel(p: string): string {
  return find(p)?.label ?? p
}

export function priorityColor(p: string): string {
  return PRIORITY_ITEMS.find(i => i.value === p)?.color ?? 'neutral'
}

// 卡片底色(看板/移动端列表):配了主色的档位给 .priority-card(样式见 main.css),
// 首档(最高优先级)额外描边强调;返回空串表示走调用方默认底色
export function priorityCardClass(p: string): string {
  const item = find(p)
  if (!item?.background || !isSafeHexColor(item.background)) return ''
  return configured.value[0]?.value === p ? 'priority-card priority-card-top' : 'priority-card'
}

export function priorityCardStyle(p: string): Record<string, string> | undefined {
  return mainColorVar(p)
}

// 优先级徽章(看板卡/待办卡/列表/筛选标签):配了主色的档位给 .priority-badge
// (样式见 main.css,覆盖 UBadge subtle 的语义色);返回空串表示回退静态语义色 badge
export function priorityBadgeClass(p: string): string {
  return mainColorVar(p) ? 'priority-badge' : ''
}

export function priorityBadgeStyle(p: string): Record<string, string> | undefined {
  return mainColorVar(p)
}

function mainColorVar(p: string): Record<string, string> | undefined {
  const bg = find(p)?.background
  return bg && isSafeHexColor(bg) ? { '--prio': bg } : undefined
}
