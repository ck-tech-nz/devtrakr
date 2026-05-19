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
        <template v-if="form.assignee">已自动分配给 <strong>{{ assigneeName }}</strong> · </template>
        优先级 <strong>{{ form.priority }}</strong>
      </div>
      <UButton size="sm" icon="i-heroicons-plus" @click="emit('reset')">继续提交新 Issue</UButton>
    </div>

    <!-- Draft state -->
    <div v-else class="draft-wrap">
      <!-- Header -->
      <div class="draft-header">
        <div class="header-icon"><UIcon name="i-heroicons-check" class="w-4 h-4 text-white" /></div>
        <div class="header-title">Issue 已生成 · 确认后一键提交</div>
        <span class="header-sub">AI 自动分析完成</span>
      </div>

      <!-- Possible duplicates (advisory only — does not block submit) -->
      <div v-if="duplicates.length" class="dup-panel">
        <details>
          <summary>
            <UIcon name="i-heroicons-exclamation-triangle" class="w-4 h-4" />
            <span>发现 {{ duplicates.length }} 条可能重复的 Issue</span>
            <span class="dup-hint">— 点开查看（仅提示，不阻止提交）</span>
          </summary>
          <ul class="dup-list">
            <li v-for="d in duplicates" :key="d.id">
              <NuxtLink :to="`/app/issues/${d.id}`" target="_blank" class="dup-link">
                ISS-{{ String(d.id).padStart(3, '0') }} · {{ d.title }}
                <span class="dup-status">[{{ d.status }}]</span>
              </NuxtLink>
              <div v-if="d.reason" class="dup-reason">{{ d.reason }}</div>
            </li>
          </ul>
        </details>
      </div>

      <!-- Title (centered, large) -->
      <div class="field-row">
        <UInput v-model="form.title" :ui="{ base: 'text-center text-lg font-semibold' }" />
      </div>

      <!-- Description -->
      <div class="field-row">
        <UTextarea v-model="form.description" :rows="2" autoresize :ui="{ base: 'text-center text-sm text-gray-500' }" />
      </div>

      <!-- Pills row: priority / module / assignee -->
      <div class="pills-row">
        <USelect
          v-model="form.priority"
          :items="priorityOptions"
          value-key="value"
          size="xs"
          icon="i-heroicons-flag"
          class="pill-select"
        />
        <USelect
          v-model="form.module"
          :items="moduleOptions"
          size="xs"
          icon="i-heroicons-folder"
          class="pill-select"
        />
        <USelect
          v-model="form.assignee"
          :items="assigneeOptions"
          value-key="value"
          size="xs"
          icon="i-heroicons-user"
          placeholder="（不指派）"
          class="pill-select"
        />
      </div>

      <!-- Follow-up questions hint (if any) -->
      <div v-if="draft.follow_up_questions && draft.follow_up_questions.length" class="hint-box">
        <div class="hint-head">
          <UIcon name="i-heroicons-chat-bubble-bottom-center-text" class="w-4 h-4" />
          <span>AI 建议补充以下信息后再提交</span>
        </div>
        <ul class="hint-list">
          <li v-for="q in draft.follow_up_questions" :key="q">{{ q }}</li>
        </ul>
      </div>

      <!-- 复现步骤 sub-card -->
      <div class="repro-card">
        <div class="repro-head">
          <span class="repro-label">复现步骤</span>
          <AiBadge v-if="form.repro_steps.trim()" kind="generated" />
        </div>
        <UTextarea
          v-model="form.repro_steps"
          :rows="4"
          autoresize
          placeholder="（请按 1. 2. 3. 列出具体步骤）"
          :ui="{ base: 'text-center text-sm' }"
        />
      </div>

      <!-- Expected behavior -->
      <div class="field-row">
        <label class="field-label">预期行为 <AiBadge v-if="form.expected_behavior.trim()" kind="generated" /></label>
        <UInput v-model="form.expected_behavior" placeholder="（应该发生什么？）" />
      </div>

      <!-- Project (preserved for fix-on-final-step) -->
      <div class="field-row">
        <label class="field-label">项目</label>
        <USelect v-model="form.project" :items="projectOptions" value-key="value" size="sm" />
      </div>

      <p v-if="submitError" class="submit-error">{{ submitError }}</p>

      <!-- Footer -->
      <div class="footer">
        <span class="footer-hint">✦ AI 已自动判断优先级、模块与指派人 · 如有异议可点击修改</span>
        <UButton variant="outline" color="neutral" size="sm" @click="emit('back')">重新描述</UButton>
        <UButton
          size="sm"
          icon="i-heroicons-check"
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
import type { WizardDraft, DuplicateItem } from '~/composables/useAiWizard'

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
  duplicates: DuplicateItem[]
  submitting: boolean
  submitError: string
  successIssueId: number | null
}>()

