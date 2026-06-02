<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">AI 测试</h1>
      <div class="flex items-center gap-2">
        <UButton icon="i-heroicons-plus" size="sm" color="neutral" variant="outline" :disabled="!selectedProjectId" @click="showEnvModal = true">
          新建环境
        </UButton>
        <UButton icon="i-heroicons-plus" size="sm" color="neutral" variant="outline" :disabled="!selectedProjectId" @click="openFlowModal">
          新建流程
        </UButton>
        <UButton icon="i-heroicons-arrow-path" size="sm" variant="outline" :loading="loadingAll" @click="reloadAll">
          刷新
        </UButton>
      </div>
    </div>

    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4">
      <label class="block text-xs text-gray-500 dark:text-gray-400 mb-2">项目</label>
      <USelect
        v-model="selectedProjectId"
        :items="projectOptions"
        value-key="value"
        placeholder="选择项目"
      />
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-2">
        <p class="text-xs text-gray-400 dark:text-gray-500">环境数</p>
        <p class="text-2xl font-semibold text-gray-900 dark:text-gray-100">{{ environments.length }}</p>
      </div>
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-2">
        <p class="text-xs text-gray-400 dark:text-gray-500">流程数</p>
        <p class="text-2xl font-semibold text-gray-900 dark:text-gray-100">{{ flows.length }}</p>
      </div>
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-2">
        <p class="text-xs text-gray-400 dark:text-gray-500">执行数</p>
        <p class="text-2xl font-semibold text-gray-900 dark:text-gray-100">{{ runs.length }}</p>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <section class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">测试环境</h2>
        </div>
        <div v-if="loadingEnvs" class="text-sm text-gray-400 py-6 text-center">加载中...</div>
        <div v-else-if="!environments.length" class="text-sm text-gray-400 py-6 text-center">暂无环境</div>
        <div v-else class="space-y-2">
          <div v-for="env in environments" :key="env.id" class="rounded-lg border border-gray-100 dark:border-gray-800 px-3 py-2">
            <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ env.name }}</p>
            <p class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ env.base_url }}</p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {{ env.login_username || "未配置账号" }} · {{ env.has_login_password ? "已配置密码" : "未配置密码" }}
            </p>
          </div>
        </div>
      </section>

      <section class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">测试流程</h2>
        </div>
        <div v-if="loadingFlows" class="text-sm text-gray-400 py-6 text-center">加载中...</div>
        <div v-else-if="!flows.length" class="text-sm text-gray-400 py-6 text-center">暂无流程</div>
        <div v-else class="space-y-3">
          <div v-for="flow in orderedFlows" :key="flow.id" class="rounded-lg border border-gray-100 dark:border-gray-800 px-3 py-3">
            <div class="flex items-center justify-between gap-2">
              <p class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ flow.name }}</p>
              <div class="flex items-center gap-2 shrink-0">
                <UBadge :color="flowStatusColor(flow.status)" variant="subtle" size="xs">
                  {{ flowStatusLabel(flow.status) }}
                </UBadge>
                <UButton
                  size="xs"
                  :loading="runningFlowId === flow.id"
                  :disabled="flow.status !== 'active'"
                  @click="runFlow(flow)"
                >
                  运行
                </UButton>
              </div>
            </div>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{{ flow.description }}</p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              环境：{{ flow.environment_name || `#${flow.environment || "-"}` }}
            </p>
          </div>
        </div>
      </section>
    </div>

    <section class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">最近执行</h2>
      </div>
      <div v-if="loadingRuns" class="text-sm text-gray-400 py-6 text-center">加载中...</div>
      <div v-else-if="!runs.length" class="text-sm text-gray-400 py-6 text-center">暂无执行记录</div>
      <div v-else class="space-y-2">
        <div
          v-for="run in runs"
          :key="run.id"
          class="flex items-center justify-between rounded-lg border border-gray-100 dark:border-gray-800 px-4 py-3"
        >
          <div class="min-w-0">
            <p class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ run.name || `Run #${run.id}` }}</p>
            <p class="text-xs text-gray-500 dark:text-gray-400 truncate">
              {{ run.flow_name || "一次性执行" }} · {{ run.environment_name || `Env #${run.environment}` }}
            </p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {{ formatRunDayTime(run.created_at || run.started_at || run.updated_at) }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <UBadge :color="statusColor(run.status)" variant="subtle" size="xs">{{ run.status }}</UBadge>
            <UButton
              size="xs"
              color="neutral"
              variant="outline"
              :loading="loadingRunDetailId === run.id"
              @click="openRunConsole(run)"
            >
              详情
            </UButton>
            <UButton
              v-if="isRunningStatus(run.status)"
              size="xs"
              color="warning"
              variant="outline"
              :loading="cancellingRunId === run.id"
              @click="cancelRun(run.id)"
            >
              取消
            </UButton>
            <UButton
              v-if="canCreateIssue(run.status)"
              size="xs"
              color="error"
              variant="outline"
              :loading="creatingIssueRunId === run.id"
              @click="createIssueFromRun(run.id)"
            >
              转 Issue
            </UButton>
          </div>
        </div>
      </div>
    </section>

    <p v-if="pageError" class="text-sm text-red-500">{{ pageError }}</p>

    <UModal v-model:open="showStepsModal" title="执行详情" :ui="{ content: 'sm:max-w-7xl max-h-[92vh] overflow-hidden' }">
      <template #content>
        <div class="p-5 max-h-[88vh] overflow-y-auto overscroll-contain">
          <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
            <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
              {{ currentRunTitle }}
            </p>
            <UBadge :color="statusColor(currentRunStatus)" variant="subtle" size="xs">{{ currentRunStatus || "-" }}</UBadge>
          </div>
          <p v-if="currentRunSummary" class="text-xs text-gray-500 dark:text-gray-400 mb-4">{{ currentRunSummary }}</p>

          <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
            <section class="rounded-lg border border-gray-100 dark:border-gray-800 p-3">
              <div class="flex items-center justify-between mb-2">
                <h3 class="text-sm font-medium text-gray-900 dark:text-gray-100">步骤</h3>
                <span class="text-xs text-gray-400">{{ runSteps.length }}</span>
              </div>
              <div v-if="stepsError" class="text-sm text-red-500 py-4">{{ stepsError }}</div>
              <div v-else-if="!runSteps.length" class="text-sm text-gray-400 py-4">暂无步骤记录</div>
              <div v-else class="space-y-2 max-h-[62vh] overflow-y-auto pr-1">
                <div
                  v-for="step in runSteps"
                  :key="step.id"
                  class="rounded-lg border border-gray-100 dark:border-gray-800 p-3"
                >
                  <div class="flex items-center justify-between gap-2">
                    <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {{ step.step_index }}. {{ step.tool_name }}
                    </p>
                    <UBadge :color="step.status === 'success' ? 'success' : 'error'" variant="subtle" size="xs">
                      {{ step.status }}
                    </UBadge>
                  </div>
                  <p v-if="step.thought_summary" class="text-xs text-gray-600 dark:text-gray-300 mt-1 line-clamp-2">{{ step.thought_summary }}</p>
                  <p v-if="step.error_message" class="text-xs text-red-500 mt-1">{{ step.error_message }}</p>
                  <p class="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate">{{ step.page_url || "-" }}</p>
                </div>
              </div>
            </section>

            <section class="rounded-lg border border-gray-100 dark:border-gray-800 p-3">
              <div class="flex items-center justify-between mb-2">
                <h3 class="text-sm font-medium text-gray-900 dark:text-gray-100">证据</h3>
                <span class="text-xs text-gray-400">{{ runArtifacts.length }}</span>
              </div>
              <div v-if="artifactsError" class="text-sm text-red-500 py-4">{{ artifactsError }}</div>
              <div v-else-if="!runArtifacts.length" class="text-sm text-gray-400 py-4">暂无产物</div>
              <div v-else class="space-y-2 max-h-[62vh] overflow-y-auto pr-1">
                <div
                  v-for="artifact in runArtifacts"
                  :key="artifact.id"
                  class="rounded-lg border border-gray-100 dark:border-gray-800 p-3"
                >
                  <div class="flex items-center justify-between gap-2">
                    <UBadge :color="artifactColor(artifact.artifact_type)" variant="subtle" size="xs">
                      {{ artifactLabel(artifact.artifact_type) }}
                    </UBadge>
                    <p class="text-xs text-gray-400">{{ formatTime(artifact.created_at) }}</p>
                  </div>
                  <p v-if="artifact.step" class="text-xs text-gray-500 mt-1">Step #{{ artifact.step }}</p>
                  <div v-if="artifact.attachment_url" class="mt-2 space-y-2">
                    <img
                      v-if="artifact.artifact_type === 'screenshot'"
                      :src="artifact.attachment_url"
                      :alt="artifact.attachment_name || 'screenshot'"
                      class="w-full max-h-[70vh] object-contain rounded border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900"
                      loading="lazy"
                    />
                    <a
                      :href="artifact.attachment_url"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="text-xs text-primary-600 hover:underline inline-block"
                    >
                      打开截图 {{ artifact.attachment_name ? `(${artifact.attachment_name})` : "" }}
                    </a>
                  </div>
                  <pre
                    v-else-if="artifact.content"
                    class="mt-2 text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-words"
                  >{{ artifact.content }}</pre>
                </div>
              </div>
            </section>
          </div>
        </div>
      </template>
    </UModal>

    <UModal v-model:open="showEnvModal" title="新建测试环境" :ui="{ content: 'sm:max-w-5xl' }">
      <template #content>
        <div class="p-6 max-h-[80vh] overflow-y-auto">
          <div class="grid grid-cols-1 gap-3">
            <UInput v-model="envForm.name" class="w-full" placeholder="环境名称，例如 staging" />
            <UInput v-model="envForm.base_url" class="w-full" placeholder="基础 URL，例如 https://example.com" />
            <UInput v-model="envForm.login_username" class="w-full" placeholder="测试账号（可选）" />
            <UInput v-model="envForm.login_password" class="w-full" type="password" placeholder="测试密码（可选）" />
            <UInput v-model="envForm.login_entry_target" class="w-full" placeholder="登录入口选择器（可选，默认尝试 /login 和 登录按钮）" />
            <UInput v-model="envForm.login_url" class="w-full" placeholder="登录页 URL（可选，默认 /login）" />
            <UInput v-model="envForm.username_target" class="w-full" placeholder="账号输入框选择器（可选）" />
            <UInput v-model="envForm.password_target" class="w-full" placeholder="密码输入框选择器（可选）" />
            <UInput v-model="envForm.submit_target" class="w-full" placeholder="登录提交按钮选择器（可选）" />
            <UInput v-model="envForm.post_login_wait_text" class="w-full" placeholder="登录后等待文本（可选）" />
            <UTextarea
              v-model="envForm.allowed_url_patterns_text"
              class="w-full"
              :rows="3"
              placeholder="URL 白名单（可选，按逗号或换行分隔）"
            />
          </div>
          <div class="grid grid-cols-1 gap-3 mt-3">
            <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
              <input v-model="envForm.allow_write_actions" type="checkbox" class="rounded border-gray-300" />
              允许写操作
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
              <input v-model="envForm.allow_dangerous_actions" type="checkbox" class="rounded border-gray-300" />
              允许危险操作
            </label>
          </div>
          <div class="flex justify-end gap-2 pt-4 mt-4 border-t border-gray-100 dark:border-gray-800">
            <UButton variant="outline" color="neutral" @click="showEnvModal = false">取消</UButton>
            <UButton :loading="creatingEnv" @click="createEnvironment">创建</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <UModal v-model:open="showFlowModal" title="新建测试流程" :ui="{ content: 'sm:max-w-5xl' }">
      <template #content>
        <div class="p-6 max-h-[80vh] overflow-y-auto space-y-3">
          <UInput v-model="flowForm.name" class="w-full" placeholder="流程名称" />
          <UTextarea
            v-model="flowForm.description"
            class="w-full"
            :rows="4"
            placeholder="测试需求或 bug 现象（可简写），例如：创建 Issue 时点击新建问题无响应"
          />
          <USelect
            v-model="flowForm.environment"
            class="w-full"
            :items="environmentOptions"
            value-key="value"
            placeholder="选择默认环境"
          />
          <UInput v-model="flowForm.target_url" class="w-full" placeholder="目标 URL（可选，不填则使用环境 base_url）" />
          <UInput v-model="flowForm.success_criteria" class="w-full" placeholder="成功标准（可选）" />
          <div class="space-y-1">
            <label class="text-xs text-gray-500 dark:text-gray-400">最大步骤数</label>
            <UInput v-model.number="flowForm.max_steps" class="w-full" type="number" min="1" max="200" placeholder="例如 30" />
          </div>
          <div class="space-y-1">
            <label class="text-xs text-gray-500 dark:text-gray-400">执行超时（秒）</label>
            <UInput v-model.number="flowForm.timeout_secs" class="w-full" type="number" min="10" max="7200" placeholder="例如 300" />
          </div>
          <div class="grid grid-cols-1 gap-3 items-center">
            <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
              <input v-model="flowForm.cleanup_enabled" type="checkbox" class="rounded border-gray-300" />
              启用自动 cleanup
            </label>
            <USelect
              v-model="flowForm.cleanup_policy"
              class="w-full"
              :items="[
                { label: '不清理', value: 'none' },
                { label: '删除', value: 'delete' },
                { label: '关闭', value: 'close' },
              ]"
              value-key="value"
              placeholder="cleanup 策略"
            />
          </div>
          <div class="flex justify-end gap-2 pt-4 mt-4 border-t border-gray-100 dark:border-gray-800">
            <UButton variant="outline" color="neutral" @click="showFlowModal = false">取消</UButton>
            <UButton :loading="creatingFlow" @click="createFlow">创建</UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()

