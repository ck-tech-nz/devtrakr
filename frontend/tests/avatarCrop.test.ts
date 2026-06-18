import { describe, it, expect } from 'vitest'
import {
  centerOffset,
  clampOffset,
  coverScale,
  offsetForZoomAtCenter,
  sourceRect,
} from '../app/composables/useAvatarCrop'

const VIEW = 288

describe('coverScale', () => {
  it('scales the shorter side to cover the viewport', () => {
    // 宽图:高度是限制维度 → view/height
    expect(coverScale(800, 400, VIEW)).toBeCloseTo(VIEW / 400)
    // 高图:宽度是限制维度 → view/width
    expect(coverScale(400, 800, VIEW)).toBeCloseTo(VIEW / 400)
  })
  it('upscales images smaller than the viewport', () => {
    expect(coverScale(100, 100, VIEW)).toBeCloseTo(VIEW / 100)
  })
  it('guards against zero/negative dimensions', () => {
    expect(coverScale(0, 0, VIEW)).toBe(1)
  })
})

describe('clampOffset', () => {
  it('keeps the image covering the viewport (no gaps)', () => {
    const dw = 400, dh = 400
    // 偏移过大(露出左/上空隙)→ 夹到 0
    expect(clampOffset(50, 50, dw, dh, VIEW)).toEqual({ ox: 0, oy: 0 })
    // 偏移过小(露出右/下空隙)→ 夹到 view-d
    expect(clampOffset(-999, -999, dw, dh, VIEW)).toEqual({ ox: VIEW - dw, oy: VIEW - dh })
  })
  it('leaves valid offsets untouched', () => {
    expect(clampOffset(-20, -30, 400, 400, VIEW)).toEqual({ ox: -20, oy: -30 })
  })
})

describe('centerOffset', () => {
  it('centers the scaled image in the viewport', () => {
    expect(centerOffset(400, 400, VIEW)).toEqual({ ox: (VIEW - 400) / 2, oy: (VIEW - 400) / 2 })
  })
})

describe('offsetForZoomAtCenter', () => {
  it('keeps the viewport-center source point fixed while zooming', () => {
    const iw = 400, ih = 400
    const s0 = 1, s1 = 2
    const start = centerOffset(iw * s0, ih * s0, VIEW)
    // 缩放前中心对应的源坐标
    const cxBefore = (VIEW / 2 - start.ox) / s0
    const next = offsetForZoomAtCenter(start.ox, start.oy, s0, s1, iw, ih, VIEW)
    const cxAfter = (VIEW / 2 - next.ox) / s1
    expect(cxAfter).toBeCloseTo(cxBefore)
  })
  it('returns a clamped (valid) offset', () => {
    const iw = 400, ih = 400, s1 = 2
    const next = offsetForZoomAtCenter(0, 0, 1, s1, iw, ih, VIEW)
    expect(next.ox).toBeLessThanOrEqual(0)
    expect(next.ox).toBeGreaterThanOrEqual(VIEW - iw * s1)
  })
})

describe('sourceRect', () => {
  it('maps a centered, unzoomed cover view to the middle square of the source', () => {
    const iw = 800, ih = 400
    const base = coverScale(iw, ih, VIEW) // = VIEW/400
    const c = centerOffset(iw * base, ih * base, VIEW)
    const rect = sourceRect(c.ox, c.oy, base, VIEW)
    // cover 后源区域边长应为短边(400),并在宽方向居中
    expect(rect.size).toBeCloseTo(400)
    expect(rect.sy).toBeCloseTo(0)
    expect(rect.sx).toBeCloseTo((800 - 400) / 2)
  })
})
