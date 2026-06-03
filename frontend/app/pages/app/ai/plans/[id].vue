<template>
  <div class="space-y-6">
    <!-- 返回 -->
    <NuxtLink to="/app/ai/plans" class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors">
      <UIcon name="i-heroicons-arrow-left" class="w-4 h-4" />
      返回团队任务
    </NuxtLink>

    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <template v-else-if="plan">
      <!-- 成员信息 + 操作 -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-6">
        <div class="flex items-center gap-4 flex-wrap">
          <img
            v-if="plan.user_avatar"
            :src="resolveAvatarUrl(plan.user_avatar)"
            class="w-14 h-14 rounded-full flex-shrink-0"
          >
          <div
            v-else
            class="w-14 h-14 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center text-lg font-semibold text-crystal-600 dark:text-crystal-400 flex-shrink-0"
          >
            {{ (plan.user_name || '?').slice(0, 1) }}
          </div>

          <div class="flex-1 min-w-0">
            <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{{ plan.user_name || '未知用户' }}</h1>
            <div class="flex items-center gap-2 mt-1.5 flex-wrap">
              <span class="text-sm text-gray-500 dark:text-gray-400 tabular-nums">{{ plan.period }}</span>
              <UBadge :color="statusColor(plan.status)" variant="subtle" size="xs">{{ statusLabel(plan.status) }}</UBadge>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <UButton
              v-if="plan.status === 'draft'"
              size="sm"
              icon="i-heroicons-paper-airplane"
              :loading="publishing"
              @click="handlePublish"
            >
              发布
            </UButton>
          </div>
        </div>

        <!-- 本月概览（派生总体目标） -->
        <div class="mt-6 pt-5 border-t border-gray-100 dark:border-gray-800 grid grid-cols-2 sm:grid-cols-5 gap-4">
          <div>
            <p class="text-xs font-medium text-gray-400 dark:text-gray-500">任务总数</p>
            <p class="text-2xl font-bold tabular-nums text-gray-900 dark:text-gray-100 mt-0.5">{{ overview.total }}</p>
          </div>
          <div>
            <p class="text-xs font-medium text-gray-400 dark:text-gray-500">进行中</p>
            <p class="text-2xl font-bold tabular-nums text-blue-600 dark:text-blue-400 mt-0.5">{{ overview.inProgress }}</p>
          </div>
          <div>
            <p class="text-xs font-medium text-gray-400 dark:text-gray-500">待验收</p>
            <p class="text-2xl font-bold tabular-nums text-amber-600 dark:text-amber-400 mt-0.5">{{ overview.submitted }}</p>
          </div>
          <div>
            <p class="text-xs font-medium text-gray-400 dark:text-gray-500">已完成</p>
            <p class="text-2xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400 mt-0.5">{{ overview.done }}</p>
          </div>
          <div class="col-span-2 sm:col-span-1 flex flex-col justify-center">
            <div class="flex items-center justify-between mb-1.5">
              <p class="text-xs font-medium text-gray-400 dark:text-gray-500">完成进度</p>
              <span class="text-xs font-semibold tabular-nums text-gray-700 dark:text-gray-300">{{ overview.pct }}%</span>
            </div>
            <div class="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
              <div class="h-full rounded-full bg-gradient-to-r from-crystal-500 to-emerald-500 transition-[width] duration-700" :style="{ width: overview.pct + '%' }" />
            </div>
            <p v-if="overview.overdue > 0" class="text-[11px] font-medium text-red-600 dark:text-red-400 mt-1.5">{{ overview.overdue }} 项已逾期</p>
          </div>
        </div>
      </div>

      <!-- 任务列表 -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-gray-100">任务列表</h2>
          <UButton
            v-if="plan.status !== 'archived'"
            icon="i-heroicons-plus"
            size="sm"
            @click="openAddTask"
          >
            添加任务
          </UButton>
        </div>

        <div
          v-for="(item, index) in items"
          :key="item.id"
          class="group bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 transition-shadow hover:shadow-sm"
        >
          <!-- 头部 -->
          <div class="flex items-start justify-between gap-3 mb-3">
            <div class="flex items-center gap-2 min-w-0 flex-wrap">
              <span class="text-xs font-medium text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 rounded-md px-2 py-0.5 tabular-nums">#{{ index + 1 }}</span>
              <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="priorityDot(item.priority)" />
              <UBadge :color="itemStatusColor(item.status)" variant="subtle" size="xs">{{ itemStatusLabel(item.status) }}</UBadge>
              <span
                v-if="item.due_date"
                class="text-xs tabular-nums ml-1"
                :class="isOverdue(item) ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-400 dark:text-gray-500'"
              >截止 {{ item.due_date }}</span>
            </div>
            <div v-if="plan.status !== 'archived'" class="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
              <UButton size="xs" variant="ghost" color="neutral" icon="i-heroicons-pencil-square" @click="openEditTask(item)" />
              <UButton size="xs" variant="ghost" color="error" icon="i-heroicons-trash" :loading="removingId === item.id" @click="removeTask(item)" />
            </div>
          </div>

          <!-- 只读展示 -->
          <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ item.title || '（未命名任务）' }}</p>
          <p v-if="item.measurable_target" class="text-sm text-gray-600 dark:text-gray-400 mt-1.5">
            <span class="text-xs text-gray-400 dark:text-gray-500">目标：</span>{{ item.measurable_target }}
          </p>
          <p v-if="item.description" class="text-sm text-gray-600 dark:text-gray-400 mt-1.5 whitespace-pre-wrap">{{ item.description }}</p>

          <!-- 验收/评分（仅 submitted） -->
          <div v-if="item.status === 'submitted'" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-3">
            <div class="flex items-center gap-2 text-xs font-medium text-amber-600 dark:text-amber-400">
              <UIcon name="i-heroicons-clipboard-document-check" class="w-4 h-4" />
              验收与点评
            </div>
            <ReviewDimensionEditor v-model="item.review_dimensions" :pool="pool" />
            <p v-if="!(item.review_dimensions || []).length" class="text-xs text-amber-600 dark:text-amber-400">
              请先添加至少一个评分维度
            </p>
            <div class="space-y-1.5">
              <div v-for="d in (item.review_dimensions || [])" :key="d.key" class="flex items-center gap-2">
                <span class="text-sm text-gray-600 dark:text-gray-400 w-24 flex-shrink-0 truncate">{{ d.label }}</span>
                <UButton
                  v-for="star in 5"
                  :key="star"
                  size="xs"
                  variant="ghost"
                  :color="(scoreDraft[item.id]?.[d.key] || 0) >= star ? 'warning' : 'neutral'"
                  icon="i-heroicons-star-solid"
                  @click="setStar(item.id, d.key, star)"
                />
              </div>
            </div>
            <UTextarea v-model="commentDraft[item.id]" :rows="2" placeholder="总评（必填）" class="w-full" />
            <div class="flex items-center gap-2">
              <UButton size="sm" color="success" icon="i-heroicons-check-circle" :loading="verifyingIds.has(item.id)" @click="verifyItem(item.id, 'verified')">
                通过验收
              </UButton>
              <UButton size="sm" variant="outline" color="error" icon="i-heroicons-x-circle" :loading="verifyingIds.has(item.id)" @click="verifyItem(item.id, 'not_achieved')">
                未达成
              </UButton>
            </div>
          </div>

          <!-- 已记录点评 -->
          <div v-if="hasReview(item)" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
            <div class="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400 mb-2.5">
              <UIcon name="i-heroicons-star" class="w-3.5 h-3.5 text-amber-500" />
              点评
              <span v-if="item.reviewed_by_name" class="text-gray-400 dark:text-gray-500 font-normal">· {{ item.reviewed_by_name }}</span>
            </div>
            <div class="space-y-1.5">
              <div v-for="d in (item.review_dimensions || [])" :key="d.key" class="flex items-center justify-between gap-2 text-sm">
                <span class="text-gray-500 dark:text-gray-400">{{ d.label }}</span>
                <StarRow :value="item.scores?.[d.key] || 0" />
              </div>
            </div>
            <p v-if="item.review_comment" class="text-sm text-gray-700 dark:text-gray-300 mt-2.5 pt-2.5 border-t border-gray-50 dark:border-gray-800">
              <span class="text-xs text-gray-400 dark:text-gray-500">总评：</span>{{ item.review_comment }}
            </p>
          </div>

          <!-- 评论区 -->
          <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-3">
            <div v-if="(item.comments || []).length" class="space-y-2">
              <div
                v-for="comment in item.comments"
                :key="comment.id"
                class="flex items-start gap-2.5 bg-gray-50 dark:bg-gray-800 rounded-lg p-3"
              >
                <img
                  v-if="comment.author_avatar"
                  :src="resolveAvatarUrl(comment.author_avatar)"
                  class="w-6 h-6 rounded-full flex-shrink-0 mt-0.5"
                >
                <div
                  v-else
                  class="w-6 h-6 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-xs font-semibold text-gray-600 dark:text-gray-400 flex-shrink-0 mt-0.5"
                >
                  {{ (comment.author_name || '?').slice(0, 1) }}
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-1.5 mb-0.5">
                    <span class="text-xs font-medium text-gray-700 dark:text-gray-300">{{ comment.author_name }}</span>
                    <span class="text-xs text-gray-400 dark:text-gray-500">{{ comment.created_at?.slice(0, 10) }}</span>
                  </div>
                  <p class="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">{{ comment.content }}</p>
                  <a
                    v-if="comment.attachment_url"
                    :href="comment.attachment_url"
                    target="_blank"
                    class="text-xs text-crystal-500 dark:text-crystal-400 hover:underline mt-0.5 inline-block"
                  >附件</a>
                </div>
              </div>
            </div>
            <div class="flex items-start gap-2">
              <UTextarea
                v-model="newComments[item.id]"
                placeholder="添加反馈..."
                size="sm"
                variant="outline"
                :rows="1"
                autoresize
                class="flex-1"
              />
              <UButton
                size="sm"
                variant="soft"
                color="neutral"
                icon="i-heroicons-paper-airplane"
                :loading="commentingIds.has(item.id)"
                :disabled="!newComments[item.id]?.trim()"
                @click="addComment(item.id)"
              />
            </div>
          </div>
        </div>

        <!-- 无任务空态 -->
        <div v-if="!items.length" class="bg-white dark:bg-gray-900 rounded-xl border border-dashed border-gray-200 dark:border-gray-700 p-10 text-center">
          <UIcon name="i-heroicons-inbox" class="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
          <p class="text-sm text-gray-500 dark:text-gray-400">本月暂无任务</p>
        </div>
      </div>

      <!-- 编辑 / 添加 任务弹窗 -->
      <UModal :open="taskModalOpen" :dismissible="false" :ui="{ content: 'sm:max-w-lg' }" @update:open="onModalToggle">
        <template #content>
          <div class="p-5 space-y-4">
            <div class="flex items-center justify-between">
              <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">
                {{ editingId ? '编辑任务' : '添加任务' }}
              </h3>
              <UButton size="xs" variant="ghost" color="neutral" icon="i-heroicons-x-mark-20-solid" @click="attemptClose" />
            </div>

            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">标题</label>
              <UInput v-model="taskForm.title" size="sm" variant="outline" placeholder="任务标题" class="w-full" autofocus />
            </div>
            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">可量化目标</label>
              <UInput v-model="taskForm.measurable_target" size="sm" variant="outline" placeholder="例如：完成 5 个 PR" class="w-full" />
            </div>
            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">描述</label>
              <UTextarea v-model="taskForm.description" size="sm" variant="outline" placeholder="任务内容与背景" :rows="3" class="w-full" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1">
                <label class="text-xs font-medium text-gray-500 dark:text-gray-400">优先级</label>
                <USelect v-model="taskForm.priority" size="sm" variant="outline" :items="priorityOptions" class="w-full" />
              </div>
              <div class="space-y-1">
                <label class="text-xs font-medium text-gray-500 dark:text-gray-400">截止日期</label>
                <UInput v-model="taskForm.due_date" type="date" size="sm" variant="outline" class="w-full" />
              </div>
            </div>

            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">点评维度（验收打分用，默认取自维度库，可改）</label>
              <ReviewDimensionEditor v-model="taskForm.review_dimensions" :pool="pool" />
            </div>

            <div class="flex justify-end gap-2 pt-1">
              <UButton variant="ghost" color="neutral" :disabled="savingTask" @click="attemptClose">取消</UButton>
              <UButton color="primary" icon="i-heroicons-check" :loading="savingTask" :disabled="!taskForm.title.trim()" @click="saveTask">
                {{ editingId ? '保存' : '添加' }}
              </UButton>
            </div>
          </div>
        </template>
      </UModal>
    </template>

    <!-- 未找到 -->
    <div
      v-else-if="!loading"
      class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center"
    >
      <UIcon name="i-heroicons-document-text" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
      <p class="text-gray-500 dark:text-gray-400">未找到此计划</p>
      <NuxtLink to="/app/ai/plans">
        <UButton class="mt-4" size="sm" variant="outline" color="neutral">返回团队任务</UButton>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const route = useRoute()
