import type { Ref } from 'vue'

// SystemAlertBanner 与 UptimeMonitorsHomeWidget 之前各跑一个 5s 定时器拉同一个接口,
// 首页同时挂载就成对出现重复请求。这里抽成模块级单例 + 订阅者引用计数:
// 只要至少有一个组件在用,就只跑一个定时器;全部卸载后定时器自动停。
export interface UptimeMonitor {
  id: number
  project: number
  project_name: string
  name: string
  environment: string
  last_status: string
  last_up_at: string | null
  outage_started_at: string | null
}

const POLL_INTERVAL_MS = 60_000

const monitors = ref<UptimeMonitor[]>([])
let subscribers = 0
let pollTimer: ReturnType<typeof setInterval> | null = null
let inFlight: Promise<void> | null = null

// useApi / useAuth 期望在 setup 上下文里取,这里在第一次订阅时懒捕获,
// 之后 setInterval 回调里复用同一份引用
let apiFn: (<T>(url: string, options?: any) => Promise<T>) | null = null
let authUser: Ref<{ id: string } | null> | null = null

async function fetchOnce(): Promise<void> {
  if (!apiFn || !authUser) return
  if (!authUser.value) return
  // 页面切到后台时跳过 — 与原组件行为保持一致,避免后台标签也在白跑
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
  if (inFlight) return inFlight
  inFlight = (async () => {
    try {
      const data = await apiFn!<UptimeMonitor[]>('/api/uptime/monitors/')
      monitors.value = data ?? []
    } catch {
      // 信息性接口 — 静默失败,不打扰用户
    } finally {
      inFlight = null
    }
  })()
  return inFlight
}

export function useUptimeMonitors() {
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
    }
    // 第 2+ 个订阅者无需再发请求,直接复用现有 monitors ref
  })

  onUnmounted(() => {
    subscribers = Math.max(0, subscribers - 1)
    if (subscribers === 0 && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  })

  return {
    monitors: readonly(monitors),
    refresh: fetchOnce,
  }
}
