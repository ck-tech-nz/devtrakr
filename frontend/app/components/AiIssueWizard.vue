<template>
  <div
    class="ai-wizard"
    :class="{
      'ai-wizard--chat': inChatMode,
      'ai-wizard--draft-pending': draftPending,
    }"
  >
    <h2 v-if="!inChatMode" class="hero-title">有什么我可以帮你的？</h2>

    <!-- 清空对话按钮 — chat 模式下右上角 floating, 永远可见. 用 LiquidGlass 实现 iOS 26 折射效果 -->
    <LiquidGlass
      v-if="inChatMode"
      class="clear-btn"
      title="清空当前对话, 重新开始"
      @click="onClearConversation"
    >
      <UIcon name="i-heroicons-x-mark" class="w-3.5 h-3.5" />
      <span class="clear-btn-label">清空对话</span>
    </LiquidGlass>

    <!-- 对话 thread -->
    <div v-if="inChatMode" ref="threadEl" class="thread">
      <template v-for="turn in wizard.turns.value" :key="turn.id">
        <!-- 用户消息 -->
        <div v-if="turn.role === 'user'" class="msg msg--user">
          <div v-if="turn.attachments.length" class="msg-attach-row">
            <button
              v-for="att in turn.attachments"
              :key="att.id"
              type="button"
              class="msg-attach"
              :class="{ 'msg-attach--image': isImage(att.file_name) }"
              :title="isImage(att.file_name) ? `预览 ${att.file_name}` : att.file_name"
              :disabled="!isImage(att.file_name)"
              @click="isImage(att.file_name) && openPreview(att)"
            >
              <img v-if="isImage(att.file_name)" :src="att.file_url" :alt="att.file_name" />
              <template v-else>
                <UIcon name="i-heroicons-document" class="w-3.5 h-3.5" />
                <span class="msg-attach-name">{{ att.file_name }}</span>
              </template>
            </button>
          </div>
          <div v-if="turn.text" class="msg-bubble">{{ turn.text }}</div>
        </div>

        <!-- AI 思考过程 -->
        <div v-else-if="turn.role === 'ai-thinking'" class="msg msg--ai">
          <div class="msg-brand">
            <span class="msg-brand-mark">
              <UIcon name="i-heroicons-sparkles" class="w-3 h-3" />
            </span>
            <span class="msg-brand-name">DevTrakr</span>
            <span
              v-if="isThinkingTurnRunning(turn)"
              class="msg-brand-status"
            >
              <span class="brand-pulse" /> {{ turn.kind === 'revise' ? '正在更新' : '正在思考' }}
            </span>
            <span
              v-else-if="turn.intent === 'submit'"
              class="msg-brand-status msg-brand-status--draft"
            >
              ✓ 已确认,正在提交
            </span>
            <span
              v-else-if="!turn.errorMessage"
              class="msg-brand-status msg-brand-status--done"
            >
              {{ turn.kind === 'revise' ? '已更新' : '已分析' }}
            </span>
          </div>

          <div class="msg-thinking">
            <div
              v-for="s in turn.steps"
              :key="s.step"
              class="think-line"
              :class="`think-line--${s.status}`"
            >
              <UIcon v-if="s.status === 'done'" name="i-heroicons-check-circle" class="w-3.5 h-3.5 think-icon think-icon--done" />
              <UIcon v-else-if="s.status === 'error'" name="i-heroicons-exclamation-circle" class="w-3.5 h-3.5 think-icon think-icon--error" />
              <span v-else class="think-dot" />
              <span class="think-label">{{ s.label }}</span>
              <span v-if="s.status === 'running'" class="think-caret" aria-hidden="true">▍</span>
            </div>
          </div>

          <div v-if="turn.errorMessage" class="msg-error">
            <UIcon name="i-heroicons-exclamation-triangle" class="w-3.5 h-3.5" />
            <span>{{ turn.errorMessage }}</span>
          </div>

          <div v-if="turn.errorMessage" class="msg-actions">
            <button type="button" class="msg-action msg-action--primary" @click="onRetry">重试</button>
            <button type="button" class="msg-action" @click="onBackToDescribe">重新描述</button>
          </div>

          <!-- 非致命警告 (截图过大被丢 / 视觉模型回退) - 黄色提示, 不阻塞流程 -->
          <div v-if="turn.warnings && turn.warnings.length" class="msg-warnings">
            <div v-for="(w, i) in turn.warnings" :key="i" class="msg-warning">
              <UIcon name="i-heroicons-exclamation-triangle" class="w-3.5 h-3.5" />
              <span>{{ w }}</span>
            </div>
          </div>
        </div>

        <!-- AI 反问 (chat 路径 ask 动作): 信息不全时主动追问一个最关键的问题 -->
        <div v-else-if="turn.role === 'ai-ask'" class="msg msg--ai msg--ai-ask">
          <div class="msg-brand">
            <span class="msg-brand-mark">
              <UIcon name="i-heroicons-question-mark-circle" class="w-3 h-3" />
            </span>
            <span class="msg-brand-name">DevTrakr</span>
            <span class="msg-brand-status msg-brand-status--ask">想确认一下</span>
          </div>
          <div class="msg-ask-bubble">{{ turn.question }}</div>
        </div>

        <!-- AI 查重提示 (chat 路径 dup 事件): 不拦截, 仅供对比 -->
        <div v-else-if="turn.role === 'ai-dup-hint'" class="msg msg--ai msg--ai-dup">
          <div class="msg-brand">
            <span class="msg-brand-mark">
              <UIcon name="i-heroicons-document-duplicate" class="w-3 h-3" />
            </span>
            <span class="msg-brand-name">DevTrakr</span>
            <span class="msg-brand-status msg-brand-status--dup">我注意到类似 issue</span>
          </div>
          <div class="msg-dup-card">
            <NuxtLink
              v-for="c in turn.candidates"
              :key="c.id"
              :to="`/app/issues/${c.id}`"
              target="_blank"
              class="dup-item"
            >
              <span class="dup-id">ISS-{{ String(c.id).padStart(3, '0') }}</span>
              <span class="dup-title">{{ c.title }}</span>
              <span
                class="dup-status"
                :class="`dup-status--${c.status === '已解决' || c.status === '已关闭' || c.status === '已发布' ? 'closed' : 'open'}`"
              >{{ c.status }}</span>
            </NuxtLink>
            <div class="dup-hint">仅供参考, 可点链接对比 · 也可直接提交新建</div>
          </div>
        </div>

        <!-- AI 草稿 (可能有多张, 最新可编辑) -->
        <div v-else-if="turn.role === 'ai-draft'" class="msg msg--ai msg--ai-draft">
          <div class="msg-brand">
            <span class="msg-brand-mark">
              <UIcon name="i-heroicons-sparkles" class="w-3 h-3" />
            </span>
            <span class="msg-brand-name">DevTrakr</span>
            <span class="msg-brand-status msg-brand-status--draft">
              {{ turn.version > 1 ? `草稿 v${turn.version} 已就绪` : '草稿已就绪' }}
            </span>
            <span v-if="!isLatestDraft(turn)" class="msg-brand-status msg-brand-status--stale">
              · 已被新版替代
            </span>
          </div>
          <div class="msg-draft-card" :class="{ 'msg-draft-card--stale': !isLatestDraft(turn) }">
            <StepDraft
              :ref="(el) => captureEditableDraftRef(el, turn.id)"
              :draft="turn.draft"
              :projects="projects"
              :initial-project-id="lastAnalyzedProject"
              :modules="modules"
              :users="users"
              :valid-labels="validLabels"
              :attachment-ids="turn.attachmentIds"
              :original-input="lastOriginalInput"
              :submitting="submitting && isLatestDraft(turn)"
              :submit-error="isLatestDraft(turn) ? submitError : ''"
              :success-issue-id="isLatestDraft(turn) ? successIssueId : null"
              :success-assignee="successAssignee"
              :editable="isTurnEditable(turn)"
              :version="turn.version"
              @submit="onSubmit"
              @back="onBackToDescribe"
              @reset="onReset"
            />
          </div>
        </div>
      </template>
    </div>

    <!-- Composer -->
    <div class="composer-slot">
      <StepDescribe
        ref="describeRef"
        :projects="projects"
        :default-project-id="defaultProjectId"
        :analyzing="wizard.state.value === 'analyzing'"
        :revise-mode="hasDraft && !successIssueId"
        :ask-reply-mode="lastTurnIsAsk"
        @analyze="onAnalyze"
        @cancel="onBackToDescribe"
      />
    </div>

    <!-- 缩略图预览弹窗 -->
    <UModal v-model:open="previewOpen" :ui="{ content: 'sm:max-w-4xl' }">
      <template #content>
        <div class="preview-modal">
          <div class="preview-header">
            <span class="preview-title" :title="previewAttachment?.file_name">{{ previewAttachment?.file_name }}</span>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="previewOpen = false" />
          </div>
          <div class="preview-body" @click.self="previewOpen = false">
            <img v-if="previewAttachment" :src="previewAttachment.file_url" :alt="previewAttachment.file_name" />
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
import StepDescribe from './AiIssueWizard/StepDescribe.vue'
import StepDraft from './AiIssueWizard/StepDraft.vue'
import LiquidGlass from './LiquidGlass.vue'
import type { Turn, AttachmentRef } from '~/composables/useAiWizard'

