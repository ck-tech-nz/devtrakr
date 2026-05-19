<template>
  <div class="ai-wizard">
    <h2 v-if="currentStep === 1" class="hero-title">有什么我可以帮你的？</h2>

    <StepDescribe
      v-if="currentStep === 1"
      :projects="projects"
      :default-project-id="defaultProjectId"
      @analyze="onAnalyze"
    />
    <StepAnalyzing
      v-else-if="currentStep === 2"
      :steps="wizard.steps.value"
      :error-message="wizard.errorMessage.value"
      @retry="onRetry"
      @back="onBackToDescribe"
    />
    <StepDraft
      v-else-if="currentStep === 3 && wizard.draft.value"
      :draft="wizard.draft.value"
      :duplicates="wizard.duplicates.value"
      :projects="projects"
      :initial-project-id="lastAnalyzedProject"
      :modules="modules"
      :users="users"
      :valid-labels="validLabels"
      :attachment-ids="lastAttachmentIds"
      :original-input="lastOriginalInput"
      :submitting="submitting"
      :submit-error="submitError"
      :success-issue-id="successIssueId"
      @submit="onSubmit"
      @back="onBackToDescribe"
      @reset="onReset"
    />
  </div>
</template>

<script setup lang="ts">
import StepDescribe from './AiIssueWizard/StepDescribe.vue'
import StepAnalyzing from './AiIssueWizard/StepAnalyzing.vue'
import StepDraft from './AiIssueWizard/StepDraft.vue'

const emit = defineEmits<{ created: [issueId: number] }>()

const { api } = useApi()
const { user } = useAuth()

const defaultProjectId = computed(() => user.value?.default_project?.id || null)

const projects = ref<{ id: string; name: string }[]>([])
const modules = ref<string[]>([])
const users = ref<{ id: string; name: string }[]>([])
const validLabels = ref<string[]>([])
const lastAnalyzedProject = ref<string>('')
const lastAttachmentIds = ref<string[]>([])
// 用户最初输入的原文 (未经 AI 拼装)，用于写入 source_meta.original_input
// 避免把 AI 拼装后的 description 写进 source_meta 触发 4096 字节上限
const lastOriginalInput = ref<string>('')

const wizard = useAiWizard()
const submitting = ref(false)
const submitError = ref('')
const successIssueId = ref<number | null>(null)

const currentStep = computed(() => {
  if (successIssueId.value) return 3
  if (wizard.state.value === 'idle') return 1
  if (wizard.state.value === 'analyzing' || wizard.state.value === 'error') return 2
  if (wizard.state.value === 'drafting') return 3
  return 1
})

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

function onAnalyze(payload: { description: string; project: string; attachment_ids: string[] }) {
  lastAnalyzedProject.value = payload.project
  lastAttachmentIds.value = payload.attachment_ids
  lastOriginalInput.value = payload.description
  wizard.start(payload)
}

function onRetry() {
  onBackToDescribe()
}

function onBackToDescribe() {
  wizard.reset()
  successIssueId.value = null
  submitError.value = ''
}

function onReset() {
  onBackToDescribe()
}

async function onSubmit(body: any) {
  submitting.value = true
  submitError.value = ''
  try {
    const created = await api<any>('/api/issues/', { method: 'POST', body, format: 'json' })
    successIssueId.value = Number(created.id)
    emit('created', created.id)
  } catch (e: any) {
    const data = e?.data || e?.response?._data
    submitError.value = (data && typeof data === 'object') ? JSON.stringify(data) : (e?.message || '创建失败')
  } finally {
    submitting.value = false
  }
}

// 组件卸载时取消进行中的 SSE 请求,避免后端继续白费 LLM 调用
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
}
.hero-title {
  font-size: 1.875rem;
  font-weight: 600;
  color: #111827;
  text-align: center;
  margin: 1rem 0 0.5rem;
}
:root.dark .hero-title { color: #f3f4f6; }
</style>
