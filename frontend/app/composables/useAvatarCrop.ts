// 头像裁剪的纯几何计算(不依赖 DOM/canvas),抽出便于单元测试。
//
// 模型:正方形取景框 view×view。图片以 "cover" 方式铺满取景框为基准缩放
// (baseScale),再叠加用户 zoom(≥1)。displayed 尺寸 = 原始尺寸 × baseScale × zoom,
// 通过左上角偏移 (ox, oy) 在取景框内平移。约束:图片必须始终盖满取景框(无空隙)。

export interface CropOffset {
  ox: number
  oy: number
}

export interface SourceRect {
  sx: number
  sy: number
  size: number
}

/** 让图片以 cover 方式恰好盖满取景框所需的基准缩放。 */
export function coverScale(iw: number, ih: number, view: number): number {
  if (iw <= 0 || ih <= 0) return 1
  return Math.max(view / iw, view / ih)
}

/** 把偏移夹紧到「图片盖满取景框」的合法范围内。 */
export function clampOffset(ox: number, oy: number, dw: number, dh: number, view: number): CropOffset {
  return {
    ox: Math.min(0, Math.max(view - dw, ox)),
    oy: Math.min(0, Math.max(view - dh, oy)),
  }
}

/** 初始居中偏移。 */
export function centerOffset(dw: number, dh: number, view: number): CropOffset {
  return { ox: (view - dw) / 2, oy: (view - dh) / 2 }
}

/**
 * 缩放时锚定取景框中心:返回缩放后仍让中心源点保持不变的新偏移(已夹紧)。
 */
export function offsetForZoomAtCenter(
  ox: number,
  oy: number,
  scaleOld: number,
  scaleNew: number,
  iw: number,
  ih: number,
  view: number,
): CropOffset {
  // 当前取景框中心对应的源坐标
  const cx = (view / 2 - ox) / scaleOld
  const cy = (view / 2 - oy) / scaleOld
  const nx = view / 2 - cx * scaleNew
  const ny = view / 2 - cy * scaleNew
  return clampOffset(nx, ny, iw * scaleNew, ih * scaleNew, view)
}

/** 取景框当前显示的源图区域(正方形),用于 canvas.drawImage 的源矩形。 */
export function sourceRect(ox: number, oy: number, scale: number, view: number): SourceRect {
  return {
    sx: -ox / scale,
    sy: -oy / scale,
    size: view / scale,
  }
}
