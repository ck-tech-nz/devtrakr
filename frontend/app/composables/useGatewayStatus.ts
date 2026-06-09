import type { Ref } from 'vue'

// 电话线路状态:模块级单例 + 订阅者引用计数,对标 useUptimeMonitors。
// 首页只挂一个组件,但保持同一模式:全站只跑一个 15s 定时器,全部卸载后停。
export interface GatewayLine {
  id: number
  name: string
  proxy_ip_list: string
  port: number
  online: boolean
  ping_latency_ms: number
  active_calls: number
  today_calls: number
  today_answered: number
  today_answer_rate: number
  ping_error?: string
  last_ping_at: string
}

interface GatewayPayload {
  configured: boolean
  stale?: boolean
  fetched_at?: string
  lines?: GatewayLine[]
  error?: string
}

const POLL_INTERVAL_MS = 15_000

const lines = ref<GatewayLine[]>([])
const configured = ref(true) // 乐观:首拉前按已配置渲染 loading,拿到 false 再显示"未配置"
const stale = ref(false)
const fetchedAt = ref('')
const loading = ref(true)

let subscribers = 0
let pollTimer: ReturnType<typeof setInterval> | null = null
let inFlight: Promise<void> | null = null
let apiFn: (<T>(url: string, options?: any) => Promise<T>) | null = null
let authUser: Ref<{ id: string } | null> | null = null

async function fetchOnce(): Promise<void> {
  if (!apiFn || !authUser) return
  if (!authUser.value) return
  // 后台标签跳过,避免白跑
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
  if (inFlight) return inFlight
  inFlight = (async () => {
    try {
      const data = await apiFn!<GatewayPayload>('/api/dashboard/gateway-status/')
      configured.value = data?.configured ?? false
      lines.value = Array.isArray(data?.lines) ? data.lines : []
      stale.value = !!data?.stale
      fetchedAt.value = data?.fetched_at ?? ''
    } catch {
      // 信息性接口 — 静默失败,保留上次数据
    } finally {
      loading.value = false
      inFlight = null
    }
  })()
  return inFlight
}

// 标签重新可见时立即刷新一次(不必等满 15s)
function onVisible() {
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
    fetchOnce()
  }
}

export function useGatewayStatus() {
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

  return {
    lines: readonly(lines),
    configured: readonly(configured),
    stale: readonly(stale),
    fetchedAt: readonly(fetchedAt),
    loading: readonly(loading),
    refresh: fetchOnce,
  }
}
