<script setup lang="ts">
definePageMeta({ layout: 'default' })

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

const { api } = useApi()
const toast = useToast()

const loading = ref(false)
const targets = ref<BackupTarget[]>([])
const runningId = ref<number | null>(null)
const expandedId = ref<number | null>(null)
const recordsByTarget = ref<Record<number, BackupRecord[]>>({})

// 本页仅管理站点级目标(project===null);项目级备份在各自项目详情页管理
const siteTargets = computed(() => targets.value.filter(t => t.project === null))

async function fetchTargets() {
  loading.value = true
  try {
    const res = await api<any>('/api/backups/targets/')
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

// 启用/禁用、定时开关:PATCH 目标并就地更新本地状态
async function patchTarget(t: BackupTarget, patch: Record<string, unknown>) {
  try {
    await api(`/api/backups/targets/${t.id}/`, { method: 'PATCH', body: patch })
    Object.assign(t, patch)
  } catch {
    toast.add({ title: '更新失败', color: 'error' })
    await fetchTargets()
  }
}

onMounted(fetchTargets)
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center gap-2">
      <h1 class="text-lg font-semibold">数据库备份</h1>
      <UButton
        variant="ghost"
        icon="i-heroicons-arrow-path"
        :loading="loading"
        @click="refresh"
      >
        刷新
      </UButton>
    </div>

    <!-- 站点级(项目级备份请在各自项目详情页管理) -->
    <section class="space-y-2">
      <h2 class="text-sm font-medium text-gray-500">站点级</h2>
      <BackupTargetCard
        v-for="t in siteTargets" :key="t.id" :target="t"
        :running="runningId === t.id" :expanded="expandedId === t.id"
        :records="recordsByTarget[t.id] || []"
        @run="runBackup(t)" @toggle="toggleRecords(t)"
        @download="downloadBackup" @delete="deleteBackup"
        @update="patchTarget(t, $event)"
      />
    </section>
  </div>
</template>