const { api } = useApi()
const { resolveAvatarUrl } = useAvatars()
const toast = useToast()

const planId = route.params.id as string
const plan = ref<any>(null)
const loading = ref(true)
const publishing = ref(false)
const verifyingIds = ref(new Set<string>())
const commentingIds = ref(new Set<string>())
const removingId = ref<string | null>(null)

const pool = ref<any[]>([])
const scoreDraft = ref<Record<string, Record<string, number>>>({})
const commentDraft = ref<Record<string, string>>({})
const newComments = ref<Record<string, string>>({})

// 任务编辑/添加弹窗
const taskModalOpen = ref(false)
const savingTask = ref(false)
const editingId = ref<string | null>(null)
const taskForm = ref<any>(blankTask())
const formSnapshot = ref('')

const priorityOptions = [
  { label: '高', value: 'high' },
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' },
]
const items = computed<any[]>(() => plan.value?.action_items || [])

function blankTask() {
  return { title: '', measurable_target: '', description: '', priority: 'medium', due_date: '', review_dimensions: [] as any[] }
}

function cloneDims(dims: any[]) {
  return JSON.parse(JSON.stringify(dims || []))
}

function snapshot() {
  formSnapshot.value = JSON.stringify(taskForm.value)
}

function isDirty() {
  return JSON.stringify(taskForm.value) !== formSnapshot.value
}

