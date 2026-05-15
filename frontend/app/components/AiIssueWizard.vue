<template>
  <div class="ai-wizard">
    <!-- Header -->
    <div class="wizard-header">
      <div class="hello">
        <UIcon name="i-heroicons-sparkles" class="w-6 h-6 text-crystal-500" />
        <div>
          <h2 class="hello-title">你好，{{ userName }} <span class="wave">👋</span></h2>
          <p class="hello-sub">AI 助手已就绪 · 描述问题，让 AI 帮你创建 Issue</p>
        </div>
      </div>
      <div class="status">
        <span class="status-dot" />
        <span class="status-text">模型已就绪</span>
      </div>
    </div>

    <!-- Stepper -->
    <div class="stepper">
      <div class="step-pill" :class="{ active: currentStep >= 1, done: currentStep > 1 }">
        <span class="step-num">1</span>
        <span>描述问题</span>
      </div>
      <span class="step-connector" :class="{ done: currentStep > 1 }" />
      <div class="step-pill" :class="{ active: currentStep >= 2, done: currentStep > 2 }">
        <span class="step-num">2</span>
        <span>AI 分析</span>
      </div>
      <span class="step-connector" :class="{ done: currentStep > 2 }" />
      <div class="step-pill" :class="{ active: currentStep >= 3 }">
        <span class="step-num">3</span>
        <span>确认提交</span>
      </div>
    </div>

    <!-- Step body -->
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
      :projects="projects"
      :initial-project-id="lastAnalyzedProject"
      :modules="modules"
      :users="users"
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

const userName = computed(() => user.value?.name || user.value?.email || '')
const defaultProjectId = computed(() => (user.value as any)?.default_project?.id || null)

const projects = ref<{ id: string; name: string }[]>([])
const modules = ref<string[]>([])
const users = ref<{ id: string; name: string }[]>([])
const lastAnalyzedProject = ref<string>('')

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
  users.value = (usersData || []).map((u: any) => ({ id: String(u.id), name: u.name || u.username }))
})

function onAnalyze(payload: { description: string; project: string }) {
  lastAnalyzedProject.value = payload.project
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
</script>

<style scoped>
.ai-wizard {
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 1rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
:root.dark .ai-wizard { background-color: #111827; border-color: #1f2937; }

.wizard-header { display: flex; justify-content: space-between; align-items: flex-start; }
.hello { display: flex; align-items: center; gap: 0.75rem; }
.hello-title { font-size: 1.125rem; font-weight: 600; color: #111827; }
.hello-sub { font-size: 0.8125rem; color: #6b7280; margin-top: 0.125rem; }
:root.dark .hello-title { color: #f3f4f6; }
:root.dark .hello-sub { color: #9ca3af; }
.wave { display: inline-block; animation: wave 1.5s ease-in-out infinite; transform-origin: 70% 70%; }
@keyframes wave { 0%,60%,100% { transform: rotate(0); } 20% { transform: rotate(14deg); } 40% { transform: rotate(-8deg); } }

.status { display: flex; align-items: center; gap: 0.375rem; }
.status-dot {
  width: 0.5rem; height: 0.5rem; border-radius: 9999px;
  background-color: #10b981; animation: pulse 1.5s infinite;
}
.status-text { font-size: 0.75rem; color: #6b7280; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

.stepper { display: flex; align-items: center; gap: 0.5rem; }
.step-pill {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.375rem 0.75rem; border-radius: 9999px;
  font-size: 0.8125rem; color: #9ca3af;
  background-color: #f3f4f6;
}
.step-pill.active { color: #7c3aed; background-color: #ede9fe; }
.step-pill.done { color: #059669; background-color: #d1fae5; }
:root.dark .step-pill { background-color: #1f2937; color: #6b7280; }
:root.dark .step-pill.active { background-color: rgba(124, 58, 237, 0.15); color: #c4b5fd; }
:root.dark .step-pill.done { background-color: rgba(5, 150, 105, 0.18); color: #34d399; }
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 1.25rem; height: 1.25rem;
  border-radius: 9999px;
  background-color: currentColor;
  color: #ffffff;
  font-size: 0.625rem; font-weight: 700;
}
.step-pill.active .step-num,
.step-pill.done .step-num { background-color: currentColor; color: #ffffff; }
.step-connector {
  height: 1px; flex: 1; max-width: 3rem;
  background-color: #e5e7eb;
}
.step-connector.done { background-color: #10b981; }
:root.dark .step-connector { background-color: #374151; }
</style>
