// @vitest-environment nuxt
import { describe, it, expect, afterEach } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import LinkPreviewCard from '../app/components/LinkPreviewCard.vue'

const issue = { id: 7, title: '登录页报错', status: '进行中', priority: 'P1', assignee_name: '张三', assignee_avatar: '', created_by_name: '李四', created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00' }
const pr = { kind: 'pr' as const, number: 42, title: '加预览', state: 'merged' as const, author_login: 'alice', author_avatar: '', repo_full_name: 'octocat/hello', html_url: 'https://github.com/octocat/hello/pull/42' }

afterEach(() => { document.body.innerHTML = '' })

describe('LinkPreviewCard', () => {
  it('renders an issue card (no teleport — inline root)', async () => {
    const w = await mountSuspended(LinkPreviewCard, { props: { type: 'issue', issue, issueLoading: false, issueError: false, github: null, githubLoading: false, url: null } })
    expect(w.find('.link-preview-card').exists()).toBe(true)
    expect(w.text()).toContain('登录页报错')
    expect(w.text()).toContain('#问题-007')
    expect(w.text()).toContain('进行中')
    expect(w.text()).toContain('高')
    expect(w.find('.lpc-avatar-fallback').text()).toBe('张')
    w.unmount()
  })
  it('renders a github card', async () => {
    const w = await mountSuspended(LinkPreviewCard, { props: { type: 'github', issue: null, issueLoading: false, issueError: false, github: pr, githubLoading: false, url: pr.html_url } })
    expect(w.text()).toContain('加预览')
    expect(w.text()).toContain('#42')
    expect(w.text().toLowerCase()).toContain('merged')
    w.unmount()
  })
  it('renders a domain card for external', async () => {
    const w = await mountSuspended(LinkPreviewCard, { props: { type: 'external', issue: null, issueLoading: false, issueError: false, github: null, githubLoading: false, url: 'https://example.com/x' } })
    expect(w.find('iframe').exists()).toBe(false)
    expect(w.text()).toContain('example.com')
    expect(w.find('a.lpc-open').attributes('target')).toBe('_blank')
    w.unmount()
  })
  it('shows issue loading state', async () => {
    const w = await mountSuspended(LinkPreviewCard, { props: { type: 'issue', issue: null, issueLoading: true, issueError: false, github: null, githubLoading: false, url: null } })
    expect(w.text()).toContain('加载中')
    w.unmount()
  })
})
