// @vitest-environment nuxt
import { describe, it, expect, afterEach } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import LinkHoverCard from '../app/components/LinkHoverCard.vue'

const issue = {
  id: 7, title: '登录页报错', status: '进行中', priority: 'P1',
  assignee_name: '张三', assignee_avatar: '', created_by_name: '李四',
  created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00',
}

afterEach(() => { document.body.innerHTML = '' })

describe('LinkHoverCard (issue)', () => {
  it('renders the issue card fields', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 10, left: 10, type: 'issue',
      issue, issueLoading: false, issueError: false, url: null, iframeFallback: false,
    } })
    expect(document.body.textContent).toContain('登录页报错')
    expect(document.body.textContent).toContain('#问题-007')
    expect(document.body.textContent).toContain('进行中')
    expect(document.body.textContent).toContain('高') // P1 标签
    expect(document.body.textContent).toContain('张三')
    w.unmount()
  })

  it('shows a loading state', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'issue',
      issue: null, issueLoading: true, issueError: false, url: null, iframeFallback: false,
    } })
    expect(document.body.textContent).toContain('加载中')
    w.unmount()
  })

  it('shows an error state', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'issue',
      issue: null, issueLoading: false, issueError: true, url: null, iframeFallback: false,
    } })
    expect(document.body.textContent).toContain('加载失败')
    w.unmount()
  })

  it('renders nothing when not visible', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: false, top: 0, left: 0, type: 'issue',
      issue, issueLoading: false, issueError: false, url: null, iframeFallback: false,
    } })
    expect(document.body.querySelector('.link-hover-card')).toBeNull()
    w.unmount()
  })
})

describe('LinkHoverCard (external)', () => {
  it('renders an iframe with a safe sandbox', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'external',
      issue: null, issueLoading: false, issueError: false,
      url: 'https://example.com/docs', iframeFallback: false,
    } })
    const iframe = document.body.querySelector('iframe.lhc-iframe') as HTMLIFrameElement
    expect(iframe).toBeTruthy()
    expect(iframe.getAttribute('src')).toBe('https://example.com/docs')
    expect(iframe.getAttribute('sandbox')).toContain('allow-scripts')
    expect(iframe.getAttribute('sandbox')).not.toContain('allow-top-navigation')
    expect(iframe.getAttribute('referrerpolicy')).toBe('no-referrer')
    expect(document.body.textContent).toContain('example.com')
    w.unmount()
  })

  it('shows the fallback when framing is blocked', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'external',
      issue: null, issueLoading: false, issueError: false,
      url: 'https://blocked.example.com/', iframeFallback: true,
    } })
    expect(document.body.querySelector('iframe')).toBeNull()
    expect(document.body.textContent).toContain('不允许内嵌预览')
    w.unmount()
  })
})
