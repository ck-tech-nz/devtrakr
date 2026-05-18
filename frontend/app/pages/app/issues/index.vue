<template>
  <div class="space-y-6">
    <MyPendingTasks />
    <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <h1 class="text-xl md:text-2xl font-semibold text-gray-900 dark:text-gray-100">问题跟踪</h1>
      <div class="flex items-center justify-between md:justify-end space-x-3">
        <label class="flex items-center gap-1.5 cursor-pointer select-none">
          <span class="text-sm text-gray-500 dark:text-gray-400">查看全部</span>
          <USwitch v-model="showCompleted" size="lg" />
        </label>
        <UInput v-model="searchQuery" placeholder="搜索标题或编号" icon="i-heroicons-magnifying-glass" size="sm" class="w-44" />
        <div class="relative">
          <USelect v-model="filterAssignee" :items="filterAssigneeOptions" size="sm" class="w-28" value-key="value" placeholder="负责人" />
          <button v-if="filterAssignee" class="filter-clear" @click="filterAssignee = ''">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </div>
        <div class="relative">
          <USelect v-model="filterPriority" :items="filterPriorityOptions" size="sm" class="w-28" value-key="value" placeholder="优先级" />
          <button v-if="filterPriority" class="filter-clear" @click="filterPriority = ''">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </div>
        <div class="relative">
          <USelect v-model="filterStatus" :items="filterStatusOptions" size="sm" class="w-28" value-key="value" placeholder="状态" />
          <button v-if="filterStatus" class="filter-clear" @click="filterStatus = ''">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </div>
        <div class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
          <button
            class="px-3 py-1 text-sm font-medium rounded-md transition-colors"
            :class="viewMode === 'kanban' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
            @click="viewMode = 'kanban'"
          >
            看板
          </button>
          <button
            class="px-3 py-1 text-sm font-medium rounded-md transition-colors"
            :class="viewMode === 'table' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
            @click="viewMode = 'table'"
          >
            列表
          </button>
        </div>
        <UButton icon="i-heroicons-plus" size="sm" @click="openCreateModal">
          <span class="hidden md:inline">新建问题</span>
        </UButton>
      </div>
    </div>

    <!-- Create Issue Modal -->
    <UModal :open="showCreateModal" title="新建问题" :ui="{ content: 'sm:max-w-[960px]' }" @update:open="onCreateModalUpdate">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>新建问题</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="closeCreateModal" />
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label>项目</label>
              <USelect v-model="newIssue.project" :items="projectOptions" placeholder="选择项目" value-key="value" />
            </div>
            <div v-if="projectRepos.length > 1" class="form-row">
              <label>关联仓库</label>
              <USelect v-model="newIssue.repo" :items="projectRepoOptions" placeholder="选择仓库" value-key="value" />
            </div>
            <div class="form-row">
              <label>标题 <span class="text-red-400">*</span></label>
              <UInput v-model="newIssue.title" placeholder="输入问题标题" @blur="runDuplicateCheck" />
              <div v-if="dupChecking || dupCandidates.length" class="dup-check-box">
                <p v-if="dupChecking" class="text-xs text-gray-500 dark:text-gray-400">
                  正在检查相似问题…
                </p>
                <div v-else>
                  <p class="text-sm text-amber-700 dark:text-amber-300 font-medium">
                    发现 {{ dupCandidates.length }} 条相似的未关闭问题，请确认是否重复：
                  </p>
                  <ul class="mt-1.5 space-y-1.5">
                    <li v-for="c in dupCandidates" :key="c.id" class="text-sm">
                      <div class="flex items-center gap-1.5">
                        <NuxtLink
                          :to="`/app/issues/${c.id}`"
                          target="_blank"
                          class="text-crystal-600 dark:text-crystal-400 hover:underline"
                        >
                          #{{ c.id }} {{ c.title }}
                        </NuxtLink>
                        <UBadge :color="statusColor(c.status)" variant="subtle" size="xs">{{ c.status }}</UBadge>
                      </div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ c.reason }}</p>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
            <div class="form-row">
              <label>描述</label>
              <MarkdownEditor
                v-model="newIssue.description"
                placeholder="详细描述问题"
                @upload-complete="handleCreateUploadComplete"
                @blur="runDuplicateCheck"
              />
            </div>
            <div class="form-grid-2">
              <div class="form-row">
                <label>优先级</label>
                <USelect v-model="newIssue.priority" :items="createPriorityOptions" value-key="value" />
              </div>
              <div class="form-row">
                <label>状态</label>
                <USelect v-model="newIssue.status" :items="createStatusOptions" value-key="value" />
              </div>
            </div>
            <div class="form-grid-2">
              <div class="form-row">
                <label>标签</label>
                <USelectMenu v-model="newIssue.labels" :items="labelOptions" multiple placeholder="选择标签" />
              </div>
              <div class="form-row">
                <label>负责人</label>
                <USelect v-model="newIssue.assignee" :items="createAssigneeOptions" placeholder="选择负责人" value-key="value" />
              </div>
            </div>
            <div class="form-row">
              <label>提出人</label>
              <UInput v-model="newIssue.reporter" placeholder="提出人姓名" />
            </div>
            <p v-if="createError" class="text-sm text-red-500">{{ createError }}</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="closeCreateModal">取消</UButton>
            <UButton :loading="creating" @click="handleCreateIssue">创建</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <!-- Batch Actions -->
    <div v-if="selectedRowsData.length > 0" class="hidden md:flex bg-crystal-50 dark:bg-crystal-950 rounded-xl border border-crystal-100 dark:border-crystal-800 p-3 items-center justify-between">
      <span class="text-sm text-crystal-700 dark:text-crystal-300">已选择 {{ selectedRowsData.length }} 项</span>
      <div class="flex items-center space-x-2">
        <UDropdownMenu :items="batchAssignItems" :content="{ align: 'end' as const }">
          <UButton size="xs" color="primary" variant="outline">批量分配</UButton>
        </UDropdownMenu>
        <UDropdownMenu :items="batchPriorityItems" :content="{ align: 'end' as const }">
          <UButton size="xs" color="primary" variant="outline">修改优先级</UButton>
        </UDropdownMenu>
        <UDropdownMenu :items="batchStatusItems" :content="{ align: 'end' as const }">
          <UButton size="xs" color="primary" variant="outline">修改状态</UButton>
        </UDropdownMenu>
        <UButton v-if="can('issues.delete_issue')" size="xs" color="error" variant="outline" @click="showBatchDeleteConfirm = true">批量删除</UButton>
      </div>
    </div>

    <!-- 批量删除确认弹窗 -->
    <UModal v-model:open="showBatchDeleteConfirm">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>批量删除</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showBatchDeleteConfirm = false" />
          </div>
          <div class="modal-body">
            <p class="text-sm text-gray-700 dark:text-gray-300">
              确认删除选中的 <span class="font-medium">{{ selectedRowsData.length }}</span> 个问题？
            </p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="showBatchDeleteConfirm = false">取消</UButton>
            <UButton color="error" :loading="batchDeleting" @click="handleBatchDelete">确认删除</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <!-- Loading State -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <!-- Mobile Card List -->
    <div v-else-if="isMobile && viewMode === 'table'" class="space-y-2">
      <IssueCard v-for="issue in issues" :key="issue.id" :issue="issue" @changed="fetchIssues" @request-transfer="openTransfer($event)" />
      <div class="flex items-center justify-between pt-2">
        <span class="text-xs text-gray-400 dark:text-gray-500">共 {{ totalCount }} 条</span>
        <div class="flex items-center space-x-2">
          <UButton size="xs" variant="ghost" color="neutral" :disabled="page <= 1" @click="page--">上一页</UButton>
          <span class="text-xs text-gray-500 dark:text-gray-400">{{ page }} / {{ totalPages }}</span>
          <UButton size="xs" variant="ghost" color="neutral" :disabled="page >= totalPages" @click="page++">下一页</UButton>
        </div>
      </div>
    </div>

    <!-- Kanban View -->
    <SharedKanbanBoard
      v-else-if="viewMode === 'kanban'"
      :columns="kanbanColumns"
      :item-key="(item: any) => item.id"
      @drop="onKanbanDrop"
    >
      <template #card="{ item }">
        <NuxtLink :to="`/app/issues/${item.id}`" class="block">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-xs text-gray-400 dark:text-gray-500">#{{ item.id }}</span>
            <div class="flex items-center gap-1">
              <UBadge v-if="item.source" color="info" variant="subtle" size="xs">外部</UBadge>
              <UBadge :color="priorityColor(item.priority)" variant="subtle" size="xs">
                {{ priorityLabel(item.priority) }}
              </UBadge>
            </div>
          </div>
          <p class="text-sm text-gray-900 dark:text-gray-100 font-medium line-clamp-2">{{ item.title }}</p>
          <div class="mt-2 flex items-center">
            <div class="w-5 h-5 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center">
              <span class="text-crystal-600 dark:text-crystal-400 text-[10px] font-medium">{{ (item.assignee_name || '?').slice(0, 1) }}</span>
            </div>
            <span class="ml-1.5 text-xs text-gray-400 dark:text-gray-500">{{ item.assignee_name || '-' }}</span>
          </div>
        </NuxtLink>
      </template>
    </SharedKanbanBoard>

    <!-- Table View -->
    <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200/80 dark:border-gray-700 shadow-sm overflow-hidden">
      <div class="flex justify-end px-4 py-2 border-b border-gray-50 dark:border-gray-800">
        <label class="flex items-center gap-1.5 cursor-pointer select-none">
          <USwitch v-model="showGHColumn" size="xs" />
          <span class="text-xs text-gray-500 dark:text-gray-400">GitHub Issues</span>
        </label>
      </div>
      <UTable
        v-model:row-selection="rowSelection"
        :data="issues"
        :columns="columns"
        class="issues-table"
        :ui="{ th: 'text-xs whitespace-nowrap', td: 'text-sm', tr: 'hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-pointer' }"
        @select="onRowSelect"
      >
        <template #select-header="{ table }">
          <UCheckbox
            :model-value="table.getIsAllPageRowsSelected()"
            @update:model-value="(v: boolean) => table.toggleAllPageRowsSelected(!!v)"
          />
        </template>
        <template #select-cell="{ row }">
          <UCheckbox
            :model-value="row.getIsSelected()"
            @update:model-value="(v: boolean) => row.toggleSelected(!!v)"
          />
        </template>
        <template #id-cell="{ row }">
          <NuxtLink :to="`/app/issues/${row.original.id}`" class="text-crystal-500 dark:text-crystal-400 hover:text-crystal-700 dark:hover:text-crystal-300 font-medium">{{ row.original.id }}</NuxtLink>
        </template>
        <template #title-cell="{ row }">
          <div class="flex items-center gap-1.5 min-w-0">
            <UBadge v-if="row.original.source" color="info" variant="subtle" size="xs" class="shrink-0">外部</UBadge>
            <EditableCell class="min-w-0" :value="row.original.title" @dblclick="cancelRowClick" @save="(v: string) => inlineUpdate(row.original.id, 'title', v)" />
          </div>
        </template>
        <template #priority-cell="{ row }">
          <UBadge :color="priorityColor(row.original.priority)" variant="subtle" size="sm">{{ priorityLabel(row.original.priority) }}</UBadge>
        </template>
        <template #status-cell="{ row }">
          <StatusCell
            :issue="row.original"
            :self-user-id="selfUserId"
            @changed="fetchIssues"
            @request-transfer="openTransfer(row.original)"
            @request-assign="openAssign(row.original)"
          />
        </template>
        <template #reporter-cell="{ row }">
          <span class="block truncate" :title="row.original.reporter || row.original.created_by_name">{{ row.original.reporter || row.original.created_by_name || '-' }}</span>
        </template>
        <template #remark-cell="{ row }">
          <EditableCell :value="row.original.remark" @dblclick="cancelRowClick" @save="(v: string) => inlineUpdate(row.original.id, 'remark', v)" />
        </template>
        <template #cause-cell="{ row }">
          <EditableCell :value="row.original.cause" :placeholder="row.original.ai_cause" @dblclick="cancelRowClick" @save="(v: string) => inlineUpdate(row.original.id, 'cause', v)" />
        </template>
        <template #solution-cell="{ row }">
          <EditableCell :value="row.original.solution" :placeholder="row.original.ai_solution" @dblclick="cancelRowClick" @save="(v: string) => inlineUpdate(row.original.id, 'solution', v)" />
        </template>
        <template #created_at-cell="{ row }">
          <div class="duration-cell">
            <div class="duration-bar">
              <div
                class="duration-fill"
                :class="{ 'duration-overdue': issueDuration(row.original).pct > 100 }"
                :style="{
                  width: Math.min(issueDuration(row.original).pct, 100) + '%',
                  backgroundColor: issueDuration(row.original).color,
                }"
              />
            </div>
            <span class="duration-label" :style="{ color: issueDuration(row.original).color }">
              {{ issueDuration(row.original).label }}
            </span>
          </div>
        </template>
        <template #estimated_completion-cell="{ row }">
          {{ row.original.estimated_completion ? row.original.estimated_completion.slice(5) : '-' }}
        </template>
        <template #github_issues-cell="{ row }">
          <div v-if="row.original.github_issues?.length" class="flex flex-wrap gap-1">
            <NuxtLink
              v-for="gh in row.original.github_issues"
              :key="gh.id"
              :to="`/app/repos/${gh.repo}/issues/${gh.id}`"
              class="text-xs text-crystal-500 dark:text-crystal-400 hover:underline"
            >#{{ gh.github_id }}</NuxtLink>
          </div>
          <span v-else class="text-gray-300 dark:text-gray-600">-</span>
        </template>
      </UTable>
      <div class="flex items-center justify-between px-4 py-3 border-t border-gray-50 dark:border-gray-800">
        <span class="text-xs text-gray-400 dark:text-gray-500">共 {{ totalCount }} 条</span>
        <div class="flex items-center space-x-2">
          <UButton size="xs" variant="ghost" color="neutral" :disabled="page <= 1" @click="page--">上一页</UButton>
          <span class="text-xs text-gray-500 dark:text-gray-400">{{ page }} / {{ totalPages }}</span>
          <UButton size="xs" variant="ghost" color="neutral" :disabled="page >= totalPages" @click="page++">下一页</UButton>
        </div>
      </div>
    </div>

    <TransferDialog
      v-if="transferDialog.issueId !== null && transferDialog.projectId !== null"
      v-model="transferDialog.open"
      :issue-id="transferDialog.issueId"
      :project-id="transferDialog.projectId"
      :self-user-id="selfUserId"
      @transferred="fetchIssues"
    />
    <AssignDialog
      v-if="assignDialog.issueId !== null && assignDialog.projectId !== null"
      v-model="assignDialog.open"
      :issue-id="assignDialog.issueId"
      :project-id="assignDialog.projectId"
      @assigned="fetchIssues"
    />
  </div>
