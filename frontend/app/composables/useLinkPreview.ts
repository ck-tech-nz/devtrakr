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

export interface IssuePreview {
  id: number
  title: string
  status: string
  priority: string
  assignee_name: string | null
  assignee_avatar: string | null
  created_by_name: string | null
  created_at: string
  updated_at: string
}

// 同一 id 去重:缓存 Promise,并发悬浮只取一次;失败时清除缓存以便重试
const issueCache = new Map<string, Promise<IssuePreview>>()

export function clearIssuePreviewCache() {
  issueCache.clear()
}

export function fetchIssuePreview(
  id: string,
  fetcher: (url: string) => Promise<unknown>,
): Promise<IssuePreview> {
  const cached = issueCache.get(id)
  if (cached) return cached
  const p = fetcher(`/api/issues/${id}/`).then((raw) => {
    const d = raw as Record<string, unknown>
    return {
      id: Number(d.id),
      title: String(d.title ?? ''),
      status: String(d.status ?? ''),
      priority: String(d.priority ?? ''),
      assignee_name: d.assignee_name != null ? String(d.assignee_name) : null,
      assignee_avatar: d.assignee_avatar != null ? String(d.assignee_avatar) : null,
      created_by_name: d.created_by_name != null ? String(d.created_by_name) : null,
      created_at: String(d.created_at ?? ''),
      updated_at: String(d.updated_at ?? ''),
    } satisfies IssuePreview
  })
  p.catch(() => issueCache.delete(id))
  issueCache.set(id, p)
  return p
}
