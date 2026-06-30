import { clampWidth, DEFAULT_MIN_WIDTH, DEFAULT_MAX_WIDTH } from '~/utils/columnWidth'

// 表格单列宽度:拖拽调整 + 记忆。持久化由调用方通过 persist.{load,save} 注入
// (可接 localStorage 或按账号的用户设置),本组合式不直接依赖某种存储。
// width 为 null → 使用默认列宽(CSS auto);非 null → 像素值。

interface ColumnWidthPersist {
  load: () => number | null
  save: (v: number | null) => void
}

interface ColumnWidthOptions {
  min?: number
  max?: number
}

export function useColumnWidth(persist: ColumnWidthPersist, options: ColumnWidthOptions = {}) {
  const min = options.min ?? DEFAULT_MIN_WIDTH
  const max = options.max ?? DEFAULT_MAX_WIDTH
  const width = ref<number | null>(null)

  // 从持久化源恢复;非空值夹到 [min, max] 区间。
  function load() {
    const v = persist.load()
    width.value = v == null ? null : clampWidth(v, min, max)
  }

  // 在表头手柄上按下指针后开始拖拽;startPx = 当前列的实际像素宽。
  // 拖拽过程实时更新 width,松手时落盘一次。
  function startResize(event: PointerEvent, startPx: number) {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX

    const onMove = (e: PointerEvent) => {
      width.value = clampWidth(startPx + (e.clientX - startX), min, max)
    }
    const onUp = () => {
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
      persist.save(width.value)
    }
    document.addEventListener('pointermove', onMove)
    document.addEventListener('pointerup', onUp)
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
  }

  // 复原为默认列宽。
  function reset() {
    width.value = null
    persist.save(null)
  }

  return { width, load, startResize, reset }
}
