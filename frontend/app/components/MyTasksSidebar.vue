<template>
  <div v-if="visible" class="pt-2">
    <hr class="my-2 border-gray-100 dark:border-gray-800" />
    <button
      class="relative flex items-center w-full h-10 px-2 rounded-lg transition-colors"
      :class="open
        ? 'text-crystal-600 dark:text-crystal-400'
        : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'"
      @click="toggle"
    >
      <UIcon name="i-heroicons-inbox-stack" class="w-5 h-5 flex-shrink-0" />
      <transition name="fade">
        <span v-if="expanded" class="ml-3 text-sm font-medium whitespace-nowrap flex-1 text-left flex items-center gap-2">
          All Tasks
          <span
            v-if="totalCount > 0"
            class="text-[10px] bg-crystal-50 dark:bg-crystal-950 text-crystal-600 dark:text-crystal-400 px-1.5 py-0.5 rounded-full"
          >{{ totalCount }}</span>
        </span>
      </transition>
      <transition name="fade">
        <UIcon
          v-if="expanded"
          :name="open ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
          class="w-3.5 h-3.5 flex-shrink-0 opacity-50"
        />
      </transition>
      <span
        v-if="!expanded && totalCount > 0"
        class="absolute right-2 top-2 text-[10px] bg-crystal-500 text-white rounded-full px-1.5 leading-tight"
      >{{ totalCount }}</span>
    </button>

    <template v-if="expanded && open">
      <NuxtLink
        v-for="task in displayTasks"
        :key="task.id"
        :to="`/app/issues/${task.id}`"
        class="flex items-center h-9 pl-9 pr-2 rounded-lg transition-colors text-xs text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200"
      >
        <span class="font-mono text-gray-400 dark:text-gray-600 mr-2">#{{ task.id }}</span>
        <span class="truncate flex-1">{{ task.title }}</span>
        <span class="w-1.5 h-1.5 rounded-full ml-2 flex-shrink-0" :class="dotColor(task.status)" />
      </NuxtLink>

      <div v-if="displayTasks.length === 0" class="pl-9 pr-2 py-1.5 text-xs text-gray-400 dark:text-gray-600">
        暂无待办
      </div>

      <NuxtLink
        v-if="totalCount > 0"
        to="/app/issues"
        class="flex items-center h-8 pl-9 pr-2 rounded-lg text-xs text-crystal-600 dark:text-crystal-400 hover:bg-crystal-50 dark:hover:bg-crystal-950"
      >
        查看全部 →
      </NuxtLink>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{ expanded: boolean }>()

const { user, can } = useAuth()
const { tasks, totalCount, load } = useMyTasks()

const visible = computed(() => !!user.value && can('issues.view_issue'))
const open = ref(true)

const displayTasks = computed(() => tasks.value)

function toggle() {
  open.value = !open.value
  if (open.value && tasks.value.length === 0) load()
}

function dotColor(status: string) {
  if (status === '待分配') return 'bg-amber-400'
  if (status === '待确认') return 'bg-amber-400'
  if (status === '进行中') return 'bg-blue-400'
  if (status === '已发布') return 'bg-emerald-400'
  return 'bg-gray-300'
}

onMounted(() => { if (visible.value) load() })
</script>

<style scoped>
.fade-enter-active { transition: opacity 0.2s ease 0.1s; }
.fade-leave-active { transition: opacity 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
