import type { Ref } from 'vue'

export interface Bulletin {
  id: number
  category: 'quote' | 'prompt' | 'pitfall' | 'value' | 'announcement'
  content: string
  source: string
  link_url: string
}

// 走马灯公告:模块级单例 + 订阅者引用计数,对标 useGatewayStatus。
// 全站只跑一个 5min 定时器,全部卸载后停。内容变化很少,5min 足够。
const POLL_INTERVAL_MS = 300_000

const items = ref<Bulletin[]>([])
const loading = ref(true)

let subscribers = 0
let pollTimer: ReturnType<typeof setInterval> | null = null
let inFlight: Promise<void> | null = null
let apiFn: (<T>(url: string, options?: any) => Promise<T>) | null = null
let authUser: Ref<{ id: string } | null> | null = null

async function fetchOnce(): Promise<void> {
  if (!apiFn || !authUser) return
  if (!authUser.value) return
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
  if (inFlight) return inFlight
  inFlight = (async () => {
    try {
      const data = await apiFn!<Bulletin[]>('/api/notifications/bulletins/active/')
      items.value = Array.isArray(data) ? data : []
    } catch {
      // 信息性接口 — 静默失败,保留上次数据
    } finally {
      loading.value = false
      inFlight = null
    }
  })()
  return inFlight
}

function onVisible() {
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
    fetchOnce()
  }
}

export function useBulletins() {
  if (!apiFn) {
    const { api } = useApi()
    apiFn = api
  }
  if (!authUser) {
    const { user } = useAuth()
    authUser = user as unknown as Ref<{ id: string } | null>
  }

  onMounted(async () => {
    subscribers++
    if (subscribers === 1) {
      await fetchOnce()
      pollTimer = setInterval(fetchOnce, POLL_INTERVAL_MS)
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', onVisible)
      }
    }
  })

  onUnmounted(() => {
    subscribers = Math.max(0, subscribers - 1)
    if (subscribers === 0) {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisible)
      }
    }
  })

  const announcements = computed(() => items.value.filter(b => b.category === 'announcement'))
  const rotating = computed(() => items.value.filter(b => b.category !== 'announcement'))

  return {
    announcements,
    rotating,
    loading: readonly(loading),
    refresh: fetchOnce,
  }
}
