import { describe, it, expect } from 'vitest'
import { changeSummary, type HistoryEntry } from '../app/utils/issueHistory'

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
