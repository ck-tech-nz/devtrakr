// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import MarkdownHoverPreview from '../app/components/MarkdownHoverPreview.vue'
import { clearIssuePreviewCache } from '../app/composables/useLinkPreview'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

function makeContainer(html: string): HTMLElement {
  const el = document.createElement('div')
  el.innerHTML = html
  document.body.appendChild(el)
  return el
}

beforeEach(() => { apiMock.mockReset(); clearIssuePreviewCache(); document.body.innerHTML = '' })
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

  it('hovering an external link shows an iframe', async () => {
    const container = makeContainer('<a class="external-link" href="https://example.com/docs">example</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    const iframe = document.body.querySelector('iframe.lhc-iframe') as HTMLIFrameElement | null
    expect(iframe).toBeTruthy()
    expect(iframe!.getAttribute('src')).toBe('https://example.com/docs')
    w.unmount()
  })
})
