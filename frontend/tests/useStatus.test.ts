// @vitest-environment nuxt
import { describe, it, expect, afterEach } from 'vitest'
import {
  STATUS_ITEMS,
  STATUS_FALLBACK_COLOR,
  useStatusItems,
  setStatusesFromSettings,
  statusLabel,
  statusMainColor,
} from '../app/composables/useStatus'

// configured 是模块级单例,每个用例结束后还原静态默认,避免跨用例污染
afterEach(() => {
  setStatusesFromSettings(STATUS_ITEMS)
})

describe('useStatus', () => {
  it('默认 7 个状态,主色与后端 default_issue_statuses 一致', () => {
    const items = useStatusItems()
    expect(items.value.map(s => s.value)).toEqual([
      '未计划', '待分配', '待确认', '进行中', '已解决', '已发布', '已关闭',
    ])
    expect(statusMainColor('未计划')).toBe('#8b5cf6')
    expect(statusMainColor('已关闭')).toBe('#6b7280')
  })

  it('对象格式配置覆盖 label 与主色', () => {
    setStatusesFromSettings([
      { value: '进行中', label: '处理中', background: '#123456' },
    ])
    expect(statusLabel('进行中')).toBe('处理中')
    expect(statusMainColor('进行中')).toBe('#123456')
  })

  it('兼容旧版扁平字符串列表,主色回落静态默认', () => {
    setStatusesFromSettings(['已解决', '已关闭'])
    expect(useStatusItems().value).toHaveLength(2)
    expect(statusMainColor('已解决')).toBe('#10b981')
  })

  it('非法主色不进 CSS:statusMainColor 兜底灰', () => {
    setStatusesFromSettings([
      { value: '进行中', label: '进行中', background: 'url(javascript:alert(1))' },
    ])
    expect(statusMainColor('进行中')).toBe(STATUS_FALLBACK_COLOR)
  })

  it('未知状态与空配置不破坏现状', () => {
    expect(statusMainColor('不存在')).toBe(STATUS_FALLBACK_COLOR)
    expect(statusLabel('不存在')).toBe('不存在')
    const before = useStatusItems().value
    setStatusesFromSettings([])
    setStatusesFromSettings('garbage')
    expect(useStatusItems().value).toBe(before)
  })
})
