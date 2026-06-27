<template>
  <div v-if="totalCount > 0" class="mb-6 bg-gray-50/70 dark:bg-gray-800/40 rounded-xl p-4 border border-gray-100 dark:border-gray-800">
    <div
      class="flex items-center justify-between cursor-pointer select-none"
      :class="collapsed ? '' : 'mb-3'"
      @click="collapsed = !collapsed"
    >
      <h2 class="text-sm font-medium text-gray-500 dark:text-gray-400">
        我的待办
        <span class="ml-1.5 text-xs bg-crystal-50 dark:bg-crystal-950 text-crystal-600 dark:text-crystal-400 px-1.5 py-0.5 rounded-full">{{ totalCount }}</span>
      </h2>
      <UIcon
        :name="collapsed ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-up'"
        class="w-4 h-4 text-gray-400 dark:text-gray-500"
      />
    </div>
    <transition name="slide">
      <div v-show="!collapsed" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        <NuxtLink
          v-for="task in tasks"
          :key="task.id"
          :to="`/app/issues/${task.id}`"
          class="group flex flex-col h-full bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 rounded-lg p-3.5 hover:border-crystal-200 dark:hover:border-crystal-800 hover:shadow-sm transition-all"
        >
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs text-gray-400 dark:text-gray-500 font-mono">#{{ task.id }}</span>
            <UBadge
              :color="priorityColor(task.priority)"
              variant="subtle"
              size="xs"
              :class="priorityBadgeClass(task.priority)"
              :style="priorityBadgeStyle(task.priority)"
            >
              {{ priorityLabel(task.priority) }}
            </UBadge>
          </div>
          <p class="text-sm text-gray-900 dark:text-gray-100 font-medium line-clamp-2 group-hover:text-crystal-600 dark:group-hover:text-crystal-400 transition-colors">
            {{ task.title }}
          </p>
          <div class="flex items-center justify-between mt-auto pt-2.5">
            <span
              v-if="task.status === '待确认'"
              class="text-[11px] font-medium px-1.5 py-0.5 rounded-full bg-crystal-500 text-white"
            >待我接手</span>
            <UBadge
              v-else
              :color="statusColor(task.status)"
              variant="solid"
              size="xs"
            >
              {{ task.status }}
            </UBadge>
            <template v-if="task.status === '已发布' && isTester">
              <UButton
                size="xs"
                color="neutral"
                variant="ghost"
                :loading="closingId === task.id"
                @click.stop.prevent="onClose(task)"
              >
                关闭
              </UButton>
            </template>
            <span v-else-if="task.project_name" class="text-[11px] text-gray-400 dark:text-gray-500 truncate ml-2">{{ task.project_name }}</span>
          </div>
        </NuxtLink>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
const { tasks, totalCount, load, closeIssue, isTester } = useMyTasks()
const closingId = ref<number | null>(null)

// 折叠状态:持久化到浏览器 localStorage,刷新后保持上次的展开/收起
const COLLAPSE_KEY = 'my-pending-tasks:collapsed'
const collapsed = ref(false)
if (import.meta.client) {
  try {
    const saved = localStorage.getItem(COLLAPSE_KEY)
    if (saved === '0' || saved === '1') collapsed.value = saved === '1'
  } catch { /* 损坏的存储忽略,用默认值 */ }
  watch(collapsed, v => localStorage.setItem(COLLAPSE_KEY, v ? '1' : '0'))
}

function statusColor(status: string) {
  if (status === '待分配') return 'warning'
  if (status === '待确认') return 'warning'
  if (status === '进行中') return 'info'
  if (status === '已解决') return 'success'
  if (status === '已发布') return 'success'
  return 'neutral'
}

async function onClose(task: any) {
  closingId.value = task.id
  try {
    await closeIssue(task)
  } catch (e) {
    console.error('Failed to close issue:', e)
  } finally {
    closingId.value = null
  }
}

onMounted(() => { load() })
</script>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>
