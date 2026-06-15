// @vitest-environment nuxt
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { matchPreviewAnchor } from '../app/composables/useLinkPreview'
import { fetchIssuePreview, clearIssuePreviewCache } from '../app/composables/useLinkPreview'
import { fetchGithubPreview, clearGithubPreviewCache } from '../app/composables/useLinkPreview'

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

  it('returns null for a mention-issue anchor missing data-issue-id', () => {
    const a = anchor('<a class="mention-issue" href="/app/issues/99">#问题-099</a>')
    expect(matchPreviewAnchor(a)).toBeNull()
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

describe('matchPreviewAnchor github', () => {
  function anchorEl(html: string): HTMLAnchorElement {
    const d = document.createElement('div'); d.innerHTML = html; return d.querySelector('a')!
  }
  it('classifies a github PR link as github', () => {
    const a = anchorEl('<a class="external-link" href="https://github.com/octocat/hello/pull/42">PR</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'github', url: 'https://github.com/octocat/hello/pull/42' })
  })
  it('classifies a github issue link as github', () => {
    const a = anchorEl('<a class="external-link" href="https://github.com/octocat/hello/issues/7">x</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'github', url: 'https://github.com/octocat/hello/issues/7' })
  })
  it('a non-PR github link stays external', () => {
    const a = anchorEl('<a class="external-link" href="https://github.com/octocat/hello">repo</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'external', url: 'https://github.com/octocat/hello' })
  })
})

describe('fetchGithubPreview', () => {
  beforeEach(() => clearGithubPreviewCache())
  it('maps the endpoint payload', async () => {
    const fetcher = vi.fn().mockResolvedValue({ kind: 'pr', number: 42, title: 'T', state: 'merged', author_login: 'a', author_avatar: 'av', repo_full_name: 'o/r', html_url: 'u' })
    const r = await fetchGithubPreview('https://github.com/o/r/pull/42', fetcher)
    expect(fetcher).toHaveBeenCalledWith('/api/repos/github-preview/?url=' + encodeURIComponent('https://github.com/o/r/pull/42'))
    expect(r).toMatchObject({ kind: 'pr', number: 42, state: 'merged' })
  })
  it('returns null when backend says unsupported', async () => {
    const fetcher = vi.fn().mockResolvedValue({ supported: false })
    expect(await fetchGithubPreview('https://github.com/o/r/pull/1', fetcher)).toBeNull()
  })
  it('caches by url', async () => {
    const fetcher = vi.fn().mockResolvedValue({ kind: 'pr', number: 1, title: '', state: 'open', author_login: '', author_avatar: '', repo_full_name: '', html_url: '' })
    await fetchGithubPreview('u1', fetcher); await fetchGithubPreview('u1', fetcher)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
