<template>
  <div v-if="loading" class="flex items-center justify-center py-20">
    <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
  </div>

  <div v-else-if="project" class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">{{ project.name }}</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ project.description }}</p>
      </div>
      <UBadge
        :color="project.status === '进行中' ? 'primary' : project.status === '已完成' ? 'success' : 'neutral'"
        variant="subtle"
      >
        {{ project.status }}
      </UBadge>
    </div>

    <!-- Project Info -->
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">项目信息</h3>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="bg-gray-50 dark:bg-gray-800 rounded-lg px-4 py-3">
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">预计完成时间</p>
          <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ project.estimated_completion ? project.estimated_completion.slice(0, 10) : '-' }}</p>
        </div>
        <div class="bg-gray-50 dark:bg-gray-800 rounded-lg px-4 py-3">
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">实际完成耗时</p>
          <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ project.actual_hours ? formatHours(project.actual_hours) : '-' }}</p>
        </div>
        <div class="bg-gray-50 dark:bg-gray-800 rounded-lg px-4 py-3">
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">创建时间</p>
          <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ project.created_at?.slice(0, 10) }}</p>
        </div>
      </div>
      <div v-if="project.remark" class="mt-4 bg-gray-50 dark:bg-gray-800 rounded-lg px-4 py-3">
        <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">备注</p>
        <p class="text-sm text-gray-700 dark:text-gray-300">{{ project.remark }}</p>
      </div>
    </div>

    <!-- Members -->
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">项目成员</h3>
      <div v-if="projectMembers.length" class="flex flex-wrap gap-3">
        <div
          v-for="m in projectMembers"
          :key="m.user_id"
          class="flex flex-col bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2 max-w-xs"
        >
          <div class="flex items-center gap-2">
            <div class="w-7 h-7 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center shrink-0">
              <span class="text-crystal-600 dark:text-crystal-400 text-xs font-medium">{{ (m.user_name || '?').slice(0, 1) }}</span>
            </div>
            <span class="text-sm text-gray-700 dark:text-gray-300 truncate">{{ m.user_name || '未知' }}</span>
            <UBadge v-if="m.role" color="neutral" variant="subtle" size="xs">{{ m.role }}</UBadge>
            <UBadge v-else color="neutral" variant="soft" size="xs">未分配角色</UBadge>
            <button
              v-if="canManageMembers"
              class="ml-auto text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
              title="编辑"
              @click="openEditMember(m)"
            >
              <UIcon name="i-heroicons-pencil-square" class="w-3.5 h-3.5" />
            </button>
          </div>
          <p
            v-if="m.personal_description"
            class="mt-1.5 text-xs text-gray-500 dark:text-gray-400 line-clamp-2"
            :title="m.personal_description"
          >
            {{ m.personal_description }}
          </p>
        </div>
      </div>
      <div v-else class="text-sm text-gray-400 dark:text-gray-500">暂无成员</div>
    </div>

    <!-- Issues View (collapsible) -->
    <div>
      <button
        class="w-full flex items-center justify-between mb-3 group"
        @click="issuesExpanded = !issuesExpanded"
      >
        <div class="flex items-center gap-2">
          <UIcon
            :name="issuesExpanded ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
            class="w-4 h-4 text-gray-400 dark:text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-200 transition-colors"
          />
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Issues</h3>
          <span class="text-xs text-gray-400 dark:text-gray-500">({{ projectIssues.length }})</span>
        </div>
      </button>

      <div v-if="issuesExpanded">
        <div class="flex items-center justify-end mb-3">
          <div class="flex items-center gap-3">
            <div class="flex items-center gap-2">
              <UInput v-model="search" placeholder="搜索" icon="i-heroicons-magnifying-glass" size="xs" class="w-40" />
              <USelect v-model="filterPriority" :items="priorityOptions" size="xs" class="w-24" value-key="value" />
              <USelect v-model="filterStatus" :items="statusOptions" size="xs" class="w-24" value-key="value" />
              <USelect v-model="filterAssignee" :items="assigneeOptions" size="xs" class="w-28" value-key="value" />
            </div>
            <div class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
              <button
                class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
                :class="viewMode === 'kanban' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
                @click="viewMode = 'kanban'"
              >
                看板
              </button>
              <button
                class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
                :class="viewMode === 'table' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
                @click="viewMode = 'table'"
              >
                列表
              </button>
            </div>
          </div>
        </div>

        <ProjectsKanbanBoard v-if="viewMode === 'kanban'" :issues="filteredIssues" @update:status="onStatusChange" />

        <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
          <UTable
            :data="filteredIssues"
            :columns="tableColumns"
            :ui="{ th: 'text-xs', td: 'text-sm' }"
          >
            <template #id-cell="{ row }">
              <NuxtLink :to="`/app/issues/${row.original.id}`" class="text-crystal-500 dark:text-crystal-400 hover:text-crystal-700 dark:hover:text-crystal-300 font-medium">{{ row.original.id }}</NuxtLink>
            </template>
            <template #title-cell="{ row }">
              <NuxtLink :to="`/app/issues/${row.original.id}`" class="text-gray-900 dark:text-gray-100 hover:text-crystal-600 dark:hover:text-crystal-400 line-clamp-1">{{ row.original.title }}</NuxtLink>
            </template>
            <template #priority-cell="{ row }">
              <UBadge :color="row.original.priority === 'P0' ? 'error' : row.original.priority === 'P1' ? 'warning' : row.original.priority === 'P2' ? 'warning' : 'neutral'" variant="subtle" size="xs">{{ row.original.priority }}</UBadge>
            </template>
            <template #status-cell="{ row }">
              <UBadge :color="row.original.status === '未计划' ? 'secondary' : row.original.status === '待处理' ? 'warning' : row.original.status === '进行中' ? 'info' : row.original.status === '已解决' ? 'success' : row.original.status === '已发布' ? 'primary' : 'neutral'" variant="subtle" size="xs">{{ row.original.status }}</UBadge>
            </template>
            <template #assignee_name-cell="{ row }">
              {{ row.original.assignee_name || '-' }}
            </template>
            <template #created_at-cell="{ row }">
              {{ row.original.created_at ? row.original.created_at.slice(0, 10) : '-' }}
            </template>
          </UTable>
        </div>
      </div>
    </div>

    <!-- Edit Member Modal -->
    <UModal v-model:open="showMemberModal" title="编辑成员" :ui="{ width: 'sm:max-w-md' }">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>编辑成员 - {{ editingMember?.user_name }}</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showMemberModal = false" />
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label>角色</label>
              <USelect
                v-model="memberForm.role_id"
                :items="roleOptions"
                placeholder="未分配角色"
                value-key="value"
              />
              <p class="text-xs text-gray-400 dark:text-gray-500">从「权限管理 - 组」中选择</p>
            </div>
            <div class="form-row">
              <label>个人描述</label>
              <UTextarea
                v-model="memberForm.personal_description"
                placeholder="该成员在本项目中的职责或备注"
                :rows="3"
              />
            </div>
            <p v-if="memberFormError" class="text-sm text-red-500">{{ memberFormError }}</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="showMemberModal = false">取消</UButton>
            <UButton :loading="savingMember" @click="saveMember">保存</UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>

  <div v-else class="text-center py-20 text-sm text-gray-400 dark:text-gray-500">项目不存在</div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const { can } = useAuth()
