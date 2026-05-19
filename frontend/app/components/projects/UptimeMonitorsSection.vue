<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">
        系统监控 ({{ monitors.length }})
      </h3>
      <UButton
        v-if="canManage"
        size="xs" icon="i-heroicons-plus"
        @click="openCreate"
      >添加监控</UButton>
    </div>

    <div v-if="loading" class="text-sm text-gray-400 dark:text-gray-500 py-2">加载中...</div>

    <div v-else-if="monitors.length === 0" class="text-sm text-gray-400 dark:text-gray-500 py-2">
      暂无监控
    </div>

    <div v-else class="divide-y divide-gray-100 dark:divide-gray-800">
      <ProjectsUptimeMonitorRow
        v-for="m in monitors" :key="m.id"
        :monitor="m"
        :checks="checksMap[m.id] ?? []"
        :can-manage="canManage"
        @edit="openEdit(m)"
        @delete="confirmDelete(m)"
      />
    </div>

    <ProjectsUptimeMonitorFormModal
      v-model:open="modalOpen"
      :project-id="projectId"
      :initial="editing"
      @saved="onSaved"
    />

    <UModal v-model:open="deleteDialogOpen" title="删除监控">
      <template #body>
        <p class="text-sm">确定要删除监控 "{{ pendingDelete?.name }}" 吗?此操作不可撤销。</p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton color="neutral" variant="ghost" @click="deleteDialogOpen = false">取消</UButton>
          <UButton color="error" :loading="deleting" @click="doDelete">删除</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
interface Monitor {
  id: number
  name: string
  environment: string
  url: string
  method: string
  expected_status: string
  expected_body: string
  interval_minutes: number
  timeout_secs: number
  is_enabled: boolean
  last_status: string
  last_check_at: string | null
  last_up_at: string | null
  outage_started_at: string | null
  active_incident_issue_id: number | null
}

interface Check {
  checked_at: string
  is_up: boolean
  status_code: number | null
  response_ms: number | null
  error: string
}

const props = defineProps<{
  projectId: number
}>()

const { api } = useApi()
const { user } = useAuth()

const canManage = computed(() => Boolean(user.value?.is_superuser))

const monitors = ref<Monitor[]>([])
const checksMap = ref<Record<number, Check[]>>({})
const loading = ref(true)

const modalOpen = ref(false)
const editing = ref<Monitor | null>(null)

const deleteDialogOpen = ref(false)
const pendingDelete = ref<Monitor | null>(null)
const deleting = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null

async function fetchMonitors() {
  const data = await api<Monitor[]>(`/api/projects/${props.projectId}/monitors/`)
  monitors.value = data ?? []
}

async function fetchAllChecks() {
  const results = await Promise.all(
    monitors.value.map(async (m) => {
      try {
        const checks = await api<Check[]>(`/api/uptime/monitors/${m.id}/checks/?limit=60`)
        return [m.id, checks] as const
      } catch {
        return [m.id, []] as const
      }
    }),
  )
  checksMap.value = Object.fromEntries(results)
}

function patchStatusFields(fresh: Monitor[]) {
  // In-place update existing rows; add new ones; drop removed ones.
  const byId = new Map(fresh.map(m => [m.id, m]))
  monitors.value = monitors.value
    .filter(m => byId.has(m.id))
    .map((m) => {
      const f = byId.get(m.id)!
      return {
        ...m,
        last_status: f.last_status,
        last_check_at: f.last_check_at,
        last_up_at: f.last_up_at,
        outage_started_at: f.outage_started_at,
        active_incident_issue_id: f.active_incident_issue_id,
      }
    })
  // Append monitors that weren't there before
  const existingIds = new Set(monitors.value.map(m => m.id))
  for (const m of fresh) {
    if (!existingIds.has(m.id)) monitors.value.push(m)
  }
}

async function pollStatus() {
  try {
    const fresh = await api<Monitor[]>(`/api/projects/${props.projectId}/monitors/`)
    patchStatusFields(fresh ?? [])
  } catch (e) {
    console.warn('Failed to poll uptime monitors', e)
  }
}

function openCreate() {
  editing.value = null
  modalOpen.value = true
}

function openEdit(m: Monitor) {
  editing.value = { ...m }
  modalOpen.value = true
}

async function onSaved() {
  await fetchMonitors()
  await fetchAllChecks()
}

function confirmDelete(m: Monitor) {
  pendingDelete.value = m
  deleteDialogOpen.value = true
}

async function doDelete() {
  if (!pendingDelete.value) return
  deleting.value = true
  try {
    await api(`/api/uptime/monitors/${pendingDelete.value.id}/`, { method: 'DELETE' })
    await fetchMonitors()
    await fetchAllChecks()
    deleteDialogOpen.value = false
  } catch (e) {
    console.error('Delete failed', e)
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  try {
    await fetchMonitors()
    await fetchAllChecks()
  } finally {
    loading.value = false
  }
  pollTimer = setInterval(pollStatus, 5_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
