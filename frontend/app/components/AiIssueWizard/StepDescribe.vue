<template>
  <div class="step-describe">
    <div class="input-wrap">
      <!-- 附件预览行 -->
      <div v-if="attachments.length" class="attach-row">
        <div v-for="att in attachments" :key="att.id" class="attach-chip">
          <UIcon :name="isImage(att.file_name) ? 'i-heroicons-photo' : 'i-heroicons-document'" class="w-3.5 h-3.5" />
          <span class="attach-name">{{ att.file_name }}</span>
          <button class="attach-remove" @click="removeAttachment(att.id)">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </div>
      </div>

      <UTextarea
        v-model="description"
        :rows="3"
        placeholder="描述你发现的问题：在哪个页面、做了什么操作、出现了什么现象？"
        autoresize
        variant="none"
        @paste="onPaste"
        @drop.prevent="onDrop"
        @dragover.prevent
      />

      <!-- 隐藏文件输入 -->
      <input
        ref="fileInputRef"
        type="file"
        multiple
        accept="image/*,.pdf,.txt,.md,.log,.zip"
        style="display:none"
        @change="onFileSelect"
      />
      <input
        ref="imgInputRef"
        type="file"
        multiple
        accept="image/*"
        style="display:none"
        @change="onFileSelect"
      />

      <div class="toolbar">
        <UButton
          size="xs"
          variant="ghost"
          color="neutral"
          icon="i-heroicons-plus"
          title="添加附件"
          @click="fileInputRef?.click()"
        />
        <UButton
          size="xs"
          variant="ghost"
          color="neutral"
          icon="i-heroicons-photo"
          title="添加图片"
          @click="imgInputRef?.click()"
        />
        <USelect
          v-model="projectId"
          :items="projectOptions"
          value-key="value"
          size="xs"
          icon="i-heroicons-folder"
          placeholder="选择项目"
          class="project-chip"
        />
        <div class="toolbar-spacer" />
        <UButton
          icon="i-heroicons-arrow-up"
          color="primary"
          size="sm"
          :disabled="!canAnalyze"
          class="send-btn"
          title="AI 分析"
          @click="onAnalyze"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
type Project = { id: string; name: string }
type AttachmentRef = { id: string; file_name: string; file_url: string }

const props = defineProps<{
  projects: Project[]
  defaultProjectId: string | null
}>()

const emit = defineEmits<{
  analyze: [payload: { description: string; project: string; attachment_ids: string[] }]
}>()

const { api } = useApi()

const description = ref('')
const projectId = ref<string>(props.defaultProjectId ?? '')
const fileInputRef = ref<HTMLInputElement | null>(null)
const imgInputRef = ref<HTMLInputElement | null>(null)
const attachments = ref<AttachmentRef[]>([])

const projectOptions = computed(() =>
  props.projects.map(p => ({ label: p.name, value: String(p.id) })),
)

const canAnalyze = computed(() => description.value.trim().length >= 5 && !!projectId.value)

function isImage(name: string): boolean {
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(name || '')
}

async function uploadFile(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await api<{ url: string; filename: string; id: string }>('/api/tools/upload/image/', {
      method: 'POST',
      body: fd,
    })
    attachments.value.push({ id: res.id, file_name: res.filename, file_url: res.url })
  } catch (e) {
    console.error('upload failed', e)
  }
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  for (const f of files) uploadFile(f)
  input.value = '' // 允许重复选择同一个文件
}

function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items || []
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) uploadFile(file)
    }
  }
}

function onDrop(e: DragEvent) {
  const files = Array.from(e.dataTransfer?.files || [])
  for (const f of files) uploadFile(f)
}

function removeAttachment(id: string) {
  attachments.value = attachments.value.filter(a => a.id !== id)
}

function onAnalyze() {
  if (!canAnalyze.value) return
  emit('analyze', {
    description: description.value.trim(),
    project: projectId.value,
    attachment_ids: attachments.value.map(a => a.id),
  })
}

watch(() => props.defaultProjectId, (v) => {
  if (v && !projectId.value) projectId.value = v
})
</script>

<style scoped>
.step-describe { display: flex; flex-direction: column; gap: 1rem; }

.input-wrap {
  display: flex; flex-direction: column;
  border: 1px solid #e5e7eb;
  border-radius: 1rem;
  padding: 0.75rem 1rem;
  background-color: #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
:root.dark .input-wrap { border-color: #374151; background-color: #1f2937; }

.toolbar { display: flex; align-items: center; gap: 0.5rem; padding-top: 0.5rem; }
.toolbar-spacer { flex: 1; }
.project-chip :deep(button) {
  font-size: 0.75rem;
  background-color: #f9fafb;
  border-color: #e5e7eb;
}
:root.dark .project-chip :deep(button) {
  background-color: #111827;
  border-color: #374151;
}
.send-btn { border-radius: 9999px !important; }

.attach-row {
  display: flex; flex-wrap: wrap; gap: 0.375rem;
  padding-bottom: 0.5rem;
}
.attach-chip {
  display: inline-flex; align-items: center; gap: 0.375rem;
  padding: 0.25rem 0.5rem 0.25rem 0.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  background-color: #f9fafb;
  font-size: 0.75rem;
  color: #4b5563;
  max-width: 16rem;
}
:root.dark .attach-chip { background-color: #1f2937; border-color: #374151; color: #d1d5db; }
.attach-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 12rem;
}
.attach-remove {
  display: flex; align-items: center; justify-content: center;
  width: 1rem; height: 1rem; border-radius: 9999px;
  background-color: transparent; border: 0; cursor: pointer;
  color: #9ca3af;
}
.attach-remove:hover { background-color: #e5e7eb; color: #374151; }
:root.dark .attach-remove:hover { background-color: #374151; color: #d1d5db; }
</style>
</content>
</invoke>