const emit = defineEmits<{ created: [issueId: number] }>()

const { api } = useApi()
const { user } = useAuth()

const defaultProjectId = computed(() => user.value?.default_project?.id || null)

const projects = ref<{ id: string; name: string }[]>([])
const modules = ref<string[]>([])
const users = ref<{ id: string; name: string }[]>([])
const validLabels = ref<string[]>([])
const lastAnalyzedProject = ref<string>('')
const lastOriginalInput = ref<string>('')

const describeRef = ref<InstanceType<typeof StepDescribe> | null>(null)
const threadEl = ref<HTMLElement | null>(null)
// 最新可编辑的 StepDraft 实例 - affirmative auto-submit 用
const editableDraftRef = ref<{ triggerSubmit: () => void } | null>(null)
function captureEditableDraftRef(el: any, turnId: string) {
  if (turnId === latestDraftId.value) editableDraftRef.value = el
}

const wizard = useAiWizard()
const submitting = ref(false)
const submitError = ref('')
const successIssueId = ref<number | null>(null)
const successAssignee = ref<string | null>(null)

// thread 内是否有任意 turn
const inChatMode = computed(() => wizard.turns.value.length > 0)
// 是否已经至少有一张 draft (决定 composer 走 start 还是 revise)
const hasDraft = computed(() => !!wizard.latestDraft.value)
// 草稿待提交 (sticky composer 触发条件)
const draftPending = computed(() => inChatMode.value && !successIssueId.value)
// 最后一条 turn 是 AI 反问 - composer placeholder 切到"回答 AI 的问题…"
const lastTurnIsAsk = computed(() => {
  const last = wizard.turns.value[wizard.turns.value.length - 1]
  return !!last && last.role === 'ai-ask'
})

