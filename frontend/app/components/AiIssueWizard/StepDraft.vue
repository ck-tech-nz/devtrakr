<template>
  <div class="step-draft">
    <!-- Success state -->
    <div v-if="successIssueId" class="success">
      <div class="success-icon">
        <UIcon name="i-heroicons-check" class="w-8 h-8 text-emerald-500" />
      </div>
      <div class="success-title">Issue 已成功提交！</div>
      <NuxtLink :to="`/app/issues/${successIssueId}`" class="success-iss">
        ISS-{{ String(successIssueId).padStart(3, '0') }}
      </NuxtLink>
      <div class="success-sub">
        <template v-if="successAssigneeName">已分配给 <strong>{{ successAssigneeName }}</strong> · </template>
        <template v-else>AI 正在后台自动分派负责人 · </template>
        优先级 <strong>{{ form.priority }}</strong>
      </div>
      <UButton size="sm" icon="i-heroicons-plus" @click="emit('reset')">继续提交新 Issue</UButton>
    </div>

    <!-- Draft state -->
    <div v-else class="draft-wrap">
      <!-- Header -->
      <div class="draft-header">
        <div class="header-icon"><UIcon name="i-heroicons-sparkles" class="w-4 h-4 text-white" /></div>
        <div class="header-text">
          <div class="header-title">
            Issue 草稿
            <span v-if="(version || 0) > 1" class="header-version">v{{ version }}</span>
          </div>
          <div class="header-sub">{{ isEditable ? '可直接编辑下方字段后点提交, 或在底部对话框告诉 AI 怎么改' : '该版本已被新版替代,仅供查看' }}</div>
        </div>
        <AiBadge kind="generated" class="header-badge" />
      </div>

      <!-- Body: 2-column layout -->
      <div class="draft-body">
        <!-- Left: issue content -->
        <div class="content-col">
          <UInput
            v-model="form.title"
            placeholder="问题标题"
            :ui="{ base: 'issue-title-input' }"
            :disabled="!isEditable"
          />

          <!-- AI 生成的描述里会带 ![image](url) 之类的 markdown, 默认进入预览模式让图片直接渲染;
               点击"编辑"tab 可改文本 -->
          <MarkdownEditor
            ref="descEditorRef"
            v-model="form.description"
            placeholder="一句话补充上下文（可选）"
            default-mode="preview"
          />

          <div class="section">
            <div class="section-label">复现步骤</div>
            <UTextarea
              v-model="form.repro_steps"
              :rows="4"
              autoresize
              placeholder="1. ...&#10;2. ...&#10;3. ..."
              :ui="{ base: 'issue-body-input' }"
              :disabled="!isEditable"
            />
          </div>

          <div class="section">
            <div class="section-label">预期行为</div>
            <UInput
              v-model="form.expected_behavior"
              placeholder="应该发生什么？"
              :ui="{ base: 'issue-body-input' }"
              :disabled="!isEditable"
            />
          </div>
        </div>

        <!-- Right: meta sidebar -->
        <aside class="meta-col">
          <div class="meta-group">
            <div class="meta-row">
              <span class="meta-label">项目</span>
              <USelect
                v-model="form.project"
                :items="projectOptions"
                value-key="value"
                size="xs"
                class="meta-select"
                :disabled="!isEditable"
              />
            </div>
            <div class="meta-row">
              <span class="meta-label">优先级</span>
              <USelect
                v-model="form.priority"
                :items="priorityOptions"
                value-key="value"
                size="xs"
                class="meta-select"
                :disabled="!isEditable"
              />
            </div>
            <div class="meta-row">
              <span class="meta-label">模块</span>
              <USelect
                v-model="form.module"
                :items="moduleOptions"
                size="xs"
                class="meta-select"
                :disabled="!isEditable"
              />
            </div>
            <div class="meta-row">
              <span class="meta-label">指派人</span>
              <USelect
                v-model="form.assignee"
                :items="assigneeOptions"
                value-key="value"
                size="xs"
                placeholder="AI 自动分派"
                class="meta-select"
                :disabled="!isEditable"
              />
            </div>
          </div>

          <!-- AI suggestions callout (only if present) -->
          <div v-if="draft.follow_up_questions && draft.follow_up_questions.length" class="ai-suggest">
            <div class="ai-suggest-head">
              <UIcon name="i-heroicons-light-bulb" class="w-3.5 h-3.5" />
              <span>AI 建议补充</span>
            </div>
            <ul class="ai-suggest-list">
              <li v-for="q in draft.follow_up_questions" :key="q">{{ q }}</li>
            </ul>
          </div>
        </aside>
      </div>

      <p v-if="submitError" class="submit-error">{{ submitError }}</p>

      <!-- Footer (历史 draft 不展示, 只有可编辑卡才显示操作区) -->
      <div v-if="isEditable" class="footer">
        <UButton variant="ghost" color="neutral" size="sm" icon="i-heroicons-arrow-uturn-left" @click="emit('back')">
          重新描述
        </UButton>
        <div class="footer-spacer" />
        <UButton
          size="sm"
          icon="i-heroicons-paper-airplane"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="onSubmit"
        >提交 Issue</UButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AiBadge from './AiBadge.vue'
