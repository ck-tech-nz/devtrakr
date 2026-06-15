export type HoverPreviewType = 'issue' | 'external'

export interface PreviewMatch {
  type: HoverPreviewType
  issueId?: string
  url?: string
}

// 判断渲染后的锚点是否可预览,以及属于哪类(供悬浮预览取数)
export function matchPreviewAnchor(a: HTMLAnchorElement | null): PreviewMatch | null {
  if (!a) return null
  if (a.classList.contains('mention-issue')) {
    const id = a.dataset.issueId || ''
    if (id) return { type: 'issue', issueId: id }
  }
  if (a.classList.contains('external-link')) {
    try {
      if (new URL(a.href).host !== location.host) return { type: 'external', url: a.href }
    } catch {
      // 无法解析的 href 不预览
    }
  }
  return null
}
