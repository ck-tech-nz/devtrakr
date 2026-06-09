// 工作台区块布局纯逻辑 —— 无 Nuxt 依赖,可被 Vitest 直接单测。

export interface DashboardBlockMeta {
  id: string
  title: string
  defaultVisible: boolean
}

export interface LayoutEntry {
  id: string
  visible: boolean
}

// 规范注册表 + 默认顺序(服务器资源卡落在最近动态之后)
export const DASHBOARD_BLOCKS: readonly DashboardBlockMeta[] = Object.freeze([
  { id: 'stats', title: '数据概览', defaultVisible: true },
  { id: 'uptime', title: '生产环境监控', defaultVisible: true },
  { id: 'todos', title: '我的待办', defaultVisible: true },
  { id: 'mentions', title: '提及我的', defaultVisible: true },
  { id: 'tasks', title: '我的任务', defaultVisible: true },
  { id: 'activity', title: '最近动态', defaultVisible: true },
  { id: 'server', title: '服务器资源', defaultVisible: true },
  { id: 'gateway', title: '电话线路状态', defaultVisible: true },
])

export function defaultLayout(): LayoutEntry[] {
  return DASHBOARD_BLOCKS.map(b => ({ id: b.id, visible: b.defaultVisible }))
}

// 合并已存布局与注册表:已存且仍在注册表中的条目去重保序在前;
// 注册表里有、已存没有的,按注册表顺序补到末尾;未知 id 丢弃。
export function mergeLayout(
  saved: LayoutEntry[] | null | undefined,
  registry: readonly DashboardBlockMeta[] = DASHBOARD_BLOCKS,
): LayoutEntry[] {
  const known = new Set(registry.map(b => b.id))
  const savedArr = Array.isArray(saved) ? saved : []
  const seen = new Set<string>()
  const result: LayoutEntry[] = []
  for (const entry of savedArr) {
    if (entry && known.has(entry.id) && !seen.has(entry.id)) {
      // 兼容旧存储:visible 缺失或非 false 均视为可见
      result.push({ id: entry.id, visible: entry.visible !== false })
      seen.add(entry.id)
    }
  }
  for (const b of registry) {
    if (!seen.has(b.id)) {
      result.push({ id: b.id, visible: b.defaultVisible })
      seen.add(b.id)
    }
  }
  return result
}

// 移动区块:direction = -1 上移 / +1 下移;越界或未知 id 返回原数组(不报错)。返回新数组,不改入参。
export function moveBlock(layout: LayoutEntry[], id: string, direction: -1 | 1): LayoutEntry[] {
  const idx = layout.findIndex(e => e.id === id)
  if (idx === -1) return layout
  const target = idx + direction
  if (target < 0 || target >= layout.length) return layout
  const next = layout.slice()
  const [item] = next.splice(idx, 1)
  next.splice(target, 0, item!)
  return next
}

// 切换某区块显隐,返回新数组,不改入参。
export function toggleBlock(layout: LayoutEntry[], id: string): LayoutEntry[] {
  return layout.map(e => (e.id === id ? { ...e, visible: !e.visible } : e))
}