// 最新 ai-draft turn 的 id — 只有它可编辑/提交
const latestDraftId = computed(() => wizard.latestDraft.value?.turn.id || null)
/** 是否是最新那张 draft (无论是否已提交) — 用于把 success 视图/submit 反馈定位到正确卡片 */
function isLatestDraft(turn: Turn): boolean {
  return turn.role === 'ai-draft' && turn.id === latestDraftId.value
}
/** 表单是否仍可编辑/可点提交按钮 — 提交成功后整张卡进入 success 视图, 不再编辑 */
function isTurnEditable(turn: Turn): boolean {
  return isLatestDraft(turn) && !successIssueId.value
}

function isThinkingTurnRunning(turn: Turn & { role: 'ai-thinking' }): boolean {
  return turn.steps.some(s => s.status === 'running' || s.status === 'pending') && !turn.errorMessage
}

// 缩略图预览
const previewOpen = ref(false)
const previewAttachment = ref<AttachmentRef | null>(null)
function openPreview(att: AttachmentRef) {
  previewAttachment.value = att
  previewOpen.value = true
}

function isImage(name: string): boolean {
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(name || '')
}

onMounted(async () => {
  const [projectData, settingsData, usersData] = await Promise.all([
    api<any>('/api/projects/').catch(() => ({ results: [] })),
    api<any>('/api/settings/').catch(() => ({ modules: [] })),
    api<any[]>('/api/users/choices/').catch(() => []),
  ])
  projects.value = (projectData.results || projectData || []).map((p: any) => ({ id: String(p.id), name: p.name }))
  modules.value = settingsData.modules || []
  validLabels.value = Object.keys(settingsData.labels || {})
  users.value = (usersData || []).map((u: any) => ({ id: String(u.id), name: u.name || u.username }))
})

function onAnalyze(payload: { description: string; project: string; attachments: AttachmentRef[] }) {
  lastAnalyzedProject.value = payload.project
  lastOriginalInput.value = payload.description
  // 统一走对话式 chat - LLM 拿到完整 messages 历史, 自行判定 draft/ask/submit
  wizard.chat({
    text: payload.description,
    project: payload.project,
    attachments: payload.attachments,
  })
}