async function fetchPlan() {
  loading.value = true
  try {
    plan.value = await api<any>(`/api/kpi/plans/${planId}/`)
    if (!pool.value.length) {
      try { pool.value = (await api<any>('/api/kpi/review-dimensions/')).review_dimensions || [] } catch { /* pool optional */ }
    }
  } catch {
    plan.value = null
  } finally {
    loading.value = false
  }
}

// 把现有任务映射为编辑接口所需的载荷（保留 id / 奖赏字段 / 维度）
function toPayload(item: any) {
  return {
    id: item.id,
    title: item.title || '',
    description: item.description || '',
    measurable_target: item.measurable_target || '',
    points: item.points,
    priority: item.priority || 'medium',
    dimension: item.dimension || 'general',
    due_date: item.due_date || null,
    review_dimensions: item.review_dimensions || [],
  }
}

function openAddTask() {
  editingId.value = null
  taskForm.value = blankTask()
  // 点评维度默认从维度库带出（与派发弹窗一致）
  taskForm.value.review_dimensions = cloneDims(pool.value)
  snapshot()
  taskModalOpen.value = true
}

function openEditTask(item: any) {
  editingId.value = item.id
  taskForm.value = {
    title: item.title || '',
    measurable_target: item.measurable_target || '',
    description: item.description || '',
    priority: item.priority || 'medium',
    due_date: item.due_date || '',
    review_dimensions: cloneDims(item.review_dimensions),
  }
  snapshot()
  taskModalOpen.value = true
}

