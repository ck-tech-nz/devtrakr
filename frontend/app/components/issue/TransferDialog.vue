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
  selfUserId: number
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'transferred'): void
}>()

const { api } = useApi()
const { transfer } = useIssueActions()

const members = ref<ProjectMember[]>([])
const selectedUserId = ref<number | undefined>(undefined)
const reason = ref('')
const submitting = ref(false)
const error = ref('')

async function loadMembers() {
  try {
    const data = await api<ProjectMember[]>(`/api/projects/${props.projectId}/members/`)
    members.value = data.filter(m => m.user_id !== props.selfUserId)
  } catch (e) {
    error.value = '加载成员失败'
  }
}

watch(() => props.modelValue, (v) => {
  if (v) {
    selectedUserId.value = undefined
    reason.value = ''
    error.value = ''
    loadMembers()
  }
})

const canSubmit = computed(() =>
  selectedUserId.value !== undefined && reason.value.trim().length > 0 && !submitting.value,
)

async function onSubmit() {
  if (!canSubmit.value || selectedUserId.value === undefined) return
  submitting.value = true
  error.value = ''
  try {
    await transfer(props.issueId, selectedUserId.value, reason.value.trim())
    emit('transferred')
    emit('update:modelValue', false)
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || '转单失败'
  } finally {
    submitting.value = false
  }
}

const userOptions = computed(() =>
  members.value.map(m => ({
    label: m.role ? `${m.user_name} · ${m.role}` : m.user_name,
    value: m.user_id,
  })),
)
</script>

<template>
  <UModal :open="modelValue" @update:open="emit('update:modelValue', $event)" title="转单">
    <template #body>
      <div class="space-y-4">
        <div>
          <label class="block text-sm mb-1">转给谁</label>
          <USelect
            v-model="selectedUserId"
            :items="userOptions"
            value-key="value"
            placeholder="选择项目成员"
          />
        </div>
        <div>
          <label class="block text-sm mb-1">转单原因 <span class="text-red-500">*</span></label>
          <UTextarea
            v-model="reason"
            placeholder="为什么把这个 issue 转给这位同事"
            :rows="3"
            :maxlength="500"
          />
        </div>
        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" @click="emit('update:modelValue', false)">取消</UButton>
        <UButton color="primary" :loading="submitting" :disabled="!canSubmit" @click="onSubmit">
          确定转单
        </UButton>
      </div>
    </template>
  </UModal>
</template>