const route = useRoute()
const { settings, update: updateSettings } = useUserSettings()

const loading = ref(true)
const project = ref<any>(null)
const projectIssues = ref<any[]>([])
const users = ref<any[]>([])
const roleChoices = ref<{ id: number, name: string }[]>([])
const issuesExpanded = ref(false)
const viewMode = computed({
  get: () => settings.value.project_view_mode,
  set: (v: 'kanban' | 'table') => updateSettings('project_view_mode', v),
})

const canManageMembers = computed(() => can('projects.manage_project_members'))

const search = ref('')
const filterPriority = ref('_all')
const filterStatus = ref('_all')
const filterAssignee = ref('_all')

const priorityOptions = [{ label: '全部', value: '_all' }, { label: 'P0', value: 'P0' }, { label: 'P1', value: 'P1' }, { label: 'P2', value: 'P2' }, { label: 'P3', value: 'P3' }]
const statusOptions = [{ label: '全部', value: '_all' }, { label: '未计划', value: '未计划' }, { label: '待处理', value: '待处理' }, { label: '进行中', value: '进行中' }, { label: '已解决', value: '已解决' }, { label: '已发布', value: '已发布' }, { label: '已关闭', value: '已关闭' }]
const assigneeOptions = computed(() => [{ label: '全部', value: '_all' }, ...users.value.map(u => ({ label: u.name || u.username, value: String(u.id) }))])

