import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { formatCardTime, timeAgo } from '../app/utils/timeAgo'

describe('formatCardTime', () => {
  beforeEach(() => {
    // 固定「现在」为 2026-06-11 15:30 本地时间
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 5, 11, 15, 30, 0))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('今天显示时分', () => {
    expect(formatCardTime(new Date(2026, 5, 11, 9, 5, 0).toISOString())).toBe('09:05')
    expect(formatCardTime(new Date(2026, 5, 11, 0, 0, 0).toISOString())).toBe('00:00')
  })

  it('昨天显示「昨天」', () => {
    expect(formatCardTime(new Date(2026, 5, 10, 23, 59, 0).toISOString())).toBe('昨天')
    expect(formatCardTime(new Date(2026, 5, 10, 0, 1, 0).toISOString())).toBe('昨天')
  })

  it('前天显示「前天」', () => {
    expect(formatCardTime(new Date(2026, 5, 9, 12, 0, 0).toISOString())).toBe('前天')
  })

  it('更早显示具体日期 MM-DD', () => {
    expect(formatCardTime(new Date(2026, 5, 8, 12, 0, 0).toISOString())).toBe('06-08')
    expect(formatCardTime(new Date(2026, 0, 3, 12, 0, 0).toISOString())).toBe('01-03')
  })

  it('跨年带年份', () => {
    expect(formatCardTime(new Date(2025, 11, 31, 12, 0, 0).toISOString())).toBe('2025-12-31')
  })

  it('无效时间返回空串', () => {
    expect(formatCardTime('not-a-date')).toBe('')
    expect(formatCardTime('')).toBe('')
  })
})

describe('timeAgo', () => {
  it('无效时间返回空串', () => {
    expect(timeAgo('not-a-date')).toBe('')
  })
})
