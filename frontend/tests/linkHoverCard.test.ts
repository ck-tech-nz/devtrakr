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
      issue, issueLoading: false, issueError: false, url: null,
      github: null, githubLoading: false,
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
      issue: null, issueLoading: true, issueError: false, url: null,
      github: null, githubLoading: false,
    } })
    expect(document.body.textContent).toContain('加载中')
    w.unmount()
  })

  it('shows an error state', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'issue',
      issue: null, issueLoading: false, issueError: true, url: null,
      github: null, githubLoading: false,
    } })
    expect(document.body.textContent).toContain('加载失败')
    w.unmount()
  })

  it('renders nothing when not visible', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: false, top: 0, left: 0, type: 'issue',
      issue, issueLoading: false, issueError: false, url: null,
      github: null, githubLoading: false,
    } })
    expect(document.body.querySelector('.link-hover-card')).toBeNull()
    w.unmount()
  })
})

describe('LinkHoverCard (external)', () => {
  it('renders a domain card with an open-in-new-tab link (no iframe)', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'external',
      issue: null, issueLoading: false, issueError: false,
      github: null, githubLoading: false,
      url: 'https://example.com/docs',
    } })
    expect(document.body.querySelector('iframe')).toBeNull()
    expect(document.body.textContent).toContain('example.com')
    const open = document.body.querySelector('a.lhc-open') as HTMLAnchorElement
    expect(open.getAttribute('target')).toBe('_blank')
    expect(open.getAttribute('rel')).toContain('noopener')
    w.unmount()
  })
})

describe('LinkHoverCard (github)', () => {
  const pr = {
    kind: 'pr' as const, number: 42, title: '添加悬停预览', state: 'merged' as const,
    author_login: 'alice', author_avatar: '', repo_full_name: 'octocat/hello',
    html_url: 'https://github.com/octocat/hello/pull/42',
  }
  it('renders a github PR card with state and author', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'github',
      issue: null, issueLoading: false, issueError: false,
      github: pr, githubLoading: false, url: pr.html_url,
    } })
    expect(document.body.textContent).toContain('添加悬停预览')
    expect(document.body.textContent).toContain('#42')
    expect(document.body.textContent).toContain('octocat/hello')
    expect(document.body.textContent).toContain('alice')
    expect(document.body.textContent?.toLowerCase()).toContain('merged')
    w.unmount()
  })
  it('shows a loading state for github', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'github',
      issue: null, issueLoading: false, issueError: false,
      github: null, githubLoading: true, url: pr.html_url,
    } })
    expect(document.body.textContent).toContain('加载中')
    w.unmount()
  })
})