const roleOptions = computed(() => [
  { label: '未分配角色', value: null },
  ...roleChoices.value.map(g => ({ label: g.name, value: g.id })),
])

const filteredIssues = computed(() => {
  let result = projectIssues.value
  if (search.value) {
    const q = search.value.toLowerCase()
    result = result.filter(i => i.title?.toLowerCase().includes(q) || String(i.id).includes(q))
  }
  if (filterPriority.value !== '_all') result = result.filter(i => i.priority === filterPriority.value)
  if (filterStatus.value !== '_all') result = result.filter(i => i.status === filterStatus.value)
  if (filterAssignee.value !== '_all') result = result.filter(i => String(i.assignee) === filterAssignee.value)
  return result
})

const projectMembers = computed(() => project.value?.members ?? [])

function formatHours(hours: number): string {
  if (hours >= 24) {
    const days = Math.floor(hours / 8)
    return `${days} 人天 (${hours}h)`
  }
  return `${hours}h`
}

async function onStatusChange({ issueId, newStatus }: { issueId: number, newStatus: string }) {
  const issue = projectIssues.value.find((i: any) => i.id === issueId)
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

// ---- Member edit ----
const showMemberModal = ref(false)
const editingMember = ref<any>(null)
const savingMember = ref(false)
const memberFormError = ref('')
const memberForm = ref<{ role_id: number | null, personal_description: string }>({
  role_id: null,
  personal_description: '',
})

function openEditMember(member: any) {
  editingMember.value = member
  const matching = roleChoices.value.find(g => g.name === member.role)
  memberForm.value = {
    role_id: matching ? matching.id : null,
    personal_description: member.personal_description || '',
  }
  memberFormError.value = ''
  showMemberModal.value = true
}

async function saveMember() {
  if (!editingMember.value) return
  savingMember.value = true
  memberFormError.value = ''
  try {
    const updated = await api<any>(
      `/api/projects/${route.params.id}/members/${editingMember.value.user_id}/`,
      {
        method: 'PATCH',
        body: {
          role_id: memberForm.value.role_id,
          personal_description: memberForm.value.personal_description,
        },
      },
    )
    const idx = projectMembers.value.findIndex((m: any) => m.user_id === editingMember.value.user_id)
    if (idx !== -1) {
      project.value.members[idx] = updated
    }
    showMemberModal.value = false
  } catch (e: any) {
    const data = e?.data || e?.response?._data
    memberFormError.value = (data && typeof data === 'object' && Object.values(data).flat().join('; ')) || e?.message || '保存失败'
  } finally {
    savingMember.value = false
  }
}

const tableColumns = [
  { accessorKey: 'id', header: 'ID' },
  { accessorKey: 'title', header: '标题' },
  { accessorKey: 'priority', header: '优先级' },
  { accessorKey: 'status', header: '状态' },
  { accessorKey: 'assignee_name', header: '负责人' },
  { accessorKey: 'created_at', header: '创建时间' },
]

onMounted(async () => {
  const id = route.params.id
  try {
    const [projectData, issuesData, usersData, rolesData] = await Promise.all([
      api<any>(`/api/projects/${id}/`),
      api<any>(`/api/projects/${id}/issues/`),
      api<any[]>('/api/users/choices/').catch(() => []),
      api<any[]>('/api/projects/role-choices/').catch(() => []),
    ])
    project.value = projectData
    projectIssues.value = issuesData.results || issuesData || []
    users.value = usersData || []
    roleChoices.value = rolesData || []
  } catch (e) {
    console.error('Failed to load project:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.modal-form {
  padding: 1.5rem 2rem;
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
</style>