// LLM 在 revise 路径中判定为"submit"意图时, useAiWizard 递增 submitIntentCounter,
// 这里 watch 它 → 模拟点击最新草稿卡的"提交 Issue"按钮
watch(() => wizard.submitIntentCounter.value, (n, prev) => {
  if (n > (prev ?? 0)) {
    nextTick(() => editableDraftRef.value?.triggerSubmit())
  }
})

function onRetry() {
  // 错误恢复: 把最后一条 user turn 的内容再发一次
  const lastUser = [...wizard.turns.value].reverse().find(t => t.role === 'user') as
    | (Turn & { role: 'user' })
    | undefined
  if (!lastUser || !lastAnalyzedProject.value) return

  // 删除上一条出错的 ai-thinking turn, 让 retry 看起来干净 (不堆砌错误)
  const last = wizard.turns.value[wizard.turns.value.length - 1]
  if (last && last.role === 'ai-thinking' && last.errorMessage) {
    wizard.turns.value.pop()
    // 还要去掉对应的 user turn (它会被 start/revise 重新追加)
    const newLast = wizard.turns.value[wizard.turns.value.length - 1]
    if (newLast && newLast.role === 'user') wizard.turns.value.pop()
  }

  onAnalyze({
    description: lastUser.text,
    project: lastAnalyzedProject.value,
    attachments: lastUser.attachments,
  })
}

function onBackToDescribe() {
  // 还原最后一条 user 内容到 composer, 清掉 thread
  const lastUser = [...wizard.turns.value].reverse().find(t => t.role === 'user') as
    | (Turn & { role: 'user' })
    | undefined
  if (describeRef.value && lastUser) {
    describeRef.value.setText(lastUser.text)
    describeRef.value.setAttachments(lastUser.attachments)
  }
  wizard.reset()
  successIssueId.value = null
  successAssignee.value = null
  submitError.value = ''
}

function onReset() {
  wizard.reset()
  successIssueId.value = null
  successAssignee.value = null
  submitError.value = ''
}

function onClearConversation() {
  onReset()
}

async function onSubmit(body: any) {
  submitting.value = true
  submitError.value = ''
  try {
    const created = await api<any>('/api/issues/', { method: 'POST', body, format: 'json' })
    let id = Number(created?.id)
    // POST 响应理论上一定带 id, 但若上游代理改写过 / api 包装层丢字段, 用最新 issue 兜底
    if (!id || Number.isNaN(id)) {
      try {
        const list = await api<any>('/api/issues/?ordering=-id&page_size=1')
        const items = list?.results || list || []
        const fallbackId = items[0]?.id
        if (fallbackId) id = Number(fallbackId)
      } catch { /* fallback 取不到就让 successIssueId 留空; UI 仍显示 success 但无链接 */ }
    }
    successIssueId.value = id && !Number.isNaN(id) ? id : null
    successAssignee.value = created?.assignee != null ? String(created.assignee) : null
    emit('created', successIssueId.value || 0)
  } catch (e: any) {
    const data = e?.data || e?.response?._data
    submitError.value = (data && typeof data === 'object') ? JSON.stringify(data) : (e?.message || '创建失败')
  } finally {
    submitting.value = false
  }
}

// 新消息进来时滚到底
watch(() => wizard.turns.value.length, async () => {
  await nextTick()
  if (threadEl.value) threadEl.value.scrollTop = threadEl.value.scrollHeight
})

onBeforeUnmount(() => {
  wizard.abort()
})
</script>

<style scoped>
.ai-wizard {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1rem 0;
  position: relative;  /* 锚 .clear-btn 的 absolute */
}

/* 清空对话: viewport-fixed 右上角胶囊, 页面/thread 怎么滚都不会消失.
   做得稍大些 — 11px 字号在 1.5K 屏太隐形 */
