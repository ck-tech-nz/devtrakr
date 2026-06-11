<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">权限管理</h1>
    </div>

    <!-- Non-superuser redirect -->
    <div v-if="!isSuperuser" class="flex items-center justify-center py-20">
      <div class="text-sm text-red-500">仅超级管理员可访问此页面</div>
    </div>

    <template v-else>
      <!-- Tab Switcher -->
      <div class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5 w-fit">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="px-4 py-1.5 text-xs font-medium rounded-md transition-colors"
          :class="activeTab === tab.key ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
      </div>

      <template v-else>
        <!-- Tab 1: Page Routes -->
        <div v-if="activeTab === 'routes'">
          <div class="flex items-center justify-between mb-4">
            <span class="text-sm text-gray-500 dark:text-gray-400">共 {{ routes.length }} 条路由</span>
            <UButton icon="i-heroicons-plus" size="sm" @click="openCreateRoute">新建路由</UButton>
          </div>

          <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
            <UTable :data="routes" :columns="routeColumns" :ui="{ th: 'text-xs', td: 'text-sm' }">
              <template #is_active-cell="{ row }">
                <button
                  class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none"
                  :class="row.original.is_active ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'"
                  @click="toggleRouteActive(row.original)"
                >
                  <span
                    class="inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform"
                    :class="row.original.is_active ? 'translate-x-4.5' : 'translate-x-0.5'"
                  />
                </button>
              </template>
              <template #show_in_nav-cell="{ row }">
                <button
                  class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none"
                  :class="row.original.show_in_nav ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'"
                  @click="toggleRouteNav(row.original)"
                >
                  <span
                    class="inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform"
                    :class="row.original.show_in_nav ? 'translate-x-4.5' : 'translate-x-0.5'"
                  />
                </button>
              </template>
              <template #permission-cell="{ row }">
                <UBadge v-if="row.original.permission" variant="subtle" color="info" size="xs">{{ row.original.permission }}</UBadge>
                <span v-else class="text-gray-400">—</span>
              </template>
              <template #source-cell="{ row }">
                <UBadge :color="row.original.source === 'seed' ? 'neutral' : 'warning'" variant="subtle" size="xs">{{ row.original.source }}</UBadge>
              </template>
              <template #actions-cell="{ row }">
                <div class="flex items-center space-x-1">
                  <UButton icon="i-heroicons-pencil-square" variant="ghost" color="neutral" size="xs" @click="openEditRoute(row.original)" />
                  <UButton icon="i-heroicons-trash" variant="ghost" color="error" size="xs" @click="confirmDeleteRoute(row.original)" />
                </div>
              </template>
            </UTable>
          </div>
        </div>

        <!-- Tab 2: Group Permissions -->
        <div v-if="activeTab === 'groups'">
          <div class="flex items-center justify-between mb-4">
            <span class="text-sm text-gray-500 dark:text-gray-400">共 {{ groups.length }} 个组</span>
            <div class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
              <button
                class="px-2.5 py-1 text-xs rounded transition-colors"
                :class="groupViewMode === 'listbox' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400'"
                @click="groupViewMode = 'listbox'"
              >
                列表模式
              </button>
              <button
                class="px-2.5 py-1 text-xs rounded transition-colors"
                :class="groupViewMode === 'tags' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400'"
                @click="groupViewMode = 'tags'"
              >
                标签模式
              </button>
            </div>
          </div>

          <div class="space-y-4">
            <div
              v-for="group in groups"
              :key="group.id"
              class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5"
            >
              <div class="flex items-center justify-between mb-3">
                <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">{{ group.name }}</h3>
                <div class="flex items-center gap-2">
                  <UButton size="xs" variant="ghost" color="neutral" icon="i-heroicons-document-duplicate" @click="openCloneGroup(group)">克隆</UButton>
                  <UButton size="xs" variant="outline" color="neutral" :loading="savingGroup === group.id" @click="saveGroup(group)">保存</UButton>
                </div>
              </div>

              <!-- Listbox mode -->
              <DualListbox
                v-if="groupViewMode === 'listbox'"
                :items="allPermissionNames"
                :model-value="Array.from(group._selectedPerms)"
                @update:model-value="updateGroupPerms(group, $event)"
              />

              <!-- Tags mode (original) -->
              <div v-else class="flex flex-wrap gap-2">
                <label
                  v-for="perm in allPermissions"
                  :key="perm.full_codename"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs cursor-pointer transition-colors"
                  :class="group._selectedPerms.has(perm.full_codename) ? 'bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800' : 'bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700'"
                >
                  <input
                    type="checkbox"
                    class="sr-only"
                    :checked="group._selectedPerms.has(perm.full_codename)"
                    @change="toggleGroupPerm(group, perm.full_codename)"
                  />
                  {{ perm.full_codename }}
                </label>
              </div>
            </div>
          </div>
        </div>

        <!-- Tab 3: Permission List -->
        <div v-if="activeTab === 'permissions'">
          <div class="flex items-center justify-between mb-4">
            <span class="text-sm text-gray-500 dark:text-gray-400">共 {{ allPermissions.length }} 个权限</span>
            <UButton icon="i-heroicons-plus" size="sm" @click="showCreatePermModal = true">新建自定义权限</UButton>
          </div>

          <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
            <UTable :data="allPermissions" :columns="permColumns" :ui="{ th: 'text-xs', td: 'text-sm' }">
              <template #source-cell="{ row }">
                <UBadge :color="row.original.source === 'custom' ? 'warning' : 'neutral'" variant="subtle" size="xs">{{ row.original.source === 'custom' ? '自定义' : '模型' }}</UBadge>
              </template>
              <template #actions-cell="{ row }">
                <UButton
                  v-if="row.original.source === 'custom'"
                  icon="i-heroicons-trash"
                  variant="ghost"
                  color="error"
                  size="xs"
                  @click="confirmDeletePerm(row.original)"
                />
              </template>
            </UTable>
          </div>
        </div>
      </template>

      <!-- Create/Edit Route Modal -->
      <UModal v-model:open="showRouteModal" :title="editingRoute ? '编辑路由' : '新建路由'" :ui="{ width: 'sm:max-w-2xl' }">
        <template #content>
          <div class="modal-form">
            <div class="modal-header">
              <h3>{{ editingRoute ? '编辑路由' : '新建路由' }}</h3>
              <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showRouteModal = false" />
            </div>
            <div class="modal-body">
              <div class="form-row">
                <label>路径 <span class="text-red-400">*</span></label>
                <UInput v-model="routeForm.path" placeholder="/app/example" />
              </div>
              <div class="form-row">
                <label>标签 <span class="text-red-400">*</span></label>
                <UInput v-model="routeForm.label" placeholder="页面名称" />
              </div>
              <div class="form-row">
                <label>图标</label>
                <UInput v-model="routeForm.icon" placeholder="i-heroicons-..." />
              </div>
              <div class="form-row">
                <label>关联权限</label>
                <USelect
                  :model-value="routeForm.permission || '_none'"
                  :items="permSelectOptions"
                  placeholder="不绑定权限"
                  value-key="value"
                  @update:model-value="(v: string) => routeForm.permission = v === '_none' ? '' : v"
                />
              </div>
              <div class="form-grid-2">
                <div class="form-row">
                  <label>排序</label>
                  <UInput v-model.number="routeForm.sort_order" type="number" />
                </div>
                <div class="form-row">
                  <label>状态</label>
                  <div class="flex items-center gap-4 pt-1.5">
                    <label class="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 cursor-pointer whitespace-nowrap">
                      <input v-model="routeForm.is_active" type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                      启用
                    </label>
                    <label class="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 cursor-pointer whitespace-nowrap">
                      <input v-model="routeForm.show_in_nav" type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                      显示在导航
                    </label>
                  </div>
                </div>
              </div>
              <p v-if="routeFormError" class="text-sm text-red-500">{{ routeFormError }}</p>
            </div>
            <div class="modal-footer">
              <UButton variant="outline" color="neutral" @click="showRouteModal = false">取消</UButton>
              <UButton :loading="savingRoute" @click="handleSaveRoute">{{ editingRoute ? '保存' : '创建' }}</UButton>
            </div>
          </div>
        </template>
      </UModal>

      <!-- Create Permission Modal -->
      <UModal v-model:open="showCreatePermModal" title="新建自定义权限" :ui="{ width: 'sm:max-w-md' }">
        <template #content>
          <div class="modal-form">
            <div class="modal-header">
              <h3>新建自定义权限</h3>
              <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showCreatePermModal = false" />
            </div>
            <div class="modal-body">
              <div class="form-row">
                <label>代码名 <span class="text-red-400">*</span></label>
                <UInput v-model="newPerm.codename" placeholder="access_xxx" />
              </div>
              <div class="form-row">
                <label>显示名称 <span class="text-red-400">*</span></label>
                <UInput v-model="newPerm.name" placeholder="Can access xxx" />
              </div>
              <p v-if="permFormError" class="text-sm text-red-500">{{ permFormError }}</p>
            </div>
            <div class="modal-footer">
              <UButton variant="outline" color="neutral" @click="showCreatePermModal = false">取消</UButton>
              <UButton :loading="creatingPerm" @click="handleCreatePerm">创建</UButton>
            </div>
          </div>
        </template>
      </UModal>

      <!-- Clone Group Modal -->
      <UModal v-model:open="showCloneModal" title="克隆权限组" :ui="{ width: 'sm:max-w-md' }">
        <template #content>
          <div class="modal-form">
            <div class="modal-header">
              <h3>克隆权限组</h3>
              <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showCloneModal = false" />
            </div>
            <div class="modal-body">
              <div class="form-row">
                <label>新组名 <span class="text-red-400">*</span></label>
                <UInput v-model="cloneGroupName" placeholder="输入新组名" />
              </div>
              <p class="text-xs text-gray-400 dark:text-gray-500">将复制「{{ cloningFrom?.name }}」的所有权限</p>
              <p v-if="cloneError" class="text-sm text-red-500">{{ cloneError }}</p>
            </div>
            <div class="modal-footer">
              <UButton variant="outline" color="neutral" @click="showCloneModal = false">取消</UButton>
              <UButton :loading="cloning" @click="handleCloneGroup">创建</UButton>
            </div>
          </div>
        </template>
      </UModal>

      <!-- Delete Confirmation Modal -->
      <UModal v-model:open="showDeleteModal" title="确认删除" :ui="{ width: 'sm:max-w-sm' }">
        <template #content>
          <div class="modal-form">
            <div class="modal-header">
              <h3>确认删除</h3>
              <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showDeleteModal = false" />
            </div>
            <div class="modal-body">
              <p class="text-sm text-gray-600 dark:text-gray-400">{{ deleteMessage }}</p>
              <p v-if="deleteError" class="text-sm text-red-500">{{ deleteError }}</p>
            </div>
            <div class="modal-footer">
              <UButton variant="outline" color="neutral" @click="showDeleteModal = false">取消</UButton>
              <UButton color="error" :loading="deleting" @click="handleDelete">删除</UButton>
            </div>
          </div>
        </template>
      </UModal>
    </template>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const { user } = useAuth()