</template>

<script setup lang="ts">
import { ISSUE_STATUS, ISSUE_STATUS_OPTIONS, kanbanColor, KANBAN_DEFAULT_COLUMNS, KANBAN_COMPLETED_LEFT, KANBAN_COMPLETED_RIGHT, statusColor as statusColorFn } from '~/constants/issueStatus'
import StatusCell from '~/components/issue/StatusCell.vue'
import TransferDialog from '~/components/issue/TransferDialog.vue'
import AssignDialog from '~/components/issue/AssignDialog.vue'

definePageMeta({ layout: 'default' })

const { api } = useApi()
const { user, can } = useAuth()
const { isMobile } = useMobile()

const selfUserId = computed(() => Number(user.value?.id ?? 0))

const transferDialog = ref<{ open: boolean; issueId: number | null; projectId: number | null }>({
  open: false, issueId: null, projectId: null,
})
const assignDialog = ref<{ open: boolean; issueId: number | null; projectId: number | null }>({
  open: false, issueId: null, projectId: null,
})

function openTransfer(issue: any) {
  transferDialog.value = { open: true, issueId: issue.id, projectId: issue.project }
}
function openAssign(issue: any) {
  assignDialog.value = { open: true, issueId: issue.id, projectId: issue.project }
}
const { settings, update: updateSettings } = useUserSettings()
const route = useRoute()
const toast = useToast()

