type WizardState = 'idle' | 'analyzing' | 'drafting' | 'error'

type StepStatus = 'pending' | 'running' | 'done' | 'error'

type StepProgress = {
  step: 1 | 2 | 3
  label: string
  status: StepStatus
}

export type WizardDraft = {
  title: string
  description: string
  repro_steps: string
  expected_behavior: string
  priority: 'P0' | 'P1' | 'P2' | 'P3'
  module: string
  labels: string[]
  follow_up_questions: string[]
  inferred_env: string
}

export type DuplicateItem = {
  id: number
  title: string
  status: string
  reason: string
}

const INITIAL_STEPS: StepProgress[] = [
  { step: 1, label: 'AI 正在理解描述与截图', status: 'pending' },
]

async function refreshAccessToken(): Promise<string | null> {
  if (typeof localStorage === 'undefined') return null
  const refresh = localStorage.getItem('refresh_token')
  if (!refresh) return null
  try {
    const resp = await fetch('/api/auth/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
    if (!resp.ok) return null
    const data = await resp.json()
    if (data?.access) {
      localStorage.setItem('access_token', data.access)
      return data.access
    }
  } catch {
    return null
  }
  return null
}

async function getValidAccessToken(): Promise<string | null> {
  if (typeof localStorage === 'undefined') return null
  const token = localStorage.getItem('access_token')
  if (!token) return null
  // 解析 JWT 的 exp 字段;若不足 60s 即将过期,主动刷新
  // 注:无法解析时 (例如格式异常) 继续使用,让服务端 401 触发再刷新
  try {
    const segments = token.split('.')
    if (segments.length >= 2 && segments[1]) {
      const payload = JSON.parse(atob(segments[1]))
      const expMs = payload.exp * 1000
      if (expMs - Date.now() < 60_000) {
        return await refreshAccessToken()
      }
    }
  } catch {
    // 令牌格式异常 — 继续使用,服务端会以 401 处理
  }
  return token
}

export function useAiWizard() {
  const state = ref<WizardState>('idle')
  const steps = ref<StepProgress[]>(structuredClone(INITIAL_STEPS))
  const draft = ref<WizardDraft | null>(null)
  const errorMessage = ref<string>('')
  const duplicates = ref<DuplicateItem[]>([])

  let abortController: AbortController | null = null

  function reset() {
    state.value = 'idle'
    steps.value = structuredClone(INITIAL_STEPS)
    draft.value = null
    errorMessage.value = ''
    duplicates.value = []
    abortController?.abort()
    abortController = null
  }

  async function doFetch(
    token: string | null,
    params: { description: string; project: string; attachment_ids?: string[] },
  ): Promise<Response> {
    return fetch('/api/issues/ai-draft/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        description: params.description,
        project: params.project,
        attachment_ids: params.attachment_ids || [],
      }),
      signal: abortController!.signal,
    })
  }

  async function start(params: { description: string; project: string; attachment_ids?: string[] }) {
    reset()
    state.value = 'analyzing'
    abortController = new AbortController()

    let token = await getValidAccessToken()
    let resp: Response
    try {
      resp = await doFetch(token, params)
      // 服务端返回 401 时尝试刷新令牌后重试一次 (SSE 无法中途切换 token,所以只能整体重发)
      if (resp.status === 401) {
        token = await refreshAccessToken()
        if (token) {
          resp = await doFetch(token, params)
        }
      }
    } catch (e: any) {
      state.value = 'error'
      errorMessage.value = e?.message || '网络错误，请重试'
      return
    }

    if (!resp.ok || !resp.body) {
      state.value = 'error'
      errorMessage.value = `请求失败 (${resp.status})`
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // Split SSE frames: blank line separates events
        let idx
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          handleFrame(frame)
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        state.value = 'error'
        errorMessage.value = e?.message || '流读取失败'
      }
    }

    // 流意外结束但既无 draft 也无 error 事件，视为分析失败避免界面卡死
    if (state.value === 'analyzing' && draft.value === null) {
      state.value = 'error'
      errorMessage.value = '分析中断，请重试'
    }
  }

  function handleFrame(frame: string) {
    // Parse "event: <name>\ndata: <json>"
    const lines = frame.split('\n')
    let event = 'message'
    let data = ''
    for (const ln of lines) {
      if (ln.startsWith('event:')) event = ln.slice(6).trim()
      else if (ln.startsWith('data:')) data = ln.slice(5).trim()
    }
    if (!data) return
    let payload: any
    try { payload = JSON.parse(data) } catch { return }

    if (event === 'step') {
      const s = steps.value.find(x => x.step === payload.step)
      if (s) s.status = (payload.status as StepStatus) || 'done'
    } else if (event === 'draft') {
      draft.value = payload as WizardDraft
      state.value = 'drafting'
    } else if (event === 'duplicates') {
      duplicates.value = (payload.items || []) as DuplicateItem[]
    } else if (event === 'error') {
      const s = steps.value.find(x => x.step === payload.step)
      if (s) s.status = 'error'
      state.value = 'error'
      errorMessage.value = payload.message || 'AI 分析失败'
    }
    // 'done' is a no-op signal — the stream is finished
  }

  function abort() {
    abortController?.abort()
    abortController = null
  }

  return { state, steps, draft, duplicates, errorMessage, start, reset, abort }
}
