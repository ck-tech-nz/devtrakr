<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">我的任务</h1>

    <!-- 加载中 -->
    <div v-if="loading" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center">
      <UIcon name="i-heroicons-clipboard-document-list" class="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-3 animate-pulse" />
      <p class="text-gray-500 dark:text-gray-400">加载中...</p>
    </div>

    <!-- 暂无任务 -->
    <div v-else-if="!current" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center">
      <UIcon name="i-heroicons-clipboard-document-list" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
      <p class="text-gray-500 dark:text-gray-400">暂无派发给你的任务</p>
    </div>

    <template v-else>
      <!-- 汇总卡片 -->
      <div class="grid grid-cols-2 lg:grid-cols-2 gap-4">
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
          <p class="text-sm text-gray-400 dark:text-gray-500 mb-1">行动项数量</p>
          <p class="text-3xl font-bold text-gray-900 dark:text-gray-100">{{ actionItems.length }}</p>
        </div>
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
          <p class="text-sm text-gray-400 dark:text-gray-500 mb-2">完成进度</p>
          <p class="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
            {{ doneCount }} / {{ actionItems.length }} 项
          </p>
          <UProgress :value="progressPct" color="success" size="sm" />
        </div>
      </div>

      <!-- 行动项列表 -->
      <div class="space-y-3">
        <div
          v-for="item in actionItems"
          :key="item.id"
          class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden"
        >
          <!-- 标题行（可点击展开） -->
          <div
            class="p-4 cursor-pointer flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
            @click="toggleExpand(item.id)"
          >
            <div class="flex items-center gap-3 min-w-0">
              <UIcon
                :name="expandedItems.has(item.id) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                class="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0"
              />
              <UBadge :color="priorityColor(item.priority)" size="xs" class="flex-shrink-0">
                {{ priorityLabel(item.priority) }}
              </UBadge>
              <span class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ item.title }}</span>
            </div>
            <div class="flex items-center gap-3 flex-shrink-0 ml-3">
              <span
                v-if="item.due_date"
                class="text-xs"
                :class="isOverdue(item) ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-400 dark:text-gray-500'"
              >截止 {{ item.due_date }}</span>
              <UBadge :color="statusColor(item.status)" variant="subtle" size="xs">
                {{ statusLabel(item.status) }}
              </UBadge>
            </div>
          </div>

          <!-- 展开内容 -->
          <div v-if="expandedItems.has(item.id)" class="border-t border-gray-100 dark:border-gray-800 p-4 space-y-4">
            <!-- 描述 -->
            <div v-if="item.description">
              <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">描述</p>
              <p class="text-sm text-gray-700 dark:text-gray-300">{{ item.description }}</p>
            </div>

            <!-- 可量化目标 -->
            <div v-if="item.measurable_target">
              <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">可量化目标</p>
              <p class="text-sm text-gray-700 dark:text-gray-300">{{ item.measurable_target }}</p>
            </div>

            <!-- 状态操作 -->
            <div class="flex items-center gap-3">
              <UButton
                v-if="item.status === 'pending'"
                size="sm"
                color="primary"
                icon="i-heroicons-play"
                :loading="updatingStatus[item.id]"
                @click.stop="updateStatus(item.id, 'in_progress')"
              >
                开始执行
              </UButton>
              <UButton
                v-if="item.status === 'in_progress'"
                size="sm"
                color="success"
                icon="i-heroicons-check"
                :loading="updatingStatus[item.id]"
                @click.stop="openSubmit(item.id)"
              >
                提交完成
              </UButton>
              <div v-if="item.status === 'submitted'" class="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
                <UIcon name="i-heroicons-clock" class="w-4 h-4" />
                <span>等待验收</span>
              </div>
              <div v-if="item.status === 'verified'" class="w-full space-y-2">
                <div class="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                  <UIcon name="i-heroicons-check-badge" class="w-4 h-4" />
                  <span>已评分</span>
                </div>
                <div
                  v-for="d in (item.review_dimensions || [])"
                  :key="d.key"
                  class="flex items-center gap-2 text-sm"
                >
                  <span class="text-gray-500 dark:text-gray-400 w-20">{{ d.label }}</span>
                  <span class="text-amber-500">{{ '★'.repeat(item.scores?.[d.key] || 0) }}<span class="text-gray-300 dark:text-gray-600">{{ '★'.repeat(5 - (item.scores?.[d.key] || 0)) }}</span></span>
                </div>
                <div v-if="item.review_comment" class="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 rounded p-2">
                  <span class="text-xs text-gray-400 dark:text-gray-500">总评：</span>{{ item.review_comment }}
                </div>
              </div>
              <div v-if="item.status === 'not_achieved'" class="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                <UIcon name="i-heroicons-x-circle" class="w-4 h-4" />
                <span>未达成</span>
              </div>
            </div>

            <!-- 评论列表 -->
            <div v-if="item.comments && item.comments.length" class="space-y-2">
              <p class="text-xs font-medium text-gray-400 dark:text-gray-500">评论</p>
              <div
                v-for="c in item.comments"
                :key="c.id"
                class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3"
              >
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-xs font-medium text-gray-700 dark:text-gray-300">{{ c.author_name }}</span>
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ formatDate(c.created_at) }}</span>
                </div>
                <p class="text-sm text-gray-600 dark:text-gray-400">{{ c.content }}</p>
                <img
                  v-if="c.attachment_url"
                  :src="c.attachment_url"
                  class="mt-2 max-w-xs rounded border border-gray-200 dark:border-gray-700"
                  alt="附件"
                />
              </div>
            </div>

            <!-- 评论表单 -->
            <div class="flex gap-2">
              <UInput
                v-model="commentText[item.id]"
                placeholder="添加评论..."
                class="flex-1"
                size="sm"
                @keydown.enter.prevent="addComment(item.id)"
              />
              <UButton
                size="sm"
                variant="soft"
                icon="i-heroicons-paper-airplane"
                :loading="submittingComment[item.id]"
                :disabled="!commentText[item.id]?.trim()"
                @click.stop="addComment(item.id)"
              >
                发送
              </UButton>
            </div>
          </div>
        </div>
      </div>

      <!-- 提交完成对话框 -->
      <UModal v-model:open="submitModalOpen">
        <template #content>
          <div class="p-4 space-y-3">
            <h3 class="font-medium">提交完成</h3>
            <UTextarea v-model="submitNote" :rows="3" placeholder="成果说明（线上/线下完成情况，可留空）" class="w-full" />
            <div class="flex justify-end gap-2">
              <UButton variant="ghost" color="neutral" @click="submitModalOpen = false">取消</UButton>
              <UButton color="success" :loading="updatingStatus[submitItemId]" @click="confirmSubmit">确认提交</UButton>
            </div>
          </div>
        </template>
      </UModal>

      <!-- 历史归档 -->
      <div v-if="history.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
        <button
          class="w-full flex items-center justify-between p-5 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
          @click="showHistory = !showHistory"
        >
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-archive-box" class="w-4 h-4 text-gray-400 dark:text-gray-500" />
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">历史归档</h3>
            <UBadge color="neutral" variant="subtle" size="xs">{{ history.length }}</UBadge>
          </div>
          <UIcon
            :name="showHistory ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'"
            class="w-4 h-4 text-gray-400 dark:text-gray-500"
          />
        </button>
        <div v-if="showHistory" class="border-t border-gray-100 dark:border-gray-800">
          <div
            v-for="h in history"
            :key="h.id"
            class="flex items-center justify-between px-5 py-3 border-b border-gray-50 dark:border-gray-800/50 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors"
          >
            <span class="text-sm text-gray-700 dark:text-gray-300">{{ h.period }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const toast = useToast()

const loading = ref(true)
const current = ref<any>(null)
const history = ref<any[]>([])
const expandedItems = ref<Set<string>>(new Set())
const commentText = ref<Record<string, string>>({})
const updatingStatus = ref<Record<string, boolean>>({})
const submittingComment = ref<Record<string, boolean>>({})
const showHistory = ref(false)

const submitModalOpen = ref(false)
const submitNote = ref('')
const submitItemId = ref('')

async function fetchPlan() {
  loading.value = true
  try {
    const res = await api<any>('/api/kpi/plans/me/')
    current.value = res.current
    history.value = res.history || []
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function toggleExpand(itemId: string) {
  if (expandedItems.value.has(itemId)) {
    expandedItems.value.delete(itemId)
  } else {
    expandedItems.value.add(itemId)
  }
}

async function updateStatus(itemId: string, newStatus: string) {
  updatingStatus.value[itemId] = true
  try {
    await api(`/api/kpi/action-items/${itemId}/status/`, {
      method: 'POST',
      body: { status: newStatus },
    })
    toast.add({ title: '状态已更新', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '更新失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    updatingStatus.value[itemId] = false
  }
}

function openSubmit(itemId: string) {
  submitItemId.value = itemId
  submitNote.value = ''
  submitModalOpen.value = true
}

async function confirmSubmit() {
  const id = submitItemId.value
  updatingStatus.value[id] = true
  try {
    await api(`/api/kpi/action-items/${id}/status/`, {
      method: 'POST',
      body: { status: 'submitted', note: submitNote.value.trim() },
    })
    submitModalOpen.value = false
    toast.add({ title: '已提交', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '提交失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    updatingStatus.value[id] = false
  }
}

async function addComment(itemId: string) {
  const content = commentText.value[itemId]?.trim()
  if (!content) return
  submittingComment.value[itemId] = true
  try {
    await api(`/api/kpi/action-items/${itemId}/comments/`, {
      method: 'POST',
      body: { content },
    })
    commentText.value[itemId] = ''
    toast.add({ title: '评论已添加', color: 'success' })
    await fetchPlan()
  } catch {
    toast.add({ title: '评论失败', color: 'error' })
  } finally {
    submittingComment.value[itemId] = false
  }
}

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function priorityColor(priority: string) {
  if (priority === 'high') return 'error'
  if (priority === 'medium') return 'warning'
  return 'neutral'
}

function priorityLabel(priority: string) {
  if (priority === 'high') return '高'
  if (priority === 'medium') return '中'
  return '低'
}

function statusColor(status: string) {
  switch (status) {
    case 'in_progress': return 'info'
    case 'submitted': return 'warning'
    case 'verified': return 'success'
    case 'not_achieved': return 'error'
    default: return 'neutral'
  }
}

function statusLabel(status: string) {
  switch (status) {
    case 'pending': return '待开始'
    case 'in_progress': return '进行中'
    case 'submitted': return '已提交'
    case 'verified': return '已验收'
    case 'not_achieved': return '未达成'
    default: return status
  }
}

function isOverdue(item: any): boolean {
  if (!item.due_date || ['verified', 'not_achieved'].includes(item.status)) return false
  return new Date(item.due_date) < new Date(new Date().toDateString())
}

const actionItems = computed(() => current.value?.action_items || [])
const doneCount = computed(() => actionItems.value.filter((i: any) => i.status === 'verified').length)
const progressPct = computed(() =>
  actionItems.value.length > 0 ? (doneCount.value / actionItems.value.length) * 100 : 0
)

onMounted(fetchPlan)
</script>