const viewMode = computed({
  get: () => settings.value.issues_view_mode,
  set: (v: 'kanban' | 'table') => updateSettings('issues_view_mode', v),
})
const showCompleted = ref(false)
const page = ref(1)
const pageSize = 15

// Filters：初始值从 URL query 读取，使外部链接（如首页统计卡片）可预填筛选条件
const filterAssignee = ref<string>(typeof route.query.assignee === 'string' ? route.query.assignee : '')
const filterPriority = ref<string>(typeof route.query.priority === 'string' ? route.query.priority : '')
const filterStatus = ref<string>(typeof route.query.status === 'string' ? route.query.status : '')
const searchQuery = ref<string>(typeof route.query.search === 'string' ? route.query.search : '')
const rowSelection = ref<Record<string, boolean>>({})
const showBatchDeleteConfirm = ref(false)
const batchDeleting = ref(false)

const loading = ref(true)
const issues = ref<any[]>([])
const analyzingIssueIds = ref<Set<number>>(new Set())
const totalCount = ref(0)
const users = ref<any[]>([])
const labelOptions = ref<string[]>([])
const projects = ref<any[]>([])
const repos = ref<any[]>([])

// Create issue modal state
const { confirm: showConfirm } = useDialog()
const showCreateModal = ref(false)

