<template>
  <UModal v-model:open="isOpen" :title="title">
    <template #body>
      <div class="space-y-4">
        <UFormField label="监控名称" required>
          <UInput v-model="form.name" placeholder="例如：api-prod" />
        </UFormField>
        <UFormField label="URL" required>
          <UInput v-model="form.url" placeholder="https://example.com/health" />
        </UFormField>
        <UFormField label="期望状态码" hint="单个或逗号分隔,例如 200 或 200,204">
          <UInput v-model="form.expected_status" placeholder="200" />
        </UFormField>
        <UFormField label="期望响应体关键字" hint="留空表示不校验响应体">
          <UInput v-model="form.expected_body" placeholder="healthy" />
        </UFormField>
        <UFormField label="检查间隔">
          <USelect v-model="form.interval_minutes" :items="intervalOptions" value-key="value" />
        </UFormField>
        <UFormField label="超时(秒)">
          <UInput v-model.number="form.timeout_secs" type="number" :min="1" :max="60" />
        </UFormField>
        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" @click="isOpen = false">取消</UButton>
        <UButton :loading="submitting" @click="submit">{{ isEdit ? '保存' : '创建' }}</UButton>
      </div>
    </template>
  </UModal>
</template>

<script setup lang="ts">
interface MonitorPayload {
  id?: number
  name: string
  url: string
  method: string
  expected_status: string
  expected_body: string
  interval_minutes: number
  timeout_secs: number
  is_enabled: boolean
}

const props = defineProps<{
  open: boolean
  projectId: number
  initial?: MonitorPayload | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  saved: []
}>()

const { api } = useApi()

const isOpen = computed({
  get: () => props.open,
  set: (v: boolean) => emit('update:open', v),
})

const isEdit = computed(() => Boolean(props.initial?.id))
const title = computed(() => isEdit.value ? '编辑监控' : '添加监控')

const intervalOptions = [
  { label: '每 1 分钟', value: 1 },
  { label: '每 5 分钟', value: 5 },
  { label: '每 10 分钟', value: 10 },
  { label: '每 30 分钟', value: 30 },
  { label: '每 60 分钟', value: 60 },
]

const form = reactive<MonitorPayload>({
  name: '',
  url: '',
  method: 'GET',
  expected_status: '200',
  expected_body: '',
  interval_minutes: 1,
  timeout_secs: 20,
  is_enabled: true,
})

const submitting = ref(false)
const error = ref('')

watch(() => props.open, (open) => {
  if (open) {
    error.value = ''
    if (props.initial) {
      Object.assign(form, props.initial)
    } else {
      Object.assign(form, {
        name: '', url: '', method: 'GET', expected_status: '200',
        expected_body: '', interval_minutes: 1, timeout_secs: 20, is_enabled: true,
      })
    }
  }
})

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    if (isEdit.value) {
      await api(`/api/uptime/monitors/${props.initial!.id}/`, { method: 'PATCH', body: form })
    } else {
      await api(`/api/projects/${props.projectId}/monitors/`, { method: 'POST', body: form })
    }
    emit('saved')
    isOpen.value = false
  } catch (e: any) {
    error.value = e?.data ? JSON.stringify(e.data) : (e?.message ?? '保存失败')
  } finally {
    submitting.value = false
  }
}
</script>
