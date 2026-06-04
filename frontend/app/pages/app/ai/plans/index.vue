<template>
  <div class="space-y-6">
    <!-- 头部 -->
    <div class="flex items-end justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">团队任务</h1>
        <p class="text-sm text-gray-400 dark:text-gray-500 mt-0.5">派发任务、跟踪进度、按维度点评</p>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <UButtonGroup>
          <UButton size="sm" variant="outline" color="neutral" icon="i-heroicons-chevron-left" @click="prevMonth" />
          <UButton size="sm" variant="outline" color="neutral" class="min-w-24 justify-center pointer-events-none tabular-nums">
            {{ period }}
          </UButton>
          <UButton size="sm" variant="outline" color="neutral" icon="i-heroicons-chevron-right" @click="nextMonth" />
        </UButtonGroup>
        <UButton size="sm" icon="i-heroicons-paper-airplane" @click="openDispatch">
          派发任务
        </UButton>
      </div>
    </div>

    <!-- 团队概览 -->
    <div v-if="!loading && plans.length" class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4">
        <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">有计划成员</p>
        <p class="text-2xl font-bold tabular-nums text-gray-900 dark:text-gray-100">{{ plans.length }}</p>
      </div>
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4">
        <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">任务总数</p>
        <p class="text-2xl font-bold tabular-nums text-gray-900 dark:text-gray-100">{{ totals.items }}</p>
      </div>
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4">
        <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">待验收</p>
        <p class="text-2xl font-bold tabular-nums text-amber-600 dark:text-amber-400">{{ totals.reviewing }}</p>
      </div>
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4">
        <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">已完成</p>
        <p class="text-2xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400">{{ totals.done }}</p>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <!-- 空态 -->
    <div v-else-if="!plans.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center">
      <UIcon name="i-heroicons-users" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
      <p class="text-gray-500 dark:text-gray-400">{{ period }} 暂无任何计划</p>
      <UButton class="mt-4" size="sm" icon="i-heroicons-paper-airplane" @click="openDispatch">派发任务</UButton>
    </div>

    <!-- 成员列表 -->
    <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden divide-y divide-gray-50 dark:divide-gray-800/60">
      <div
        v-for="row in tableRows"
        :key="row.plan_id"
        class="group flex items-center gap-4 px-5 py-3.5 hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors cursor-pointer"
        @click="goDetail(row.plan_id)"
      >
        <!-- 头像 -->
        <img
          v-if="row.avatar"
          :src="resolveAvatarUrl(row.avatar)"
          class="w-9 h-9 rounded-full flex-shrink-0"
        >
        <div
          v-else
          class="w-9 h-9 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center text-sm font-semibold text-crystal-600 dark:text-crystal-400 flex-shrink-0"
        >
          {{ (row.user_name || '?').slice(0, 1) }}
        </div>

        <!-- 姓名 + 状态 + 迷你进度 -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ row.user_name }}</span>
            <UBadge :color="statusColor(row.status)" variant="subtle" size="xs">{{ statusLabel(row.status) }}</UBadge>
          </div>
          <div class="flex items-center gap-2 mt-1.5">
            <div class="h-1.5 w-28 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
              <div
                class="h-full rounded-full bg-gradient-to-r from-crystal-500 to-emerald-500 transition-[width] duration-500"
                :style="{ width: pct(row) + '%' }"
              />
            </div>
            <span class="text-xs text-gray-400 dark:text-gray-500 tabular-nums">{{ row.done }}/{{ row.items_count }}</span>
          </div>
        </div>

        <!-- 计数 -->
        <div class="hidden sm:flex items-center gap-5 text-xs flex-shrink-0">
          <div class="text-center">
            <p class="font-semibold tabular-nums text-amber-600 dark:text-amber-400">{{ row.reviewing }}</p>
            <p class="text-gray-400 dark:text-gray-500">待验收</p>
          </div>
          <div class="text-center">
            <p class="font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">{{ row.done }}</p>
            <p class="text-gray-400 dark:text-gray-500">已完成</p>
          </div>
        </div>

        <!-- 操作 -->
        <div class="flex items-center gap-1.5 flex-shrink-0" @click.stop>
          <UButton
            v-if="row.status === 'draft'"
            size="xs"
            variant="outline"
            color="success"
            icon="i-heroicons-paper-airplane"
            :loading="publishingIds.has(row.plan_id)"
            @click="publishPlan(row.plan_id)"
          >
            发布
          </UButton>
          <UButton
            v-else-if="row.status === 'published'"
            size="xs"
            variant="ghost"
            color="neutral"
            icon="i-heroicons-archive-box"
            :loading="archivingIds.has(row.plan_id)"
            @click="archivePlan(row.plan_id)"
          />
          <UIcon name="i-heroicons-chevron-right" class="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-gray-400 dark:group-hover:text-gray-500 transition-colors" />
        </div>
      </div>
    </div>

    <!-- 派发任务弹窗 -->
    <UModal v-model:open="dispatchOpen">
      <template #content>
        <div class="p-5 space-y-3">
          <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">派发任务</h3>
          <div class="space-y-1">
            <label class="text-xs font-medium text-gray-500 dark:text-gray-400">成员</label>
            <USelectMenu v-model="form.user_id" :items="memberOptions" value-key="value" label-key="label" placeholder="选择成员" class="w-full" />
          </div>
          <div class="space-y-1">
            <label class="text-xs font-medium text-gray-500 dark:text-gray-400">任务标题</label>
            <UInput v-model="form.title" placeholder="任务标题" class="w-full" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">截止日期</label>
              <UInput v-model="form.due_date" type="date" class="w-full" />
            </div>
            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">优先级</label>
              <USelect v-model="form.priority" :items="priorityOptions" class="w-full" />
            </div>
          </div>
          <div class="space-y-1">
            <label class="text-xs font-medium text-gray-500 dark:text-gray-400">描述 / 可量化目标（可选）</label>
            <UTextarea v-model="form.description" :rows="2" placeholder="描述任务内容与期望成果" class="w-full" />
          </div>
          <div class="space-y-1">
            <label class="text-xs font-medium text-gray-500 dark:text-gray-400">点评维度（默认取自维度库，可改）</label>
            <ReviewDimensionEditor v-model="form.review_dimensions" :pool="pool" />
          </div>
          <div class="flex justify-end gap-2 pt-1">
            <UButton variant="ghost" color="neutral" @click="dispatchOpen = false">取消</UButton>
            <UButton :loading="dispatching" :disabled="!form.user_id || !form.title || !form.due_date" @click="submitDispatch">派发</UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const { resolveAvatarUrl } = useAvatars()
