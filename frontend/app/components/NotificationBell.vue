<template>
  <div class="relative" ref="containerRef">
    <UButton
      icon="i-heroicons-bell"
      variant="ghost"
      color="neutral"
      size="sm"
      class="relative"
      @click="togglePanel"
    >
      <span
        v-if="unreadCount > 0"
        class="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-red-500 text-white text-[10px] font-medium rounded-full flex items-center justify-center"
      >
        {{ unreadCount > 99 ? '99+' : unreadCount }}
      </span>
    </UButton>

    <!-- Dropdown panel -->
    <Transition
      enter-active-class="transition ease-out duration-150"
      enter-from-class="opacity-0 translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition ease-in duration-100"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-1"
    >
      <!-- 手机(max-md):锚定到视口、贴 header 下方、左右留 8px 的全宽面板,避免被铃铛右对齐挤出屏外 -->
      <div
        v-if="open"
        class="absolute right-0 top-full mt-2 w-80 max-md:fixed max-md:left-2 max-md:right-2 max-md:top-16 max-md:w-auto max-md:mt-0 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-50 overflow-hidden"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
          <span class="text-sm font-semibold text-gray-900 dark:text-gray-100">通知</span>
          <button
            v-if="unreadCount > 0"
            class="text-xs text-primary-600 dark:text-primary-400 hover:underline"
            @click="handleMarkAllRead"
          >
            全部已读
          </button>
        </div>

        <!-- List -->
        <div class="max-h-80 overflow-y-auto">
          <div v-if="notifications.length === 0" class="py-8 text-center text-sm text-gray-400">
            暂无通知
          </div>
          <button
            v-for="n in notifications"
            :key="n.id"
            class="w-full text-left px-4 py-3 border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            :class="{ 'bg-primary-50/50 dark:bg-primary-950/30': !n.is_read }"
            @click="handleClick(n)"
          >
            <div class="flex items-start gap-2">
              <span
                v-if="!n.is_read"
                class="mt-1.5 w-2 h-2 rounded-full bg-primary-500 flex-shrink-0"
              />
              <div class="min-w-0 flex-1">
                <p class="text-sm text-gray-900 dark:text-gray-100 truncate">{{ n.title }}</p>
                <p class="text-xs text-gray-400 mt-0.5">{{ formatTime(n.created_at) }}</p>
              </div>
            </div>
          </button>
        </div>

        <!-- Footer -->
        <div class="px-4 py-2 border-t border-gray-100 dark:border-gray-800 text-center">
          <NuxtLink
            to="/app/notifications"
            class="text-xs text-primary-600 dark:text-primary-400 hover:underline"
            @click="open = false"
          >
            查看全部通知
          </NuxtLink>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
const { unreadCount, notifications, fetchRecent, markRead, markAllRead, startPolling, stopPolling } = useNotifications()

const open = ref(false)
const containerRef = ref<HTMLElement | null>(null)

function togglePanel() {
  open.value = !open.value
  if (open.value) fetchRecent()
}

function handleClick(n: (typeof notifications.value)[0]) {
  if (!n.is_read) markRead(n.id)
  navigateTo(`/app/notifications/${n.id}`)
  open.value = false
}

async function handleMarkAllRead() {
  await markAllRead()
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} 天前`
  return date.toLocaleDateString('zh-CN')
}

// Close on outside click
function onClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => {
  startPolling()
  document.addEventListener('click', onClickOutside)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('click', onClickOutside)
})
</script>
