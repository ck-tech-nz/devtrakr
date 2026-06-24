import { describe, it, expect } from 'vitest'
import { changeSummary, changeLines, formatHistoryValue, type HistoryEntry } from '../app/utils/issueHistory'

function entry(partial: Partial<HistoryEntry>): HistoryEntry {
  return { id: 1, type: '~', date: '2026-06-24T00:00:00Z', user: '凯歌', changes: [], ...partial }
}

describe('changeSummary', () => {
  it('创建记录显示「创建」', () => {
    expect(changeSummary(entry({ type: '+', changes: [{ field: '_created', label: '创建', before: null, after: null }] }))).toBe('创建')
  })

  it('首个变更字段为 _created 时也显示「创建」', () => {
    expect(changeSummary(entry({ type: '~', changes: [{ field: '_created', label: '创建', before: null, after: null }] }))).toBe('创建')
  })

  it('删除记录显示「删除」', () => {
    expect(changeSummary(entry({ type: '-', changes: [{ field: 'is_deleted', label: '已删除', before: false, after: true }] }))).toBe('删除')
  })

  it('更新记录用「、」连接变更字段名', () => {
    expect(changeSummary(entry({
      changes: [
        { field: 'status', label: '状态', before: '进行中', after: '已解决' },
        { field: 'description', label: '描述', before: 'a', after: 'b' },
      ],
    }))).toBe('状态、描述')
  })

  it('无变更字段时兜底「更新」', () => {
    expect(changeSummary(entry({ changes: [] }))).toBe('更新')
  })
})

describe('formatHistoryValue', () => {
  it('空值显示「空」', () => {
    expect(formatHistoryValue(null)).toBe('空')
    expect(formatHistoryValue('')).toBe('空')
    expect(formatHistoryValue([])).toBe('空')
  })

  it('布尔值显示是/否', () => {
    expect(formatHistoryValue(true)).toBe('是')
    expect(formatHistoryValue('True')).toBe('是')
    expect(formatHistoryValue(false)).toBe('否')
    expect(formatHistoryValue('False')).toBe('否')
  })

  it('数组用「、」连接', () => {
    expect(formatHistoryValue(['bug', '功能'])).toBe('bug、功能')
  })

  it('对象(如结算快照)显示「已更新」', () => {
    expect(formatHistoryValue({ amount: 100 })).toBe('已更新')
  })

  it('ISO 日期时间仅保留日期部分', () => {
    expect(formatHistoryValue('2026-06-23')).toBe('2026-06-23')
    expect(formatHistoryValue('2026-06-23T10:30:00+00:00')).toBe('2026-06-23')
  })

  it('超长文本截断并加省略号', () => {
    const long = 'x'.repeat(80)
    const out = formatHistoryValue(long)
    expect(out.length).toBe(60)
    expect(out.endsWith('…')).toBe(true)
  })

  it('普通短文本原样返回', () => {
    expect(formatHistoryValue('进行中')).toBe('进行中')
  })
})

describe('changeLines', () => {
  it('创建记录返回单条创建行', () => {
    const lines = changeLines(entry({ type: '+', changes: [{ field: '_created', label: '创建', before: null, after: null }] }))
    expect(lines).toEqual([{ label: '创建', before: '', after: '', kind: 'created' }])
  })

  it('删除记录返回单条删除行', () => {
    const lines = changeLines(entry({ type: '-', changes: [{ field: 'is_deleted', label: '已删除', before: false, after: true }] }))
    expect(lines).toEqual([{ label: '删除', before: '', after: '', kind: 'deleted' }])
  })

  it('更新记录展开每个字段的旧值→新值', () => {
    const lines = changeLines(entry({
      changes: [
        { field: 'status', label: '状态', before: '进行中', after: '已解决' },
        { field: 'estimated_completion', label: '预计完成', before: null, after: '2026-06-24' },
      ],
    }))
    expect(lines).toEqual([
      { label: '状态', before: '进行中', after: '已解决', kind: 'update' },
      { label: '预计完成', before: '空', after: '2026-06-24', kind: 'update' },
    ])
  })

  it('对象字段(结算快照)显示「已更新」', () => {
    const lines = changeLines(entry({
      changes: [{ field: 'settlement', label: '结算快照', before: null, after: { amount: 100 } }],
    }))
    expect(lines).toEqual([{ label: '结算快照', before: '空', after: '已更新', kind: 'update' }])
  })

  it('无明细时兜底单条「更新」行', () => {
    const lines = changeLines(entry({ changes: [] }))
    expect(lines).toEqual([{ label: '更新', before: '', after: '', kind: 'update' }])
  })
})
