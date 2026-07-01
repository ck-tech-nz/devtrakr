// 问题动态弹幕数据源:开启时先 REST 回放最近 2h,再开 WebSocket 接实时。
// 广播为单一全局组(后端按 view_issue 鉴权),前端只读。连接/去重为模块级单例
// (全应用至多一条弹幕连接),queue 经 useState 跨组件共享,由弹幕栏组件消费。
export interface DanmakuEvent {
  kind: 'created' | 'completed'
  issue_id: number
  issue_number: string
  title: string
  status: string
  actor_name: string | null
  occurred_at: string | null
}

let ws: WebSocket | null = null
let retry = 0
let closedByUs = false
const seen = new Set<string>()

export function useIssueDanmaku() {
  const { api } = useApi()
  const queue = useState<DanmakuEvent[]>('danmaku-queue', () => [])

  function enqueue(e: DanmakuEvent) {
    const k = `${e.kind}:${e.issue_id}`
    if (seen.has(k)) return  // 回放项与随后的实时项去重
    seen.add(k)
    queue.value = [...queue.value, e]
    // 缓冲上限:标签页隐藏、渲染暂停时避免无界增长
    if (queue.value.length > 200) queue.value = queue.value.slice(-200)
    if (seen.size > 400) seen.clear()
  }

  async function loadBackfill() {
    try {
      const data = await api<DanmakuEvent[]>('/api/issues/danmaku/recent/')
      // 后端倒序返回;按时间正序(旧→新)灌入,滚动顺序符合直觉
      for (const e of [...data].reverse()) enqueue(e)
    } catch {
      /* 回放失败不影响实时 */
    }
  }

  function wsUrl() {
    const token = (typeof localStorage !== 'undefined' && localStorage.getItem('access_token')) || ''
    const base = (useRuntimeConfig().public.wsBase as string) || ''
    if (base) return `${base.replace(/\/$/, '')}/ws/danmaku/?token=${token}`
    const proto = (typeof location !== 'undefined' && location.protocol === 'https:') ? 'wss' : 'ws'
    const host = typeof location !== 'undefined' ? location.host : ''
    return `${proto}://${host}/ws/danmaku/?token=${token}`
  }

  function connect() {
    if (typeof WebSocket === 'undefined') return
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    closedByUs = false
    ws = new WebSocket(wsUrl())
    ws.onopen = () => { retry = 0 }
    ws.onmessage = (e: MessageEvent) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev?.kind === 'created' || ev?.kind === 'completed') enqueue(ev as DanmakuEvent)
      } catch { /* 忽略格式错误的消息 */ }
    }
    ws.onclose = () => {
      if (closedByUs) return
      retry = Math.min(retry + 1, 6)
      setTimeout(connect, Math.min(1000 * 2 ** retry, 30000))
    }
  }

  async function enable() {
    queue.value = []
    seen.clear()
    await loadBackfill()
    connect()
  }

  function disable() {
    closedByUs = true
    ws?.close()
    ws = null
    queue.value = []
    seen.clear()
  }

  return { queue, enable, disable }
}