function openCreateModal() {
  if (!newIssue.value.project && user.value?.default_project) {
    newIssue.value.project = String(user.value.default_project.id)
  }
  showCreateModal.value = true
}

async function onCreateModalUpdate(v: boolean) {
  if (v) {
    showCreateModal.value = true
    return
  }
  if (hasFormContent()) {
    const ok = await showConfirm({
      title: '放弃编辑？',
      message: '表单中有未保存的内容，关闭后将丢失。确定要放弃吗？',
      confirmText: '放弃',
      cancelText: '继续编辑',
      color: 'error',
    })
    if (!ok) return
  }
  resetCreateForm()
  showCreateModal.value = false
}
const creating = ref(false)
const createError = ref('')
const defaultAssignee = computed(() => '_none')
const newIssue = ref({
  project: '',
  title: '',
  description: '',
  priority: 'P2',
  status: ISSUE_STATUS.UNASSIGNED,
  labels: [] as string[],
  assignee: defaultAssignee.value,
  repo: null as string | null,
  reporter: user.value?.name || '',
})

// Duplicate-check state for the create-issue modal.
const dupChecking = ref(false)
const dupCandidates = ref<Array<{ id: number; title: string; status: string; reason: string }>>([])
const dupCheckedKey = ref('')

function dupCheckKey(): string {
  const p = newIssue.value.project || ''
  const t = newIssue.value.title.trim().toLowerCase()
  const d = (newIssue.value.description || '').trim().toLowerCase()
  return `${p}|${t}|${d}`
}

