<template>
  <div class="space-y-6">
    <!-- 返回 -->
    <NuxtLink to="/app/ai/plans" class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
      <UIcon name="i-heroicons-arrow-left" class="w-4 h-4" />
      返回团队计划
    </NuxtLink>

    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <template v-else-if="plan">
      <!-- 计划头部信息 -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-6">
        <div class="flex items-center gap-4 flex-wrap">
          <!-- 头像 -->
          <img
            v-if="plan.user_avatar"
            :src="resolveAvatarUrl(plan.user_avatar)"
            class="w-14 h-14 rounded-full flex-shrink-0"
          />
          <div
            v-else
            class="w-14 h-14 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center text-lg font-semibold text-crystal-600 dark:text-crystal-400 flex-shrink-0"
          >
            {{ (plan.user_name || '?').slice(0, 1) }}
          </div>

          <!-- 用户信息 -->
          <div class="flex-1 min-w-0">
            <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
              {{ plan.user_name || '未知用户' }}
            </h1>
            <div class="flex items-center gap-2 mt-1.5 flex-wrap">
              <span class="text-sm text-gray-500 dark:text-gray-400">{{ plan.period }}</span>
              <UBadge :color="statusColor(plan.status)" variant="subtle" size="xs">
                {{ statusLabel(plan.status) }}
              </UBadge>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex items-center gap-2">
            <UButton
              size="sm"
              variant="outline"
              color="neutral"
              icon="i-heroicons-check"
              :loading="saving"
              :disabled="plan.status === 'archived'"
              @click="savePlan"
            >
              保存
            </UButton>
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
      </div>

      <!-- 行动项列表 -->
      <div class="space-y-3">
        <div
          v-for="(item, index) in editItems"
          :key="item.id || `new-${index}`"
          class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5"
        >
          <!-- 行动项头部 -->
          <div class="flex items-start justify-between gap-3 mb-4">
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 rounded-md px-2 py-0.5">
                #{{ index + 1 }}
              </span>
              <UBadge :color="priorityColor(item.priority)" variant="subtle" size="xs">
                {{ priorityLabel(item.priority) }}
              </UBadge>
              <UBadge
                v-if="item.status && item.status !== 'pending'"
                :color="itemStatusColor(item.status)"
                variant="subtle"
                size="xs"
              >
                {{ itemStatusLabel(item.status) }}
              </UBadge>
            </div>
            <UButton
              v-if="plan.status !== 'archived'"
              size="xs"
              variant="ghost"
              color="error"
              icon="i-heroicons-trash"
              @click="removeItem(index)"
            />
          </div>

          <!-- 可编辑字段 -->
          <div class="space-y-3">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <!-- 标题 -->
              <div class="space-y-1">
                <label class="text-xs font-medium text-gray-500 dark:text-gray-400">标题</label>
                <UInput v-model="item.title" size="sm" variant="outline" placeholder="行动项标题" :disabled="plan.status === 'archived'" />
              </div>
              <!-- 可量化目标 -->
              <div class="space-y-1">
                <label class="text-xs font-medium text-gray-500 dark:text-gray-400">可量化目标</label>
                <UInput v-model="item.measurable_target" size="sm" variant="outline" placeholder="例如：完成 5 个 PR" :disabled="plan.status === 'archived'" />
              </div>
            </div>

            <!-- 描述 -->
            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">描述</label>
              <UTextarea v-model="item.description" size="sm" variant="outline" placeholder="描述此行动项的内容和背景" :rows="2" :disabled="plan.status === 'archived'" />
            </div>

            <!-- 优先级、维度 -->
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1">
                <label class="text-xs font-medium text-gray-500 dark:text-gray-400">优先级</label>
                <USelect v-model="item.priority" size="sm" variant="outline" :items="priorityOptions" :disabled="plan.status === 'archived'" />
              </div>
              <div class="space-y-1">
                <label class="text-xs font-medium text-gray-500 dark:text-gray-400">维度</label>
                <USelect v-model="item.dimension" size="sm" variant="outline" :items="dimensionOptions" :disabled="plan.status === 'archived'" />
              </div>
            </div>
          </div>

          <!-- 验收/评分（仅 submitted 状态） -->
          <div v-if="item.status === 'submitted'" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-3">
            <p class="text-xs font-medium text-gray-500 dark:text-gray-400">点评维度（可改）</p>
            <ReviewDimensionEditor v-model="item.review_dimensions" :pool="pool" />
            <p v-if="!(item.review_dimensions || []).length" class="text-xs text-amber-600 dark:text-amber-400">
              请先添加至少一个评分维度
            </p>
            <div v-for="d in (item.review_dimensions || [])" :key="d.key" class="flex items-center gap-2">
              <span class="text-sm text-gray-600 dark:text-gray-400 w-24">{{ d.label }}</span>
              <UButton
                v-for="star in 5" :key="star"
                size="xs" variant="ghost" :color="(scoreDraft[item.id]?.[d.key] || 0) >= star ? 'warning' : 'neutral'"
                icon="i-heroicons-star-solid"
                @click="setStar(item.id, d.key, star)"
              />
            </div>
            <UTextarea v-model="commentDraft[item.id]" :rows="2" placeholder="总评（必填）" class="w-full" />
            <div class="flex items-center gap-2">
              <UButton size="xs" color="success" icon="i-heroicons-check-circle"
                :loading="verifyingIds.has(item.id)" @click="verifyItem(item.id, 'verified')">
                通过评分
              </UButton>
              <UButton size="xs" variant="outline" color="error" icon="i-heroicons-x-circle"
                :loading="verifyingIds.has(item.id)" @click="verifyItem(item.id, 'not_achieved')">
                未达成
              </UButton>
            </div>
          </div>

          <!-- 评论区 -->
          <div v-if="item.id" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-3">
            <!-- 现有评论 -->
            <div v-if="(item.comments || []).length" class="space-y-2">
              <div
                v-for="comment in item.comments"
                :key="comment.id"
                class="flex items-start gap-2.5 bg-gray-50 dark:bg-gray-800 rounded-lg p-3"
              >
                <img
                  v-if="comment.author?.avatar"
                  :src="resolveAvatarUrl(comment.author.avatar)"
                  class="w-6 h-6 rounded-full flex-shrink-0 mt-0.5"
                />
                <div
                  v-else
                  class="w-6 h-6 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-xs font-semibold text-gray-600 dark:text-gray-400 flex-shrink-0 mt-0.5"
                >
                  {{ (comment.author?.name || comment.author?.username || '?').slice(0, 1) }}
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-1.5 mb-0.5">
                    <span class="text-xs font-medium text-gray-700 dark:text-gray-300">
                      {{ comment.author?.name || comment.author?.username }}
                    </span>
                    <span class="text-xs text-gray-400 dark:text-gray-500">
                      {{ comment.created_at?.slice(0, 10) }}
                    </span>
                  </div>
                  <p class="text-sm text-gray-600 dark:text-gray-400">{{ comment.content }}</p>
                  <a
                    v-if="comment.attachment"
                    :href="comment.attachment"
                    target="_blank"
                    class="text-xs text-crystal-500 dark:text-crystal-400 hover:underline mt-0.5 inline-block"
                  >
                    附件
                  </a>
                </div>
              </div>
            </div>

            <!-- 添加评论 -->
            <div class="flex items-start gap-2">
              <UTextarea
                v-model="newComments[item.id]"
                placeholder="添加评论..."
                size="sm"
                variant="outline"
                :rows="2"
                class="flex-1"
              />
              <UButton
                size="sm"
                variant="outline"
                color="neutral"
                :loading="commentingIds.has(item.id)"
                :disabled="!newComments[item.id]?.trim()"
                @click="addComment(item.id)"
              >
                发送
              </UButton>
            </div>
          </div>
        </div>

        <!-- 添加行动项按钮 -->
        <UButton
          v-if="plan.status !== 'archived'"
          variant="outline"
          color="neutral"
          icon="i-heroicons-plus"
          block
          @click="addItem"
        >
          添加行动项
        </UButton>
      </div>
    </template>

    <!-- 无数据 -->
    <div
      v-else-if="!loading"
      class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center"
    >
      <UIcon name="i-heroicons-document-text" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
      <p class="text-gray-500 dark:text-gray-400">未找到此计划</p>
      <NuxtLink to="/app/ai/plans">
        <UButton class="mt-4" size="sm" variant="outline" color="neutral">返回团队计划</UButton>
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
const saving = ref(false)
const publishing = ref(false)
const verifyingIds = ref(new Set<string>())
const commentingIds = ref(new Set<string>())