.clear-btn {
  position: fixed;
  top: 5rem;          /* 顶 navbar 之下 */
  right: 1.5rem;
  z-index: 50;
  display: inline-flex;
  align-items: center;
  gap: 0.4375rem;
  padding: 0.5rem 0.875rem;
  /* iOS 26 Liquid Glass: 真折射由 <LiquidGlass> 通过 SVG feDisplacementMap 提供,
     这里只负责形态 (边/影/高光) + 一丝冷色折射底, 让玻璃在纯白页面上也能看出来. */
  background-image: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(180, 200, 220, 0.04) 50%,
    rgba(255, 255, 255, 0.08) 100%
  );
  background-color: transparent;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 9999px;
  font-size: 0.8125rem;
  font-weight: 500;
  color: #374151;
  cursor: pointer;
  /* 上沿白高光 + 下沿暗线 = 玻璃厚度, 外加双层浮起阴影 */
  box-shadow:
    inset 0 1px 0.5px rgba(255, 255, 255, 0.6),
    inset 0 -1px 0.5px rgba(0, 0, 0, 0.05),
    0 8px 24px -6px rgba(15, 23, 42, 0.15),
    0 3px 8px -2px rgba(15, 23, 42, 0.08);
  transition: color 0.2s, background-color 0.2s, border-color 0.2s, transform 0.2s, box-shadow 0.2s;
}
.clear-btn:hover {
  color: #dc2626;
  border-color: rgba(252, 165, 165, 0.7);
  background-color: rgba(254, 226, 226, 0.35);
  transform: translateY(-1px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    inset 0 -1px 0 rgba(0, 0, 0, 0.04),
    0 8px 20px -4px rgba(220, 38, 38, 0.18),
    0 2px 6px -2px rgba(0, 0, 0, 0.1);
}
:root.dark .clear-btn {
  background-image: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.08) 0%,
    rgba(255, 255, 255, 0.01) 50%,
    rgba(255, 255, 255, 0.04) 100%
  );
  background-color: transparent;
  border-color: rgba(255, 255, 255, 0.08);
  color: #e5e7eb;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    inset 0 -1px 0 rgba(0, 0, 0, 0.4),
    0 6px 16px -4px rgba(0, 0, 0, 0.5),
    0 2px 6px -2px rgba(0, 0, 0, 0.3);
}
:root.dark .clear-btn:hover {
  color: #fca5a5;
  border-color: rgba(239, 68, 68, 0.45);
  background-color: rgba(239, 68, 68, 0.18);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.2),
    inset 0 -1px 0 rgba(0, 0, 0, 0.4),
    0 8px 20px -4px rgba(239, 68, 68, 0.3),
    0 2px 6px -2px rgba(0, 0, 0, 0.35);
}
.clear-btn-label { letter-spacing: 0.01em; }
@media (max-width: 480px) {
  .clear-btn {
    top: 4.25rem;
    right: 0.75rem;
    padding: 0.4375rem 0.5rem;
  }
  .clear-btn-label { display: none; }  /* 窄屏只剩 × 图标 */
}

/* chat 模式: wizard 占据视口可用高度, 内部 flex column 让 thread 滚动而 composer 钉底.
   高度按 100dvh 减去 top navbar (≈4rem) + 页面 padding (≈2rem) + 缓冲 (≈3rem) = 9rem */
.ai-wizard--chat {
  gap: 1rem;
  height: calc(100dvh - 9rem);
  min-height: 32rem;   /* 极矮窗口下兜底, 避免对话区被挤没 */
}

.hero-title {
  font-size: 1.875rem;
  font-weight: 600;
  color: #111827;
  text-align: center;
  margin: 1rem 0 0.5rem;
}
:root.dark .hero-title { color: #f3f4f6; }

/* ---------- Thread ---------- */
/* chat 模式下: 占据 wizard 内剩余高度, 内部独立 scroll */
.thread {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 0.5rem 0.25rem 1rem;
}
.ai-wizard--chat .thread {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  /* 自定义滚动条更轻量 */
  scrollbar-width: thin;
}
.ai-wizard--chat .thread::-webkit-scrollbar { width: 6px; }
.ai-wizard--chat .thread::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12); border-radius: 3px;
}
:root.dark .ai-wizard--chat .thread::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
}

.msg { display: flex; flex-direction: column; gap: 0.5rem; }

