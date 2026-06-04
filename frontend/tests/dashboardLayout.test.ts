import { describe, it, expect } from 'vitest'
import {
  DASHBOARD_BLOCKS,
  defaultLayout,
  mergeLayout,
  moveBlock,
  toggleBlock,
} from '../app/utils/dashboardLayout'

describe('defaultLayout', () => {
  it('returns one entry per registry block in order, all visible', () => {
    const layout = defaultLayout()
    expect(layout.map(e => e.id)).toEqual(DASHBOARD_BLOCKS.map(b => b.id))
    expect(layout.every(e => e.visible)).toBe(true)
  })
  it('puts server block last (after activity)', () => {
    const ids = defaultLayout().map(e => e.id)
    expect(ids[ids.length - 1]).toBe('server')
    expect(ids.indexOf('server')).toBeGreaterThan(ids.indexOf('activity'))
  })
})

describe('mergeLayout', () => {
  it('returns default layout for null/undefined', () => {
    expect(mergeLayout(null)).toEqual(defaultLayout())
    expect(mergeLayout(undefined)).toEqual(defaultLayout())
  })
  it('returns default layout for empty array', () => {
    expect(mergeLayout([])).toEqual(defaultLayout())
  })
  it('appends registry blocks missing from saved layout, in registry order, at the end', () => {
    const saved = [
      { id: 'activity', visible: true },
      { id: 'stats', visible: false },
    ]
    const merged = mergeLayout(saved)
    expect(merged[0]).toEqual({ id: 'activity', visible: true })
    expect(merged[1]).toEqual({ id: 'stats', visible: false })
    const rest = merged.slice(2).map(e => e.id)
    expect(rest).toEqual(['uptime', 'todos', 'mentions', 'tasks', 'server'])
    expect(merged).toHaveLength(DASHBOARD_BLOCKS.length)
  })
  it('drops unknown ids', () => {
    const merged = mergeLayout([{ id: 'ghost', visible: true }, { id: 'stats', visible: true }])
    expect(merged.find(e => e.id === 'ghost')).toBeUndefined()
    expect(merged.map(e => e.id)).toContain('stats')
    expect(merged).toHaveLength(DASHBOARD_BLOCKS.length)
  })
  it('preserves saved order and visible:false', () => {
    const saved = DASHBOARD_BLOCKS.map(b => ({ id: b.id, visible: false })).reverse()
    const merged = mergeLayout(saved)
    expect(merged.map(e => e.id)).toEqual(DASHBOARD_BLOCKS.map(b => b.id).reverse())
    expect(merged.every(e => e.visible === false)).toBe(true)
  })
  it('dedups repeated ids, keeping first occurrence', () => {
    const merged = mergeLayout([
      { id: 'stats', visible: false },
      { id: 'stats', visible: true },
    ])
    const statsEntries = merged.filter(e => e.id === 'stats')
    expect(statsEntries).toHaveLength(1)
    expect(statsEntries[0]!.visible).toBe(false)
  })
})

describe('moveBlock', () => {
  const base = defaultLayout()
  it('moves a block up (direction -1)', () => {
    const moved = moveBlock(base, 'uptime', -1)
    expect(moved.map(e => e.id).slice(0, 2)).toEqual(['uptime', 'stats'])
  })
  it('moves a block down (direction +1)', () => {
    const moved = moveBlock(base, 'stats', 1)
    expect(moved.map(e => e.id).slice(0, 2)).toEqual(['uptime', 'stats'])
  })
  it('returns same order when moving first block up', () => {
    expect(moveBlock(base, 'stats', -1)).toEqual(base)
  })
  it('returns same order when moving last block down', () => {
    expect(moveBlock(base, 'server', 1)).toEqual(base)
  })
  it('returns same order for unknown id', () => {
    expect(moveBlock(base, 'ghost', 1)).toEqual(base)
  })
  it('does not mutate the input array', () => {
    const copy = base.slice()
    moveBlock(base, 'stats', 1)
    expect(base).toEqual(copy)
  })
})

describe('toggleBlock', () => {
  it('flips visible for the matching id only', () => {
    const layout = defaultLayout()
    const toggled = toggleBlock(layout, 'todos')
    expect(toggled.find(e => e.id === 'todos')!.visible).toBe(false)
    expect(toggled.filter(e => e.id !== 'todos').every(e => e.visible)).toBe(true)
  })
  it('does not mutate the input array', () => {
    const layout = defaultLayout()
    const copy = layout.map(e => ({ ...e }))
    toggleBlock(layout, 'todos')
    expect(layout).toEqual(copy)
  })
  it('returns unchanged layout for unknown id', () => {
    const layout = defaultLayout()
    expect(toggleBlock(layout, 'ghost')).toEqual(layout)
  })
})
