<script setup lang="ts">
import { useIssueActions } from '~/composables/useIssueActions'

interface ProjectMember {
  user_id: number
  user_name: string
  role?: string | null
}

const props = defineProps<{
  modelValue: boolean
  issueId: number
  projectId: number
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'assigned'): void
}>()

const { api } = useApi()
const { assignTo } = useIssueActions()

const members = ref<ProjectMember[]>([])
const selectedUserId = ref<number | undefined>(undefined)
const submitting = ref(false)
const error = ref('')

async function loadMembers() {
  try {
    members.value = await api<ProjectMember[]>(`/api/projects/${props.projectId}/members/`)
  } catch (e) {
    error.value = '加载成员失败'
  }
}

watch(() => props.modelValue, (v) => {
  if (v) {
    selectedUserId.value = undefined
    error.value = ''
    loadMembers()
  }
})

const userOptions = computed(() =>
  members.value.map(m => ({
    label: m.role ? `${m.user_name} · ${m.role}` : m.user_name,
    value: m.user_id,
  })),
)

async function onSubmit() {
  if (selectedUserId.value === undefined) return
  submitting.value = true
  error.value = ''
  try {
    await assignTo(props.issueId, selectedUserId.value)
    emit('assigned')
    emit('update:modelValue', false)
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || '指派失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UModal :open="modelValue" @update:open="emit('update:modelValue', $event)" title="指派给">
    <template #body>
      <div class="space-y-4">
        <USelect
          v-model="selectedUserId"
          :items="userOptions"
          value-key="value"
          placeholder="选择项目成员"
        />
        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" @click="emit('update:modelValue', false)">取消</UButton>
        <UButton color="primary" :loading="submitting" :disabled="selectedUserId === undefined" @click="onSubmit">
          指派
        </UButton>
      </div>
    </template>
  </UModal>
</template>
