<template>
  <div class="step-draft">
    <!-- Success state -->
    <div v-if="successIssueId" class="success">
      <div class="success-icon">
        <UIcon name="i-heroicons-check" class="w-8 h-8 text-emerald-500" />
      </div>
      <div class="success-title">Issue 已成功提交！</div>
      <div class="success-iss">ISS-{{ String(successIssueId).padStart(3, '0') }}</div>
      <div class="success-sub">
        <template v-if="form.assignee">已自动分配给 <strong>{{ assigneeName }}</strong> · </template>
        优先级 <strong>{{ form.priority }}</strong>
      </div>
      <UButton size="sm" icon="i-heroicons-plus" @click="emit('reset')">继续提交新 Issue</UButton>
    </div>

    <!-- Draft state -->
    <div v-else class="draft">
      <div class="draft-header">
        <UIcon name="i-heroicons-check" class="w-4 h-4 text-emerald-500" />
        <span class="draft-title">Issue 草稿已生成 · 请确认并编辑后提交</span>
        <span class="draft-sub">AI 自动填写 <span class="count">6</span> 个字段</span>
      </div>

      <div class="field">
        <label class="field-label">Issue 标题 <AiBadge kind="generated" /></label>
        <UInput v-model="form.title" />
      </div>

      <div class="field">
        <label class="field-label">问题描述</label>
        <UTextarea v-model="form.description" :rows="3" autoresize />
      </div>

      <div class="field">
        <label class="field-label">复现步骤 <AiBadge kind="generated" /></label>
        <UTextarea v-model="form.repro_steps" :rows="4" autoresize />
      </div>

      <div class="row-3">
        <div class="field">
          <label class="field-label">优先级 <AiBadge kind="inferred" /></label>
          <USelect v-model="form.priority" :items="priorityOptions" value-key="value" />
        </div>
        <div class="field">
          <label class="field-label">所属模块 <AiBadge kind="inferred" /></label>
          <USelect v-model="form.module" :items="moduleOptions" />
        </div>
        <div class="field">
          <label class="field-label">指派给</label>
          <USelect v-model="form.assignee" :items="assigneeOptions" value-key="value" placeholder="（不指派）" />
        </div>
      </div>

      <div class="row-3">
        <div class="field span-2">
          <label class="field-label">预期行为 <AiBadge kind="generated" /></label>
          <UInput v-model="form.expected_behavior" />
        </div>
        <div class="field">
          <label class="field-label">环境</label>
          <USelect v-model="form.environment" :items="envOptions" placeholder="（可选）" />
        </div>
      </div>

      <div class="field">
        <label class="field-label">项目</label>
        <USelect v-model="form.project" :items="projectOptions" value-key="value" />
      </div>

      <p v-if="submitError" class="submit-error">{{ submitError }}</p>

      <div class="footer">
        <span class="footer-hint">✦ 所有字段均可编辑 · 提交后将自动创建 Issue 并通知相关成员</span>
        <UButton variant="ghost" color="neutral" size="sm" @click="emit('back')">重新描述</UButton>
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
import type { WizardDraft } from '~/composables/useAiWizard'

type UserChoice = { id: string; name: string }
type Project = { id: string; name: string }

const props = defineProps<{
  draft: WizardDraft
  projects: Project[]
  initialProjectId: string
  modules: string[]
  users: UserChoice[]
  submitting: boolean
  submitError: string
  successIssueId: number | null
}>()

const emit = defineEmits<{
  submit: [payload: any]
  back: []
  reset: []
}>()

const form = ref({
  title: props.draft.title,
  description: props.draft.description,
  repro_steps: props.draft.repro_steps,
  expected_behavior: props.draft.expected_behavior,
  priority: props.draft.priority,
  module: props.draft.module,
  environment: props.draft.environment ?? '',
  labels: props.draft.labels,
  assignee: '',
  project: props.initialProjectId,
})

const priorityOptions = [
  { label: '🔴 P0 — 紧急', value: 'P0' },
  { label: '🟠 P1 — 高', value: 'P1' },
  { label: '🟡 P2 — 中', value: 'P2' },
  { label: '⚪ P3 — 低', value: 'P3' },
]

const envOptions = ['Chrome / Windows', 'Safari / macOS', 'Safari / iOS', 'Chrome / Android', '其他']

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

  const body: any = {
    project: form.value.project,
    title: form.value.title.trim(),
    description: desc,
    priority: form.value.priority,
    labels: form.value.labels,
    source: 'ai_wizard',
    source_meta: {
      module: form.value.module || null,
      environment: form.value.environment || null,
      original_input: props.draft.description,
    },
  }
  if (form.value.assignee) body.assignee = form.value.assignee

  emit('submit', body)
}
</script>

<style scoped>
.step-draft { display: flex; flex-direction: column; gap: 1rem; }
.draft-header {
  display: flex; align-items: center; gap: 0.5rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #f3f4f6;
}
:root.dark .draft-header { border-bottom-color: #374151; }
.draft-title { font-size: 0.875rem; font-weight: 600; color: #111827; }
:root.dark .draft-title { color: #f3f4f6; }
.draft-sub { font-size: 0.75rem; color: #9ca3af; margin-left: auto; }
.count { color: #7c3aed; font-weight: 600; }

.field { display: flex; flex-direction: column; gap: 0.375rem; }
.field-label { font-size: 0.8125rem; font-weight: 500; color: #374151; display: flex; align-items: center; }
:root.dark .field-label { color: #d1d5db; }
.row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }
.span-2 { grid-column: span 2; }
@media (max-width: 768px) { .row-3 { grid-template-columns: 1fr; } .span-2 { grid-column: auto; } }

.submit-error { font-size: 0.8125rem; color: #dc2626; }

.footer {
  display: flex; align-items: center; gap: 0.5rem;
  padding-top: 0.75rem; border-top: 1px solid #f3f4f6;
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
.success-iss { font-size: 1.5rem; font-weight: 700; color: #7c3aed; font-family: ui-monospace, monospace; }
.success-sub { font-size: 0.8125rem; color: #6b7280; margin-bottom: 0.5rem; }
:root.dark .success-sub { color: #9ca3af; }
</style>