async function runDuplicateCheck() {
  const projectId = newIssue.value.project
  const title = newIssue.value.title.trim()
  if (!projectId || title.length < 3) {
    dupCandidates.value = []
    return
  }
  const key = dupCheckKey()
  if (key === dupCheckedKey.value) return
  dupCheckedKey.value = key
  dupChecking.value = true
  try {
    const res = await api<{ candidates: Array<{ id: number; title: string; status: string; reason: string }> }>(
      '/api/issues/check-duplicate/',
      {
        method: 'POST',
        body: {
          project: projectId,
          title,
          description: newIssue.value.description || '',
        },
        format: 'json',
      },
    )
    // Discard stale responses if the user edited the form mid-call.
    if (dupCheckKey() === key) dupCandidates.value = res.candidates || []
  } catch {
    dupCandidates.value = []
  } finally {
    dupChecking.value = false
  }
}

function hasFormContent(): boolean {
  const n = newIssue.value
  return !!(
    n.title.trim()
    || n.description.trim()
    || n.project
    || n.labels.length > 0
    || attachmentIds.value.length > 0
    || n.repo
    || n.priority !== 'P2'
    || n.status !== ISSUE_STATUS.UNASSIGNED
    || n.assignee !== '_none'
  )
}

function resetCreateForm() {
  newIssue.value = {
    project: String(user.value?.default_project?.id || ''),
    title: '',
    description: '',
    priority: 'P2',
    status: ISSUE_STATUS.UNASSIGNED,
    labels: [],
    assignee: defaultAssignee.value,
    repo: null,
    reporter: user.value?.name || '',
  }
  attachmentIds.value = []
  projectRepos.value = []
  dupCandidates.value = []
  dupCheckedKey.value = ''
  dupChecking.value = false
}

const attachmentIds = ref<string[]>([])

const projectRepos = ref<any[]>([])

watch(() => newIssue.value.project, (projectId) => {
  if (!projectId) {
    projectRepos.value = []
    newIssue.value.repo = null
    return
  }
  const project = projects.value.find(p => String(p.id) === String(projectId))
  const repoIds: string[] = (project?.repos || []).map((r: any) => String(r))
  projectRepos.value = repos.value.filter(r => repoIds.includes(String(r.id)))
  if (projectRepos.value.length === 1) {
    newIssue.value.repo = String(projectRepos.value[0].id)
  } else {
    newIssue.value.repo = null
  }
})

watch([() => newIssue.value.title, () => newIssue.value.description], () => {
  dupCandidates.value = []
  dupCheckedKey.value = ''
})

const projectRepoOptions = computed(() => projectRepos.value.map(r => ({ label: r.name, value: String(r.id) })))

const projectOptions = computed(() => projects.value.map(p => ({ label: p.name, value: String(p.id) })))
const createPriorityOptions = PRIORITY_ITEMS.map(p => ({ label: `${p.value} ${p.label}`, value: p.value }))
const createStatusOptions: { label: string; value: string }[] = ISSUE_STATUS_OPTIONS
const createAssigneeOptions = computed(() => [{ label: '无', value: '_none' }, ...users.value.map(u => ({ label: u.name || u.username, value: String(u.id) }))])