const isSuperuser = computed(() => user.value?.is_superuser === true)

// Tabs
type TabKey = 'routes' | 'groups' | 'permissions'
const tabs: { key: TabKey; label: string }[] = [
  { key: 'routes', label: '页面路由' },
  { key: 'groups', label: '组-权限' },
  { key: 'permissions', label: '权限列表' },
]
const activeTab = ref<TabKey>('routes')
const groupViewMode = ref<'listbox' | 'tags'>('listbox')

// Data
const loading = ref(true)
const routes = ref<any[]>([])
const groups = ref<any[]>([])
const allPermissions = ref<any[]>([])

// Route columns
const routeColumns = [
  { accessorKey: 'path', header: '路径' },
  { accessorKey: 'label', header: '标签' },
  { accessorKey: 'icon', header: '图标' },
  { accessorKey: 'permission', header: '权限' },
  { accessorKey: 'sort_order', header: '排序' },
  { accessorKey: 'is_active', header: '启用' },
  { accessorKey: 'show_in_nav', header: '导航' },
  { accessorKey: 'source', header: '来源' },
  { accessorKey: 'actions', header: '操作' },
]

// Permission columns
const permColumns = [
  { accessorKey: 'full_codename', header: '完整代码名' },
  { accessorKey: 'name', header: '名称' },
  { accessorKey: 'app_label', header: '应用' },
  { accessorKey: 'source', header: '来源' },
  { accessorKey: 'actions', header: '操作' },
]

