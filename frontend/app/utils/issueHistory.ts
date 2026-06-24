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

// 单个变更明细:字段标签 + 旧值 + 新值。kind 区分创建 / 删除 / 普通更新。
export type ChangeLineKind = 'created' | 'deleted' | 'update'
export type ChangeLine = { label: string; before: string; after: string; kind: ChangeLineKind }

const MAX_VALUE_LEN = 60

// 把后端返回的原始值格式化为可读文本(后端已对长文本截断到 80 字)。
export function formatHistoryValue(value: any): string {
  if (value === null || value === undefined || value === '') return '空'
  if (value === true || value === 'True') return '是'
  if (value === false || value === 'False') return '否'
  if (Array.isArray(value)) return value.length ? value.map(String).join('、') : '空'
  if (typeof value === 'object') return '已更新'
  const text = String(value)
  // ISO 日期 / 日期时间 → 仅展示日期部分,避免时区与冗长时间戳。
  const isoDate = text.match(/^(\d{4}-\d{2}-\d{2})(?:T[\d:.+\-Z]*)?$/)
  if (isoDate) return isoDate[1]!
  return text.length <= MAX_VALUE_LEN ? text : text.slice(0, MAX_VALUE_LEN - 1) + '…'
}

// 展开一条历史记录为「变更内容」明细行(一次保存可能改动多个字段)。
export function changeLines(entry: HistoryEntry): ChangeLine[] {
  if (entry.type === '+' || entry.changes[0]?.field === '_created') {
    return [{ label: '创建', before: '', after: '', kind: 'created' }]
  }
  if (entry.type === '-') {
    return [{ label: '删除', before: '', after: '', kind: 'deleted' }]
  }
  const lines = entry.changes
    .filter(c => c.field !== '_created')
    .map<ChangeLine>(c => ({
      label: c.label,
      before: formatHistoryValue(c.before),
      after: formatHistoryValue(c.after),
      kind: 'update',
    }))
  return lines.length ? lines : [{ label: '更新', before: '', after: '', kind: 'update' }]
}