const filterAssigneeOptions = computed(() => users.value.map(u => ({ label: u.name || u.username, value: String(u.id) })))
const filterPriorityOptions = PRIORITY_ITEMS.map(p => ({ label: `${p.value} ${p.label}`, value: p.value }))
const filterStatusOptions: { label: string; value: string }[] = ISSUE_STATUS_OPTIONS

function closeCreateModal() {
  onCreateModalUpdate(false)
}

function handleCreateUploadComplete(uploaded: { url: string; filename: string; id: string }) {
  attachmentIds.value.push(uploaded.id)
}

async function handleCreateIssue() {
  if (!newIssue.value.title.trim()) {
    createError.value = '标题不能为空'
    return
  }
  creating.value = true
  createError.value = ''
  try {
    const body: any = {
      title: newIssue.value.title,
      description: newIssue.value.description,
      priority: newIssue.value.priority,
      status: newIssue.value.status,
      labels: newIssue.value.labels,
      attachment_ids: attachmentIds.value,
    }
    if (newIssue.value.project) body.project = newIssue.value.project
    if (newIssue.value.assignee && newIssue.value.assignee !== '_none') body.assignee = newIssue.value.assignee
    if (newIssue.value.repo) body.repo = newIssue.value.repo
    if (newIssue.value.reporter) body.reporter = newIssue.value.reporter
    const created = await api<any>('/api/issues/', { method: 'POST', body, format: 'json' })
    const msg = created?.assignee
      ? `已创建，分配给 ${created.assignee_name || '该成员'}`
      : '已创建，等待人工接单'
    toast.add({ title: msg, color: 'success' })
    resetCreateForm()
    showCreateModal.value = false
    await fetchIssues()
  } catch (e: any) {
    createError.value = formatApiError(e, '创建失败，请重试')
  } finally {
    creating.value = false
  }
}

const selectedRowsData = computed(() => {
  return Object.entries(rowSelection.value)
    .filter(([_, selected]) => selected)
    .map(([idx]) => issues.value[parseInt(idx)])
    .filter(Boolean)
})

const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize)))

const showGHColumn = ref(false)

const columns = computed(() => {
  const cols = [
    { id: 'select', header: '', cell: '' },
    { accessorKey: 'id', header: 'ID' },
    { accessorKey: 'title', header: '标题' },
    { accessorKey: 'cause', header: '原因分析' },
    { accessorKey: 'solution', header: '解决方案' },
    { accessorKey: 'remark', header: '备注' },
    { accessorKey: 'priority', header: '优先级' },
    { accessorKey: 'status', header: '状态' },
    { accessorKey: 'reporter', header: '提出人' },
    { accessorKey: 'created_at', header: '历时' },
    { accessorKey: 'estimated_completion', header: '预计完成' },
  ]
  if (showGHColumn.value) {
    cols.push({ accessorKey: 'github_issues', header: 'GitHub Issues' })
  }
  return cols
})

async function onStatusChange({ issueId, newStatus }: { issueId: number, newStatus: string }) {
  const issue = issues.value.find((i: any) => i.id === issueId)
  if (!issue) return

  const oldStatus = issue.status
  issue.status = newStatus

  try {
    await api(`/api/issues/${issueId}/`, {
      method: 'PATCH',
      body: { status: newStatus },
    })
  } catch (e) {
    console.error('Failed to update issue status:', e)
    issue.status = oldStatus
  }
}

const kanbanColumns = computed(() => {
  const baseKeys = KANBAN_DEFAULT_COLUMNS
  const keys = showCompleted.value
    ? [...KANBAN_COMPLETED_LEFT, ...baseKeys, ...KANBAN_COMPLETED_RIGHT]
    : baseKeys
  return keys.map(key => ({
    key,
    label: key,
    color: kanbanColor(key),
    items: issues.value.filter(i => i.status === key),
  }))
})

function onKanbanDrop({ itemId, toColumn }: { itemId: string | number; fromColumn: string; toColumn: string }) {
  onStatusChange({ issueId: itemId as number, newStatus: toColumn })
}

let rowClickTimer: ReturnType<typeof setTimeout> | null = null
function onRowSelect(row: any, e?: Event) {
  if (!e) return
  const target = e.target as HTMLElement
  // Ignore clicks on checkboxes, buttons, links, and active inputs
  if (target.closest('input, button, a')) return
  // Delay navigation so double-click can cancel it
  if (rowClickTimer) clearTimeout(rowClickTimer)
  rowClickTimer = setTimeout(() => {
    navigateTo(`/app/issues/${row.original.id}`)
  }, 250)
}
function cancelRowClick() {
  if (rowClickTimer) { clearTimeout(rowClickTimer); rowClickTimer = null }
}