// Permission select options for route form（SelectItem 不允许空字符串 value，「不绑定」用 '_none' 哨兵表示）
const permSelectOptions = computed(() => [
  { label: '不绑定权限', value: '_none' },
  ...allPermissions.value.map(p => ({ label: p.full_codename, value: p.full_codename })),
])

const allPermissionNames = computed(() =>
  allPermissions.value.map(p => p.full_codename)
)

// ---- Route CRUD ----
const showRouteModal = ref(false)
const editingRoute = ref<any>(null)
const savingRoute = ref(false)
const routeFormError = ref('')
const routeForm = ref({
  path: '',
  label: '',
  icon: '',
  permission: '',
  sort_order: 0,
  is_active: true,
  show_in_nav: true,
})

function openCreateRoute() {
  editingRoute.value = null
  routeForm.value = { path: '', label: '', icon: '', permission: '', sort_order: 0, is_active: true, show_in_nav: true }
  routeFormError.value = ''
  showRouteModal.value = true
}

function openEditRoute(route: any) {
  editingRoute.value = route
  routeForm.value = {
    path: route.path,
    label: route.label,
    icon: route.icon || '',
    permission: route.permission || '',
    sort_order: route.sort_order,
    is_active: route.is_active,
    show_in_nav: route.show_in_nav,
  }
  routeFormError.value = ''
  showRouteModal.value = true
}