function onModalToggle(val: boolean) {
  // 仅拦截"关闭"动作（点遮罩 / Esc / 关闭按钮均会触发 update:open=false）
  if (!val) attemptClose()
}

function attemptClose() {
  if (savingTask.value) return
  if (isDirty() && !window.confirm('当前任务有未保存的修改，确定放弃吗？')) return
  taskModalOpen.value = false
}

async function saveTask() {
  if (!taskForm.value.title.trim()) return
  savingTask.value = true
  const fields = {
    title: taskForm.value.title.trim(),
    measurable_target: taskForm.value.measurable_target || '',
    description: taskForm.value.description || '',
    priority: taskForm.value.priority || 'medium',
    due_date: taskForm.value.due_date || null,
    review_dimensions: Array.isArray(taskForm.value.review_dimensions) ? taskForm.value.review_dimensions : [],
  }
  const payload: any[] = items.value.map(toPayload)
  if (editingId.value) {
    const idx = payload.findIndex((i: any) => i.id === editingId.value)
    if (idx >= 0) payload[idx] = { ...payload[idx], ...fields }
  } else {
    payload.push({ ...fields, dimension: 'general' })
  }
  try {
    plan.value = await api(`/api/kpi/plans/${planId}/edit/`, {
      method: 'PUT',
      body: { action_items: payload },
    })
    taskModalOpen.value = false
    toast.add({ title: editingId.value ? '已保存' : '已添加', color: 'success' })
  } catch (e: any) {
    toast.add({ title: '保存失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    savingTask.value = false
  }
}

async function removeTask(item: any) {
  if (!window.confirm(`确定删除任务「${item.title || '未命名'}」吗？`)) return
  removingId.value = item.id
  const payload = items.value.map(toPayload).filter((i: any) => i.id !== item.id)
  try {
    plan.value = await api(`/api/kpi/plans/${planId}/edit/`, {
      method: 'PUT',
      body: { action_items: payload },
    })
    toast.add({ title: '已删除', color: 'success' })
  } catch (e: any) {
    toast.add({ title: '删除失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    removingId.value = null
  }
}

async function handlePublish() {
  publishing.value = true
  try {
    await api(`/api/kpi/plans/${planId}/publish/`, { method: 'POST' })
    toast.add({ title: '已发布', color: 'success' })
    await fetchPlan()
  } catch {
    toast.add({ title: '发布失败', color: 'error' })
  } finally {
    publishing.value = false
  }
}

function setStar(itemId: string, key: string, star: number) {
  if (!scoreDraft.value[itemId]) scoreDraft.value[itemId] = {}
  scoreDraft.value[itemId][key] = star
}

async function verifyItem(itemId: string, status: string) {
  const item = items.value.find((i: any) => i.id === itemId)
  if (status === 'verified' && !commentDraft.value[itemId]?.trim()) {
    toast.add({ title: '请填写总评', color: 'warning' })
    return
  }
  verifyingIds.value = new Set([...verifyingIds.value, itemId])
  const body: any = { status }
  if (status === 'verified') {
    body.scores = scoreDraft.value[itemId] || {}
    body.review_comment = commentDraft.value[itemId]?.trim()
    body.review_dimensions = item?.review_dimensions || []
  }
  try {
    await api(`/api/kpi/action-items/${itemId}/verify/`, { method: 'POST', body })
    toast.add({ title: status === 'verified' ? '已验收' : '已标记未达成', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '操作失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    verifyingIds.value = new Set([...verifyingIds.value].filter(id => id !== itemId))
  }
}

async function addComment(itemId: string) {
  const content = newComments.value[itemId]?.trim()
  if (!content) return
  commentingIds.value = new Set([...commentingIds.value, itemId])
  try {
    await api(`/api/kpi/action-items/${itemId}/comments/`, {
      method: 'POST',
      body: { content },
    })
    newComments.value[itemId] = ''
    toast.add({ title: '反馈已发送', color: 'success' })
    await fetchPlan()
  } catch {
    toast.add({ title: '发送失败', color: 'error' })
  } finally {
    commentingIds.value = new Set([...commentingIds.value].filter(id => id !== itemId))
  }
}

function statusLabel(status: string) {
  const map: Record<string, string> = { draft: '草案', published: '已发布', archived: '已归档' }
  return map[status] ?? status
}
function statusColor(status: string): any {
  if (status === 'published') return 'success'
  if (status === 'draft') return 'warning'
  return 'neutral'
}
function priorityDot(priority: string) {
  if (priority === 'high') return 'bg-red-500'
  if (priority === 'medium') return 'bg-amber-500'
  return 'bg-gray-300 dark:bg-gray-600'
}
function itemStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '待开始', in_progress: '进行中', submitted: '已提交',
    verified: '已验收', not_achieved: '未达成',
  }
  return map[status] ?? status
}
function itemStatusColor(status: string): any {
  if (status === 'verified') return 'success'
  if (status === 'not_achieved') return 'error'
  if (status === 'submitted') return 'warning'
  if (status === 'in_progress') return 'info'
  return 'neutral'
}
function isOverdue(item: any): boolean {
  if (!item.due_date || ['verified', 'not_achieved'].includes(item.status)) return false
  const t = new Date()
  const today = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`
  return item.due_date < today
}
function hasReview(item: any): boolean {
  return (item.scores && Object.keys(item.scores).length > 0) || !!item.review_comment
}

const overview = computed(() => {
  const list = items.value
  const total = list.length
  const done = list.filter((i: any) => i.status === 'verified').length
  return {
    total,
    inProgress: list.filter((i: any) => i.status === 'in_progress').length,
    submitted: list.filter((i: any) => i.status === 'submitted').length,
    done,
    overdue: list.filter((i: any) => isOverdue(i)).length,
    pct: total > 0 ? Math.round((done / total) * 100) : 0,
  }
})

onMounted(fetchPlan)
</script>
