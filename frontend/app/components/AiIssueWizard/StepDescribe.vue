<template>
  <div class="step-describe">
    <div class="input-wrap" :class="{ 'input-wrap--busy': analyzing }">
      <!-- 附件预览行 (composer 编辑态; analyzing 时附件已上移到 thread) -->
      <div v-if="attachments.length && !analyzing" class="attach-row">
        <div v-for="att in attachments" :key="att.id" class="attach-chip" :class="{ 'attach-chip--image': isImage(att.file_name) }">
          <button
            v-if="isImage(att.file_name)"
            type="button"
            class="attach-thumb"
            :title="`预览 ${att.file_name}`"
            @click="openPreview(att)"
          >
            <img :src="att.file_url" :alt="att.file_name" />
          </button>
          <UIcon v-else name="i-heroicons-document" class="w-3.5 h-3.5 attach-icon" />
          <span v-if="!isImage(att.file_name)" class="attach-name">{{ att.file_name }}</span>
          <button class="attach-remove" :title="`移除 ${att.file_name}`" @click="removeAttachment(att.id)">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </div>
      </div>

      <!-- 图片预览弹窗 -->
      <UModal v-model:open="previewOpen" :ui="{ content: 'sm:max-w-4xl' }">
        <template #content>
          <div class="preview-modal">
            <div class="preview-header">
              <span class="preview-title" :title="previewAttachment?.file_name">{{ previewAttachment?.file_name }}</span>
              <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="previewOpen = false" />
            </div>
            <div class="preview-body" @click.self="previewOpen = false">
              <img v-if="previewAttachment" :src="previewAttachment.file_url" :alt="previewAttachment.file_name" />
            </div>
          </div>
        </template>
      </UModal>

      <UTextarea
        v-model="description"
        :rows="3"
        :placeholder="placeholderText"
        autoresize
        variant="none"
        :disabled="analyzing"
        @paste="onPaste"
        @drop.prevent="onDrop"
        @dragover.prevent
        @keydown="onKeydown"
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
          :disabled="analyzing"
          @click="fileInputRef?.click()"
        />
        <UButton
          size="xs"
          variant="ghost"
          color="neutral"
          icon="i-heroicons-photo"
          title="添加图片"
          :disabled="analyzing"
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
          :disabled="analyzing"
        />
        <div class="toolbar-spacer" />
        <span v-if="!analyzing && validationHint" class="send-hint send-hint--warn">{{ validationHint }}</span>
        <div
          v-if="!analyzing"
          class="send-mode-toggle"
          role="group"
          :aria-label="sendModeTitle"
          :title="sendModeTitle"
        >
          <span class="send-mode-thumb" :class="{ 'send-mode-thumb--right': sendMode === 'modifier' }" aria-hidden="true" />
          <button
            type="button"
            class="send-mode-opt"
            :class="{ 'send-mode-opt--active': sendMode === 'enter' }"
            :aria-pressed="sendMode === 'enter'"
            title="Enter 直接发送 · Shift+Enter 换行"
            @click="sendMode = 'enter'"
          >Enter</button>
          <button
            type="button"
            class="send-mode-opt"
            :class="{ 'send-mode-opt--active': sendMode === 'modifier' }"
            :aria-pressed="sendMode === 'modifier'"
            :title="`${isMac ? '⌘' : 'Ctrl'}+Enter 发送 · Enter 换行`"
            @click="sendMode = 'modifier'"
          >{{ isMac ? '⌘↵' : 'Ctrl↵' }}</button>
        </div>
        <UButton
          v-if="!analyzing"
          icon="i-heroicons-arrow-up"
          color="primary"
          size="sm"
          :disabled="!canAnalyze"
          class="send-btn"
          :title="validationHint || sendModeTitle || 'AI 分析'"
          @click="onAnalyze"
        />
        <button
          v-else
          type="button"
          class="stop-btn"
          title="取消"
          @click="emit('cancel')"
        >
          <span class="stop-square" aria-hidden="true" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
type Project = { id: string; name: string }
export type AttachmentRef = { id: string; file_name: string; file_url: string }

const props = defineProps<{
  projects: Project[]
  defaultProjectId: string | null
  analyzing?: boolean
  /** thread 内已有 draft 时, composer 进入"修订模式" - 改 placeholder/最短长度 */
  reviseMode?: boolean
  /** 最近一条 AI 反问待用户回答 - placeholder 变"回答 AI 的问题..." */
  askReplyMode?: boolean
  /** 父级可清空已编辑内容 */
  resetSignal?: number
}>()

const emit = defineEmits<{
  analyze: [payload: { description: string; project: string; attachments: AttachmentRef[] }]
  cancel: []
}>()

const { api } = useApi()

const description = ref('')
const projectId = ref<string>(props.defaultProjectId ?? '')
const fileInputRef = ref<HTMLInputElement | null>(null)
const imgInputRef = ref<HTMLInputElement | null>(null)
const attachments = ref<AttachmentRef[]>([])
const previewOpen = ref(false)
const previewAttachment = ref<AttachmentRef | null>(null)