import type { WizardDraft } from '~/composables/useAiWizard'

type UserChoice = { id: string; name: string }
type Project = { id: string; name: string }

const props = defineProps<{
  draft: WizardDraft
  projects: Project[]
  initialProjectId: string
  modules: string[]
  users: UserChoice[]
  validLabels: string[]
  attachmentIds: string[]
  // 用户最初输入的原文（未经 AI 拼装）。写入 source_meta.original_input。
  originalInput: string
  submitting: boolean
  submitError: string
  successIssueId: number | null
  // 后端创建 Issue 后返回的 assignee — 同步路径下一般为 null(分派走 Celery),
  // 留空时 UI 提示"暂未分派,AI 后台正在自动分派"
  successAssignee: string | null
  /** false 时整张卡只读 — 用于多轮修订后的历史 draft */
  editable?: boolean
  /** 草稿版本号; >1 时 header 显示 v2/v3 徽标 */
  version?: number
}>()

const emit = defineEmits<{
  submit: [payload: any]
  back: []
  reset: []
}>()

// 强制 description 编辑器进入预览态 — 避免某些环境下 default-mode prop 时序不稳
const descEditorRef = ref<{ setMode: (m: 'edit' | 'preview') => void } | null>(null)
onMounted(() => { descEditorRef.value?.setMode('preview') })

// editable 默认为 true (向后兼容旧调用方); false 时整张卡只读 — 多轮修订下的历史 draft 用
const isEditable = computed(() => props.editable !== false)

// 父级通过 ref 调用, 在 affirmative auto-submit 路径下直接走与"提交 Issue"按钮相同的逻辑
defineExpose({
  triggerSubmit() {
    if (!isEditable.value || !canSubmit.value) return
    onSubmit()
  },
})

const form = ref({
  title: props.draft.title,
  description: props.draft.description,
  repro_steps: props.draft.repro_steps,
  expected_behavior: props.draft.expected_behavior,
  priority: props.draft.priority,
  module: props.draft.module,
  labels: props.draft.labels,
  // 默认留空;提交后 Celery 异步跑 issue_auto_assign 自动挑人,
  // 用户在下拉里手动选择会优先于自动分派
  assignee: '',
  // 父级 lastAnalyzedProject 可能是 number/string, 显式 String() 让 USelect 严格比对成功
  project: props.initialProjectId ? String(props.initialProjectId) : '',
})

// 兜底: 若 props.initialProjectId 在 mount 之后才推到 (上游异步加载),
// 自动同步进 form.project. 用户手动改过 (form.project 非空) 时不覆盖.
watch(() => props.initialProjectId, (v) => {
  if (v && !form.value.project) form.value.project = String(v)
})

const priorityOptions = [
  { label: '🔴 P0 — 紧急', value: 'P0' },
  { label: '🟠 P1 — 高', value: 'P1' },
  { label: '🟡 P2 — 中', value: 'P2' },
  { label: '⚪ P3 — 低', value: 'P3' },
]

const projectOptions = computed(() => props.projects.map(p => ({ label: p.name, value: String(p.id) })))
const moduleOptions = computed(() => props.modules)
const assigneeOptions = computed(() => props.users.map(u => ({ label: u.name, value: String(u.id) })))

