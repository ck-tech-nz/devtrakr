// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

  it('does not duplicate when the WS echo races the optimistic sendReply', async () => {
    apiMock.mockResolvedValue({ id: 99, content: 'once' })  // POST(+markRead) 都返回同一条
    const w = await mountSuspended(Harness)
    await flushPromises()
    ;(w.vm.activeIssueId as any) = 5
    // echo 先到(自己发的回声),handleIncoming 先插入 id=99
    ;(w.vm.handleIncoming as Function)({ type: 'comment.new', issue_id: 5, issue_title: 'X', unread_count: 0, comment: { id: 99, content: 'once' } as any })
    // 随后 POST 解析,sendReply 不应重复插入同一 id
    await (w.vm.sendReply as Function)(5, 'once')
    await flushPromises()
    expect((w.vm.messages as any).length).toBe(1)
    w.unmount()
  })
})

describe('useChat WebSocket', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('connect opens a socket and routes comment.new to handleIncoming', async () => {
    vi.useFakeTimers()
    const sockets: any[] = []
    class FakeWS {
      url: string; onopen: any; onmessage: any; onclose: any; readyState = 1
      constructor(url: string) { this.url = url; sockets.push(this) }
      close() { this.readyState = 3 }
    }
    vi.stubGlobal('WebSocket', FakeWS as any)
    vi.stubGlobal('localStorage', { getItem: () => 'tok123' } as any)

    const w = await mountSuspended(Harness)
    ;(w.vm.connect as Function)()
    expect(sockets[0].url).toContain('/ws/chat/?token=tok123')

    sockets[0].onmessage({ data: JSON.stringify({ type: 'comment.new', issue_id: 3, issue_title: 'W', unread_count: 1, comment: { id: 1, content: 'x' } }) })
    expect((w.vm.conversations as any).find((v: any) => v.issue_id === 3)?.unread_count).toBe(1)

    ;(w.vm.disconnect as Function)()
    // 确认 disconnect 后不触发重连定时器
    vi.runAllTimers()
    expect(sockets.length).toBe(1)

    w.unmount()
  })
})
