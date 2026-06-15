// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import InlineLinkCardItem from '../app/components/InlineLinkCardItem.vue'
import { clearIssuePreviewCache, clearGithubPreviewCache } from '../app/composables/useLinkPreview'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

beforeEach(() => { apiMock.mockReset(); clearIssuePreviewCache(); clearGithubPreviewCache(); document.body.innerHTML = '' })
afterEach(() => { vi.useRealTimers() })

describe('InlineLinkCardItem', () => {
  it('issue match fetches and renders the issue card', async () => {
    apiMock.mockResolvedValue({ id: 7, title: '登录页报错', status: '进行中', priority: 'P1', assignee_name: '张三', assignee_avatar: '', created_by_name: '李四', created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00' })
    const w = await mountSuspended(InlineLinkCardItem, { props: { match: { type: 'issue', issueId: '7' } } })
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/issues/7/')
    expect(w.text()).toContain('登录页报错')
    w.unmount()
  })
  it('external match renders a domain card without fetching', async () => {
    const w = await mountSuspended(InlineLinkCardItem, { props: { match: { type: 'external', url: 'https://example.com/x' } } })
    await flushPromises()
    expect(apiMock).not.toHaveBeenCalled()
    expect(w.text()).toContain('example.com')
    w.unmount()
  })
  it('github match fetches and renders the github card', async () => {
    apiMock.mockResolvedValue({ kind: 'pr', number: 42, title: 'PR标题', state: 'open', author_login: 'a', author_avatar: '', repo_full_name: 'o/r', html_url: 'u' })
    const w = await mountSuspended(InlineLinkCardItem, { props: { match: { type: 'github', url: 'https://github.com/o/r/pull/42' } } })
    await flushPromises()
    expect(w.text()).toContain('PR标题')
    w.unmount()
  })
  it('hovering an issue card opens an iframe popup after the delay', async () => {
    apiMock.mockResolvedValue({ id: 7, title: 'T', status: '进行中', priority: 'P1', assignee_name: '', assignee_avatar: '', created_by_name: '', created_at: '', updated_at: '' })
    const w = await mountSuspended(InlineLinkCardItem, { props: { match: { type: 'issue', issueId: '7' } } })
    await flushPromises()
    vi.useFakeTimers()
    await w.find('.link-preview-card').trigger('mouseenter')
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    const iframe = document.body.querySelector('iframe.ilc-iframe') as HTMLIFrameElement | null
    expect(iframe).toBeTruthy()
    expect(iframe!.getAttribute('src')).toBe('/app/issues/7')
    w.unmount()
  })
})
