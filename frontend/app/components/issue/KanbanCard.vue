<template>
  <NuxtLink :to="`/app/issues/${item.id}`" class="block">
    <div class="flex items-center justify-between mb-1.5">
      <span class="text-xs text-gray-400 dark:text-gray-500">#{{ item.id }}</span>
      <div class="flex items-center gap-1">
        <UBadge v-if="item.source" color="info" variant="subtle" size="xs">外部</UBadge>
        <UBadge
          :color="priorityColor(item.priority)" variant="subtle" size="xs"
          :class="priorityBadgeClass(item.priority)" :style="priorityBadgeStyle(item.priority)"
        >
          {{ priorityLabel(item.priority) }}
        </UBadge>
      </div>
    </div>
    <p class="text-sm text-gray-900 dark:text-gray-100 font-medium line-clamp-2">{{ item.title }}</p>
    <div class="mt-2 flex items-center justify-between gap-2">
      <div class="flex items-center min-w-0">
        <img
          v-if="avatarUrl"
          :src="avatarUrl"
          :alt="item.assignee_name || '头像'"
          class="w-5 h-5 rounded-full shrink-0"
        >
        <div v-else class="w-5 h-5 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center shrink-0">
          <span class="text-crystal-600 dark:text-crystal-400 text-[10px] font-medium">{{ (item.assignee_name || '?').slice(0, 1) }}</span>
        </div>
        <span class="ml-1.5 text-xs text-gray-400 dark:text-gray-500 truncate">{{ item.assignee_name || '-' }}</span>
      </div>
      <SharedSmartTime v-if="item.updated_at" :date="item.updated_at" class="text-[11px] text-gray-400 dark:text-gray-500 shrink-0" />
    </div>
    <div
      v-if="item.estimated_completion"
      class="mt-1.5 flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400"
    >
      <UIcon name="i-heroicons-calendar-days" class="w-3 h-3 shrink-0" />
      <span>要求完成日期 {{ item.estimated_completion }}</span>
    </div>
  </NuxtLink>
</template>

<script setup lang="ts">
const props = defineProps<{
  item: {
    id: string | number
    title: string
    priority: string
    assignee_name?: string
    assignee_avatar?: string | null
    updated_at?: string
    estimated_completion?: string | null
    source?: string | null
  }
}>()

// 处理人头像:能解析出资源才显示图片,无头像/未知 id 回退首字 flag
const { resolveAvatarUrl } = useAvatars()
const avatarUrl = computed(() =>
  props.item.assignee_avatar ? resolveAvatarUrl(props.item.assignee_avatar) : '',
)
</script>