// 成功视图里展示后端实际分派到的人 (form.assignee 在自动分派路径下是空字符串)
const successAssigneeName = computed(() => {
  if (!props.successAssignee) return ''
  const u = props.users.find(x => String(x.id) === String(props.successAssignee))
  return u?.name || ''
})

const canSubmit = computed(() => form.value.title.trim().length >= 3 && !!form.value.project && !props.submitting)

function onSubmit() {
  // Build the Issue create payload — embeds repro_steps + expected_behavior in description Markdown
  const desc = [
    form.value.description.trim(),
    form.value.repro_steps.trim() ? `\n\n## 复现步骤\n${form.value.repro_steps.trim()}` : '',
    form.value.expected_behavior.trim() ? `\n\n## 预期行为\n${form.value.expected_behavior.trim()}` : '',
  ].join('')

  // 过滤掉 AI 可能臆造的、不在 SiteSettings.labels 中的标签，避免后端 400
  const filteredLabels = form.value.labels.filter(l => props.validLabels.includes(l))

  const body: any = {
    project: form.value.project,
    title: form.value.title.trim(),
    description: desc,
    priority: form.value.priority,
    status: '待分配',
    labels: filteredLabels,
    source: 'ai_wizard',
    source_meta: {
      module: form.value.module || null,
      inferred_env: props.draft.inferred_env || null,
      // 用户最初输入的原文 — 不是 AI 拼装后的 description，避免触发 source_meta 4096B 上限
      original_input: props.originalInput,
    },
    attachment_ids: props.attachmentIds,
  }
  if (form.value.assignee) body.assignee = form.value.assignee

  emit('submit', body)
}
</script>

<style scoped>
.step-draft { display: flex; flex-direction: column; gap: 1rem; }