const projects = ref<any[]>([])
const selectedProjectId = ref<number | null>(null)

const environments = ref<any[]>([])
const flows = ref<any[]>([])
const runs = ref<any[]>([])

const loadingAll = ref(false)
const loadingEnvs = ref(false)
const loadingFlows = ref(false)
const loadingRuns = ref(false)

const pageError = ref("")
const runningFlowId = ref<number | null>(null)
const creatingIssueRunId = ref<number | null>(null)
const loadingRunDetailId = ref<number | null>(null)
const cancellingRunId = ref<number | null>(null)

const showStepsModal = ref(false)
const runSteps = ref<any[]>([])
const runArtifacts = ref<any[]>([])
const stepsError = ref("")
const artifactsError = ref("")
const currentRunTitle = ref("")
const currentRunId = ref<number | null>(null)
const currentRunStatus = ref("")
const currentRunSummary = ref("")
let runPollingTimer: ReturnType<typeof setInterval> | null = null

const showEnvModal = ref(false)
const creatingEnv = ref(false)
const envForm = ref({
  name: "",
  base_url: "",
  login_username: "",
  login_password: "",
  login_entry_target: "",
  login_url: "",
  username_target: "",
  password_target: "",
  submit_target: "",
  post_login_wait_text: "",
  allowed_url_patterns_text: "",
  allow_write_actions: false,
  allow_dangerous_actions: false,
})

