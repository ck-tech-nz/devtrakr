<script setup lang="ts">
import { ISSUE_STATUS, statusColor } from '~/constants/issueStatus'
import { useIssueActions } from '~/composables/useIssueActions'

interface IssueLike {
  id: number
  status: string
  assignee: number | null
  assignee_name: string | null
  can_claim?: boolean
  can_confirm?: boolean
  can_transfer?: boolean
  can_assign?: boolean
}

const props = defineProps<{
  issue: IssueLike
  selfUserId: number
}>()
const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'request-transfer'): void
  (e: 'request-assign'): void
}>()

const { claim, confirm } = useIssueActions()
const busy = ref(false)

const isAssignedToSelf = computed(() => props.issue.assignee === props.selfUserId)

const assigneeLabel = computed(() => {
  if (!props.issue.assignee_name) return ''
  return isAssignedToSelf.value ? '我' : props.issue.assignee_name
})

const trailingActionLabel = computed(() => {
  switch (props.issue.status) {
    case ISSUE_STATUS.PENDING_CONFIRMATION: return '待确认'
    case ISSUE_STATUS.IN_PROGRESS: return '处理中'
    case ISSUE_STATUS.RESOLVED: return '已解决'
    case ISSUE_STATUS.PUBLISHED: return '已发布'
    case ISSUE_STATUS.CLOSED: return '已关闭'
    default: return props.issue.status
  }
})

const badgeLabel = computed(() => {
  if (!assigneeLabel.value) return trailingActionLabel.value
  return `${assigneeLabel.value} ${trailingActionLabel.value}`
})

async function onClaim() {
  if (busy.value) return
  busy.value = true
  try {
    await claim(props.issue.id)
    emit('changed')
  } finally { busy.value = false }
}

async function onConfirm() {
  if (busy.value) return
  busy.value = true
  try {
    await confirm(props.issue.id)
    emit('changed')
  } finally { busy.value = false }
}
</script>

<template>
  <div class="flex items-center gap-1 min-w-0">
    <!-- 待分配 -->
    <template v-if="issue.status === ISSUE_STATUS.UNASSIGNED">
      <UButton
        v-if="issue.can_claim"
        size="xs" color="primary" variant="soft"
        icon="i-lucide-plus" :loading="busy"
        @click.stop="onClaim"
      >接单</UButton>
      <UButton
        v-if="issue.can_assign"
        size="xs" color="neutral" variant="ghost"
        @click.stop="emit('request-assign')"
      >指派</UButton>
      <UBadge
        v-if="!issue.can_claim && !issue.can_assign"
        :color="statusColor(issue.status)" variant="subtle" size="sm"
      >待分配</UBadge>
    </template>

    <!-- 待确认: 自己的 -->
    <template v-else-if="issue.status === ISSUE_STATUS.PENDING_CONFIRMATION && isAssignedToSelf">
      <UButton
        size="xs" color="primary" variant="soft"
        icon="i-lucide-check" :loading="busy"
        @click.stop="onConfirm"
      >接受</UButton>
      <UButton
        size="xs" color="neutral" variant="ghost"
        icon="i-lucide-corner-up-right"
        @click.stop="emit('request-transfer')"
      />
    </template>

    <!-- 待确认/进行中: 别人的 (经理可转单) -->
    <template v-else-if="(issue.status === ISSUE_STATUS.PENDING_CONFIRMATION || issue.status === ISSUE_STATUS.IN_PROGRESS) && !isAssignedToSelf">
      <UBadge :color="statusColor(issue.status)" variant="subtle" size="sm">
        {{ badgeLabel }}
      </UBadge>
      <UButton
        v-if="issue.can_transfer"
        size="xs" color="neutral" variant="ghost"
        icon="i-lucide-corner-up-right"
        @click.stop="emit('request-transfer')"
      />
    </template>

    <!-- 进行中: 自己的 -->
    <template v-else-if="issue.status === ISSUE_STATUS.IN_PROGRESS && isAssignedToSelf">
      <UBadge :color="statusColor(issue.status)" variant="subtle" size="sm">
        我 处理中
      </UBadge>
      <UButton
        size="xs" color="neutral" variant="ghost"
        icon="i-lucide-corner-up-right"
        @click.stop="emit('request-transfer')"
      />
    </template>

    <!-- 已解决/已发布/已关闭/未计划 -->
    <template v-else>
      <UBadge :color="statusColor(issue.status)" variant="subtle" size="sm">
        {{ badgeLabel }}
      </UBadge>
    </template>
  </div>
</template>
