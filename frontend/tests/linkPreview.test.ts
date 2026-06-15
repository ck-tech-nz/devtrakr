// @vitest-environment nuxt
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { matchPreviewAnchor } from '../app/composables/useLinkPreview'
import { fetchIssuePreview, clearIssuePreviewCache } from '../app/composables/useLinkPreview'

function anchor(html: string): HTMLAnchorElement {
  const d = document.createElement('div')
  d.innerHTML = html
  return d.querySelector('a')!
}

describe('matchPreviewAnchor', () => {
  it('matches an issue mention by data-issue-id', () => {
    const a = anchor('<a class="mention-issue" data-issue-id="42" href="/app/issues/42">#问题-042</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'issue', issueId: '42' })
  })

  it('matches an external link to a different host', () => {
    const a = anchor('<a class="external-link" href="https://example.com/docs">x</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'external', url: 'https://example.com/docs' })
  })

  it('does not match a same-host external-link', () => {
    const a = anchor(`<a class="external-link" href="${location.origin}/x">x</a>`)
    expect(matchPreviewAnchor(a)).toBeNull()
  })

  it('returns null for a plain anchor', () => {
    const a = anchor('<a href="/app/issues/3">x</a>')
    expect(matchPreviewAnchor(a)).toBeNull()
  })

  it('returns null for null input', () => {
    expect(matchPreviewAnchor(null)).toBeNull()
  })
})

describe('fetchIssuePreview', () => {
  beforeEach(() => clearIssuePreviewCache())

  it('maps the API payload to an IssuePreview', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      id: 7, title: 'T', status: '进行中', priority: 'P1',
      assignee_name: '张三', assignee_avatar: 'a.png', created_by_name: '李四',
      created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00',
    })
    const r = await fetchIssuePreview('7', fetcher)
    expect(fetcher).toHaveBeenCalledWith('/api/issues/7/')
    expect(r).toMatchObject({ id: 7, title: 'T', status: '进行中', priority: 'P1', assignee_name: '张三' })
  })

  it('caches by id — a second call does not refetch', async () => {
    const fetcher = vi.fn().mockResolvedValue({ id: 7, title: 'T', status: '进行中', priority: 'P1', created_at: '', updated_at: '' })
    await fetchIssuePreview('7', fetcher)
    await fetchIssuePreview('7', fetcher)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('drops the cache entry on failure so a retry refetches', async () => {
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({ id: 7, title: 'T', status: '进行中', priority: 'P1', created_at: '', updated_at: '' })
    await expect(fetchIssuePreview('7', fetcher)).rejects.toThrow('boom')
    const r = await fetchIssuePreview('7', fetcher)
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(r.id).toBe(7)
  })
})