// 可编辑的行动项副本
const editItems = ref<any[]>([])

// 评分草稿（按 item.id → dim key → 1..5）
const pool = ref<any[]>([])
const scoreDraft = ref<Record<string, Record<string, number>>>({})
const commentDraft = ref<Record<string, string>>({})

// 新评论输入（按 item.id）
const newComments = ref<Record<string, string>>({})

const priorityOptions = [
  { label: '高', value: 'high' },
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' },
]

const dimensionOptions = [
  { label: '通用', value: 'general' },
  { label: '技术', value: 'technical' },
  { label: '协作', value: 'collaboration' },
  { label: '成长', value: 'growth' },
  { label: '质量', value: 'quality' },
]

function statusLabel(status: string) {
  const map: Record<string, string> = {
    draft: '草案',
    published: '已发布',
    archived: '已归档',
  }
  return map[status] ?? status
}

function statusColor(status: string): any {
  if (status === 'published') return 'success'
  if (status === 'archived') return 'neutral'
  return 'neutral'
}

function priorityLabel(priority: string) {
  const map: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return map[priority] ?? priority
}

function priorityColor(priority: string): any {
  if (priority === 'high') return 'error'
  if (priority === 'medium') return 'warning'
  return 'neutral'
}

function itemStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '待处理',
    submitted: '已提交',
    verified: '已验收',
    not_achieved: '未达成',
  }
  return map[status] ?? status
}