async function handleSaveRoute() {
  if (!routeForm.value.path.trim() || !routeForm.value.label.trim()) {
    routeFormError.value = '路径和标签不能为空'
    return
  }
  savingRoute.value = true
  routeFormError.value = ''
  try {
    const body: any = {
      path: routeForm.value.path,
      label: routeForm.value.label,
      icon: routeForm.value.icon,
      permission: routeForm.value.permission || null,
      sort_order: routeForm.value.sort_order,
      is_active: routeForm.value.is_active,
      show_in_nav: routeForm.value.show_in_nav,
    }
    if (editingRoute.value) {
      await api(`/api/page-perms/routes/${editingRoute.value.id}/`, { method: 'PATCH', body })
    } else {
      await api('/api/page-perms/routes/', { method: 'POST', body })
    }
    showRouteModal.value = false
    await fetchRoutes()
  } catch (e: any) {
    routeFormError.value = formatApiError(e, '操作失败，请重试')
  } finally {
    savingRoute.value = false
  }
}

async function toggleRouteActive(route: any) {
  try {
    await api(`/api/page-perms/routes/${route.id}/`, { method: 'PATCH', body: { is_active: !route.is_active } })
    route.is_active = !route.is_active
  } catch (e: any) {
    alert(formatApiError(e, '操作失败'))
  }
}

async function toggleRouteNav(route: any) {
  try {
    await api(`/api/page-perms/routes/${route.id}/`, { method: 'PATCH', body: { show_in_nav: !route.show_in_nav } })
    route.show_in_nav = !route.show_in_nav
  } catch (e: any) {
    alert(formatApiError(e, '操作失败'))
  }
}

// ---- Permission CRUD ----
const showCreatePermModal = ref(false)
const creatingPerm = ref(false)
const permFormError = ref('')
const newPerm = ref({ codename: '', name: '' })

async function handleCreatePerm() {
  if (!newPerm.value.codename.trim() || !newPerm.value.name.trim()) {
    permFormError.value = '代码名和名称不能为空'
    return
  }
  creatingPerm.value = true
  permFormError.value = ''
  try {
    await api('/api/page-perms/permissions/', { method: 'POST', body: { codename: newPerm.value.codename, name: newPerm.value.name } })
    showCreatePermModal.value = false
    newPerm.value = { codename: '', name: '' }
    await fetchPermissions()
  } catch (e: any) {
    permFormError.value = formatApiError(e, '创建失败，请重试')
  } finally {
    creatingPerm.value = false
  }
}

