// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import ChatBubble from '../app/components/chat/ChatBubble.vue'

const { apiMock, navigateToMock } = vi.hoisted(() => ({ apiMock: vi.fn(), navigateToMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))
mockNuxtImport('navigateTo', () => navigateToMock)

beforeEach(() => {
  apiMock.mockReset(); apiMock.mockResolvedValue({ results: [] })
  navigateToMock.mockReset()
})

describe('ChatBubble', () => {
  it('shows unread badge from useChat state', async () => {
    apiMock.mockResolvedValueOnce({ results: [
      { issue_id: 1, issue_title: 'A', unread_count: 2, last_comment: null },
      { issue_id: 2, issue_title: 'B', unread_count: 1, last_comment: null },
    ] })
    const w = await mountSuspended(ChatBubble)
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('[data-test="fab-badge"]').text()).toBe('3')
  })

  it('toggles panel open on FAB click', async () => {
    const w = await mountSuspended(ChatBubble)
    expect(w.find('[data-test="chat-panel"]').exists()).toBe(false)
    await w.find('[data-test="fab"]').trigger('click')
    expect(w.find('[data-test="chat-panel"]').exists()).toBe(true)
  })

  it('hides unread badge when there are no unread conversations', async () => {
    apiMock.mockResolvedValueOnce({ results: [] })
    const w = await mountSuspended(ChatBubble)
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('[data-test="fab-badge"]').exists()).toBe(false)
  })

  it('title links to issue detail (SPA nav) without closing the popup', async () => {
    apiMock.mockResolvedValueOnce({ results: [        // loadConversations
      { issue_id: 7, issue_title: '案件标题', unread_count: 0, last_comment: null },
    ] })
    apiMock.mockResolvedValueOnce([])                  // openConversation → comments
    const w = await mountSuspended(ChatBubble)
    await new Promise(r => setTimeout(r, 0))
    await w.find('[data-test="fab"]').trigger('click')           // 打开面板
    await w.find('[data-test="conv"]').trigger('click')          // 进入会话(thread 视图)
    await new Promise(r => setTimeout(r, 0))

    const title = w.find('[data-test="chat-title-link"]')
    expect(title.exists()).toBe(true)
    expect(title.text()).toBe('案件标题')

    await title.trigger('click')
    expect(navigateToMock).toHaveBeenCalledWith('/app/issues/7')   // SPA 导航到详情页
    expect(w.find('[data-test="chat-panel"]').exists()).toBe(true) // 弹窗保持打开
  })
})
