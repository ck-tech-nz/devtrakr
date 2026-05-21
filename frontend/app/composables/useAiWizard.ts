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

export type AttachmentRef = { id: string; file_name: string; file_url: string }

export type Turn =
  | { id: string; role: 'user'; text: string; attachments: AttachmentRef[] }
  | {
      id: string
      role: 'ai-thinking'
      /** initial/revise 是旧的两端点路径; chat 是新对话式路径 */
      kind: 'initial' | 'revise' | 'chat'
      steps: StepProgress[]
      errorMessage: string
      /** AI 判定用户意图; 控制 brand status 副标题 */
      intent?: 'update' | 'submit' | 'ask'
      /** 服务端 emit 的非致命警告 (如截图超大被丢弃 / 视觉模型回退到文字) */
      warnings?: string[]
    }
  | {
      id: string
      role: 'ai-draft'
      version: number
      draft: WizardDraft
      attachmentIds: string[]
      /** 该 draft 已被提交为正式 issue 时, 记下 ISS 号让卡片永久 morph 成 success 视图.
       * 同时 useAiWizard.messages 会在 checkpoint 时清空, LLM 下一轮看不到本会话, 即"新对话" */
      submittedIssueId?: number
      /** POST 响应里的 assignee, 仅用于 success 视图的副标题 */
      submittedAssignee?: string | null
    }
  | { id: string; role: 'ai-ask'; question: string }
  | {
      id: string
      role: 'ai-dup-hint'
      candidates: Array<{ id: number; title: string; status: string; reason: string }>
    }
  | {
      /** Hard session boundary: rendered as a pill in thread, also resets attachment scope + draft version */
      id: string
      role: 'session-divider'
      issueId: number
    }

/** 发送给后端 /ai-draft/chat/ 的对话历史; system 由服务端控制不能从这里送 */
export type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
}

const INITIAL_STEPS_INITIAL: StepProgress[] = [
  { step: 1, label: 'AI 正在理解描述与截图', status: 'pending' },
]
const INITIAL_STEPS_REVISE: StepProgress[] = [
  { step: 1, label: 'AI 正在更新草稿', status: 'pending' },
]
const INITIAL_STEPS_CHAT: StepProgress[] = [
  { step: 1, label: 'AI 正在思考', status: 'pending' },
]

const STORAGE_KEY = 'ai-wizard:turns'
const STORAGE_MSG_KEY = 'ai-wizard:messages'
const MAX_TURNS = 60   // 60 个 turn (含 user/thinking/draft/ask) 大约 20 轮, 够多
const MAX_MESSAGES = 20  // 10 轮 user+assistant; 与后端 _truncate_messages 上限对齐
const STORAGE_CAP_BYTES = 64 * 1024  // 单 key 不超过 64KB; LocalStorage 单域 5MB 配额

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
    // 令牌格式异常 — 继续使用,服务端 401 触发再刷新
  }
  return token
}