async function inlineUpdate(issueId: string, field: string, value: string) {
  try {
    await api(`/api/issues/${issueId}/`, {
      method: 'PATCH',
      body: { [field]: value },
    })
    // Update locally without full refetch
    const issue = issues.value.find((i: any) => i.id === issueId)
    if (issue) issue[field] = value
  } catch (e) {
    console.error('Inline update failed:', e)
    await fetchIssues()
  }
}

function formatApiError(e: any, fallback: string): string {
  const data = e?.data || e?.response?._data
  if (data && typeof data === 'object') {
    const msgs = Object.entries(data)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
      .join('; ')
    if (msgs) return msgs
  }
  return e?.message || fallback
}

function issueDuration(issue: any): { pct: number; color: string; label: string } {
  if (!issue.created_at) return { pct: 0, color: '#9ca3af', label: '-' }
  const now = Date.now()
  const start = new Date(issue.created_at).getTime()
  const elapsed = now - start
  const hours = elapsed / 3600000

  const deadline = issue.estimated_completion
    ? new Date(issue.estimated_completion).getTime()
    : start + 3 * 86400000 // 默认3天
  const total = deadline - start
  const pct = total > 0 ? Math.round((elapsed / total) * 100) : 100

  // 颜色: ≤50% 绿, ≤80% 黄, >80% 红
  const color = pct <= 50 ? '#22c55e' : pct <= 80 ? '#f59e0b' : '#ef4444'

  // 标签
  let label: string
  if (hours < 24) {
    label = `${Math.max(1, Math.round(hours))}h`
  } else {
    const days = (hours / 24).toFixed(1).replace(/\.0$/, '')
    label = `${days}d`
  }
  if (issue.estimated_completion) label += ` / ${issue.estimated_completion.slice(5)}`

  return { pct, color, label }
}

const statusColor = statusColorFn

async function fetchIssues() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize))
    if (!showCompleted.value && !filterStatus.value) {
      params.set('exclude_statuses', '已关闭,未计划')
    }
    if (filterAssignee.value) params.set('assignee', filterAssignee.value)
    if (filterPriority.value) params.set('priority', filterPriority.value)
    if (filterStatus.value) params.set('status', filterStatus.value)
    if (searchQuery.value.trim()) params.set('search', searchQuery.value.trim())

    const data = await api<any>(`/api/issues/?${params.toString()}`)
    issues.value = data.results || data || []
    totalCount.value = data.count ?? issues.value.length
  } catch (e) {
    console.error('Failed to load issues:', e)
  } finally {
    loading.value = false
  }
}

async function batchUpdate(action: string, value: string) {
  const ids = selectedRowsData.value.map((row: any) => row.id)
  if (!ids.length) return
  try {
    await api('/api/issues/batch-update/', {
      method: 'POST',
      body: { ids, action, value },
    })
    rowSelection.value = {}
    await fetchIssues()
  } catch (e) {
    console.error('Batch update failed:', e)
  }
}

async function handleBatchDelete() {
  const ids = selectedRowsData.value.map((row: any) => row.id)
  if (!ids.length) return
  batchDeleting.value = true
  try {
    await api('/api/issues/batch-update/', {
      method: 'POST',
      body: { ids, action: 'delete' },
    })
    showBatchDeleteConfirm.value = false
    rowSelection.value = {}
    await fetchIssues()
  } catch (e) {
    console.error('Batch delete failed:', e)
  } finally {
    batchDeleting.value = false
  }
}

const batchAssignItems = computed(() => [users.value.map(u => ({
  label: u.name || u.username,
  onSelect: () => batchUpdate('assign', String(u.id)),
}))])

const batchPriorityItems = [PRIORITY_ITEMS.map(p => ({
  label: `${p.value} ${p.label}`,
  onSelect: () => batchUpdate('priority', p.value),
}))]

const batchStatusItems = [filterStatusOptions.map(s => ({
  label: s.label,
  onSelect: () => batchUpdate('set_status', s.value),
}))]

watch(page, () => {
  rowSelection.value = {}
  fetchIssues()
})

watch(showCompleted, () => {
  page.value = 1
  rowSelection.value = {}
  fetchIssues()
})

watch([filterAssignee, filterPriority, filterStatus], () => {
  page.value = 1
  rowSelection.value = {}
  fetchIssues()
})

let searchDebounce: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    page.value = 1
    rowSelection.value = {}
    fetchIssues()
  }, 300)
})

