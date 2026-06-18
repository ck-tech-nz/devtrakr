<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">
        数据库备份 ({{ targets.length }})
      </h3>
      <UButton
        size="xs" color="neutral" variant="ghost"
        icon="i-heroicons-arrow-path"
        :loading="loading"
        @click="refresh"
      >刷新</UButton>
    </div>

    <div v-if="loading" class="text-sm text-gray-400 dark:text-gray-500 py-2">加载中...</div>

    <div v-else-if="targets.length === 0" class="text-sm text-gray-400 dark:text-gray-500 py-2">
      暂无备份目标
    </div>

    <div v-else class="space-y-2">
      <BackupTargetCard
        v-for="t in targets" :key="t.id" :target="t"
        :bordered="false"
        :running="runningId === t.id" :expanded="expandedId === t.id"
        :records="recordsByTarget[t.id] || []"
        @run="runBackup(t)" @toggle="toggleRecords(t)"
        @download="downloadBackup" @delete="deleteBackup"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
interface LatestBackup { status: string; created_at: string }
interface BackupTarget {
  id: number
  project: number | null
  project_name: string | null
  name: string
  db_name: string
  ssh_host: string
  docker_container: string
  schedule_cron: string
  schedule_enabled: boolean
  retention_count: number
  is_active: boolean
  latest_backup: LatestBackup | null
}
interface BackupRecord {
  id: number
  target: number | null
  filename: string
  file_size: number | null
  status: 'running' | 'success' | 'failed'
  error_message: string
  trigger: 'manual' | 'scheduled'
  created_by_name: string | null
  created_at: string
}

const props = defineProps<{
  projectId: number
}>()

const { api } = useApi()
const toast = useToast()

const loading = ref(false)
const targets = ref<BackupTarget[]>([])
const runningId = ref<number | null>(null)
const expandedId = ref<number | null>(null)
const recordsByTarget = ref<Record<number, BackupRecord[]>>({})

async function fetchTargets() {
  loading.value = true
  try {
    const res = await api<any>(`/api/backups/targets/?project=${props.projectId}`)
    targets.value = res.results ?? res
  } finally {
    loading.value = false
  }
}

async function runBackup(t: BackupTarget) {
  runningId.value = t.id
  try {
    await api(`/api/backups/targets/${t.id}/run/`, { method: 'POST' })
    toast.add({ title: '已开始备份', color: 'success' })
  } catch (e: any) {
    toast.add({ title: e?.data?.detail || '备份失败', color: 'error' })
  } finally {
    runningId.value = null
  }
}

async function toggleRecords(t: BackupTarget) {
  if (expandedId.value === t.id) { expandedId.value = null; return }
  expandedId.value = t.id
  const res = await api<any>(`/api/backups/backups/?target=${t.id}&page_size=200`)
  recordsByTarget.value[t.id] = res.results ?? res
}

// 刷新:重新拉取目标列表,并刷新当前展开目标的记录(异步备份完成后用)
async function refresh() {
  await fetchTargets()
  if (expandedId.value) {
    const res = await api<any>(`/api/backups/backups/?target=${expandedId.value}&page_size=200`)
    recordsByTarget.value[expandedId.value] = res.results ?? res
  }
}

async function downloadBackup(row: BackupRecord) {
  const token = localStorage.getItem('access_token')
  try {
    const response = await fetch(`/api/backups/backups/${row.id}/download/`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) throw new Error()
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = row.filename; a.click()
    URL.revokeObjectURL(url)
  } catch { toast.add({ title: '下载失败', color: 'error' }) }
}

async function deleteBackup(row: BackupRecord) {
  if (!confirm(`确定要删除备份 ${row.filename}？`)) return
  try {
    await api(`/api/backups/backups/${row.id}/`, { method: 'DELETE' })
    toast.add({ title: '已删除', color: 'success' })
    if (expandedId.value) {
      const res = await api<any>(`/api/backups/backups/?target=${expandedId.value}&page_size=200`)
      recordsByTarget.value[expandedId.value] = res.results ?? res
    }
  } catch { toast.add({ title: '删除失败', color: 'error' }) }
}

onMounted(fetchTargets)
</script>