const showFlowModal = ref(false)
const creatingFlow = ref(false)
const flowForm = ref({
  name: "",
  description: "",
  environment: null as number | null,
  target_url: "",
  success_criteria: "",
  max_steps: 30,
  timeout_secs: 300,
  cleanup_enabled: false,
  cleanup_policy: "none",
})

const projectOptions = computed(() =>
  projects.value.map(p => ({ label: p.name, value: p.id })),
)

const environmentOptions = computed(() =>
  environments.value.map(e => ({ label: `${e.name} (${e.base_url})`, value: e.id })),
)

const orderedFlows = computed(() =>
  [...flows.value].sort((a, b) => {
    const rank = (status: string) => (status === "active" ? 0 : status === "draft" ? 1 : 2)
    const r = rank(a.status) - rank(b.status)
    if (r !== 0) return r
    return b.id - a.id
  }),
)

function statusColor(status: string) {
  if (status === "success") return "success"
  if (status === "running" || status === "pending") return "warning"
  return "error"
}

function flowStatusLabel(status: string) {
  if (status === "active") return "启用"
  if (status === "draft") return "草稿"
  if (status === "archived") return "归档"
  return status || "-"
}

function flowStatusColor(status: string) {
  if (status === "active") return "success"
  if (status === "draft") return "warning"
  return "neutral"
}