function genId(): string {
  // 简单单调 ID, 不需要 UUID 强度; thread 内部 :key 用
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function useAiWizard() {
  const state = ref<WizardState>('idle')
  const turns = ref<Turn[]>([])
  /** LLM 对话历史 (chat 路径用) - user/assistant 交替; 后端无状态, 每次把完整数组送过去 */
  const messages = ref<ChatMessage[]>([])
  const errorMessage = ref<string>('')
  // LLM 判定用户在确认时, 递增此 counter; 父组件 watch 它触发 StepDraft.triggerSubmit
  const submitIntentCounter = ref(0)

  let abortController: AbortController | null = null

  // ---------- LocalStorage 持久化 ----------
  // 挂载时 restore (仅在 idle 状态有效, 避免覆盖正在进行的流)
  if (typeof window !== 'undefined') {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          // 把任何残留的 ai-thinking running 状态降级为 error, 防止 UI 永远转圈
          turns.value = parsed.map((t: any) => {
            if (t?.role === 'ai-thinking' && Array.isArray(t.steps)) {
              return {
                ...t,
                steps: t.steps.map((s: any) =>
                  s.status === 'running' || s.status === 'pending' ? { ...s, status: 'error' } : s,
                ),
                errorMessage: t.errorMessage || (t.steps.some((s: any) => s.status === 'running') ? '页面刷新中断' : ''),
              }
            }
            return t
          })
          if (turns.value.length) state.value = 'drafting'
        }
      }
    } catch {
      // 损坏的 JSON, 静默清除
      try { localStorage.removeItem(STORAGE_KEY) } catch {}
    }
    // 同样 restore messages (用于 chat 路径下次发消息时把完整历史送给 LLM)
    try {
      const rawMsg = localStorage.getItem(STORAGE_MSG_KEY)
      if (rawMsg) {
        const parsedMsg = JSON.parse(rawMsg)
        if (Array.isArray(parsedMsg)) {
          messages.value = parsedMsg.filter((m: any) =>
            m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string'
          )
        }
      }
    } catch {
      try { localStorage.removeItem(STORAGE_MSG_KEY) } catch {}
    }

    // 任何 turns 变化都 debounced 写回 (200ms)
    let persistTimer: ReturnType<typeof setTimeout> | null = null
    watch(turns, (v) => {
      if (persistTimer) clearTimeout(persistTimer)
      persistTimer = setTimeout(() => {
        try {
          // 超出上限时截断最早的 turns; 保留最近 MAX_TURNS 个
          let payload = v.slice(-MAX_TURNS)
          let serialized = JSON.stringify(payload)
          // 极端情况下单个 turn 内容过大, 二分截到 cap 以下
          while (serialized.length > STORAGE_CAP_BYTES && payload.length > 1) {
            payload = payload.slice(Math.floor(payload.length / 2))
            serialized = JSON.stringify(payload)
          }
          if (serialized.length <= STORAGE_CAP_BYTES) {
            localStorage.setItem(STORAGE_KEY, serialized)
          }
        } catch {
          // 配额满 / 隐私模式 - 静默
        }
      }, 200)
    }, { deep: true })

    // messages 单独 debounced 持久化, 截掉超过 MAX_MESSAGES 的最早历史
    let persistMsgTimer: ReturnType<typeof setTimeout> | null = null
    watch(messages, (v) => {
      if (persistMsgTimer) clearTimeout(persistMsgTimer)
      persistMsgTimer = setTimeout(() => {
        try {
          let payload = v.slice(-MAX_MESSAGES)
          // 截后首条若是 assistant, 再丢一条让首条仍是 user (与后端协议对齐)
          while (payload.length && payload[0]!.role !== 'user') payload = payload.slice(1)
          const serialized = JSON.stringify(payload)
          if (serialized.length <= STORAGE_CAP_BYTES) {
            localStorage.setItem(STORAGE_MSG_KEY, serialized)
          }
        } catch {}
      }, 200)
    }, { deep: true })
  }

  // ---------- 基础 reducers ----------
  function appendTurn(turn: Turn) {
    turns.value.push(turn)
  }

  function reset() {
    state.value = 'idle'
    turns.value = []
    messages.value = []
    errorMessage.value = ''
    abortController?.abort()
    abortController = null
    if (typeof window !== 'undefined') {
      try { localStorage.removeItem(STORAGE_KEY) } catch {}
      try { localStorage.removeItem(STORAGE_MSG_KEY) } catch {}
    }
  }

  function abort() {
    abortController?.abort()
    abortController = null
  }

  // ---------- 会话边界 ----------
  /** 上一条 session-divider 之后的 index, 没有就是 0. checkpoint 后再发的消息都在新 session 内. */
  function sessionStartIndex(): number {
    for (let i = turns.value.length - 1; i >= 0; i--) {
      if (turns.value[i]!.role === 'session-divider') return i + 1
    }
    return 0
  }

  // ---------- 派生 ----------
  const latestDraft = computed<{ turn: Turn & { role: 'ai-draft' }; index: number } | null>(() => {
    for (let i = turns.value.length - 1; i >= 0; i--) {
      const t = turns.value[i]
      if (t && t.role === 'ai-draft') return { turn: t as Turn & { role: 'ai-draft' }, index: i }
    }
    return null
  })
  const draft = computed<WizardDraft | null>(() => latestDraft.value?.turn.draft || null)
  const draftVersion = computed<number>(() => latestDraft.value?.turn.version || 0)

  // ---------- SSE 共享解析 ----------
  type FrameOutcome = { kind: 'draft'; draft: WizardDraft } | { kind: 'submit' } | null

  function applyFrameToThinkingTurn(thinking: Turn & { role: 'ai-thinking' }, event: string, payload: any): FrameOutcome {
    if (event === 'step') {
      const s = thinking.steps.find(x => x.step === payload.step)
      if (s) s.status = (payload.status as StepStatus) || 'done'
      // 若服务端给了新的 label (例如 revise 用 "AI 正在更新草稿"), 同步过来
      if (s && payload.label) s.label = payload.label
    } else if (event === 'draft') {
      thinking.intent = 'update'
      return { kind: 'draft', draft: payload as WizardDraft }
    } else if (event === 'submit') {
      thinking.intent = 'submit'
      // 把 thinking 步骤标完成
      for (const s of thinking.steps) {
        if (s.status === 'running' || s.status === 'pending') s.status = 'done'
      }
      return { kind: 'submit' }
    } else if (event === 'error') {
      const s = thinking.steps.find(x => x.step === payload.step)
      if (s) s.status = 'error'
      thinking.errorMessage = payload.message || 'AI 分析失败'
      state.value = 'error'
      errorMessage.value = thinking.errorMessage
    }
    return null
  }

  async function consumeSseStream(
    resp: Response,
    thinkingTurn: Turn & { role: 'ai-thinking' },
    onDraft: (d: WizardDraft, attachmentIds: string[]) => void,
    attachmentIds: string[],
  ) {
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let gotTerminal = false   // draft 或 submit 任一发生即视为已收到终态

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let idx
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          // Parse SSE frame
          const lines = frame.split('\n')
          let event = 'message'
          let data = ''
          for (const ln of lines) {
            if (ln.startsWith('event:')) event = ln.slice(6).trim()
            else if (ln.startsWith('data:')) data = ln.slice(5).trim()
          }
          if (!data) continue
          let payload: any
          try { payload = JSON.parse(data) } catch { continue }
          const outcome = applyFrameToThinkingTurn(thinkingTurn, event, payload)
          if (outcome?.kind === 'draft') {
            gotTerminal = true
            onDraft(outcome.draft, attachmentIds)
          } else if (outcome?.kind === 'submit') {
            gotTerminal = true
            state.value = 'drafting'
            submitIntentCounter.value++
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        state.value = 'error'
        errorMessage.value = e?.message || '流读取失败'
        thinkingTurn.errorMessage = errorMessage.value
        const running = thinkingTurn.steps.find(s => s.status === 'running' || s.status === 'pending')
        if (running) running.status = 'error'
      }
    }

    if (!gotTerminal && state.value === 'analyzing') {
      state.value = 'error'
      errorMessage.value = '分析中断，请重试'
      thinkingTurn.errorMessage = errorMessage.value
    }
  }

  // ---------- start (首发或重描述后的第一条) ----------
  async function start(params: { description: string; project: string; attachment_ids?: string[]; attachments?: AttachmentRef[] }) {
    // 首发清空 thread (重描述也会先走 reset 再 start)
    reset()
    state.value = 'analyzing'
    errorMessage.value = ''
    abortController = new AbortController()

    // 1) 追加 user turn
    appendTurn({
      id: genId(),
      role: 'user',
      text: params.description,
      attachments: params.attachments || [],
    })
    // 2) 追加 thinking turn (initial kind)
    const thinking: Turn & { role: 'ai-thinking' } = {
      id: genId(),
      role: 'ai-thinking',
      kind: 'initial',
      steps: structuredClone(INITIAL_STEPS_INITIAL),
      errorMessage: '',
    }
    appendTurn(thinking)

    let token = await getValidAccessToken()
    let resp: Response
    try {
      resp = await doFetch('/api/issues/ai-draft/', token, {
        description: params.description,
        project: params.project,
        attachment_ids: params.attachment_ids || [],
      })
      if (resp.status === 401) {
        token = await refreshAccessToken()
        if (token) {
          resp = await doFetch('/api/issues/ai-draft/', token, {
            description: params.description,
            project: params.project,
            attachment_ids: params.attachment_ids || [],
          })
        }
      }
    } catch (e: any) {
      state.value = 'error'
      errorMessage.value = e?.message || '网络错误，请重试'
      thinking.errorMessage = errorMessage.value
      thinking.steps[0]!.status = 'error'
      return
    }

    if (!resp.ok || !resp.body) {
      state.value = 'error'
      errorMessage.value = `请求失败 (${resp.status})`
      thinking.errorMessage = errorMessage.value
      thinking.steps[0]!.status = 'error'
      return
    }

    await consumeSseStream(resp, thinking, (newDraft, attIds) => {
      appendTurn({
        id: genId(),
        role: 'ai-draft',
        version: 1,
        draft: newDraft,
        attachmentIds: attIds,
      })
      state.value = 'drafting'
    }, params.attachment_ids || [])
  }

  // ---------- revise (基于现有 draft 多轮修订) ----------
  async function revise(params: { instruction: string; project: string; attachment_ids?: string[]; attachments?: AttachmentRef[] }) {
    const last = latestDraft.value
    if (!last) {
      // 没有基础 draft, 不该被调到; 调用方应该走 start
      return start({
        description: params.instruction,
        project: params.project,
        attachment_ids: params.attachment_ids,
        attachments: params.attachments,
      })
    }

    state.value = 'analyzing'
    errorMessage.value = ''
    abortController?.abort()
    abortController = new AbortController()

    // 追加 user + ai-thinking(revise kind)
    appendTurn({
      id: genId(),
      role: 'user',
      text: params.instruction,
      attachments: params.attachments || [],
    })
    const thinking: Turn & { role: 'ai-thinking' } = {
      id: genId(),
      role: 'ai-thinking',
      kind: 'revise',
      steps: structuredClone(INITIAL_STEPS_REVISE),
      errorMessage: '',
    }
    appendTurn(thinking)

    let token = await getValidAccessToken()
    let resp: Response
    const body = {
      current_draft: last.turn.draft,
      instruction: params.instruction,
      project: params.project,
      attachment_ids: params.attachment_ids || [],
    }
    try {
      resp = await doFetch('/api/issues/ai-draft/revise/', token, body)
      if (resp.status === 401) {
        token = await refreshAccessToken()
        if (token) resp = await doFetch('/api/issues/ai-draft/revise/', token, body)
      }
    } catch (e: any) {
      state.value = 'error'
      errorMessage.value = e?.message || '网络错误，请重试'
      thinking.errorMessage = errorMessage.value
      thinking.steps[0]!.status = 'error'
      return
    }

    if (!resp.ok || !resp.body) {
      state.value = 'error'
      errorMessage.value = `请求失败 (${resp.status})`
      thinking.errorMessage = errorMessage.value
      thinking.steps[0]!.status = 'error'
      return
    }

    const prevVersion = last.turn.version
    await consumeSseStream(resp, thinking, (newDraft, attIds) => {
      appendTurn({
        id: genId(),
        role: 'ai-draft',
        version: prevVersion + 1,
        draft: newDraft,
        attachmentIds: attIds,
      })
      state.value = 'drafting'
    }, params.attachment_ids || [])
  }

  // ---------- chat (对话式, 替代 start/revise 的新主路径) ----------
  async function chat(params: { text: string; project: string; attachments?: AttachmentRef[] }) {
    state.value = 'analyzing'
    errorMessage.value = ''
    abortController?.abort()
    abortController = new AbortController()

    const userText = params.text
    const userAtts = params.attachments || []

    // 1. user turn + user message
    appendTurn({
      id: genId(),
      role: 'user',
      text: userText,
      attachments: userAtts,
    })
    messages.value.push({ role: 'user', content: userText })

    // 2. ai-thinking turn (chat kind)
    const thinking: Turn & { role: 'ai-thinking' } = {
      id: genId(),
      role: 'ai-thinking',
      kind: 'chat',
      steps: structuredClone(INITIAL_STEPS_CHAT),
      errorMessage: '',
    }
    appendTurn(thinking)

    // 3. 调 /ai-draft/chat/, 把完整 messages 历史送过去
    // 累计 attachment_ids: 仅本会话 (最近一次 session-divider 之后) 所有 user turn 的图片.
    // 跨 checkpoint 不带 - 上个 issue 的截图不应该污染下一个 issue 的草稿.
    const start = sessionStartIndex()
    const cumulativeIds = Array.from(new Set(
      turns.value
        .slice(start)
        .filter(t => t.role === 'user')
        .flatMap(t => (t as Turn & { role: 'user' }).attachments.map(a => a.id))
    ))
    let token = await getValidAccessToken()
    const body = {
      messages: messages.value.slice(-MAX_MESSAGES),
      project: params.project,
      attachment_ids: userAtts.map(a => a.id),     // 本轮新图 → LLM vision
      conversation_attachment_ids: cumulativeIds,  // 全程累计 → draft.description 渲染
    }
    let resp: Response
    try {
      resp = await doFetch('/api/issues/ai-draft/chat/', token, body)
      if (resp.status === 401) {
        token = await refreshAccessToken()
        if (token) resp = await doFetch('/api/issues/ai-draft/chat/', token, body)
      }
    } catch (e: any) {
      state.value = 'error'
      errorMessage.value = e?.message || '网络错误，请重试'
      thinking.errorMessage = errorMessage.value
      thinking.steps[0]!.status = 'error'
      return
    }

    if (!resp.ok || !resp.body) {
      state.value = 'error'
      errorMessage.value = `请求失败 (${resp.status})`
      thinking.errorMessage = errorMessage.value
      thinking.steps[0]!.status = 'error'
      return
    }

    await consumeChatStream(resp, thinking, userAtts.map(a => a.id))
  }

  /** chat 路径专用 SSE 消费 - 处理 draft/ask/submit/error 4 种终态事件 */
  async function consumeChatStream(
    resp: Response,
    thinking: Turn & { role: 'ai-thinking' },
    lastUserAttachmentIds: string[],
  ) {
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let gotTerminal = false

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let idx
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          const lines = frame.split('\n')
          let event = 'message'
          let data = ''
          for (const ln of lines) {
            if (ln.startsWith('event:')) event = ln.slice(6).trim()
            else if (ln.startsWith('data:')) data = ln.slice(5).trim()
          }
          if (!data) continue
          let payload: any
          try { payload = JSON.parse(data) } catch { continue }

          if (event === 'step') {
            const s = thinking.steps.find(x => x.step === payload.step)
            if (s) {
              s.status = (payload.status as StepStatus) || 'done'
              if (payload.label) s.label = payload.label
            }
          } else if (event === 'warning') {
            // 服务端非致命警告: 截图过大 / 视觉调用失败 / etc. 累积挂到 thinking turn
            const text = String(payload.message || '').trim()
            if (text) {
              if (!thinking.warnings) thinking.warnings = []
              thinking.warnings.push(text)
            }
          } else if (event === 'dup') {
            // 重复检测命中 - 追加独立的提示气泡, 不阻塞已经显示的 draft
            const cands = Array.isArray(payload.candidates) ? payload.candidates : []
            if (cands.length) {
              appendTurn({
                id: genId(),
                role: 'ai-dup-hint',
                candidates: cands,
              })
            }
          } else if (event === 'draft') {
            gotTerminal = true
            thinking.intent = 'update'
            // 版本号按本会话独立递增 - 跨 checkpoint 重新从 v1 开始, 而非接着上个 issue 的 v2/v3
            const sessionStart = sessionStartIndex()
            let prevVersion = 0
            for (let i = turns.value.length - 1; i >= sessionStart; i--) {
              const t = turns.value[i]
              if (t && t.role === 'ai-draft') { prevVersion = t.version; break }
            }
            const newDraft = payload as WizardDraft
            appendTurn({
              id: genId(),
              role: 'ai-draft',
              version: prevVersion + 1,
              draft: newDraft,
              attachmentIds: lastUserAttachmentIds,
            })
            messages.value.push({
              role: 'assistant',
              content: JSON.stringify({ action: 'draft', ...newDraft }),
            })
            state.value = 'drafting'
          } else if (event === 'ask') {
            gotTerminal = true
            thinking.intent = 'ask'
            const q = String(payload.question || '').trim()
            if (q) {
              appendTurn({ id: genId(), role: 'ai-ask', question: q })
              messages.value.push({
                role: 'assistant',
                content: JSON.stringify({ action: 'ask', question: q }),
              })
            }
            // ask 后等用户回答, 不视为 error 也不结束对话
            state.value = 'drafting'
          } else if (event === 'submit') {
            gotTerminal = true
            thinking.intent = 'submit'
            for (const s of thinking.steps) {
              if (s.status === 'running' || s.status === 'pending') s.status = 'done'
            }
            messages.value.push({
              role: 'assistant',
              content: JSON.stringify({ action: 'submit' }),
            })
            state.value = 'drafting'
            submitIntentCounter.value++
          } else if (event === 'error') {
            thinking.errorMessage = payload.message || 'AI 调用失败'
            const r = thinking.steps.find(s => s.status === 'running' || s.status === 'pending')
            if (r) r.status = 'error'
            state.value = 'error'
            errorMessage.value = thinking.errorMessage
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        state.value = 'error'
        errorMessage.value = e?.message || '流读取失败'
        thinking.errorMessage = errorMessage.value
        const r = thinking.steps.find(s => s.status === 'running' || s.status === 'pending')
        if (r) r.status = 'error'
      }
    }

    if (!gotTerminal && state.value === 'analyzing') {
      state.value = 'error'
      errorMessage.value = '响应中断，请重试'
      thinking.errorMessage = errorMessage.value
    }
  }

  // ---------- 通用 doFetch ----------
  async function doFetch(url: string, token: string | null, body: any): Promise<Response> {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal: abortController!.signal,
    })
  }

  // ---------- 局部 mutators (供 UI 在用户编辑草稿时用) ----------
  function updateDraftInPlace(turnId: string, patch: Partial<WizardDraft>) {
    const t = turns.value.find(x => x.id === turnId)
    if (t && t.role === 'ai-draft') {
      t.draft = { ...t.draft, ...patch }
    }
  }

  /** 追加一条 user turn 但不触发 LLM (供 affirmative auto-submit 快捷路径用) */
  function appendUserTurn(text: string, attachments: AttachmentRef[] = []) {
    appendTurn({
      id: genId(),
      role: 'user',
      text,
      attachments,
    })
  }

  /** 一个 issue 提交成功后调一下: 把对应 draft turn 标 sealed, 同时清空 LLM 历史
   * (下一条 user 消息 = 全新会话, LLM 不再受之前 issue 的上下文污染).
   * thread 里所有 turn 不动 - 用户仍能滚动回看历史。 */
  function checkpoint(turnId: string, issueId: number, assignee?: string | null) {
    const t = turns.value.find(x => x.id === turnId)
    if (t && t.role === 'ai-draft') {
      t.submittedIssueId = issueId
      t.submittedAssignee = assignee ?? null
    }
    // 视觉上插入一条 session-divider, 同时也是 sessionStartIndex() 用来切分本会话的标记 -
    // 让"图片归属本轮"、"版本号本会话独立"两件事都建立在这条 turn 上.
    turns.value.push({
      id: genId(),
      role: 'session-divider',
      issueId,
    })
    // 关键: 清空 messages, 下次 chat() 调用时 LLM 看到的是空历史 + 新一条 user 消息
    messages.value = []
    state.value = 'idle'
    errorMessage.value = ''
    abortController?.abort()
    abortController = null
  }

  return {
    state,
    turns,
    messages,
    draft,           // 向后兼容: 等同 latestDraft.draft
    draftVersion,
    latestDraft,
    errorMessage,
    chat,
    start,           // @deprecated: 改用 chat()
    revise,          // @deprecated: 改用 chat()
    reset,
    abort,
    updateDraftInPlace,
    appendUserTurn,
    checkpoint,
    sessionStartIndex,
    submitIntentCounter,
  }
}
