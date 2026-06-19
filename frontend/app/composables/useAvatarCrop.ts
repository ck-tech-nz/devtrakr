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

/** 让整张图片完整放入取景框(contain)所需的缩放;小于此即出现留白。 */
export function containScale(iw: number, ih: number, view: number): number {
  if (iw <= 0 || ih <= 0) return 1
  return Math.min(view / iw, view / ih)
}

/**
 * 相对 cover 基准(=1)的最小 zoom。
 * 头像最终显示为圆形,故按「整张图(含四角)收进内切圆」来定下限:
 * 图片对角线 ≤ 取景框边长(= 圆直径)。这样连方图也能缩到 ~0.707,
 * 把边角内容(如尾巴)收进圆形头像;长图缩得更多。封顶 1(cover 为上界)。
 */
export function minZoom(iw: number, ih: number, view: number): number {
  if (iw <= 0 || ih <= 0) return 1
  const cover = coverScale(iw, ih, view)
  if (cover <= 0) return 1
  const fitCircle = view / Math.hypot(iw, ih)
  return Math.min(1, fitCircle / cover)
}

/**
 * 把偏移夹紧到合法范围。
 * 盖满取景框(d≥view):范围 [view-d, 0](无空隙)。
 * 图片小于取景框(d<view,缩到 contain):范围 [0, view-d],图片整体留在框内,
 * 四周为留白(导出时作为透明 padding,不裁切内容)。
 */
export function clampOffset(ox: number, oy: number, dw: number, dh: number, view: number): CropOffset {
  const clamp1 = (v: number, d: number) => Math.min(Math.max(0, view - d), Math.max(Math.min(0, view - d), v))
  return { ox: clamp1(ox, dw), oy: clamp1(oy, dh) }
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
