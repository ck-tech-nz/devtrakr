// @vitest-environment nuxt
import { describe, it, expect, afterEach } from 'vitest'
import {
  PRIORITY_ITEMS,
  usePriorityItems,
  setPrioritiesFromSettings,
  isSafeHexColor,
  priorityLabel,
  priorityColor,
  priorityCardClass,
  priorityCardStyle,
  priorityBadgeClass,
  priorityBadgeStyle,
} from '../app/composables/usePriority'

// configured 是模块级单例,每个用例结束后还原静态默认,避免跨用例污染(同 useStatus 测试)
afterEach(() => {
  setPrioritiesFromSettings(
    PRIORITY_ITEMS.map(p => ({ value: p.value, label: p.label, background: p.background })),
  )
})

describe('usePriority', () => {
  it('默认 4 档,label/主色与静态 PRIORITY_ITEMS 一致(回归:接入站点设置后默认行为不变)', () => {
    const items = usePriorityItems()
    expect(items.value.map(p => p.value)).toEqual(['P0', 'P1', 'P2', 'P3'])
    expect(priorityLabel('P0')).toBe('紧急')
    expect(priorityLabel('P3')).toBe('低')
    expect(priorityLabel('P9')).toBe('P9') // 未知档位原样返回
  })

  it('对象格式配置覆盖 label 与主色', () => {
    setPrioritiesFromSettings([
      { value: 'P1', label: '加急', background: '#123456' },
    ])
    expect(priorityLabel('P1')).toBe('加急')
    expect(priorityCardStyle('P1')).toEqual({ '--prio': '#123456' })
  })

  it('兼容旧版扁平字符串列表,label/主色回落静态默认', () => {
    setPrioritiesFromSettings(['P0', 'P3', 'PX'])
    expect(usePriorityItems().value).toHaveLength(3)
    expect(priorityLabel('P0')).toBe('紧急')
    expect(priorityLabel('PX')).toBe('PX') // 静态表没有的值,label 退回值本身
    expect(priorityCardStyle('P3')).toBeUndefined() // P3 默认无底色
  })

  it('空数组/非数组/纯垃圾条目不改变现有配置', () => {
    const before = usePriorityItems().value
    setPrioritiesFromSettings([])
    setPrioritiesFromSettings('garbage')
    setPrioritiesFromSettings([{ label: '缺 value' }, null, 42])
    expect(usePriorityItems().value).toBe(before)
  })

  it('isSafeHexColor 只认 hex,拒绝注入 CSS 的危险值', () => {
    expect(isSafeHexColor('#ef4444')).toBe(true)
    expect(isSafeHexColor('#fff')).toBe(true)
    expect(isSafeHexColor('')).toBe(false)
    expect(isSafeHexColor('red')).toBe(false)
    expect(isSafeHexColor('url(javascript:alert(1))')).toBe(false)
    expect(isSafeHexColor('#ef4444; background: red')).toBe(false)
  })

  it('priorityCardClass:首档加描边强调,其余有主色档给 priority-card,无主色/非法主色返回空串', () => {
    expect(priorityCardClass('P0')).toBe('priority-card priority-card-top')
    expect(priorityCardClass('P1')).toBe('priority-card')
    expect(priorityCardClass('P3')).toBe('') // 默认无底色
    expect(priorityCardClass('P9')).toBe('') // 未知档位

    setPrioritiesFromSettings([
      { value: 'PX', label: 'X', background: 'url(javascript:alert(1))' },
    ])
    expect(priorityCardClass('PX')).toBe('') // 非法主色不进 CSS
    expect(priorityCardStyle('PX')).toBeUndefined()
  })

  it('priorityColor 走静态语义色,仅作无主色档位的 badge 兜底', () => {
    expect(priorityColor('P0')).toBe('error')
    expect(priorityColor('P3')).toBe('neutral')
    setPrioritiesFromSettings([{ value: 'P0', label: '紧急', background: '#000000' }])
    expect(priorityColor('P0')).toBe('error')
    expect(priorityColor('自定义')).toBe('neutral')
  })

  it('priorityBadgeClass/Style:badge 配色随站点设置主色,无主色/非法主色回退语义色', () => {
    expect(priorityBadgeClass('P0')).toBe('priority-badge')
    expect(priorityBadgeStyle('P0')).toEqual({ '--prio': '#ef4444' })
    expect(priorityBadgeClass('P3')).toBe('') // 默认无主色 → 调用方回退语义色 badge
    expect(priorityBadgeStyle('P3')).toBeUndefined()
    expect(priorityBadgeClass('P9')).toBe('') // 未知档位

    setPrioritiesFromSettings([
      { value: 'P0', label: '紧急', background: '#123456' },
      { value: 'PX', label: 'X', background: 'url(javascript:alert(1))' },
    ])
    expect(priorityBadgeStyle('P0')).toEqual({ '--prio': '#123456' }) // 跟随站点设置
    expect(priorityBadgeClass('PX')).toBe('') // 非法主色不进 CSS
    expect(priorityBadgeStyle('PX')).toBeUndefined()
  })
})