const toast = useToast()
const router = useRouter()

const period = ref(new Date().toISOString().slice(0, 7))
const plans = ref<any[]>([])
const loading = ref(true)
const publishingIds = ref(new Set<string>())
const archivingIds = ref(new Set<string>())

const priorityOptions = [
  { label: '高', value: 'high' },
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' },
]
const dispatchOpen = ref(false)
const dispatching = ref(false)
const pool = ref<any[]>([])
const memberOptions = ref<{ label: string, value: number }[]>([])
const form = ref<any>({ user_id: null, title: '', due_date: '', priority: 'medium', description: '', review_dimensions: [] })

interface PlanRow {
  user_id: number
  user_name: string
  avatar: string
  plan_id: string
  status: string
  items_count: number
  reviewing: number
  done: number
}

const tableRows = computed<PlanRow[]>(() =>
  plans.value.map((p: any) => ({
    user_id: p.user?.id ?? p.user_id ?? p.user,
    user_name: p.user_name || p.user?.name || p.user?.username || '',
    avatar: p.user_avatar || p.user?.avatar || p.avatar || '',
    plan_id: p.id,
    status: p.status ?? 'draft',
    items_count: p.item_count ?? 0,
    reviewing: p.reviewing_count ?? 0,
    done: p.done_count ?? 0,
  })),
)

