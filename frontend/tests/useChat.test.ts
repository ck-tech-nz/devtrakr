// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { clearNuxtState } from '#imports'
import { useChat } from '../app/composables/useChat'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

beforeEach(() => {
  apiMock.mockReset()
  // useState 使用全局 key，测试间需清除共享状态。
  clearNuxtState(['chat-conversations', 'chat-unread-total', 'chat-active', 'chat-messages', 'chat-last-incoming'])
})

function conv(over = {}) {
  return { issue_id: 1, issue_title: 'T', unread_count: 2, last_comment: null, ...over }
}

// 最小宿主组件驱动 useChat，使 useState 在组件 setup 上下文中运行。
// Vue 在 expose 时自动解包 Ref，所以 w.vm.foo 直接是值（不需要 .value）。
const Harness = defineComponent({
  setup() {
    return useChat()
  },
  render: () => h('div'),
})

describe('useChat REST', () => {
  it('loads conversations and totals unread', async () => {
    apiMock.mockResolvedValueOnce({ results: [conv({ issue_id: 1, unread_count: 2 }), conv({ issue_id: 2, unread_count: 3 })] })
    const w = await mountSuspended(Harness)
    await (w.vm.loadConversations as () => Promise<void>)()
    await flushPromises()
    expect((w.vm.conversations as any).length).toBe(2)
    expect(w.vm.unreadTotal as any).toBe(5)
    w.unmount()
  })

  it('handleIncoming bumps conversation + unread when not active', async () => {
    const w = await mountSuspended(Harness)
    await flushPromises()
    ;(w.vm.handleIncoming as Function)({ type: 'comment.new', issue_id: 9, issue_title: 'Z', unread_count: 1, comment: { id: 5, content: 'hi' } as any })
    expect(w.vm.unreadTotal as any).toBe(1)
    expect((w.vm.conversations as any)[0].issue_id).toBe(9)
    w.unmount()
  })
})