const emit = defineEmits<{
  submit: [payload: any]
  back: []
  reset: []
}>()

const { user: authUser } = useAuth()

const form = ref({
  title: props.draft.title,
  description: props.draft.description,
  repro_steps: props.draft.repro_steps,
  expected_behavior: props.draft.expected_behavior,
  priority: props.draft.priority,
  module: props.draft.module,
  labels: props.draft.labels,
  assignee: String(authUser.value?.id ?? ''),
  project: props.initialProjectId,
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

const assigneeName = computed(() => {
  const u = props.users.find(x => String(x.id) === String(form.value.assignee))
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
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
:root.dark .draft-wrap { background-color: #1f2937; border-color: #374151; }

.draft-header {
  display: flex; align-items: center; gap: 0.625rem;
  padding-bottom: 0.875rem;
  border-bottom: 1px solid #f3f4f6;
}
:root.dark .draft-header { border-bottom-color: #374151; }
.header-icon {
  width: 1.75rem; height: 1.75rem; border-radius: 0.5rem;
  background-color: #7c3aed; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.header-title { font-size: 0.9375rem; font-weight: 600; color: #111827; }
:root.dark .header-title { color: #f3f4f6; }
.header-sub { font-size: 0.75rem; color: #9ca3af; margin-left: auto; }

.field-row { display: flex; flex-direction: column; gap: 0.375rem; }
.field-label { font-size: 0.8125rem; font-weight: 500; color: #374151; display: flex; align-items: center; }
:root.dark .field-label { color: #d1d5db; }

.pills-row {
  display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 0.25rem 0;
}
.pill-select :deep(button) { font-size: 0.75rem; min-width: auto; }

.hint-box {
  background-color: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  font-size: 0.8125rem;
}
:root.dark .hint-box { background-color: rgba(251, 191, 36, 0.08); border-color: rgba(251, 191, 36, 0.3); }
.hint-head {
  display: flex; align-items: center; gap: 0.375rem;
  color: #92400e; font-weight: 500; margin-bottom: 0.375rem;
}
:root.dark .hint-head { color: #fcd34d; }
.hint-list { list-style: disc; padding-left: 1.5rem; color: #78350f; }
:root.dark .hint-list { color: #fde68a; }
.hint-list li { padding: 0.125rem 0; }

.repro-card {
  background-color: #f9fafb;
  border: 1px solid #f3f4f6;
  border-radius: 0.625rem;
  padding: 1rem;
  display: flex; flex-direction: column; gap: 0.625rem;
}
:root.dark .repro-card { background-color: #111827; border-color: #1f2937; }
.repro-head { display: flex; align-items: center; gap: 0.375rem; }
.repro-label { font-size: 0.8125rem; font-weight: 500; color: #374151; }
:root.dark .repro-label { color: #d1d5db; }

.submit-error { font-size: 0.8125rem; color: #dc2626; }

.footer {
  display: flex; align-items: center; gap: 0.5rem;
  padding-top: 0.875rem; border-top: 1px solid #f3f4f6;
}
:root.dark .footer { border-top-color: #374151; }
.footer-hint { font-size: 0.75rem; color: #9ca3af; flex: 1; }

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

.dup-panel {
  background-color: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 0.5rem;
  padding: 0.5rem 0.875rem;
  font-size: 0.8125rem;
}
:root.dark .dup-panel { background-color: rgba(251, 191, 36, 0.08); border-color: rgba(251, 191, 36, 0.3); }
.dup-panel summary {
  display: flex; align-items: center; gap: 0.375rem;
  cursor: pointer; color: #92400e; font-weight: 500;
}
:root.dark .dup-panel summary { color: #fcd34d; }
.dup-hint { color: #9ca3af; font-weight: 400; margin-left: auto; }
.dup-list { list-style: none; padding: 0.5rem 0 0 0; margin: 0; display: flex; flex-direction: column; gap: 0.375rem; }
.dup-list li { padding: 0.25rem 0; border-top: 1px dashed rgba(146, 64, 14, 0.2); }
.dup-link { color: #1f2937; text-decoration: none; }
.dup-link:hover { text-decoration: underline; }
:root.dark .dup-link { color: #e5e7eb; }
.dup-status { color: #9ca3af; font-size: 0.75rem; margin-left: 0.25rem; }
.dup-reason { color: #78350f; font-size: 0.75rem; margin-top: 0.125rem; }
:root.dark .dup-reason { color: #fcd34d; }
</style>
