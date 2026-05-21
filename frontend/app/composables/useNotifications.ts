export interface NotificationItem {
  id: string
  notification_type: string
  title: string
  content: string
  source_user_name: string | null
  source_issue_id: number | null
  source_issue_title: string | null
  is_read: boolean
  read_at: string | null
  created_at: string
}

interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const POLL_INTERVAL = 60_000

export function useNotifications() {
  const { api } = useApi()
  const unreadCount = useState<number>('notification_unread_count', () => 0)
  const notifications = useState<NotificationItem[]>('notification_list', () => [])
  let pollTimer: ReturnType<typeof setInterval> | null = null

  async function fetchUnreadCount() {
    try {
      const data = await api<{ count: number }>('/api/notifications/unread-count/')
      unreadCount.value = data.count
    } catch {
      // silently ignore polling errors
    }
  }

  async function fetchNotifications(params: { is_read?: string; page?: number } = {}) {
    const query = new URLSearchParams()
    if (params.is_read !== undefined) query.set('is_read', params.is_read)
    if (params.page) query.set('page', String(params.page))
    const qs = query.toString()
    const url = `/api/notifications/${qs ? '?' + qs : ''}`
    return await api<PaginatedResponse<NotificationItem>>(url)
  }

  async function fetchRecent() {
    const data = await api<PaginatedResponse<NotificationItem>>('/api/notifications/?page_size=5')
    notifications.value = data.results
    return data
  }

  async function markRead(id: string) {
    await api(`/api/notifications/${id}/read/`, { method: 'POST' })
    const item = notifications.value.find(n => n.id === id)
    if (item) item.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }

  async function markAllRead() {
    await api('/api/notifications/read-all/', { method: 'POST' })
    notifications.value.forEach(n => { n.is_read = true })
    unreadCount.value = 0
  }

  async function deleteNotification(id: string) {
    await api(`/api/notifications/${id}/`, { method: 'DELETE' })
    notifications.value = notifications.value.filter(n => n.id !== id)
  }

  function startPolling() {
    if (pollTimer) return
    fetchUnreadCount()
    pollTimer = setInterval(fetchUnreadCount, POLL_INTERVAL)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    unreadCount,
    notifications,
    fetchUnreadCount,
    fetchNotifications,
    fetchRecent,
    markRead,
    markAllRead,
    deleteNotification,
    startPolling,
    stopPolling,
  }
}
