// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import ChatBubble from '../app/components/chat/ChatBubble.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

beforeEach(() => { apiMock.mockReset(); apiMock.mockResolvedValue({ results: [] }) })

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
})