function openPreview(att: AttachmentRef) {
  previewAttachment.value = att
  previewOpen.value = true
}

const projectOptions = computed(() =>
  props.projects.map(p => ({ label: p.name, value: String(p.id) })),
)

const MIN_DESC_LEN = 5
const MIN_REVISE_LEN = 2  // 修订指令 / 回答反问可以很短, 例如 "P0" / "prod"
const minLen = computed(() => (props.reviseMode || props.askReplyMode ? MIN_REVISE_LEN : MIN_DESC_LEN))
const trimmedLen = computed(() => description.value.trim().length)
const canAnalyze = computed(() => trimmedLen.value >= minLen.value && !!projectId.value && !props.analyzing)

const placeholderText = computed(() => {
  if (props.analyzing) return 'AI 正在思考，可点击 ■ 取消…'
  if (props.askReplyMode) return '回答 AI 刚才的问题…'
  if (props.reviseMode) return '告诉 AI 怎么改这份草稿，例如「复现步骤加一条 xxx」「优先级提到 P0」「OK 提交」'
  return '描述问题：哪个页面/角色，做了什么，看到什么。可以贴截图——AI 会读取截图内容。'
})

const isMac = computed(() => {
  if (typeof navigator === 'undefined') return false
  return /Mac|iPhone|iPad|iPod/.test(navigator.platform)
})

// 发送键模式: 'enter' = 直接 Enter 发送, Shift+Enter 换行 / 'modifier' = ⌘/Ctrl+Enter 发送, Enter 换行.
// 默认 modifier (跟历史行为一致, 不会让长按 Enter 的老用户突然误发)
type SendMode = 'enter' | 'modifier'
const SEND_MODE_KEY = 'ai-wizard:send-mode'
function readSendMode(): SendMode {
  if (typeof localStorage === 'undefined') return 'modifier'
  return localStorage.getItem(SEND_MODE_KEY) === 'enter' ? 'enter' : 'modifier'
}
const sendMode = ref<SendMode>(readSendMode())
watch(sendMode, (v) => {
  if (typeof localStorage !== 'undefined') {
    try { localStorage.setItem(SEND_MODE_KEY, v) } catch {}
  }
})

const sendModeTitle = computed(() =>
  sendMode.value === 'enter'
    ? `Enter 发送 · Shift+Enter 换行 (${isMac.value ? '⌘' : 'Ctrl'}+Enter 也可发送)`
    : `${isMac.value ? '⌘' : 'Ctrl'}+Enter 发送 · Enter 换行`,
)

// 只用于显示"为什么按了没反应" - 不再重复显示快捷键提示 (toggle 已表达)
const validationHint = computed(() => {
  if (trimmedLen.value > 0 && trimmedLen.value < minLen.value) {
    return `至少 ${minLen.value} 个字（当前 ${trimmedLen.value}）`
  }
  if (trimmedLen.value >= minLen.value && !projectId.value) return '请选择项目'
  return ''
})

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
  input.value = ''
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
  const sent = {
    description: description.value.trim(),
    project: projectId.value,
    attachments: [...attachments.value],
  }
  // 视觉清空: 父级会在 thread 中显示快照
  description.value = ''
  attachments.value = []
  emit('analyze', sent)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key !== 'Enter') return
  // ⌘/Ctrl+Enter 永远发送 (即便在 'enter' 模式下也是) - 给重度用户一个稳定的快捷键
  if (e.metaKey || e.ctrlKey) {
    e.preventDefault()
    onAnalyze()
    return
  }
  // 'enter' 模式: 裸 Enter 发送, Shift+Enter 走默认换行行为
  if (sendMode.value === 'enter' && !e.shiftKey && !e.altKey) {
    e.preventDefault()
    onAnalyze()
  }
}

watch(() => props.defaultProjectId, (v) => {
  if (v && !projectId.value) projectId.value = v
})

// 父级触发"重新描述"时, 把 thread 里的快照写回 composer 由父级直接 setText/setAttachments 暴露接口
defineExpose({
  setText(text: string) { description.value = text },
  setAttachments(list: AttachmentRef[]) { attachments.value = [...list] },
})
</script>

<style scoped>
.step-describe { display: flex; flex-direction: column; }

