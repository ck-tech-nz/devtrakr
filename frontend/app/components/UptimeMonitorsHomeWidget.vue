<template>
  <div v-if="productionMonitors.length > 0" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">
        生产环境监控 ({{ productionMonitors.length }})
      </h3>
      <div class="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
        <span class="flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-green-500" />正常 {{ upCount }}
        </span>
        <span class="flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-red-500" />宕机 {{ downCount }}
        </span>
        <span v-if="unknownCount > 0" class="flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-gray-300 dark:bg-gray-600" />未知 {{ unknownCount }}
        </span>
      </div>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
      <NuxtLink
        v-for="m in productionMonitors" :key="m.id"
        :to="`/app/projects/${m.project}`"
        class="flex items-center gap-2.5 px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors min-w-0"
      >
        <span class="w-2 h-2 rounded-full shrink-0" :class="dotClass(m.last_status)" />
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ m.name }}</div>
          <div class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ m.project_name || '-' }}</div>
        </div>
        <span class="text-xs shrink-0" :class="statusTextClass(m.last_status)">
          {{ shortStatus(m) }}
        </span>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatUptime } from '~/utils/formatUptime'

interface Monitor {
  id: number
  project: number
  project_name: string
  name: string
  environment: string
  last_status: string
  last_up_at: string | null
  outage_started_at: string | null
}

const { api } = useApi()

const monitors = ref<Monitor[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

async function fetchMonitors() {
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
  try {
    const data = await api<Monitor[]>('/api/uptime/monitors/')
    monitors.value = data ?? []
  } catch (e) {
    console.warn('Failed to fetch uptime monitors', e)
  }
}

const productionMonitors = computed(() => monitors.value.filter(m => m.environment === 'production'))

const upCount = computed(() => productionMonitors.value.filter(m => m.last_status === 'up').length)
const downCount = computed(() => productionMonitors.value.filter(m => m.last_status === 'down').length)
const unknownCount = computed(() => productionMonitors.value.filter(m => m.last_status === 'unknown').length)

function dotClass(status: string): string {
  switch (status) {
    case 'up': return 'bg-green-500'
    case 'down': return 'bg-red-500'
    default: return 'bg-gray-300 dark:bg-gray-600'
  }
}

function statusTextClass(status: string): string {
  switch (status) {
    case 'up': return 'text-green-600 dark:text-green-400'
    case 'down': return 'text-red-600 dark:text-red-400'
    default: return 'text-gray-400 dark:text-gray-500'
  }
}

function shortStatus(m: Monitor): string {
  return formatUptime(m.last_up_at, m.outage_started_at, m.last_status)
}

onMounted(async () => {
  await fetchMonitors()
  pollTimer = setInterval(fetchMonitors, 5_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
