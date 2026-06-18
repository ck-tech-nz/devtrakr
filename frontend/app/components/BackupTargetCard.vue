<script setup lang="ts">
interface LatestBackup {
  status: string
  created_at: string
}

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

const props = withDefaults(defineProps<{
  target: BackupTarget
  running: boolean
  expanded: boolean
  records: BackupRecord[]
  // 是否显示卡片外边框;项目详情页已套在 section 容器内,传 false 去掉多余的双层边框
  bordered?: boolean
}>(), {
  bordered: true,
})

const emit = defineEmits<{
  run: []
  toggle: []
  download: [record: BackupRecord]
  delete: [record: BackupRecord]
}>()

const { formatSize, formatTime, statusMap } = useBackupFormat()
const toast = useToast()

// 失败记录可点击查看完整原因（pg_dump / ssh 的 stderr 存在 error_message 里）
function isFailedWithReason(r: BackupRecord): boolean {
  return r.status === 'failed' && !!r.error_message
}

function showError(r: BackupRecord) {
  toast.add({
    title: `备份失败：${r.filename}`,
    description: r.error_message,
    color: 'error',
    icon: 'i-heroicons-exclamation-triangle',
    duration: 0,
  })
}

const recordColumns = [
  { accessorKey: 'filename', header: '文件名' },
  { accessorKey: 'file_size', header: '大小' },
  { accessorKey: 'status', header: '状态' },
  { accessorKey: 'trigger', header: '触发方式' },
  { accessorKey: 'created_by_name', header: '操作人' },
  { accessorKey: 'created_at', header: '时间' },
  { accessorKey: 'actions', header: '操作' },
]

const triggerMap: Record<string, string> = {
  manual: '手动',
  scheduled: '定时',
}

const connectionSummary = computed(() => {
  const parts: string[] = [props.target.ssh_host || '本地', props.target.db_name]
  if (props.target.docker_container) parts.push(props.target.docker_container)
  return parts.join(' / ')
})
</script>

<template>
  <div
    class="rounded-lg bg-white dark:bg-gray-900 divide-y divide-gray-100 dark:divide-gray-800"
    :class="{ border: bordered }"
  >
    <!-- 卡片头部：整行点击展开/收起（参考 issue card 的整卡可点击；立即备份按钮 @click.stop 不触发） -->
    <div
      class="p-4 flex items-start justify-between gap-4 cursor-pointer rounded-t-lg hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors"
      @click="emit('toggle')"
    >
      <div class="flex-1 min-w-0 space-y-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-medium text-sm">{{ target.name }}</span>
          <span class="text-xs text-gray-400">{{ target.project_name || '站点级' }}</span>
          <UBadge
            v-if="target.latest_backup"
            :color="statusMap[target.latest_backup.status]?.color"
            variant="subtle"
            size="xs"
          >
            {{ statusMap[target.latest_backup.status]?.label }}
            {{ formatTime(target.latest_backup.created_at) }}
          </UBadge>
          <UBadge v-else color="neutral" variant="subtle" size="xs">暂无备份</UBadge>
        </div>
        <div class="text-xs text-gray-500 flex flex-wrap gap-x-4 gap-y-0.5">
          <span>连接：{{ connectionSummary }}</span>
          <span>计划：{{ target.schedule_cron || '仅手动' }}</span>
          <span>保留：{{ target.retention_count }} 份</span>
        </div>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <UButton
          size="xs"
          variant="outline"
          icon="i-heroicons-play"
          :loading="running"
          @click.stop="emit('run')"
        >
          立即备份
        </UButton>
        <!-- 被动的展开/收起指示箭头（不再是单独按钮,整个 header 才是点击区域） -->
        <UIcon
          :name="expanded ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'"
          class="size-5 text-gray-400 dark:text-gray-500 shrink-0"
        />
      </div>
    </div>

    <!-- 备份记录列表（展开时显示） -->
    <div v-if="expanded" class="p-4">
      <UTable
        :data="records"
        :columns="recordColumns"
        :ui="{ th: 'text-xs', td: 'text-sm' }"
      >
        <template #file_size-cell="{ row }">
          {{ formatSize(row.original.file_size) }}
        </template>
        <template #status-cell="{ row }">
          <UBadge
            :color="statusMap[row.original.status]?.color"
            variant="subtle"
            :class="isFailedWithReason(row.original) ? 'cursor-pointer gap-1' : ''"
            :title="isFailedWithReason(row.original) ? '点击查看失败原因' : undefined"
            @click="isFailedWithReason(row.original) && showError(row.original)"
          >
            {{ statusMap[row.original.status]?.label }}
            <UIcon
              v-if="isFailedWithReason(row.original)"
              name="i-heroicons-exclamation-circle-16-solid"
              class="size-3.5"
            />
          </UBadge>
        </template>
        <template #trigger-cell="{ row }">
          {{ triggerMap[row.original.trigger] || row.original.trigger }}
        </template>
        <template #created_by_name-cell="{ row }">
          {{ row.original.created_by_name || '-' }}
        </template>
        <template #created_at-cell="{ row }">
          {{ formatTime(row.original.created_at) }}
        </template>
        <template #actions-cell="{ row }">
          <div class="flex gap-2">
            <UButton
              v-if="row.original.status === 'success'"
              size="xs"
              variant="ghost"
              icon="i-heroicons-arrow-down-tray"
              @click="emit('download', row.original)"
            />
            <UButton
              size="xs"
              variant="ghost"
              color="error"
              icon="i-heroicons-trash"
              @click="emit('delete', row.original)"
            />
          </div>
        </template>
      </UTable>
    </div>
  </div>
</template>