.msg--user {
  align-items: flex-end;
  animation: msg-rise 0.32s ease both;
}
.msg--ai {
  align-items: flex-start;
  animation: msg-rise 0.32s ease both;
  animation-delay: 80ms;
}
.msg--ai-draft {
  animation-delay: 0ms;
}
@keyframes msg-rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ---------- 用户气泡 ---------- */
.msg-bubble {
  max-width: min(40rem, 90%);
  padding: 0.625rem 0.875rem;
  background-color: #f3f4f6;
  color: #1f2937;
  border-radius: 1rem 1rem 0.25rem 1rem;
  font-size: 0.875rem;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
:root.dark .msg-bubble { background-color: #1f2937; color: #e5e7eb; }

.msg-attach-row {
  display: flex; flex-wrap: wrap; justify-content: flex-end;
  gap: 0.375rem;
  max-width: min(40rem, 90%);
}
.msg-attach {
  display: inline-flex; align-items: center; gap: 0.25rem;
  padding: 0;
  border: 0;
  border-radius: 0.5rem;
  background: transparent;
  overflow: hidden;
  cursor: default;
}
.msg-attach--image {
  width: 3.5rem;
  height: 3.5rem;
  border: 1px solid #e5e7eb;
  background-color: #ffffff;
  cursor: zoom-in;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.msg-attach--image:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px -2px rgba(0, 0, 0, 0.15);
}
:root.dark .msg-attach--image { border-color: #374151; background-color: #111827; }
.msg-attach--image img { width: 100%; height: 100%; object-fit: cover; display: block; }
.msg-attach:not(.msg-attach--image) {
  padding: 0.25rem 0.5rem;
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  font-size: 0.75rem;
  color: #4b5563;
}
:root.dark .msg-attach:not(.msg-attach--image) {
  background-color: #1f2937; border-color: #374151; color: #d1d5db;
}
.msg-attach-name {
  max-width: 10rem;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ---------- AI 品牌标识 ---------- */
.msg-brand {
  display: flex; align-items: center; gap: 0.5rem;
  font-size: 0.75rem;
  color: #6b7280;
}
:root.dark .msg-brand { color: #9ca3af; }

.msg-brand-mark {
  width: 1.125rem; height: 1.125rem;
  border-radius: 0.375rem;
  display: inline-flex; align-items: center; justify-content: center;
  color: #ffffff;
  background: linear-gradient(135deg, #7c3aed, #9333ea);
  box-shadow: 0 1px 4px -1px rgba(124, 58, 237, 0.45);
}

.msg-brand-name {
  font-weight: 600;
  color: #374151;
  letter-spacing: -0.005em;
}
:root.dark .msg-brand-name { color: #e5e7eb; }

.msg-brand-status {
  display: inline-flex; align-items: center; gap: 0.375rem;
  font-size: 0.6875rem;
  color: #9ca3af;
  padding-left: 0.5rem;
  border-left: 1px solid #e5e7eb;
}
:root.dark .msg-brand-status { color: #6b7280; border-left-color: #374151; }
.msg-brand-status--done { color: #059669; }
:root.dark .msg-brand-status--done { color: #34d399; }
.msg-brand-status--draft { color: #7c3aed; }
:root.dark .msg-brand-status--draft { color: #c4b5fd; }
.msg-brand-status--stale {
  color: #9ca3af;
  padding-left: 0.25rem;
  border-left: 0;
}
.msg-brand-status--ask {
  color: #d97706;
}
:root.dark .msg-brand-status--ask { color: #fbbf24; }

.msg-brand-status--dup { color: #0ea5e9; }
:root.dark .msg-brand-status--dup { color: #7dd3fc; }

/* AI 查重提示卡 - 蓝色边框, 表明"信息性"而非"警告/错误" */
.msg-dup-card {
  display: flex; flex-direction: column;
  gap: 0.375rem;
  margin-left: 1.625rem;
  padding: 0.625rem 0.75rem;
  max-width: min(40rem, 90%);
  background-color: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 0.625rem;
  animation: msg-rise 0.32s ease both;
}
:root.dark .msg-dup-card {
  background-color: rgba(14, 165, 233, 0.08);
  border-color: rgba(14, 165, 233, 0.25);
}
.dup-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.5rem;
  padding: 0.3125rem 0.5rem;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  color: #0c4a6e;
  text-decoration: none;
  transition: background-color 0.15s;
}
.dup-item:hover { background-color: rgba(14, 165, 233, 0.12); }
:root.dark .dup-item { color: #bae6fd; }
:root.dark .dup-item:hover { background-color: rgba(14, 165, 233, 0.18); }
.dup-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.6875rem;
  color: #0284c7;
  flex-shrink: 0;
}
:root.dark .dup-id { color: #7dd3fc; }
.dup-title {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dup-status {
  font-size: 0.625rem;
  padding: 0.0625rem 0.375rem;
  border-radius: 0.25rem;
  flex-shrink: 0;
}
.dup-status--open {
  background-color: #fef3c7; color: #92400e;
}
.dup-status--closed {
  background-color: #d1fae5; color: #065f46;
}
:root.dark .dup-status--open { background-color: rgba(251, 191, 36, 0.18); color: #fde68a; }
:root.dark .dup-status--closed { background-color: rgba(16, 185, 129, 0.18); color: #6ee7b7; }
.dup-hint {
  font-size: 0.6875rem;
  color: #075985;
  padding-top: 0.25rem;
  border-top: 1px solid rgba(14, 165, 233, 0.18);
}
:root.dark .dup-hint { color: #7dd3fc; }

/* AI 反问气泡 - 跟用户气泡视觉成对, 但左对齐 + 暖色边框透露"求确认"语气 */
.msg-ask-bubble {
  max-width: min(36rem, 90%);
  padding: 0.625rem 0.875rem;
  background-color: #fffbeb;
  color: #78350f;
  border: 1px solid #fde68a;
  border-radius: 0.25rem 1rem 1rem 1rem;
  font-size: 0.875rem;
  line-height: 1.55;
  margin-left: 1.625rem;
  animation: msg-rise 0.32s ease both;
}
:root.dark .msg-ask-bubble {
  background-color: rgba(251, 191, 36, 0.08);
  color: #fde68a;
  border-color: rgba(251, 191, 36, 0.25);
}

.brand-pulse {
  width: 0.4375rem; height: 0.4375rem;
  border-radius: 9999px;
  background-color: #7c3aed;
  animation: brand-pulse 1.2s ease-in-out infinite;
}
@keyframes brand-pulse {
  0%, 100% { opacity: 0.35; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.15); box-shadow: 0 0 0 4px rgba(124, 58, 237, 0.12); }
}

/* ---------- 思考流 ---------- */
.msg-thinking {
  display: flex; flex-direction: column;
  gap: 0.5rem;
  padding-left: 1.625rem;
}

.think-line {
  display: flex; align-items: center; gap: 0.5rem;
  font-size: 0.8125rem;
  color: #6b7280;
}
.think-line--done { color: #059669; }
.think-line--error { color: #dc2626; }
.think-line--running { color: #4b5563; }
:root.dark .think-line { color: #9ca3af; }
:root.dark .think-line--running { color: #d1d5db; }
:root.dark .think-line--done { color: #34d399; }
:root.dark .think-line--error { color: #fca5a5; }

.think-icon--done { color: #10b981; }
.think-icon--error { color: #ef4444; }

.think-dot {
  width: 0.5rem; height: 0.5rem; border-radius: 9999px;
  background-color: #c4b5fd;
  animation: think-pulse 1s ease-in-out infinite alternate;
}
:root.dark .think-dot { background-color: #6d28d9; }
@keyframes think-pulse {
  from { opacity: 0.35; transform: scale(0.85); }
  to { opacity: 1; transform: scale(1.05); }
}

.think-caret {
  display: inline-block;
  color: #7c3aed;
  font-weight: 500;
  animation: caret-blink 0.9s steps(2, end) infinite;
  margin-left: -0.125rem;
  line-height: 1;
}
:root.dark .think-caret { color: #c4b5fd; }
@keyframes caret-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

/* ---------- 错误态 ---------- */
.msg-error {
  display: flex; align-items: center; gap: 0.375rem;
  margin-left: 1.625rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  color: #b91c1c;
  background-color: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.625rem;
}
:root.dark .msg-error {
  color: #fca5a5;
  background-color: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.25);
}

.msg-warnings {
  display: flex; flex-direction: column; gap: 0.375rem;
  margin-left: 1.625rem;
}
.msg-warning {
  display: flex; align-items: center; gap: 0.375rem;
  padding: 0.4375rem 0.625rem;
  font-size: 0.75rem;
  color: #92400e;
  background-color: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 0.5rem;
}
:root.dark .msg-warning {
  color: #fde68a;
  background-color: rgba(251, 191, 36, 0.10);
  border-color: rgba(251, 191, 36, 0.30);
}

.msg-actions {
  display: flex; gap: 0.5rem;
  margin-left: 1.625rem;
}
.msg-action {
  padding: 0.3125rem 0.75rem;
  font-size: 0.75rem;
  border-radius: 0.5rem;
  border: 1px solid #e5e7eb;
  background-color: #ffffff;
  color: #4b5563;
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s, border-color 0.15s;
}
.msg-action:hover { background-color: #f9fafb; color: #111827; }
:root.dark .msg-action {
  background-color: #1f2937; border-color: #374151; color: #d1d5db;
}
:root.dark .msg-action:hover { background-color: #111827; color: #f3f4f6; }
.msg-action--primary {
  background-color: #7c3aed; border-color: #7c3aed; color: #ffffff;
}
.msg-action--primary:hover {
  background-color: #6d28d9; border-color: #6d28d9; color: #ffffff;
}

/* ---------- 草稿卡片容器 ---------- */
.msg-draft-card {
  width: min(72%, 44rem);
  margin-left: 0;
  animation: draft-rise 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
  transition: opacity 0.25s ease, filter 0.25s ease;
}
.msg-draft-card--stale {
  opacity: 0.55;
  filter: saturate(0.7);
  pointer-events: none;
}
@keyframes draft-rise {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 整体外壳收紧 */
.msg-draft-card :deep(.draft-wrap) {
  padding: 0.875rem 1rem 0.75rem;
  border-radius: 0.75rem;
  gap: 0.75rem;
}
.msg-draft-card :deep(.draft-header) {
  padding-bottom: 0.625rem;
}
.msg-draft-card :deep(.header-icon) {
  width: 1.375rem; height: 1.375rem;
  border-radius: 0.375rem;
}
.msg-draft-card :deep(.header-title) { font-size: 0.8125rem; }
.msg-draft-card :deep(.header-sub) { font-size: 0.6875rem; margin-top: 0.0625rem; }

/* 两栏布局 */
.msg-draft-card :deep(.draft-body) {
  grid-template-columns: minmax(0, 1fr) 12rem;
  gap: 1rem;
}

/* 左侧 */
.msg-draft-card :deep(.content-col) { gap: 0.625rem; }
.msg-draft-card :deep(.issue-title-input) {
  font-size: 0.9375rem !important;
  padding: 0.375rem 0.5rem !important;
}
.msg-draft-card :deep(.issue-desc-input),
.msg-draft-card :deep(.issue-body-input) {
  font-size: 0.75rem !important;
  padding: 0.375rem 0.5rem !important;
}
.msg-draft-card :deep(.section) { gap: 0.25rem; padding-top: 0.125rem; }
.msg-draft-card :deep(.section-label) { font-size: 0.6875rem; }

/* MarkdownEditor */
.msg-draft-card :deep(.markdown-editor) { border-radius: 0.5rem; }
.msg-draft-card :deep(.markdown-editor textarea) {
  min-height: 6.5rem !important;
  font-size: 0.75rem !important;
  padding: 0.625rem !important;
}
.msg-draft-card :deep(.markdown-editor .markdown-body) {
  min-height: 6.5rem !important;
  padding: 0.625rem 0.75rem !important;
  font-size: 0.75rem;
}
.msg-draft-card :deep(.markdown-editor img) {
  max-height: 9rem;
  width: auto;
}

/* 右侧 meta */
.msg-draft-card :deep(.meta-col) {
  padding-left: 0.875rem;
  gap: 0.625rem;
}
.msg-draft-card :deep(.meta-row) {
  grid-template-columns: 3.25rem 1fr;
  gap: 0.375rem;
}
.msg-draft-card :deep(.meta-label) { font-size: 0.6875rem; }

.msg-draft-card :deep(.footer) { padding-top: 0.625rem; }
.msg-draft-card :deep(.ai-suggest) { padding: 0.5rem 0.625rem; font-size: 0.6875rem; }

@media (max-width: 768px) {
  .msg-draft-card { width: 100%; }
  .msg-draft-card :deep(.draft-body) { grid-template-columns: 1fr; }
}

/* ---------- Composer slot ---------- */
/* chat 模式下 composer 是 wizard flex 的末项, 自然贴底, 无需 sticky.
   非 chat 模式 (首屏 idle) 时 composer 也只在自然流位置, 不做特殊处理 */
.composer-slot {
  flex-shrink: 0;
}

/* ---------- 图片预览弹窗 ---------- */
.preview-modal {
  display: flex; flex-direction: column;
  max-height: 85vh;
  background-color: #ffffff;
  border-radius: 0.75rem;
  overflow: hidden;
}
:root.dark .preview-modal { background-color: #1f2937; }
.preview-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #e5e7eb;
}
:root.dark .preview-header { border-bottom-color: #374151; }
.preview-title {
  font-size: 0.875rem; color: #374151;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
:root.dark .preview-title { color: #d1d5db; }
.preview-body {
  display: flex; align-items: center; justify-content: center;
  padding: 1rem;
  background-color: #f9fafb;
  overflow: auto;
  cursor: zoom-out;
}
:root.dark .preview-body { background-color: #111827; }
.preview-body img {
  max-width: 100%;
  max-height: calc(85vh - 4rem);
  object-fit: contain;
  cursor: default;
}
</style>
