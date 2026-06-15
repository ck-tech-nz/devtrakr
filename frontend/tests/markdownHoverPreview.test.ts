// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import MarkdownHoverPreview from '../app/components/MarkdownHoverPreview.vue'
import { clearIssuePreviewCache, clearGithubPreviewCache } from '../app/composables/useLinkPreview'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

function makeContainer(html: string): HTMLElement {
  const el = document.createElement('div')
  el.innerHTML = html
  document.body.appendChild(el)
  return el
}

beforeEach(() => { apiMock.mockReset(); clearIssuePreviewCache(); clearGithubPreviewCache(); document.body.innerHTML = '' })
afterEach(() => { vi.useRealTimers() })

describe('MarkdownHoverPreview', () => {
  it('hovering an issue mention fetches and shows the issue card', async () => {
    apiMock.mockResolvedValue({
      id: 7, title: '登录页报错', status: '进行中', priority: 'P1',
      assignee_name: '张三', assignee_avatar: '', created_by_name: '李四',
      created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00',
    })
    const container = makeContainer('<a class="mention-issue" data-issue-id="7" href="/app/issues/7">#问题-007</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/issues/7/')
    expect(document.body.textContent).toContain('登录页报错')
    expect(document.body.textContent).toContain('进行中')
    w.unmount()
  })

  it('hovering a non-github external link shows the domain card (no iframe)', async () => {
    const container = makeContainer('<a class="external-link" href="https://example.com/docs">example</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(document.body.querySelector('iframe')).toBeNull()
    expect(document.body.textContent).toContain('example.com')
    w.unmount()
  })

  it('hovering a github PR link fetches and shows the github card', async () => {
    apiMock.mockResolvedValue({ kind: 'pr', number: 42, title: 'PR标题', state: 'open', author_login: 'alice', author_avatar: '', repo_full_name: 'octocat/hello', html_url: 'https://github.com/octocat/hello/pull/42' })
    const container = makeContainer('<a class="external-link" href="https://github.com/octocat/hello/pull/42">PR</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/repos/github-preview/?url=' + encodeURIComponent('https://github.com/octocat/hello/pull/42'))
    expect(document.body.textContent).toContain('PR标题')
    w.unmount()
  })

  it('github link that backend marks unsupported falls back to the domain card', async () => {
    apiMock.mockResolvedValue({ supported: false })
    const container = makeContainer('<a class="external-link" href="https://github.com/octocat/hello/pull/99">PR</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(document.body.textContent).toContain('github.com')
    w.unmount()
  })

  it('moving from one issue mention to another keeps the card and swaps content (no stuck loading)', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/issues/7/') return Promise.resolve({ id: 7, title: '问题A', status: '进行中', priority: 'P1', assignee_name: '张三', assignee_avatar: '', created_by_name: '李四', created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00' })
      if (url === '/api/issues/8/') return Promise.resolve({ id: 8, title: '问题B', status: '进行中', priority: 'P1', assignee_name: '李四', assignee_avatar: '', created_by_name: '张三', created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00' })
      return Promise.resolve({})
    })
    const container = makeContainer(
      '<a class="mention-issue" data-issue-id="7" href="/app/issues/7">#问题-007</a>' +
      '<a class="mention-issue" data-issue-id="8" href="/app/issues/8">#问题-008</a>'
    )
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    const [a, b] = Array.from(container.querySelectorAll('a'))
    vi.useFakeTimers()
    a!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()
    expect(document.body.textContent).toContain('问题A')
    // move A -> B directly while the card is visible
    a!.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: b }))
    b!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(document.body.textContent).toContain('问题B')
    expect(document.body.textContent).not.toContain('加载中')
    w.unmount()
  })
})
