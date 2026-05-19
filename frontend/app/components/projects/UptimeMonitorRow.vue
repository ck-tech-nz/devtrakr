<template>
  <div class="group flex items-center gap-4 py-3 px-3 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg">
    <div
      class="w-2 h-2 rounded-full shrink-0"
      :class="statusDotClass"
    />
    <div class="min-w-0 flex-shrink-0 w-56">
      <div class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ monitor.name }}</div>
      <a
        :href="monitor.url" target="_blank" rel="noopener"
        class="text-xs text-gray-500 dark:text-gray-400 hover:text-crystal-500 truncate block"
      >{{ monitor.url }}</a>
    </div>
    <div class="flex-1 min-w-0 overflow-hidden">
      <ProjectsUptimeMonitorTimeline :checks="checks" />
    </div>
    <div class="shrink-0 text-xs w-32 text-right" :class="statusTextClass">
      {{ statusText }}
    </div>
    <div v-if="canManage" class="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
      <UButton icon="i-heroicons-pencil-square" size="xs" color="neutral" variant="ghost" @click="emit('edit')" />
      <UButton icon="i-heroicons-trash" size="xs" color="error" variant="ghost" @click="emit('delete')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatUptime } from '~/utils/formatUptime'

interface Monitor {
  id: number
  name: string
  url: string
  last_status: string
  last_up_at: string | null
  outage_started_at: string | null
}

interface Check {
  checked_at: string
  is_up: boolean
  status_code: number | null
  response_ms: number | null
  error: string
}

const props = defineProps<{
  monitor: Monitor
  checks: Check[]
  canManage: boolean
}>()

const emit = defineEmits<{ edit: []; delete: [] }>()

const statusDotClass = computed(() => {
  switch (props.monitor.last_status) {
    case 'up': return 'bg-green-500'
    case 'down': return 'bg-red-500'
    default: return 'bg-gray-300 dark:bg-gray-600'
  }
})

const statusText = computed(() => formatUptime(
  props.monitor.last_up_at, props.monitor.outage_started_at, props.monitor.last_status,
))

const statusTextClass = computed(() => {
  switch (props.monitor.last_status) {
    case 'up': return 'text-green-600 dark:text-green-400'
    case 'down': return 'text-red-600 dark:text-red-400'
    default: return 'text-gray-400 dark:text-gray-500'
  }
})
</script>
