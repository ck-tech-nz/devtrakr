// 问题变更历史的纯逻辑(无 Nuxt 依赖,可被 Vitest 直接单测)。
// 数据来源:GET /api/issues/{id}/history/(django-simple-history diff)。

export type HistoryChange = { field: string; label: string; before: any; after: any }
export type HistoryEntry = {
  id: number
  type: '+' | '~' | '-'
  date: string
  user: string | null
  changes: HistoryChange[]
}

// 每行「变更内容」:仅显示变动的字段名(用顿号连接);创建/删除单独成词。
export function changeSummary(entry: HistoryEntry): string {
  if (entry.type === '+' || entry.changes[0]?.field === '_created') return '创建'
  if (entry.type === '-') return '删除'
  const labels = entry.changes.map(c => c.label).filter(Boolean)
  return labels.length ? labels.join('、') : '更新'
}
