<template>
  <div
    class="group flex items-center gap-4 py-3 px-3 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg"
    :class="{ 'cursor-pointer': canManage }"
    @click="onRowClick"
  >
    <div
      class="w-2 h-2 rounded-full shrink-0"
      :class="statusDotClass"
    />
    <div class="min-w-0 flex-shrink-0 w-56">
      <div class="flex items-center gap-1.5">
        <span class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ monitor.name }}</span>
        <span
          class="text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0"
          :class="envBadgeClass"
        >{{ envLabel }}</span>
      </div>
      <a
        :href="monitor.url" target="_blank" rel="noopener noreferrer"
        class="text-xs text-gray-500 dark:text-gray-400 hover:text-crystal-500 truncate block"
        @click.stop
      >{{ monitor.url }}</a>
    </div>
    <div class="flex-1 min-w-0 overflow-hidden">
      <ProjectsUptimeMonitorTimeline :checks="checks" />
    </div>
    <div class="shrink-0 text-xs w-32 text-right" :class="statusTextClass">
      {{ statusText }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatUptime } from '~/utils/formatUptime'

interface Monitor {
  id: number
  name: string
  environment: string
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

const emit = defineEmits<{ edit: [] }>()

function onRowClick() {
  if (props.canManage) emit('edit')
}

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

const envLabel = computed(() => {
  switch (props.monitor.environment) {
    case 'production': return '生产'
    case 'staging': return '预发'
    case 'test': return '测试'
    default: return props.monitor.environment || '-'
  }
})

const envBadgeClass = computed(() => {
  switch (props.monitor.environment) {
    case 'production': return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
    case 'staging': return 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300'
    case 'test': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
    default: return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
  }
})
</script>