function itemStatusColor(status: string): any {
  if (status === 'verified') return 'success'
  if (status === 'not_achieved') return 'error'
  if (status === 'submitted') return 'warning'
  return 'neutral'
}

async function fetchPlan() {
  loading.value = true
  try {
    plan.value = await api<any>(`/api/kpi/plans/${planId}/`)
    editItems.value = (plan.value.action_items || []).map((item: any) => ({
      ...item,
      review_dimensions: Array.isArray(item.review_dimensions)
        ? item.review_dimensions.map((d: any) => ({ ...d }))
        : [],
    }))
    if (!pool.value.length) {
      try { pool.value = (await api<any>('/api/kpi/review-dimensions/')).review_dimensions || [] } catch { /* ignore: pool optional */ }
    }
  } catch {
    // 保持 plan 为 null，显示空状态
  } finally {
    loading.value = false
  }
}

function addItem() {
  editItems.value.push({
    title: '',
    description: '',
    measurable_target: '',
    points: 20,
    priority: 'medium',
    dimension: 'general',
  })
}

function removeItem(index: number) {
  editItems.value.splice(index, 1)
}

async function savePlan() {
  saving.value = true
  try {
    plan.value = await api(`/api/kpi/plans/${planId}/edit/`, {
      method: 'PUT',
      body: { action_items: editItems.value },
    })
    editItems.value = (plan.value.action_items || []).map((item: any) => ({ ...item }))
    toast.add({ title: '已保存', color: 'success' })
  } catch {
    toast.add({ title: '保存失败', color: 'error' })
  } finally {
    saving.value = false
  }
}

async function handlePublish() {
  publishing.value = true
  try {
    // 先保存，再发布
    plan.value = await api(`/api/kpi/plans/${planId}/edit/`, {
      method: 'PUT',
      body: { action_items: editItems.value },
    })
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
  const item = editItems.value.find((i: any) => i.id === itemId)
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
    toast.add({ title: status === 'verified' ? '已评分' : '已标记未达成', color: 'success' })
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
    toast.add({ title: '评论已发送', color: 'success' })
    await fetchPlan()
  } catch {
    toast.add({ title: '评论发送失败', color: 'error' })
  } finally {
    commentingIds.value = new Set([...commentingIds.value].filter(id => id !== itemId))
  }
}

onMounted(fetchPlan)
</script>