const totals = computed(() => ({
  items: tableRows.value.reduce((s, r) => s + r.items_count, 0),
  reviewing: tableRows.value.reduce((s, r) => s + r.reviewing, 0),
  done: tableRows.value.reduce((s, r) => s + r.done, 0),
}))

function pct(row: PlanRow) {
  return row.items_count > 0 ? Math.round((row.done / row.items_count) * 100) : 0
}

function goDetail(planId: string) {
  if (planId) router.push(`/app/ai/plans/${planId}`)
}

function statusLabel(status: string | null) {
  const map: Record<string, string> = { draft: '草案', published: '已发布', archived: '已归档' }
  return status ? (map[status] ?? status) : '-'
}

function statusColor(status: string | null): any {
  if (status === 'published') return 'success'
  if (status === 'draft') return 'warning'
  return 'neutral'
}

function prevMonth() {
  const [y, m] = period.value.split('-').map(Number)
  const d = new Date(y!, (m! - 2), 1)
  period.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function nextMonth() {
  const [y, m] = period.value.split('-').map(Number)
  const d = new Date(y!, m!, 1)
  period.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

async function fetchPlans() {
  loading.value = true
  try {
    plans.value = await api<any[]>(`/api/kpi/plans/?period=${period.value}`)
  } catch {
    plans.value = []
  } finally {
    loading.value = false
  }
}

async function publishPlan(planId: string) {
  publishingIds.value = new Set([...publishingIds.value, planId])
  try {
    await api(`/api/kpi/plans/${planId}/publish/`, { method: 'POST' })
    toast.add({ title: '已发布', color: 'success' })
    await fetchPlans()
  } catch (e: any) {
    toast.add({ title: '发布失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    publishingIds.value = new Set([...publishingIds.value].filter(id => id !== planId))
  }
}

async function archivePlan(planId: string) {
  archivingIds.value = new Set([...archivingIds.value, planId])
  try {
    await api(`/api/kpi/plans/${planId}/archive/`, { method: 'POST' })
    toast.add({ title: '已归档', color: 'success' })
    await fetchPlans()
  } catch (e: any) {
    toast.add({ title: '归档失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    archivingIds.value = new Set([...archivingIds.value].filter(id => id !== planId))
  }
}

async function openDispatch() {
  form.value = { user_id: null, title: '', due_date: '', priority: 'medium', description: '', review_dimensions: [] }
  try {
    const cfg = await api<any>('/api/kpi/review-dimensions/')
    pool.value = cfg.review_dimensions || []
    form.value.review_dimensions = JSON.parse(JSON.stringify(pool.value))
  } catch { pool.value = [] }
  if (!memberOptions.value.length) {
    try {
      // 用轻量 choices 接口（无分页，已排除机器人）——避免 /users/ 默认分页只回前 20 人
      const users = await api<any[]>('/api/users/choices/')
      memberOptions.value = (users || []).map((u: any) => ({ label: u.name, value: u.id }))
    } catch {
      toast.add({ title: '加载成员失败', color: 'error' })
    }
  }
  dispatchOpen.value = true
}

async function submitDispatch() {
  dispatching.value = true
  try {
    await api('/api/kpi/tasks/dispatch/', {
      method: 'POST',
      body: {
        user_id: form.value.user_id,
        title: form.value.title.trim(),
        due_date: form.value.due_date,
        priority: form.value.priority,
        description: form.value.description,
        review_dimensions: form.value.review_dimensions,
      },
    })
    dispatchOpen.value = false
    toast.add({ title: '已派发', color: 'success' })
    await fetchPlans()
  } catch (e: any) {
    toast.add({ title: '派发失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    dispatching.value = false
  }
}

watch(period, fetchPlans)
onMounted(fetchPlans)
</script>