function canCreateIssue(status: string) {
  return status === "failed" || status === "timeout" || status === "cancelled"
}

function isRunningStatus(status: string) {
  return status === "pending" || status === "running"
}

function artifactLabel(type: string) {
  if (type === "screenshot") return "截图"
  if (type === "console_log") return "Console"
  if (type === "network_log") return "Network"
  if (type === "trace") return "Trace"
  if (type === "video") return "Video"
  return type || "未知"
}

function artifactColor(type: string) {
  if (type === "screenshot") return "primary"
  if (type === "console_log") return "neutral"
  if (type === "network_log") return "warning"
  return "neutral"
}

function formatTime(value: string) {
  if (!value) return "-"
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

function formatRunDayTime(value: string) {
  if (!value) return "-"
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
}

function buildRunName(flowName: string) {
  return `${flowName} - ${formatRunDayTime(new Date().toISOString())}`
}

async function loadProjects() {
  const data = await api<any>("/api/projects/")
  projects.value = data.results || data || []
  if (!selectedProjectId.value && projects.value.length) {
    selectedProjectId.value = projects.value[0].id
  }
}

async function loadEnvironments() {
  if (!selectedProjectId.value) {
    environments.value = []
    return
  }
  loadingEnvs.value = true
  try {
    const data = await api<any>(`/api/ai-testing/environments/?project=${selectedProjectId.value}`)
    environments.value = data.results || data || []
  } finally {
    loadingEnvs.value = false
  }
}

async function loadFlows() {
  if (!selectedProjectId.value) {
    flows.value = []
    return
  }
  loadingFlows.value = true
  try {
    const data = await api<any>(`/api/ai-testing/flows/?project=${selectedProjectId.value}`)
    flows.value = data.results || data || []
  } finally {
    loadingFlows.value = false
  }
}

async function loadRuns(options?: { silent?: boolean }) {
  if (!selectedProjectId.value) {
    runs.value = []
    return
  }
  const silent = !!options?.silent
  if (!silent) {
    loadingRuns.value = true
  }
  try {
    const data = await api<any>(`/api/ai-testing/runs/?project=${selectedProjectId.value}`)
    runs.value = data.results || data || []
  } finally {
    if (!silent) {
      loadingRuns.value = false
    }
  }
}

async function reloadAll() {
  if (!selectedProjectId.value) return
  loadingAll.value = true
  pageError.value = ""
  try {
    await Promise.all([loadEnvironments(), loadFlows(), loadRuns()])
  } catch (e: any) {
    pageError.value = e?.message || "加载失败，请重试"
  } finally {
    loadingAll.value = false
  }
}

async function createEnvironment() {
  if (!selectedProjectId.value) return
  if (!envForm.value.name.trim() || !envForm.value.base_url.trim()) {
    pageError.value = "环境名称和基础 URL 必填"
    return
  }
  creatingEnv.value = true
  pageError.value = ""
  try {
    const allowedPatterns = envForm.value.allowed_url_patterns_text
      .split(/[\n,]/)
      .map(x => x.trim())
      .filter(Boolean)
    await api("/api/ai-testing/environments/", {
      method: "POST",
      body: {
        project: selectedProjectId.value,
        name: envForm.value.name.trim(),
        base_url: envForm.value.base_url.trim(),
        login_type: "username_password",
        login_username: envForm.value.login_username.trim(),
        login_password: envForm.value.login_password,
        login_config: {
          login_entry_target: envForm.value.login_entry_target.trim(),
          login_url: envForm.value.login_url.trim(),
          username_target: envForm.value.username_target.trim(),
          password_target: envForm.value.password_target.trim(),
          submit_target: envForm.value.submit_target.trim(),
          post_login_wait_text: envForm.value.post_login_wait_text.trim(),
        },
        allowed_url_patterns: allowedPatterns,
        allow_write_actions: envForm.value.allow_write_actions,
        allow_dangerous_actions: envForm.value.allow_dangerous_actions,
      },
    })
    showEnvModal.value = false
    envForm.value = {
      name: "",
      base_url: "",
      login_username: "",
      login_password: "",
      login_entry_target: "",
      login_url: "",
      username_target: "",
      password_target: "",
      submit_target: "",
      post_login_wait_text: "",
      allowed_url_patterns_text: "",
      allow_write_actions: false,
      allow_dangerous_actions: false,
    }
    await loadEnvironments()
  } catch (e: any) {
    pageError.value = e?.message || "创建环境失败"
  } finally {
    creatingEnv.value = false
  }
}

function openFlowModal() {
  showFlowModal.value = true
  if (!flowForm.value.environment && environments.value.length) {
    flowForm.value.environment = environments.value[0].id
  }
}

async function createFlow() {
  if (!selectedProjectId.value) return
  if (!flowForm.value.name.trim()) {
    pageError.value = "流程名称必填"
    return
  }
  if (!flowForm.value.environment) {
    pageError.value = "请先选择默认环境"
    return
  }
  const normalizedDescription = flowForm.value.description.trim()
    || `测试需求：${flowForm.value.name.trim()}。请由测试专家自动拆解步骤并完成执行。`
  creatingFlow.value = true
  pageError.value = ""
  try {
    await api("/api/ai-testing/flows/", {
      method: "POST",
      body: {
        project: selectedProjectId.value,
        environment: flowForm.value.environment,
        name: flowForm.value.name.trim(),
        description: normalizedDescription,
        target_url: flowForm.value.target_url.trim(),
        success_criteria: flowForm.value.success_criteria.trim(),
        max_steps: Number(flowForm.value.max_steps) || 30,
        timeout_secs: Number(flowForm.value.timeout_secs) || 300,
        cleanup_enabled: !!flowForm.value.cleanup_enabled,
        cleanup_policy: flowForm.value.cleanup_policy || "none",
        status: "active",
      },
    })
    showFlowModal.value = false
    flowForm.value = {
      name: "",
      description: "",
      environment: null,
      target_url: "",
      success_criteria: "",
      max_steps: 30,
      timeout_secs: 300,
      cleanup_enabled: false,
      cleanup_policy: "none",
    }
    await loadFlows()
  } catch (e: any) {
    pageError.value = e?.message || "创建流程失败"
  } finally {
    creatingFlow.value = false
  }
}

async function runFlow(flow: any) {
  if (!selectedProjectId.value) return
  if (flow.status !== "active") {
    pageError.value = "该流程不是启用状态，不能执行。请先启用流程。"
    return
  }
  const envId = flow.environment || flowForm.value.environment || environments.value[0]?.id
  if (!envId) {
    pageError.value = "该流程缺少环境，请先配置环境"
    return
  }
  runningFlowId.value = flow.id
  pageError.value = ""
  try {
    await api("/api/ai-testing/runs/", {
      method: "POST",
      body: {
        flow: flow.id,
        project: selectedProjectId.value,
        environment: envId,
        name: buildRunName(flow.name),
        target_url: flow.target_url || "",
      },
    })
    await loadRuns()
  } catch (e: any) {
    pageError.value = e?.message || "触发执行失败"
  } finally {
    runningFlowId.value = null
  }
}

async function createIssueFromRun(runId: number) {
  creatingIssueRunId.value = runId
  pageError.value = ""
  try {
    const issue = await api<any>(`/api/ai-testing/runs/${runId}/create-issue/`, {
      method: "POST",
      body: {},
    })
    await navigateTo(`/app/issues/${issue.id}`)
  } catch (e: any) {
    pageError.value = e?.message || "创建 Issue 失败"
  } finally {
    creatingIssueRunId.value = null
  }
}

async function loadRunDetail(runId: number) {
  const run = await api<any>(`/api/ai-testing/runs/${runId}/`)
  currentRunStatus.value = run.status || ""
  const summaryParts = [run.final_summary, run.failure_reason]
    .map((x: any) => (x || "").toString().trim())
    .filter(Boolean)
  currentRunSummary.value = summaryParts.join(" ｜ ")
  return run
}

async function loadRunSteps(runId: number) {
  const data = await api<any>(`/api/ai-testing/runs/${runId}/steps/`)
  runSteps.value = data.results || data || []
}

async function loadRunArtifacts(runId: number) {
  const data = await api<any>(`/api/ai-testing/runs/${runId}/artifacts/`)
  runArtifacts.value = data.results || data || []
}

function stopRunPolling() {
  if (runPollingTimer) {
    clearInterval(runPollingTimer)
    runPollingTimer = null
  }
}

function startRunPolling() {
  stopRunPolling()
  runPollingTimer = setInterval(async () => {
    if (!currentRunId.value || !showStepsModal.value) return
    try {
      const run = await loadRunDetail(currentRunId.value)
      await Promise.all([
        loadRunSteps(currentRunId.value),
        loadRunArtifacts(currentRunId.value),
        loadRuns({ silent: true }),
      ])
      if (!isRunningStatus(run.status)) {
        stopRunPolling()
      }
    } catch {
      stopRunPolling()
    }
  }, 4000)
}

async function cancelRun(runId: number) {
  cancellingRunId.value = runId
  pageError.value = ""
  try {
    await api(`/api/ai-testing/runs/${runId}/cancel/`, { method: "POST", body: {} })
    await loadRuns()
    if (currentRunId.value === runId) {
      await loadRunDetail(runId)
    }
  } catch (e: any) {
    pageError.value = e?.message || "取消执行失败"
  } finally {
    cancellingRunId.value = null
  }
}

async function openRunConsole(run: any) {
  loadingRunDetailId.value = run.id
  stepsError.value = ""
  artifactsError.value = ""
  runSteps.value = []
  runArtifacts.value = []
  currentRunId.value = run.id
  currentRunStatus.value = run.status || ""
  const summaryParts = [run.final_summary, run.failure_reason]
    .map((x: any) => (x || "").toString().trim())
    .filter(Boolean)
  currentRunSummary.value = summaryParts.join(" ｜ ")
  currentRunTitle.value = run.name || `Run #${run.id}`
  try {
    await Promise.all([
      loadRunDetail(run.id),
      loadRunSteps(run.id),
      loadRunArtifacts(run.id),
    ])
    showStepsModal.value = true
    if (isRunningStatus(currentRunStatus.value)) {
      startRunPolling()
    }
  } catch (e: any) {
    const msg = e?.message || "加载执行详情失败"
    stepsError.value = msg
    artifactsError.value = msg
    showStepsModal.value = true
  } finally {
    loadingRunDetailId.value = null
  }
}

watch(selectedProjectId, async () => {
  await reloadAll()
})

watch(showStepsModal, (open) => {
  if (!open) {
    stopRunPolling()
    currentRunId.value = null
  }
})

onMounted(async () => {
  loadingAll.value = true
  try {
    await loadProjects()
    await reloadAll()
  } catch (e: any) {
    pageError.value = e?.message || "初始化失败"
  } finally {
    loadingAll.value = false
  }
})

onBeforeUnmount(() => {
  stopRunPolling()
})
</script>
