// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { ref } from 'vue'
import IssueComments from '../app/components/issue/IssueComments.vue'

const { apiMock, authBox } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authBox: {
    user: { id: '1', name: '我', is_superuser: false },
    groups: [] as string[],
  },
}))

mockNuxtImport('useApi', () => () => ({ api: apiMock }))
mockNuxtImport('useAuth', () => () => ({
  user: ref(authBox.user),
  hasGroup: (g: string) => authBox.groups.includes(g),
}))

// MarkdownEditor/MarkdownView 依赖重(mention 拉用户列表、markdown-it),stub 掉
// 注意: 运行时模板不支持 TS 类型断言,这里必须是纯 JS 表达式
const stubs = {
  MarkdownEditor: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: `<textarea data-testid="editor" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
  },
  MarkdownView: { props: ['text'], template: '<div class="md-view">{{ text }}</div>' },
}

function comment(over: Record<string, unknown> = {}) {
  return {
    id: 1, author: 1, author_name: '张三', author_avatar: '',
    content: '第一条评论', created_at: '2026-06-11T10:00:00+08:00',
    updated_at: '2026-06-11T10:00:00+08:00', is_edited: false, ...over,
  }
}

const flush = () => new Promise<void>(resolve => setTimeout(resolve))

async function mount() {
  const w = await mountSuspended(IssueComments, {
    props: { issueId: 5 },
    global: { stubs },
  })
  await flush()
  return w
}

beforeEach(() => {
  apiMock.mockReset()
  authBox.user = { id: '1', name: '我', is_superuser: false }
  authBox.groups = []
})

describe('IssueComments', () => {
  it('renders comments returned by the API with count', async () => {
    apiMock.mockResolvedValue([
      comment({ id: 1, content: '第一条评论' }),
      comment({ id: 2, content: '第二条评论', is_edited: true }),
    ])
    const w = await mount()
    expect(apiMock).toHaveBeenCalledWith('/api/issues/5/comments/')
    expect(w.text()).toContain('评论 (2)')
    expect(w.text()).toContain('第一条评论')
    expect(w.text()).toContain('已编辑')
    w.unmount()
  })

  it('shows empty hint when there are no comments', async () => {
    apiMock.mockResolvedValue([])
    const w = await mount()
    expect(w.text()).toContain('暂无评论')
    w.unmount()
  })

  it('posts a new comment and appends it to the list', async () => {
    apiMock.mockImplementation((url: string, opts?: { method?: string; body?: { content: string } }) => {
      if (opts?.method === 'POST') {
        return Promise.resolve(comment({ id: 9, content: opts.body!.content }))
      }
      return Promise.resolve([])
    })
    const w = await mount()
    await w.find('[data-testid="new-comment"] [data-testid="editor"]').setValue('新评论内容')
    await w.find('[data-testid="submit-comment"]').trigger('click')
    await flush()
    expect(apiMock).toHaveBeenCalledWith('/api/issues/5/comments/', {
      method: 'POST', body: { content: '新评论内容' },
    })
    expect(w.text()).toContain('新评论内容')
    expect(w.text()).toContain('评论 (1)')
    // 发表成功后草稿编辑器应被清空
    expect((w.find('[data-testid="new-comment"] [data-testid="editor"]').element as HTMLTextAreaElement).value).toBe('')
    w.unmount()
  })

  it('hides edit/delete for non-author, shows delete only for admin', async () => {
    apiMock.mockResolvedValue([comment({ id: 1, author: 99, author_name: '别人' })])
    let w = await mount()
    expect(w.find('[data-testid="edit-comment"]').exists()).toBe(false)
    expect(w.find('[data-testid="delete-comment"]').exists()).toBe(false)
    w.unmount()

    authBox.groups = ['管理员']
    w = await mount()
    expect(w.find('[data-testid="edit-comment"]').exists()).toBe(false)
    expect(w.find('[data-testid="delete-comment"]').exists()).toBe(true)
    w.unmount()
  })
})
