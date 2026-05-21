<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">用户管理</h1>
      <UButton icon="i-heroicons-plus" size="sm" @click="openCreateModal">新建用户</UButton>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
      <UTable :data="users" :columns="columns" :ui="{ th: 'text-xs', td: 'text-sm' }">
        <template #username-cell="{ row }">
          <NuxtLink :to="`/app/users/${row.original.id}`" class="text-crystal-500 dark:text-crystal-400 hover:text-crystal-700 dark:hover:text-crystal-300 font-medium flex items-center gap-2">
            <img v-if="row.original.avatar" :src="resolveAvatarUrl(row.original.avatar)" class="w-6 h-6 rounded-full" />
            {{ row.original.username }}
          </NuxtLink>
        </template>
        <template #is_active-cell="{ row }">
          <UBadge :color="row.original.is_active ? 'success' : 'warning'" variant="subtle" size="xs">
            {{ row.original.is_active ? '已激活' : '待审批' }}
          </UBadge>
        </template>
        <template #groups-cell="{ row }">
          <div class="flex gap-1 flex-wrap">
            <UBadge v-for="g in row.original.groups" :key="g" color="neutral" variant="subtle" size="xs">{{ g }}</UBadge>
            <span v-if="!row.original.groups?.length" class="text-gray-300 dark:text-gray-600">-</span>
          </div>
        </template>
        <template #date_joined-cell="{ row }">
          {{ row.original.date_joined?.slice(0, 10) || '-' }}
        </template>
      </UTable>
      <div class="flex items-center justify-between px-4 py-3 border-t border-gray-50 dark:border-gray-800">
        <span class="text-xs text-gray-400 dark:text-gray-500">共 {{ users.length }} 位用户</span>
      </div>
    </div>

    <!-- Create User Modal -->
    <UModal v-model:open="showCreateModal" title="新建用户" :ui="{ width: 'sm:max-w-md' }">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>新建用户</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showCreateModal = false" />
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label>用户名 <span class="text-red-400">*</span></label>
              <UInput v-model="form.username" placeholder="输入用户名" />
            </div>
            <div class="form-row">
              <label>密码 <span class="text-red-400">*</span></label>
              <UInput v-model="form.password" type="password" placeholder="输入初始密码" />
            </div>
            <div class="form-row">
              <label>昵称</label>
              <UInput v-model="form.name" placeholder="可选" />
            </div>
            <div class="form-row">
              <label>邮箱</label>
              <UInput v-model="form.email" placeholder="可选" />
            </div>
            <div class="form-row">
              <label>用户组</label>
              <USelect
                v-model="form.groups"
                :items="groupOptions"
                multiple
                placeholder="选择用户组（可多选）"
              />
            </div>
            <div class="form-row">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="form.is_active" type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                <span>立即激活</span>
              </label>
            </div>
            <p v-if="createError" class="text-sm text-red-500">{{ createError }}</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="showCreateModal = false">取消</UButton>
            <UButton :loading="creating" @click="handleCreate">创建</UButton>
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

const loading = ref(true)
const users = ref<any[]>([])
const availableGroups = ref<string[]>([])

const columns = [
  { accessorKey: 'username', header: '用户名' },
  { accessorKey: 'name', header: '昵称' },
  { accessorKey: 'email', header: '邮箱' },
  { accessorKey: 'is_active', header: '状态' },
  { accessorKey: 'groups', header: '用户组' },
  { accessorKey: 'date_joined', header: '注册时间' },
]

const groupOptions = computed(() => availableGroups.value.map(g => ({ label: g, value: g })))

// ---- Create User ----
const showCreateModal = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({ username: '', password: '', name: '', email: '', groups: [] as string[], is_active: true })

function openCreateModal() {
  form.value = { username: '', password: '', name: '', email: '', groups: [], is_active: true }
  createError.value = ''
  showCreateModal.value = true
}

async function handleCreate() {
  if (!form.value.username.trim() || !form.value.password.trim()) {
    createError.value = '用户名和密码不能为空'
    return
  }
  creating.value = true
  createError.value = ''
  try {
    const newUser = await api<any>('/api/users/', {
      method: 'POST',
      body: {
        username: form.value.username.trim(),
        password: form.value.password,
        name: form.value.name.trim(),
        email: form.value.email.trim(),
        groups: form.value.groups,
        is_active: form.value.is_active,
      },
    })
    users.value.unshift(newUser)
    showCreateModal.value = false
  } catch (e: any) {
    const data = e?.data || e?.response?._data
    if (data && typeof data === 'object') {
      const msgs = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('; ')
      createError.value = msgs || '创建失败'
    } else {
      createError.value = e?.message || '创建失败，请重试'
    }
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  // 用 allSettled 避免 groups 接口对非超管返回 403 时把 users 列表也带挂
  const [usersResult, groupsResult] = await Promise.allSettled([
    api<any>('/api/users/'),
    api<any>('/api/page-perms/groups/'),
  ])
  if (usersResult.status === 'fulfilled') {
    const data = usersResult.value
    users.value = Array.isArray(data) ? data : data.results || []
  } else {
    console.error('Failed to load users:', usersResult.reason)
  }
  if (groupsResult.status === 'fulfilled') {
    const data = groupsResult.value
    const groups = Array.isArray(data) ? data : data.results || []
    availableGroups.value = groups.map((g: any) => g.name)
  }
  loading.value = false
})
</script>

<style scoped>
.modal-form { padding: 1.5rem 2rem; }
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
:root.dark .modal-header h3 { color: #f3f4f6; }
.modal-body { display: flex; flex-direction: column; gap: 1rem; }
.form-row { display: flex; flex-direction: column; gap: 0.375rem; }
.form-row label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: #374151;
}
:root.dark .form-row label { color: #9ca3af; }
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #f3f4f6;
}
:root.dark .modal-footer { border-top-color: #374151; }
</style>
