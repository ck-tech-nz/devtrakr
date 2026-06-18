// 聊天会话状态:会话列表、未读、当前会话消息。WebSocket 连接在 Task 9 加入。
// 回复走现有 REST POST .../comments/(Fork B1),接收走 WS(Task 9)。
export interface ChatComment {
  id: number; author: number | null; author_name: string | null; author_avatar: string
  content: string; created_at: string; updated_at: string; is_edited: boolean
}
export interface ChatConversation {
  issue_id: number; issue_title: string; unread_count: number; last_comment: ChatComment | null
}
export interface ChatIncoming {
  type: 'comment.new'; issue_id: number; issue_title: string; unread_count: number; comment: ChatComment
}

export function useChat() {
  const { api } = useApi()
  const conversations = useState<ChatConversation[]>('chat-conversations', () => [])
  const unreadTotal = useState<number>('chat-unread-total', () => 0)
  const activeIssueId = useState<number | null>('chat-active', () => null)
  const messages = useState<ChatComment[]>('chat-messages', () => [])
  const lastIncoming = useState<ChatIncoming | null>('chat-last-incoming', () => null)

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
    if (activeIssueId.value === issueId) messages.value.push(created)
    return created
  }

  // WS 事件入口(Task 9 wiring 调用)。
  function handleIncoming(ev: ChatIncoming) {
    lastIncoming.value = ev
    if (activeIssueId.value === ev.issue_id) {
      messages.value.push(ev.comment)
      markRead(ev.issue_id)
      return
    }
    let conv = conversations.value.find(c => c.issue_id === ev.issue_id)
    if (!conv) {
      conv = { issue_id: ev.issue_id, issue_title: ev.issue_title, unread_count: 0, last_comment: ev.comment }
      conversations.value.unshift(conv)
    } else {
      conv.last_comment = ev.comment
      conversations.value = [conv, ...conversations.value.filter(c => c.issue_id !== ev.issue_id)]
    }
    conv.unread_count = ev.unread_count
    recomputeTotal()
  }

  let ws: WebSocket | null = null
  let retry = 0
  let closedByUs = false

  function wsUrl() {
    const token = (typeof localStorage !== 'undefined' && localStorage.getItem('access_token')) || ''
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

  return { conversations, unreadTotal, activeIssueId, messages, lastIncoming,
           loadConversations, openConversation, markRead, sendReply, handleIncoming,
           connect, disconnect }
}
