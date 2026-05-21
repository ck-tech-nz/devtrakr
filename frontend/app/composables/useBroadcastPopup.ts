import type { NotificationItem } from '~/composables/useNotifications'

interface BroadcastListResponse {
  count: number
  next: string | null
  previous: string | null
  results: NotificationItem[]
}

export function useBroadcastPopup() {
  const { api } = useApi()
  const { alert } = useDialog()
  const { markRead } = useNotifications()
  const { md } = useMentionMarkdown()
  // Single-fire guard, shared across the SSR/CSR boundary. Resets on full page reload.
  const started = useState<boolean>('broadcast_popup_started', () => false)

  async function start() {
    if (started.value) return
    started.value = true
    let res: BroadcastListResponse
    try {
      res = await api<BroadcastListResponse>(
        '/api/notifications/?notification_type=broadcast&is_read=false&page_size=20',
      )
    } catch {
      // Silent fail — bell still surfaces unread state.
      return
    }
    const queue = res.results || []
    for (const n of queue) {
      try {
        await alert({
          title: n.title,
          htmlBody: md.render(n.content || ''),
          persistent: true,
          confirmText: '知道了',
          size: 'xl',
        })
      } catch {
        // If the dialog ever rejects, stop the queue — it's an unexpected state.
        return
      }
      try {
        await markRead(n.id)
      } catch {
        // Network or auth error on markRead — keep the queue going so other
        // broadcasts can still be seen and dismissed this session. The unread
        // one will pop again next time.
      }
    }
  }

  return { start }
}
