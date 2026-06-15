// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { useInlineLinkPreviews } from '../app/composables/useInlineLinkPreviews'
import { clearIssuePreviewCache } from '../app/composables/useLinkPreview'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

beforeEach(() => { apiMock.mockReset(); clearIssuePreviewCache(); document.body.innerHTML = '' })

const Harness = defineComponent({
  props: { html: { type: String, required: true } },
  setup(props) {
    const root = ref<HTMLElement | null>(null)
    const html = () => props.html
    useInlineLinkPreviews(root, html)
    return () => h('div', { ref: root, innerHTML: props.html })
  },
})

describe('useInlineLinkPreviews', () => {
  it('mounts an inline issue card after a mention-issue anchor', async () => {
    apiMock.mockResolvedValue({ id: 7, title: '内联问题标题', status: '进行中', priority: 'P1', assignee_name: '张三', assignee_avatar: '', created_by_name: '', created_at: '', updated_at: '' })
    const w = await mountSuspended(Harness, { props: { html: '<p>见 <a class="mention-issue" data-issue-id="7" href="/app/issues/7">#问题-007</a> 说明</p>' } })
    await flushPromises()
    await flushPromises()
    expect(w.element.querySelector('.link-preview-card')).toBeTruthy()
    expect(w.text()).toContain('内联问题标题')
    const anchor = w.element.querySelector('a.mention-issue') as HTMLElement
    expect(anchor.style.display).toBe('none')
    expect((w.element.querySelector('p') as HTMLElement).style.display).not.toBe('none')
    w.unmount()
  })

  it('hides the whole block when it contains only a reference', async () => {
    apiMock.mockResolvedValue({ id: 7, title: 'T', status: '进行中', priority: 'P1', assignee_name: '', assignee_avatar: '', created_by_name: '', created_at: '', updated_at: '' })
    const w = await mountSuspended(Harness, { props: { html: '<p><a class="mention-issue" data-issue-id="7" href="/app/issues/7">#问题-007</a></p>' } })
    await flushPromises(); await flushPromises()
    expect((w.element.querySelector('p') as HTMLElement).style.display).toBe('none')
    expect(w.element.querySelector('.link-preview-card')).toBeTruthy()
    w.unmount()
  })

  it('mounts a domain card for an external link and none for plain text', async () => {
    const w = await mountSuspended(Harness, { props: { html: '<p><a class="external-link" href="https://example.com/a">x</a> and plain</p>' } })
    await flushPromises()
    expect(w.element.querySelectorAll('.link-preview-card').length).toBe(1)
    expect(w.text()).toContain('example.com')
    w.unmount()
  })

  it('places the card after the list, not as an invalid child of <ul>', async () => {
    apiMock.mockResolvedValue({ id: 7, title: 'T', status: '进行中', priority: 'P1', assignee_name: '', assignee_avatar: '', created_by_name: '', created_at: '', updated_at: '' })
    const w = await mountSuspended(Harness, { props: { html: '<ul><li><a class="mention-issue" data-issue-id="7" href="/app/issues/7">#问题-007</a></li></ul>' } })
    await flushPromises(); await flushPromises()
    const ul = w.element.querySelector('ul') as HTMLElement
    expect(ul.querySelector('.link-preview-card')).toBeNull() // 不能塞进 <ul>(非法嵌套)
    expect((ul.nextElementSibling as HTMLElement)?.querySelector('.link-preview-card')).toBeTruthy() // 紧跟列表之后
    w.unmount()
  })

  it('keeps cards in document order for multiple refs in one list', async () => {
    apiMock.mockResolvedValue({ id: 1, title: 'T', status: '进行中', priority: 'P1', assignee_name: '', assignee_avatar: '', created_by_name: '', created_at: '', updated_at: '' })
    const w = await mountSuspended(Harness, { props: { html: '<ul><li><a class="mention-issue" data-issue-id="1" href="/app/issues/1">#问题-001</a></li><li><a class="mention-issue" data-issue-id="2" href="/app/issues/2">#问题-002</a></li></ul>' } })
    await flushPromises(); await flushPromises()
    const ul = w.element.querySelector('ul') as HTMLElement
    const first = ul.nextElementSibling as HTMLElement
    const second = first.nextElementSibling as HTMLElement
    expect(first.classList.contains('inline-link-card-host')).toBe(true)
    expect(second.classList.contains('inline-link-card-host')).toBe(true)
    w.unmount()
  })
})