.draft-wrap {
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 1rem;
  padding: 1.25rem 1.5rem 1.125rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
:root.dark .draft-wrap { background-color: #1f2937; border-color: #374151; }

/* ---------- Header ---------- */
.draft-header {
  display: flex; align-items: center; gap: 0.625rem;
  padding-bottom: 0.875rem;
  border-bottom: 1px solid #f3f4f6;
}
:root.dark .draft-header { border-bottom-color: #374151; }
.header-icon {
  width: 1.75rem; height: 1.75rem; border-radius: 0.5rem;
  background: linear-gradient(135deg, #7c3aed, #9333ea);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 8px -2px rgba(124, 58, 237, 0.4);
}
.header-text { display: flex; flex-direction: column; line-height: 1.2; }
.header-title {
  font-size: 0.9375rem; font-weight: 600; color: #111827;
  display: inline-flex; align-items: center; gap: 0.375rem;
}
.header-version {
  font-size: 0.625rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #ffffff;
  background: linear-gradient(135deg, #7c3aed, #9333ea);
  padding: 0.0625rem 0.375rem;
  border-radius: 0.25rem;
  text-transform: lowercase;
}
:root.dark .header-title { color: #f3f4f6; }
.header-sub { font-size: 0.75rem; color: #9ca3af; margin-top: 0.125rem; }
.header-badge { margin-left: auto; }

/* ---------- Body grid ---------- */
.draft-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18rem;
  gap: 1.75rem;
}
@media (max-width: 768px) {
  .draft-body { grid-template-columns: 1fr; gap: 1rem; }
}

/* ---------- Left content column ---------- */
.content-col {
  display: flex; flex-direction: column; gap: 1.125rem;
  min-width: 0;
}
.content-col :deep(.issue-title-input) {
  font-size: 1.25rem;
  font-weight: 600;
  color: #111827;
  letter-spacing: -0.01em;
  padding: 0.5rem 0.75rem;
}
:root.dark .content-col :deep(.issue-title-input) { color: #f3f4f6; }
.content-col :deep(.issue-desc-input) {
  font-size: 0.875rem;
  color: #4b5563;
  line-height: 1.55;
  padding: 0.5rem 0.75rem;
}
:root.dark .content-col :deep(.issue-desc-input) { color: #9ca3af; }

.section {
  display: flex; flex-direction: column; gap: 0.4375rem;
  padding-top: 0.25rem;
  border-top: 1px dashed #f3f4f6;
}
:root.dark .section { border-top-color: #374151; }
.section-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
:root.dark .section-label { color: #9ca3af; }
.content-col :deep(.issue-body-input) {
  font-size: 0.875rem;
  color: #1f2937;
  line-height: 1.6;
}
:root.dark .content-col :deep(.issue-body-input) { color: #e5e7eb; }

/* ---------- Right meta sidebar ---------- */
.meta-col {
  display: flex; flex-direction: column; gap: 0.875rem;
  padding-left: 1.25rem;
  border-left: 1px solid #f3f4f6;
}
:root.dark .meta-col { border-left-color: #374151; }
@media (max-width: 768px) {
  .meta-col { padding-left: 0; border-left: 0; border-top: 1px solid #f3f4f6; padding-top: 1rem; }
  :root.dark .meta-col { border-top-color: #374151; }
}

.meta-group { display: flex; flex-direction: column; gap: 0.5rem; }
.meta-row {
  display: grid;
  grid-template-columns: 4.5rem 1fr;
  align-items: center;
  gap: 0.5rem;
}
.meta-label {
  font-size: 0.75rem;
  color: #6b7280;
  font-weight: 500;
}
:root.dark .meta-label { color: #9ca3af; }
.meta-select { width: 100%; }
.meta-select :deep(button) {
  font-size: 0.75rem;
  width: 100%;
  justify-content: space-between;
  background-color: #f9fafb;
  border-color: #e5e7eb;
}
:root.dark .meta-select :deep(button) {
  background-color: #111827;
  border-color: #374151;
}

/* AI suggest callout */
.ai-suggest {
  background: linear-gradient(135deg, rgba(124, 58, 237, 0.04), rgba(245, 158, 11, 0.04));
  border: 1px solid rgba(124, 58, 237, 0.12);
  border-radius: 0.625rem;
  padding: 0.625rem 0.75rem;
  font-size: 0.75rem;
}
:root.dark .ai-suggest {
  background: linear-gradient(135deg, rgba(124, 58, 237, 0.12), rgba(245, 158, 11, 0.08));
  border-color: rgba(124, 58, 237, 0.3);
}
.ai-suggest-head {
  display: flex; align-items: center; gap: 0.3125rem;
  color: #7c3aed; font-weight: 600; margin-bottom: 0.375rem;
}
:root.dark .ai-suggest-head { color: #c4b5fd; }
.ai-suggest-list {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 0.25rem;
  color: #6b7280;
  line-height: 1.5;
}
:root.dark .ai-suggest-list { color: #d1d5db; }
.ai-suggest-list li {
  padding-left: 0.75rem;
  position: relative;
}
.ai-suggest-list li::before {
  content: '·';
  position: absolute;
  left: 0.25rem;
  color: #7c3aed;
  font-weight: 700;
}

/* ---------- Footer ---------- */
.submit-error { font-size: 0.8125rem; color: #dc2626; }

.footer {
  display: flex; align-items: center; gap: 0.5rem;
  padding-top: 0.875rem; border-top: 1px solid #f3f4f6;
}
:root.dark .footer { border-top-color: #374151; }
.footer-spacer { flex: 1; }

/* ---------- Success ---------- */
.success { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; padding: 2rem 0; }
.success-icon {
  width: 4rem; height: 4rem; border-radius: 9999px;
  display: flex; align-items: center; justify-content: center;
  background-color: #d1fae5;
}
:root.dark .success-icon { background-color: rgba(5, 150, 105, 0.18); }
.success-title { font-size: 1.125rem; font-weight: 600; color: #111827; }
:root.dark .success-title { color: #f3f4f6; }
.success-iss { font-size: 1.5rem; font-weight: 700; color: #7c3aed; font-family: ui-monospace, monospace; text-decoration: none; transition: color 0.15s; }
.success-iss:hover { color: #6d28d9; text-decoration: underline; }
.success-sub { font-size: 0.8125rem; color: #6b7280; margin-bottom: 0.5rem; }
:root.dark .success-sub { color: #9ca3af; }
</style>