onMounted(async () => {
  const [, usersData, settingsData, projectsData, reposData] = await Promise.all([
    fetchIssues(),
    api<any[]>('/api/users/choices/').catch(() => []),
    api<any>('/api/settings/').catch(() => ({ labels: [] })),
    api<any>('/api/projects/').catch(() => ({ results: [] })),
    api<any>('/api/repos/').catch(() => ({ results: [] })),
  ])
  users.value = usersData || []
  const rawLabels = settingsData?.labels || {}
  labelOptions.value = typeof rawLabels === 'object' && !Array.isArray(rawLabels) ? Object.keys(rawLabels) : rawLabels
  projects.value = projectsData?.results || projectsData || []
  repos.value = reposData?.results || reposData || []
  // Check AI analysis status for issues with repos
  checkAnalyzingIssues()
})

async function checkAnalyzingIssues() {
  const issuesWithRepo = issues.value.filter(i => i.repo)
  const checks = await Promise.all(
    issuesWithRepo.map(i =>
      api<any>(`/api/issues/${i.id}/ai-status/`).catch(() => ({ status: 'idle' }))
    )
  )
  const running = new Set<number>()
  issuesWithRepo.forEach((issue, idx) => {
    if (checks[idx]?.status === 'running') running.add(issue.id)
  })
  analyzingIssueIds.value = running
}
</script>

<style scoped>
.modal-form {
  padding: 1.5rem 2rem;
  max-height: 90vh;
  overflow-y: auto;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}
.modal-header h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #111827;
}
:root.dark .modal-header h3 {
  color: #f3f4f6;
}
.modal-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.form-row label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: #374151;
}
:root.dark .form-row label {
  color: #9ca3af;
}
.form-row :deep(input),
.form-row :deep(textarea),
.form-row :deep(select),
.form-row :deep(button[role="combobox"]),
.form-row :deep([data-part="trigger"]) {
  width: 100% !important;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}
@media (min-width: 768px) {
  .form-grid-2 {
    grid-template-columns: 1fr 1fr;
  }
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #f3f4f6;
}
:root.dark .modal-footer {
  border-top-color: #374151;
}
.filter-clear {
  position: absolute;
  right: 2rem;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  border-radius: 9999px;
  color: #9ca3af;
  cursor: pointer;
}
.filter-clear:hover {
  color: #374151;
  background-color: #f3f4f6;
}
:root.dark .filter-clear:hover {
  color: #d1d5db;
  background-color: #374151;
}
.duration-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 72px;
}
.duration-bar {
  height: 6px;
  border-radius: 3px;
  background-color: #f3f4f6;
  overflow: hidden;
}
:root.dark .duration-bar {
  background-color: #374151;
}
.duration-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}
.duration-overdue {
  animation: pulse-bar 2s ease-in-out infinite;
}
.duration-label {
  font-size: 11px;
  line-height: 1;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
@keyframes pulse-bar {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
.dup-check-box {
  margin-top: 0.5rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.5rem;
  background-color: #fffbeb; /* amber-50 */
  border: 1px solid #fde68a; /* amber-200 */
}
:root.dark .dup-check-box {
  background-color: rgba(120, 53, 15, 0.25); /* amber-900/25 */
  border-color: rgba(245, 158, 11, 0.4); /* amber-500/40 */
}
/*
 * Issues table: fixed layout so we control column widths.
 * Columns: select | ID | 标题 | 原因分析 | 解决方案 | 备注 | 优先级 | 状态 | 提出人 | 历时 | 预计完成
 * Narrow cols get fixed width; 标题/原因/方案 share remaining space.
 */
.issues-table :deep(table) { table-layout: fixed; width: 100%; }
.issues-table :deep(:is(th, td):nth-child(1)) { width: 2.5%; }   /* select */
.issues-table :deep(:is(th, td):nth-child(2)) { width: 3.5%; }   /* ID */
/* 3: 标题 — auto */
/* 4: 原因分析 — auto */
/* 5: 解决方案 — auto */
.issues-table :deep(:is(th, td):nth-child(6)) { width: 4.5%; }   /* 备注 */
.issues-table :deep(:is(th, td):nth-child(7)) { width: 4.5%; }   /* 优先级 */
.issues-table :deep(:is(th, td):nth-child(8)) { width: 8%; }     /* 状态 */
.issues-table :deep(:is(th, td):nth-child(9)) { width: 6%; }     /* 提出人 */
.issues-table :deep(:is(th, td):nth-child(10)) { width: 7%; }    /* 历时 */
.issues-table :deep(:is(th, td):nth-child(11)) { width: 5%; }    /* 预计完成 */
</style>