// ---- Group Permission Management ----
const savingGroup = ref<number | null>(null)

function updateGroupPerms(group: any, perms: string[]) {
  group._selectedPerms = new Set(perms)
}

function toggleGroupPerm(group: any, perm: string) {
  if (group._selectedPerms.has(perm)) {
    group._selectedPerms.delete(perm)
  } else {
    group._selectedPerms.add(perm)
  }
}

async function saveGroup(group: any) {
  savingGroup.value = group.id
  try {
    const permissions = Array.from(group._selectedPerms) as string[]
    await api(`/api/page-perms/groups/${group.id}/`, { method: 'PATCH', body: { permissions } })
  } catch (e: any) {
    alert(formatApiError(e, '保存失败'))
  } finally {
    savingGroup.value = null
  }
}

// ---- Clone Group ----
const showCloneModal = ref(false)
const cloningFrom = ref<any>(null)
const cloneGroupName = ref('')
const cloneError = ref('')
const cloning = ref(false)

function openCloneGroup(group: any) {
  cloningFrom.value = group
  cloneGroupName.value = `${group.name} (副本)`
  cloneError.value = ''
  showCloneModal.value = true
}

async function handleCloneGroup() {
  if (!cloneGroupName.value.trim()) {
    cloneError.value = '组名不能为空'
    return
  }
  cloning.value = true
  cloneError.value = ''
  try {
    await api('/api/page-perms/groups/', {
      method: 'POST',
      body: {
        name: cloneGroupName.value.trim(),
        permissions: Array.from(cloningFrom.value._selectedPerms) as string[],
      },
    })
    showCloneModal.value = false
    await fetchGroups()
  } catch (e: any) {
    cloneError.value = formatApiError(e, '创建失败，请重试')
  } finally {
    cloning.value = false
  }
}

// ---- Delete Handling ----
const showDeleteModal = ref(false)
const deleteMessage = ref('')
const deleteError = ref('')
const deleting = ref(false)
let deleteAction: (() => Promise<void>) | null = null

function confirmDeleteRoute(route: any) {
  deleteMessage.value = `确定要删除路由 "${route.path}" 吗？`
  deleteError.value = ''
  deleteAction = async () => {
    await api(`/api/page-perms/routes/${route.id}/`, { method: 'DELETE' })
    await fetchRoutes()
  }
  showDeleteModal.value = true
}

function confirmDeletePerm(perm: any) {
  deleteMessage.value = `确定要删除自定义权限 "${perm.full_codename}" 吗？`
  deleteError.value = ''
  deleteAction = async () => {
    await api(`/api/page-perms/permissions/${perm.id}/`, { method: 'DELETE' })
    await fetchPermissions()
  }
  showDeleteModal.value = true
}

async function handleDelete() {
  if (!deleteAction) return
  deleting.value = true
  deleteError.value = ''
  try {
    await deleteAction()
    showDeleteModal.value = false
  } catch (e: any) {
    deleteError.value = formatApiError(e, '删除失败')
  } finally {
    deleting.value = false
  }
}

// ---- Data Fetching ----
async function fetchRoutes() {
  try {
    const data = await api<any>('/api/page-perms/routes/?all=true')
    routes.value = data.results || data || []
  } catch (e) {
    console.error('Failed to load routes:', e)
  }
}

async function fetchPermissions() {
  try {
    const data = await api<any>('/api/page-perms/permissions/')
    allPermissions.value = Array.isArray(data) ? data : data.results || []
  } catch (e) {
    console.error('Failed to load permissions:', e)
  }
}

async function fetchGroups() {
  try {
    const data = await api<any>('/api/page-perms/groups/')
    const rawGroups = Array.isArray(data) ? data : data.results || []
    groups.value = rawGroups.map((g: any) => ({
      ...g,
      _selectedPerms: new Set(g.permissions || []),
    }))
  } catch (e) {
    console.error('Failed to load groups:', e)
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

onMounted(async () => {
  if (!isSuperuser.value) {
    loading.value = false
    return
  }
  try {
    await Promise.all([fetchRoutes(), fetchPermissions(), fetchGroups()])
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
.form-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
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
