<script setup lang="ts">
definePageMeta({ layout: 'default' })

interface BulletinRow {
  id: number
  category: 'quote' | 'prompt' | 'pitfall' | 'value' | 'announcement'
  content: string
  source: string
  link_url: string
  is_active: boolean
  sort_order: number
  starts_at: string | null
  ends_at: string | null
  created_by_name: string | null
  created_at: string
  updated_at: string
}

const { api } = useApi()
const toast = useToast()

const loading = ref(false)
const saving = ref(false)
const rows = ref<BulletinRow[]>([])
const total = ref(0)
const page = ref(1)

const CATEGORY_OPTIONS = [
  { label: '编程大神名言', value: 'quote' },
  { label: '最新最火提示词', value: 'prompt' },
  { label: '最新避坑指南', value: 'pitfall' },
  { label: '公司价值观', value: 'value' },
  { label: '重大提醒公告', value: 'announcement' },
]
const categoryLabel = (v: string) => CATEGORY_OPTIONS.find(o => o.value === v)?.label ?? v

const columns = [
  { accessorKey: 'category', header: '分类' },
  { accessorKey: 'content', header: '内容' },
  { accessorKey: 'is_active', header: '启用' },
  { accessorKey: 'sort_order', header: '排序' },
  { accessorKey: 'actions', header: '操作' },
]

const showModal = ref(false)
const editingId = ref<number | null>(null)
const form = ref<{ category: string; content: string; source: string; link_url: string; is_active: boolean; sort_order: number }>({
  category: 'quote', content: '', source: '', link_url: '', is_active: true, sort_order: 0,
})

function openCreate() {
  editingId.value = null
  form.value = { category: 'quote', content: '', source: '', link_url: '', is_active: true, sort_order: 0 }
  showModal.value = true
}

function openEdit(row: BulletinRow) {
  editingId.value = row.id
  form.value = {
    category: row.category, content: row.content, source: row.source,
    link_url: row.link_url, is_active: row.is_active, sort_order: row.sort_order,
  }
  showModal.value = true
}

async function fetchRows() {
  loading.value = true
  try {
    const res = await api<any>(`/api/notifications/bulletins/manage/?page=${page.value}`)
    rows.value = res.results
    total.value = res.count
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.content.trim()) {
    toast.add({ title: '内容不能为空', color: 'error' })
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api(`/api/notifications/bulletins/manage/${editingId.value}/`, { method: 'PATCH', body: form.value })
    } else {
      await api('/api/notifications/bulletins/manage/', { method: 'POST', body: form.value })
    }
    showModal.value = false
    toast.add({ title: '已保存', color: 'success' })
    await fetchRows()
  } catch {
    toast.add({ title: '保存失败', color: 'error' })
  } finally {
    saving.value = false
  }
}

async function remove(row: BulletinRow) {
  if (!confirm(`确定删除该条「${categoryLabel(row.category)}」？`)) return
  try {
    await api(`/api/notifications/bulletins/manage/${row.id}/`, { method: 'DELETE' })
    toast.add({ title: '已删除', color: 'success' })
    await fetchRows()
  } catch {
    toast.add({ title: '删除失败', color: 'error' })
  }
}

watch(page, fetchRows)
onMounted(fetchRows)
</script>

<template>
  <div class="p-6 space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold">走马灯管理</h1>
      <UButton icon="i-heroicons-plus" @click="openCreate">新建</UButton>
    </div>

    <UTable :data="rows" :columns="columns" :loading="loading" :ui="{ th: 'text-xs', td: 'text-sm' }">
      <template #category-cell="{ row }">
        <UBadge variant="subtle">{{ categoryLabel(row.original.category) }}</UBadge>
      </template>
      <template #content-cell="{ row }">
        <span class="line-clamp-1 max-w-md">{{ row.original.content }}</span>
      </template>
      <template #is_active-cell="{ row }">
        <UBadge :color="row.original.is_active ? 'success' : 'neutral'" variant="subtle">
          {{ row.original.is_active ? '启用' : '停用' }}
        </UBadge>
      </template>
      <template #actions-cell="{ row }">
        <div class="flex gap-2">
          <UButton size="xs" variant="ghost" icon="i-heroicons-pencil-square" @click="openEdit(row.original)" />
          <UButton size="xs" variant="ghost" color="error" icon="i-heroicons-trash" @click="remove(row.original)" />
        </div>
      </template>
    </UTable>

    <div v-if="total > 20" class="flex justify-center">
      <UPagination v-model="page" :total="total" :items-per-page="20" @update:model-value="fetchRows" />
    </div>

    <UModal v-model:open="showModal" :title="editingId ? '编辑' : '新建'" :ui="{ content: 'sm:max-w-lg' }">
      <template #content>
        <div class="p-5 space-y-4">
          <div>
            <label class="block text-sm text-gray-500 mb-1">分类</label>
            <USelect v-model="form.category" :items="CATEGORY_OPTIONS" value-key="value" class="w-full" />
          </div>
          <div>
            <label class="block text-sm text-gray-500 mb-1">内容</label>
            <UTextarea v-model="form.content" :rows="3" class="w-full" placeholder="提示语 / 公告内容" />
          </div>
          <div>
            <label class="block text-sm text-gray-500 mb-1">出处（可选）</label>
            <UInput v-model="form.source" class="w-full" placeholder="如：Linus Torvalds" />
          </div>
          <div>
            <label class="block text-sm text-gray-500 mb-1">链接（可选）</label>
            <UInput v-model="form.link_url" class="w-full" placeholder="https://..." />
          </div>
          <div class="flex items-center gap-4">
            <label class="flex items-center gap-2 text-sm">
              <USwitch v-model="form.is_active" /> 启用
            </label>
            <label class="flex items-center gap-2 text-sm">
              排序 <UInput v-model.number="form.sort_order" type="number" class="w-20" />
            </label>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <UButton variant="outline" @click="showModal = false">取消</UButton>
            <UButton :loading="saving" @click="save">保存</UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>
