// 聊天会话状态:会话列表、未读、当前会话消息。WebSocket 连接在 Task 9 加入。
// 回复走现有 REST POST .../comments/(Fork B1),接收走 WS(Task 9)。
import { ISSUE_STATUS } from '~/constants/issueStatus'

export interface ChatComment {
  id: number; author: number | null; author_name: string | null; author_avatar: string
  content: string; created_at: string; updated_at: string; is_edited: boolean
}
export interface ChatConversation {
  issue_id: number; issue_title: string; issue_status: string; unread_count: number; last_comment: ChatComment | null
}
export interface ChatIncoming {
  type: 'comment.new'; issue_id: number; issue_title: string; issue_status: string; unread_count: number; comment: ChatComment
}

export function useChat() {
  const { api } = useApi()
  const { user } = useAuth()
  const meId = computed(() => (user.value ? Number(user.value.id) : null))
  const conversations = useState<ChatConversation[]>('chat-conversations', () => [])
  const unreadTotal = useState<number>('chat-unread-total', () => 0)
  const activeIssueId = useState<number | null>('chat-active', () => null)
  const messages = useState<ChatComment[]>('chat-messages', () => [])
  const lastIncoming = useState<ChatIncoming | null>('chat-last-incoming', () => null)
  // 面板开关与视图状态上提到 useState:手机端底部栏「消息」Tab 与桌面端 FAB 共享同一面板
  const open = useState<boolean>('chat-open', () => false)
  const view = useState<'list' | 'thread'>('chat-view', () => 'list')
  function toggleChat() { open.value = !open.value }

  function recomputeTotal() {
    unreadTotal.value = conversations.value.reduce((s, c) => s + (c.unread_count || 0), 0)
  }

  async function loadConversations() {
    const data = await api<{ results: ChatConversation[] }>('/api/issues/chat/conversations/')
    conversations.value = data.results || []
    recomputeTotal()
  }

  async function openConversation(issueId: number) {
    activeIssueId.value = issueId
    messages.value = await api<ChatComment[]>(`/api/issues/${issueId}/comments/`)
    await markRead(issueId)
  }

  async function markRead(issueId: number) {
    await api(`/api/issues/chat/conversations/${issueId}/read/`, { method: 'POST' })
    const conv = conversations.value.find(c => c.issue_id === issueId)
    if (conv) conv.unread_count = 0
    recomputeTotal()
  }

  async function sendReply(issueId: number, content: string) {
    const created = await api<ChatComment>(`/api/issues/${issueId}/comments/`, {
      method: 'POST', body: { content },
    })
    // 乐观插入也要去重:WS 回声(Enhancement B)可能在 POST 解析前就先插入了同一条,
    // 二者竞态;按 id 去重避免重复显示。
    if (activeIssueId.value === issueId && !messages.value.some(m => m.id === created.id)) {
      messages.value.push(created)
    }
    return created
  }

  // WS 事件入口(Task 9 wiring 调用)。
  function handleIncoming(ev: ChatIncoming) {
    // 已关闭的问题不进会话列表,也不弹提示
    if (ev.issue_status === ISSUE_STATUS.CLOSED) return

    const isOwn = meId.value != null && ev.comment.author === meId.value
    const active = activeIssueId.value === ev.issue_id

    // 预览条 + 提示音:仅他人消息、且不在当前会话时才触发(自己发的不打扰自己)
    if (!isOwn && !active) lastIncoming.value = ev

    // 会话列表始终更新(置顶 + 刷新末条),这样自己从问题页发的评论也会实时回显到自己的列表
    let conv = conversations.value.find(c => c.issue_id === ev.issue_id)
    if (!conv) {
      conv = { issue_id: ev.issue_id, issue_title: ev.issue_title, issue_status: ev.issue_status, unread_count: 0, last_comment: ev.comment }
    } else {
      conv.last_comment = ev.comment
      conv.issue_status = ev.issue_status  // 状态可能已变,刷新
    }
    conv.unread_count = active ? 0 : ev.unread_count
    conversations.value = [conv, ...conversations.value.filter(c => c.issue_id !== ev.issue_id)]
    recomputeTotal()

    if (active) {
      // 去重:自己发的可能已被 sendReply 乐观插入,WS 回推时按 id 跳过,避免重复
      if (!messages.value.some(m => m.id === ev.comment.id)) messages.value.push(ev.comment)
      if (!isOwn) markRead(ev.issue_id)  // 他人消息推进服务端已读指针;自己的服务端已自动已读
    }
  }

  let ws: WebSocket | null = null
  let retry = 0
  let closedByUs = false

  function wsUrl() {
    const token = (typeof localStorage !== 'undefined' && localStorage.getItem('access_token')) || ''
    // 显式 WS 基址优先(dev 直连后端,绕过不转发 upgrade 的 dev proxy);
    // 留空则同源(prod 经前置反代转发 upgrade)。
    const base = (useRuntimeConfig().public.wsBase as string) || ''
    if (base) return `${base.replace(/\/$/, '')}/ws/chat/?token=${token}`
    const proto = (typeof location !== 'undefined' && location.protocol === 'https:') ? 'wss' : 'ws'
    const host = typeof location !== 'undefined' ? location.host : ''
    return `${proto}://${host}/ws/chat/?token=${token}`
  }

  function connect() {
    if (typeof WebSocket === 'undefined') return
    // 防止重复开启：已处于 OPEN 或 CONNECTING 时直接跳过（重连路径在旧 socket CLOSED 后才调用，不受影响）
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    closedByUs = false
    ws = new WebSocket(wsUrl())
    ws.onopen = () => { retry = 0 }
    ws.onmessage = (e: MessageEvent) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev?.type === 'comment.new') handleIncoming(ev as ChatIncoming)
      } catch { /* 忽略格式错误的消息 */ }
    }
    ws.onclose = () => {
      if (closedByUs) return
      // Token 刷新委托给 useApi 的 REST-401 流程：重连时从 localStorage 读取最新 access_token，
      // 任意 REST 请求触发 401 刷新后，下次重连即可自愈。
      // 已知边界：标签页空闲超过 token 有效期（约 2h）且期间无 REST 流量时，
      // WS 会循环重连直到某次 REST 请求刷新 token 为止。
      // 注意：不在此处调用 refreshAccessToken()——其失败路径会跳转 /login，
      // 在瞬态断网时会误退登录。
      retry = Math.min(retry + 1, 6)
      setTimeout(connect, Math.min(1000 * 2 ** retry, 30000))
    }
  }

  function disconnect() {
    closedByUs = true
    ws?.close()
    ws = null
  }

  return { conversations, unreadTotal, activeIssueId, messages, lastIncoming, open, view, toggleChat,
           loadConversations, openConversation, markRead, sendReply, handleIncoming,
           connect, disconnect }
}