.input-wrap {
  display: flex; flex-direction: column;
  border: 1px solid #e5e7eb;
  border-radius: 1rem;
  padding: 0.75rem 1rem;
  background-color: #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: opacity 0.2s ease, border-color 0.2s ease;
}
:root.dark .input-wrap { border-color: #374151; background-color: #1f2937; }
.input-wrap--busy { opacity: 0.7; }

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
.send-hint {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-right: 0.25rem;
  user-select: none;
}
:root.dark .send-hint { color: #6b7280; }
/* 校验提示 (字数不够 / 没选项目) - 暖色, 比快捷键提示更"招手" */
.send-hint--warn { color: #d97706; }
:root.dark .send-hint--warn { color: #fbbf24; }

/* ---------- 发送模式 toggle (Enter vs ⌘/Ctrl+Enter) ----------
   分段开关, 滑块在两个选项间平移; 状态持久化在 localStorage */
.send-mode-toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  padding: 0.1875rem;
  background-color: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 9999px;
  margin-right: 0.375rem;
  user-select: none;
  /* 防止 thumb 溢出圆角 */
  overflow: hidden;
}
:root.dark .send-mode-toggle {
  background-color: #111827;
  border-color: #374151;
}
.send-mode-thumb {
  position: absolute;
  top: 0.1875rem;
  left: 0.1875rem;
  width: calc(50% - 0.1875rem);
  height: calc(100% - 0.375rem);
  background-color: #ffffff;
  border-radius: 9999px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12), 0 0 0 1px rgba(15, 23, 42, 0.04);
  transition: transform 0.22s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 0;
}
.send-mode-thumb--right { transform: translateX(100%); }
:root.dark .send-mode-thumb {
  background-color: #374151;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.04);
}
.send-mode-opt {
  position: relative;
  z-index: 1;
  padding: 0.1875rem 0.5625rem;
  min-width: 2.625rem;
  border: 0;
  background: transparent;
  font-size: 0.6875rem;
  line-height: 1;
  color: #9ca3af;
  cursor: pointer;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: 0.01em;
  transition: color 0.18s ease;
}
.send-mode-opt:hover { color: #4b5563; }
.send-mode-opt--active {
  color: #111827;
  font-weight: 600;
}
:root.dark .send-mode-opt { color: #6b7280; }
:root.dark .send-mode-opt:hover { color: #d1d5db; }
:root.dark .send-mode-opt--active { color: #f3f4f6; }

.stop-btn {
  width: 1.875rem; height: 1.875rem;
  border-radius: 9999px;
  border: 0;
  background-color: #111827;
  color: #ffffff;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: background-color 0.15s, transform 0.15s;
}
.stop-btn:hover { background-color: #000000; transform: scale(1.05); }
:root.dark .stop-btn { background-color: #f3f4f6; color: #111827; }
:root.dark .stop-btn:hover { background-color: #ffffff; }
.stop-square {
  width: 0.5625rem; height: 0.5625rem;
  background-color: currentColor;
  border-radius: 0.0625rem;
  display: block;
}

/* ---------- 附件 chip ---------- */
.attach-row {
  display: flex; flex-wrap: wrap; gap: 0.375rem;
  padding-bottom: 0.5rem;
}
.attach-chip {
  display: inline-flex; align-items: center; gap: 0.375rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  background-color: #f9fafb;
  font-size: 0.75rem;
  color: #4b5563;
  max-width: 16rem;
  position: relative;
}
:root.dark .attach-chip { background-color: #1f2937; border-color: #374151; color: #d1d5db; }

.attach-chip--image {
  padding: 0.125rem 0.25rem 0.125rem 0.125rem;
  gap: 0.25rem;
}

.attach-thumb {
  display: block;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: 0;
  border-radius: 0.375rem;
  overflow: hidden;
  flex-shrink: 0;
  cursor: zoom-in;
  background-color: #ffffff;
}
.attach-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
:root.dark .attach-thumb { background-color: #111827; }

.attach-icon { color: #6b7280; flex-shrink: 0; }
:root.dark .attach-icon { color: #9ca3af; }

.attach-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 12rem;
}

.attach-remove {
  display: flex; align-items: center; justify-content: center;
  width: 1rem; height: 1rem; border-radius: 9999px;
  background-color: transparent; border: 0; cursor: pointer;
  color: #9ca3af;
  flex-shrink: 0;
}
.attach-remove:hover { background-color: #e5e7eb; color: #374151; }
:root.dark .attach-remove:hover { background-color: #374151; color: #d1d5db; }

/* ---------- 图片预览弹窗 ---------- */
.preview-modal {
  display: flex; flex-direction: column;
  max-height: 85vh;
  background-color: #ffffff;
  border-radius: 0.75rem;
  overflow: hidden;
}
:root.dark .preview-modal { background-color: #1f2937; }
.preview-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #e5e7eb;
}
:root.dark .preview-header { border-bottom-color: #374151; }
.preview-title {
  font-size: 0.875rem; color: #374151;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
:root.dark .preview-title { color: #d1d5db; }
.preview-body {
  display: flex; align-items: center; justify-content: center;
  padding: 1rem;
  background-color: #f9fafb;
  overflow: auto;
  cursor: zoom-out;
}
:root.dark .preview-body { background-color: #111827; }
.preview-body img {
  max-width: 100%;
  max-height: calc(85vh - 4rem);
  object-fit: contain;
  cursor: default;
}
</style>
