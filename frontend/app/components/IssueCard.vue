<template>
  <NuxtLink
    :to="`/app/issues/${issue.id}`"
    class="block backdrop-blur-sm border rounded-xl p-3 active:scale-[0.98] transition-transform"
    :class="priorityCardClass(issue.priority) || 'bg-white/70 dark:bg-gray-800/70 border-white/85 dark:border-gray-700/50'"
    :style="priorityCardStyle(issue.priority)"
  >
    <div class="flex items-start justify-between gap-2">
      <p class="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2 flex-1">
        {{ issue.title }}
      </p>
      <div class="flex items-center gap-1 flex-shrink-0">
        <UBadge v-if="issue.source" color="info" variant="subtle" size="xs">外部</UBadge>
        <UBadge
          :color="priorityColor(issue.priority)" variant="subtle" size="xs"
          :class="priorityBadgeClass(issue.priority)" :style="priorityBadgeStyle(issue.priority)"
        >
          {{ priorityLabel(issue.priority) }}
        </UBadge>
      </div>
    </div>
    <div class="mt-2 flex items-center gap-2 text-[11px] text-gray-400 dark:text-gray-500" @click.prevent>
      <StatusCell
        :issue="(issue as any)"
        :self-user-id="selfUserId"
        @changed="emit('changed')"
        @request-transfer="emit('request-transfer', issue)"
      />
      <span>{{ issue.assignee_name || '-' }}</span>
      <span v-if="issue.created_at">{{ issue.created_at.slice(5, 10) }}</span>
    </div>
    <div
      v-if="issue.estimated_completion"
      class="mt-1 flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400"
    >
      <UIcon name="i-heroicons-calendar-days" class="w-3 h-3 shrink-0" />
      <span>要求完成日期 {{ issue.estimated_completion }}</span>
    </div>
  </NuxtLink>
</template>

<script setup lang="ts">
import StatusCell from '~/components/issue/StatusCell.vue'

const { user } = useAuth()
const selfUserId = computed(() => Number(user.value?.id ?? 0))

defineProps<{
  issue: {
    id: string | number
    title: string
    priority: string
    status: string
    assignee_name?: string
    created_at?: string
    estimated_completion?: string | null
    source?: string | null
    assignee?: number | null
    project_members?: number[]
  }
}>()

const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'request-transfer', issue: any): void
}>()
</script>
