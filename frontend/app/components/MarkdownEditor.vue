<template>
  <div
    class="markdown-editor border rounded-xl"
    :class="[
      isDragging ? 'border-primary-500 bg-primary-50 dark:bg-primary-950' : 'border-gray-200 dark:border-gray-700',
    ]"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="handleDrop"
  >
    <!-- Tab bar + toolbar -->
    <div class="flex items-center border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
      <button
        class="px-4 py-2 text-sm font-medium transition-colors"
        :class="mode === 'edit'
          ? 'text-gray-900 dark:text-gray-100 border-b-2 border-primary-500'
          : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'"
        @click="mode = 'edit'"
      >
        编辑
      </button>
      <button
        class="px-4 py-2 text-sm font-medium transition-colors"
        :class="mode === 'preview'
          ? 'text-gray-900 dark:text-gray-100 border-b-2 border-primary-500'
          : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'"
        @click="mode = 'preview'"
      >
        预览
      </button>

      <!-- Formatting toolbar -->
      <div v-show="mode === 'edit'" class="flex items-center gap-0.5 ml-auto pr-2">
        <button v-for="btn in toolbarButtons" :key="btn.title" :title="btn.title" class="toolbar-btn" @mousedown.prevent @click="btn.action">
          <UIcon :name="btn.icon" class="w-4 h-4" />
        </button>
        <span class="w-px h-4 bg-gray-300 dark:bg-gray-600 mx-1" />
        <button title="上传文件" class="toolbar-btn" @mousedown.prevent @click="triggerFileInput">
          <UIcon name="i-heroicons-paper-clip" class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Edit mode -->
    <div v-show="mode === 'edit'" class="relative">
      <textarea
        ref="textareaRef"
        :value="modelValue"
        :placeholder="placeholder"
        class="w-full p-4 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 resize-y outline-none"
        :style="{ minHeight: editorMinHeight }"
        @input="onTextareaInput"
        @keydown="handleMentionKeydown"
        @paste="handlePaste"
        @blur="emit('blur')"
      />
      <!-- Mention autocomplete -->
      <MentionDropdown
        ref="mentionRef"
        :visible="mentionVisible"
        :items="mentionItems"
        :position="mentionPosition"
        :type="mentionType"
        @select="insertMention"
      />
      <!-- Bottom bar -->
      <div class="flex items-center gap-2 px-4 py-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        <span class="text-xs text-gray-400 dark:text-gray-500">支持 Markdown 格式 · 粘贴、拖放或点击上传图片和文件</span>
        <input
          ref="fileInputRef"
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation,text/plain,text/markdown,text/csv,application/json,application/zip,application/x-zip-compressed,.md,.txt,.csv,.json,.zip"
          multiple
          class="hidden"
          @change="handleFileSelect"
        />
      </div>
    </div>

    <!-- Preview mode -->
    <div
      ref="previewRef"
      v-show="mode === 'preview'"
      class="markdown-body p-4 bg-white dark:bg-gray-900 text-sm"
      :style="{ minHeight: editorMinHeight }"
      v-html="renderedHtml"
    />
  </div>

  <!-- Hover preview for .md attachments -->
  <Teleport to="body">
    <div
      v-if="mdHover.visible"
      class="md-hover-preview"
      :style="{ top: mdHover.top + 'px', left: mdHover.left + 'px' }"
      @mouseenter="cancelHideMdPreview"
      @mouseleave="hideMdPreview"
    >
      <div class="md-hover-header">
        <span class="md-hover-title" :title="mdHover.filename">{{ mdHover.filename }}</span>
        <a
          class="md-hover-download"
          :href="mdHover.url"
          :download="mdHover.filename"
          target="_blank"
          rel="noopener noreferrer"
        >下载</a>
      </div>
      <div v-if="mdHover.loading" class="md-hover-loading">加载中...</div>
      <div v-else class="markdown-body md-hover-body" v-html="mdHover.content" />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import getCaretCoordinates from 'textarea-caret'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  defaultMode?: 'edit' | 'preview'
  minHeight?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'upload-complete': [attachment: { url: string; filename: string; id: string }]
  'blur': []
}>()

const { api } = useApi()
const toast = useToast()

const mode = ref<'edit' | 'preview'>(props.defaultMode || 'edit')
const editorMinHeight = computed(() => props.minHeight || '260px')
defineExpose({ setMode: (m: 'edit' | 'preview') => { mode.value = m } })
const isDragging = ref(false)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const mentionRef = ref<InstanceType<typeof MentionDropdown> | null>(null)
const mentionVisible = ref(false)
const mentionType = ref<'user' | 'issue'>('user')
const mentionItems = ref<{ id: number; label: string; prefix?: string }[]>([])
const mentionPosition = ref({ top: 0, left: 0 })
const mentionTriggerStart = ref(0)

let userCache: { id: number; name: string }[] | null = null

function detectMentionTrigger(): { type: 'user' | 'issue'; query: string; start: number } | null {
  const ta = textareaRef.value
  if (!ta) return null
  const text = props.modelValue || ''
  const cursor = ta.selectionStart
  const before = text.slice(0, cursor)

  const atMatch = before.match(/@([^\s@]*)$/)
  if (atMatch) {
    return { type: 'user', query: atMatch[1], start: cursor - atMatch[0].length }
  }

  const hashMatch = before.match(/#([^\s#]*)$/)
  if (hashMatch) {
    return { type: 'issue', query: hashMatch[1], start: cursor - hashMatch[0].length }
  }

  return null
}

async function fetchUserSuggestions(query: string) {
  if (!userCache) {
    userCache = await api<{ id: number; name: string }[]>('/api/users/choices/')
  }
  const q = query.toLowerCase()
  return userCache
    .filter(u => u.name.toLowerCase().includes(q))
    .map(u => ({ id: u.id, label: u.name }))
}

async function fetchIssueSuggestions(query: string) {
  if (!query) return []
  const data = await api<{ count: number; results: { id: number; title: string }[] }>(
    `/api/issues/?search=${encodeURIComponent(query)}&page_size=8`
  )
  return data.results.map(i => ({
    id: i.id,
    label: i.title,
    prefix: `#问题-${String(i.id).padStart(3, '0')}`,
  }))
}

function updateMentionPosition() {
  const ta = textareaRef.value
  if (!ta) return
  const coords = getCaretCoordinates(ta, ta.selectionStart)
  mentionPosition.value = {
    top: coords.top + coords.height + 4 - ta.scrollTop,
    left: coords.left,
  }
}

async function handleMentionInput() {
  const trigger = detectMentionTrigger()
  if (!trigger) {
    mentionVisible.value = false
    return
  }
  mentionType.value = trigger.type
  mentionTriggerStart.value = trigger.start
  updateMentionPosition()

  if (trigger.type === 'user') {
    mentionItems.value = await fetchUserSuggestions(trigger.query)
  } else {
    mentionItems.value = await fetchIssueSuggestions(trigger.query)
  }
  mentionVisible.value = mentionItems.value.length > 0
}

function insertMention(item: { id: number; label: string; prefix?: string }) {
  const ta = textareaRef.value
  if (!ta) return
  const cursor = ta.selectionStart
  let replacement: string
  if (mentionType.value === 'user') {
    replacement = `@[${item.label}](user:${item.id}) `
  } else {
    const prefix = item.prefix || `#问题-${String(item.id).padStart(3, '0')}`
    replacement = `#[${prefix}](issue:${item.id}) `
  }
  replaceRange(mentionTriggerStart.value, cursor, replacement)
  mentionVisible.value = false
}

function handleMentionKeydown(e: KeyboardEvent) {
  if (!mentionVisible.value) return
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    mentionRef.value?.moveUp()
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    mentionRef.value?.moveDown()
  } else if (e.key === 'Enter') {
    e.preventDefault()
    mentionRef.value?.confirmSelection()
  } else if (e.key === 'Escape') {
    mentionVisible.value = false
  }
}

function onTextareaInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
  nextTick(handleMentionInput)
}

const { md } = useMentionMarkdown()

const renderedHtml = computed(() => {
  if (!props.modelValue) return '<p class="text-gray-400 dark:text-gray-500">无内容</p>'
  // Replace native checkboxes with CSS-only spans (Tailwind preflight kills native checkbox appearance)
  return md.render(props.modelValue)
    .replace(/<input class="task-list-item-checkbox" checked=""type="checkbox">/g, '<span class="md-checkbox md-checked"></span>')
    .replace(/<input class="task-list-item-checkbox"type="checkbox">/g, '<span class="md-checkbox"></span>')
})

// --- .md hover preview ---

const previewRef = ref<HTMLElement | null>(null)
const mdHover = ref<{ visible: boolean; loading: boolean; content: string; top: number; left: number; url: string; filename: string }>({
  visible: false, loading: false, content: '', top: 0, left: 0, url: '', filename: '',
})
const mdCache = new Map<string, string>()
const MD_FETCH_CAP = 200 * 1024
let showTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

async function fetchMdContent(url: string): Promise<string> {
  if (mdCache.has(url)) return mdCache.get(url)!
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const reader = res.body?.getReader()
    if (!reader) {
      const text = await res.text()
      const capped = text.length > MD_FETCH_CAP ? text.slice(0, MD_FETCH_CAP) + '\n\n...(已截断)' : text
      mdCache.set(url, capped)
      return capped
    }
    const decoder = new TextDecoder()
    let received = ''
    while (received.length < MD_FETCH_CAP) {
      const { done, value } = await reader.read()
      if (done) break
      received += decoder.decode(value, { stream: true })
    }
    if (received.length >= MD_FETCH_CAP) received = received.slice(0, MD_FETCH_CAP) + '\n\n...(已截断)'
    mdCache.set(url, received)
    return received
  } catch {
    const fallback = '加载失败'
    mdCache.set(url, fallback)
    return fallback
  }
}

function showMdPreview(el: HTMLAnchorElement) {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
  if (showTimer) clearTimeout(showTimer)
  // Start prefetch immediately so the file is in cache by the time the
  // popup opens. Users who click-to-download within the 500ms delay
  // navigate before the popup ever appears (no wasted UI work).
  void fetchMdContent(el.href)
  showTimer = setTimeout(async () => {
    const rect = el.getBoundingClientRect()
    const popupHeight = Math.min(window.innerHeight * 0.7, 640)
    const popupWidth = Math.min(window.innerWidth - 32, 720)
    const wantBelow = rect.bottom + popupHeight + 8 < window.innerHeight
    const top = wantBelow
      ? rect.bottom + window.scrollY + 4
      : Math.max(8 + window.scrollY, rect.top + window.scrollY - popupHeight - 4)
    // Clamp left so the popup stays in the viewport
    const rawLeft = rect.left + window.scrollX
    const left = Math.min(rawLeft, window.scrollX + window.innerWidth - popupWidth - 16)
    const filename = el.getAttribute('download') || (el.textContent || '').trim() || el.href.split('/').pop() || 'file.md'
    mdHover.value = {
      visible: true,
      loading: true,
      content: '',
      top,
      left: Math.max(window.scrollX + 8, left),
      url: el.href,
      filename,
    }
    const text = await fetchMdContent(el.href)
    if (mdHover.value.visible) {
      mdHover.value.loading = false
      mdHover.value.content = md.render(text)
    }
  }, 500)
}

function hideMdPreview() {
  if (showTimer) { clearTimeout(showTimer); showTimer = null }
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    mdHover.value.visible = false
  }, 150)
}

function cancelHideMdPreview() {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
}

function attachMdHoverHandlers() {
  if (!previewRef.value) return
  const cards = previewRef.value.querySelectorAll<HTMLAnchorElement>('a.md-file-card.md-file-text')
  cards.forEach((card) => {
    if (!card.href.toLowerCase().endsWith('.md')) return
    if (card.dataset.mdHoverBound === '1') return
    card.dataset.mdHoverBound = '1'
    card.addEventListener('mouseenter', () => showMdPreview(card))
    card.addEventListener('mouseleave', hideMdPreview)
  })
}

function maybeAttachMdHoverHandlers() {
  if (mode.value !== 'preview') return
  nextTick(attachMdHoverHandlers)
}

// Attach on mount: covers the case where the component is created with
// mode=preview and modelValue already populated, so neither watch dep
// ever changes after setup.
onMounted(maybeAttachMdHoverHandlers)
watch([renderedHtml, mode], maybeAttachMdHoverHandlers, { flush: 'post' })

onBeforeUnmount(() => {
  if (showTimer) clearTimeout(showTimer)
  if (hideTimer) clearTimeout(hideTimer)
})

const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp'])
// Mirror this allowlist with backend/apps/tools/views.py (ALLOWED_TYPES + EXTENSION_FALLBACK).
const ALLOWED_TYPES = new Set([
  // Images
  'image/png', 'image/jpeg', 'image/gif', 'image/webp',
  // PDF
  'application/pdf',
  // Word
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  // Excel
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  // PowerPoint
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  // Text / data
  'text/plain', 'text/markdown', 'text/csv', 'application/json',
  // Archive
  'application/zip', 'application/x-zip-compressed',
])
const EXTENSION_FALLBACK = new Set(['md', 'txt', 'csv', 'json', 'zip'])
const MAX_IMAGE_SIZE = 5 * 1024 * 1024
const MAX_FILE_SIZE = 20 * 1024 * 1024

function isAllowed(file: File): boolean {
  if (ALLOWED_TYPES.has(file.type)) return true
  const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : ''
  return EXTENSION_FALLBACK.has(ext)
}

function isImage(file: File): boolean {
  return IMAGE_TYPES.has(file.type)
}

// Escape characters that would break out of markdown link text and let a
// user-controlled filename inject a different link target.
function escapeMdLinkText(s: string): string {
  return s.replace(/([\\\[\]])/g, '\\$1')
}

// --- Toolbar ---

const toolbarButtons = [
  { title: '标题', icon: 'i-heroicons-h1', action: () => prefixLines('### ') },
  { title: '粗体', icon: 'i-heroicons-bold', action: () => wrapSelection('**', '**') },
  { title: '斜体', icon: 'i-heroicons-italic', action: () => wrapSelection('_', '_') },
  { title: '引用', icon: 'i-heroicons-chat-bubble-bottom-center-text', action: () => prefixLines('> ') },
  { title: '代码', icon: 'i-heroicons-code-bracket', action: () => insertCode() },
  { title: '链接', icon: 'i-heroicons-link', action: () => insertLink() },
  { title: '无序列表', icon: 'i-heroicons-list-bullet', action: () => prefixLines('- ') },
  { title: '有序列表', icon: 'i-heroicons-numbered-list', action: () => prefixNumberedList() },
  { title: '任务列表', icon: 'i-heroicons-clipboard-document-check', action: () => prefixLines('- [ ] ') },
]

function getSelection(): { start: number; end: number; text: string } {
  const ta = textareaRef.value
  if (!ta) return { start: 0, end: 0, text: '' }
  return {
    start: ta.selectionStart,
    end: ta.selectionEnd,
    text: (props.modelValue || '').slice(ta.selectionStart, ta.selectionEnd),
  }
}

function replaceRange(start: number, end: number, text: string, cursorPos?: number) {
  const current = props.modelValue || ''
  const newValue = current.slice(0, start) + text + current.slice(end)
  emit('update:modelValue', newValue)
  const pos = cursorPos ?? (start + text.length)
  nextTick(() => {
    const ta = textareaRef.value
    if (ta) {
      ta.selectionStart = ta.selectionEnd = pos
      ta.focus()
    }
  })
}

function wrapSelection(before: string, after: string) {
  const sel = getSelection()
  if (sel.text) {
    replaceRange(sel.start, sel.end, before + sel.text + after, sel.start + before.length + sel.text.length + after.length)
  } else {
    const placeholder = before === '**' ? '粗体文本' : before === '_' ? '斜体文本' : '文本'
    replaceRange(sel.start, sel.end, before + placeholder + after, sel.start + before.length)
    nextTick(() => {
      const ta = textareaRef.value
      if (ta) {
        ta.selectionStart = sel.start + before.length
        ta.selectionEnd = sel.start + before.length + placeholder.length
        ta.focus()
      }
    })
  }
}

function prefixLines(prefix: string) {
  const sel = getSelection()
  const current = props.modelValue || ''
  if (sel.text) {
    const prefixed = sel.text.split('\n').map(line => prefix + line).join('\n')
    replaceRange(sel.start, sel.end, prefixed)
  } else {
    // Insert at line start or cursor
    const beforeCursor = current.slice(0, sel.start)
    const lineStart = beforeCursor.lastIndexOf('\n') + 1
    const needsNewline = lineStart < sel.start && current.slice(lineStart, sel.start).trim() !== ''
    const insert = needsNewline ? '\n' + prefix : prefix
    replaceRange(sel.start, sel.start, insert)
  }
}

function prefixNumberedList() {
  const sel = getSelection()
  const current = props.modelValue || ''
  if (sel.text) {
    const lines = sel.text.split('\n')
    const prefixed = lines.map((line, i) => `${i + 1}. ${line}`).join('\n')
    replaceRange(sel.start, sel.end, prefixed)
  } else {
    const beforeCursor = current.slice(0, sel.start)
    const lineStart = beforeCursor.lastIndexOf('\n') + 1
    const needsNewline = lineStart < sel.start && current.slice(lineStart, sel.start).trim() !== ''
    const insert = needsNewline ? '\n1. ' : '1. '
    replaceRange(sel.start, sel.start, insert)
  }
}

function insertCode() {
  const sel = getSelection()
  if (sel.text && sel.text.includes('\n')) {
    replaceRange(sel.start, sel.end, '```\n' + sel.text + '\n```')
  } else if (sel.text) {
    replaceRange(sel.start, sel.end, '`' + sel.text + '`')
  } else {
    replaceRange(sel.start, sel.end, '```\n\n```', sel.start + 4)
  }
}

function insertLink() {
  const sel = getSelection()
  if (sel.text) {
    replaceRange(sel.start, sel.end, '[' + sel.text + '](url)', sel.start + sel.text.length + 3)
    nextTick(() => {
      const ta = textareaRef.value
      if (ta) {
        ta.selectionStart = sel.start + sel.text.length + 3
        ta.selectionEnd = sel.start + sel.text.length + 6
        ta.focus()
      }
    })
  } else {
    replaceRange(sel.start, sel.end, '[链接文本](url)', sel.start + 1)
    nextTick(() => {
      const ta = textareaRef.value
      if (ta) {
        ta.selectionStart = sel.start + 1
        ta.selectionEnd = sel.start + 5
        ta.focus()
      }
    })
  }
}

// --- File upload ---

function triggerFileInput() {
  fileInputRef.value?.click()
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    uploadFiles(Array.from(input.files))
    input.value = ''
  }
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files) {
    uploadFiles(Array.from(e.dataTransfer.files))
  }
}

function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  // 收集所有文件(不只是图片):从访达/资源管理器复制的 .md/.pdf 等文件
  // 也走上传。否则浏览器默认行为只粘贴文件名纯文本,用户误以为附件已上传。
  const files: File[] = []
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }
  if (files.length) {
    e.preventDefault()
    uploadFiles(files)
  }
}

function insertAtCursor(text: string): { start: number; end: number } {
  const ta = textareaRef.value
  if (!ta) {
    const current = props.modelValue || ''
    emit('update:modelValue', current + text)
    return { start: current.length, end: current.length + text.length }
  }
  const start = ta.selectionStart
  const before = props.modelValue.slice(0, start)
  const after = props.modelValue.slice(ta.selectionEnd)
  emit('update:modelValue', before + text + after)
  const newPos = start + text.length
  nextTick(() => {
    ta.selectionStart = ta.selectionEnd = newPos
    ta.focus()
  })
  return { start, end: start + text.length }
}

function replacePlaceholder(placeholder: string, replacement: string) {
  const current = props.modelValue || ''
  const idx = current.indexOf(placeholder)
  if (idx >= 0) {
    emit('update:modelValue', current.slice(0, idx) + replacement + current.slice(idx + placeholder.length))
  }
}

async function uploadFiles(files: File[]) {
  for (const file of files) {
    if (!isAllowed(file)) {
      const typeLabel = file.type || `未知类型 (${file.name})`
      toast.add({ title: `不支持的文件类型: ${typeLabel}`, color: 'error' })
      continue
    }
    const image = isImage(file)
    const limit = image ? MAX_IMAGE_SIZE : MAX_FILE_SIZE
    if (file.size > limit) {
      const label = image ? '图片' : '文件'
      const limitMb = image ? 5 : 20
      toast.add({ title: `${label} ${file.name} 超过 ${limitMb}MB 限制`, color: 'error' })
      continue
    }

    const prefix = image ? '!' : ''
    const safeName = escapeMdLinkText(file.name)
    const placeholder = `${prefix}[上传中 ${safeName}...]()`
    insertAtCursor('\n' + placeholder + '\n')

    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await api<{ url: string; filename: string; id: string }>('/api/tools/upload/image/', {
        method: 'POST',
        body: formData,
      })
      replacePlaceholder(placeholder, `${prefix}[${escapeMdLinkText(res.filename)}](${res.url})`)
      emit('upload-complete', { url: res.url, filename: res.filename, id: res.id })
    } catch {
      replacePlaceholder(placeholder, `${prefix}[上传失败 ${safeName}]()`)
      toast.add({ title: `上传失败: ${file.name}`, color: 'error' })
    }
  }
}
</script>

<style>
/* Toolbar button */
.toolbar-btn {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 4px;
  color: #6b7280; transition: all 0.15s;
}
.toolbar-btn:hover { background: #e5e7eb; color: #374151; }
:root.dark .toolbar-btn { color: #9ca3af; }
:root.dark .toolbar-btn:hover { background: #374151; color: #e5e7eb; }

/* Markdown preview styles */
.markdown-body h1 { font-size: 1.5em; font-weight: 700; margin: 0.67em 0; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.3em; }
.markdown-body h2 { font-size: 1.25em; font-weight: 600; margin: 0.83em 0; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.3em; }
.markdown-body h3 { font-size: 1.1em; font-weight: 600; margin: 1em 0; }
.markdown-body p { margin: 0.5em 0; line-height: 1.6; }
.markdown-body ul { margin: 0.5em 0; padding-left: 2em; list-style-type: disc; }
.markdown-body ol { margin: 0.5em 0; padding-left: 2em; list-style-type: decimal; }
.markdown-body li { margin: 0.25em 0; }
.markdown-body code { background: #f3f4f6; padding: 0.2em 0.4em; border-radius: 3px; font-size: 0.875em; }
.markdown-body pre { background: #f3f4f6; padding: 1em; border-radius: 6px; overflow-x: auto; margin: 0.5em 0; }
.markdown-body pre code { background: none; padding: 0; }
.markdown-body blockquote { border-left: 4px solid #d1d5db; padding-left: 1em; color: #6b7280; margin: 0.5em 0; }
.markdown-body img { max-width: 100%; border-radius: 6px; margin: 0.5em 0; box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.12); }
.markdown-body a { color: #2563eb; text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body hr { border: none; border-top: 1px solid #e5e7eb; margin: 1em 0; }
.markdown-body table { border-collapse: collapse; width: 100%; margin: 0.5em 0; }
.markdown-body th, .markdown-body td { border: 1px solid #d1d5db; padding: 0.5em 0.75em; text-align: left; }
.markdown-body th { background: #f9fafb; font-weight: 600; }

/* Task list (todo) styles */
.markdown-body ul.contains-task-list { padding-left: 1.5em; list-style: none; margin: 0.5em 0; }
.markdown-body .task-list-item { list-style: none; }
.markdown-body .md-checkbox {
  display: inline-block;
  width: 0.95em; height: 0.95em;
  border: 1.5px solid #9ca3af;
  border-radius: 3px;
  margin-right: 0.4em;
  vertical-align: middle;
  position: relative;
  top: -0.05em;
}
.markdown-body .md-checkbox.md-checked {
  background: #6366f1;
  border-color: #6366f1;
}
.markdown-body .md-checkbox.md-checked::after {
  content: '';
  position: absolute;
  left: 2.5px; top: 0.5px;
  width: 4px; height: 8px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

/* Dark mode */
:root.dark .markdown-body code { background: #1f2937; }
:root.dark .markdown-body pre { background: #1f2937; }
:root.dark .markdown-body blockquote { border-left-color: #4b5563; color: #9ca3af; }
:root.dark .markdown-body h1, :root.dark .markdown-body h2 { border-bottom-color: #374151; }
:root.dark .markdown-body a { color: #60a5fa; }
:root.dark .markdown-body img { box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1), 0 2px 8px rgba(0, 0, 0, 0.45); }
:root.dark .markdown-body hr { border-top-color: #374151; }
:root.dark .markdown-body th, :root.dark .markdown-body td { border-color: #4b5563; }
:root.dark .markdown-body th { background: #1f2937; }

/* Mention styles */
.markdown-body .mention-user {
  background: #dbeafe;
  color: #1d4ed8;
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.9em;
  font-weight: 500;
}
.markdown-body .mention-issue {
  background: #dcfce7;
  color: #15803d;
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.9em;
  font-weight: 500;
  text-decoration: none;
}
.markdown-body .mention-issue:hover {
  text-decoration: underline;
}
:root.dark .markdown-body .mention-user {
  background: #1e3a5f;
  color: #93c5fd;
}
:root.dark .markdown-body .mention-issue {
  background: #14532d;
  color: #86efac;
}

/* File card (non-image attachments in markdown preview) */
.markdown-body .md-file-card {
  display: inline-flex;
  align-items: center;
  gap: 0.5em;
  padding: 0.4em 0.75em;
  margin: 0.25em 0.25em 0.25em 0;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  color: #1f2937;
  text-decoration: none;
  font-size: 0.875em;
  line-height: 1.2;
  transition: background 0.15s, border-color 0.15s;
  max-width: 100%;
}
.markdown-body .md-file-card:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
  text-decoration: none;
}
.markdown-body .md-file-card .md-file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.markdown-body .md-file-card .md-file-ext {
  font-size: 0.7em;
  font-weight: 600;
  letter-spacing: 0.05em;
  padding: 0.15em 0.4em;
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.06);
  color: #4b5563;
}
.markdown-body .md-file-card .md-file-icon {
  display: inline-block;
  width: 1.1em;
  height: 1.1em;
  flex-shrink: 0;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
}
.markdown-body .md-file-pdf .md-file-icon::before { content: '📄'; }
.markdown-body .md-file-word .md-file-icon::before { content: '📝'; }
.markdown-body .md-file-excel .md-file-icon::before { content: '📊'; }
.markdown-body .md-file-ppt .md-file-icon::before { content: '📽'; }
.markdown-body .md-file-text .md-file-icon::before { content: '📄'; }
.markdown-body .md-file-archive .md-file-icon::before { content: '📦'; }

.markdown-body .md-file-pdf .md-file-ext { background: #fee2e2; color: #b91c1c; }
.markdown-body .md-file-word .md-file-ext { background: #dbeafe; color: #1d4ed8; }
.markdown-body .md-file-excel .md-file-ext { background: #dcfce7; color: #15803d; }
.markdown-body .md-file-ppt .md-file-ext { background: #ffedd5; color: #c2410c; }
.markdown-body .md-file-text .md-file-ext { background: #f3f4f6; color: #4b5563; }
.markdown-body .md-file-archive .md-file-ext { background: #e5e7eb; color: #374151; }

:root.dark .markdown-body .md-file-card {
  background: #1f2937;
  border-color: #374151;
  color: #e5e7eb;
}
:root.dark .markdown-body .md-file-card:hover {
  background: #374151;
  border-color: #4b5563;
}
:root.dark .markdown-body .md-file-card .md-file-ext {
  background: rgba(255, 255, 255, 0.08);
  color: #d1d5db;
}
:root.dark .markdown-body .md-file-pdf .md-file-ext { background: #7f1d1d; color: #fecaca; }
:root.dark .markdown-body .md-file-word .md-file-ext { background: #1e3a5f; color: #bfdbfe; }
:root.dark .markdown-body .md-file-excel .md-file-ext { background: #14532d; color: #bbf7d0; }
:root.dark .markdown-body .md-file-ppt .md-file-ext { background: #7c2d12; color: #fed7aa; }
:root.dark .markdown-body .md-file-text .md-file-ext { background: #374151; color: #e5e7eb; }
:root.dark .markdown-body .md-file-archive .md-file-ext { background: #4b5563; color: #f3f4f6; }

/* Hover preview popup for .md attachments */
.md-hover-preview {
  position: absolute;
  width: min(720px, calc(100vw - 32px));
  max-height: min(640px, 70vh);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12), 0 4px 10px rgba(0, 0, 0, 0.06);
  z-index: 9999;
  font-size: 14px;
  line-height: 1.6;
  color: #1f2937;
}
.md-hover-preview .md-hover-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 8px 8px 0 0;
}
.md-hover-preview .md-hover-title {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  font-size: 13px;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.md-hover-preview .md-hover-download {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 4px;
  background: #6366f1;
  color: #ffffff;
  text-decoration: none;
  transition: background 0.15s;
}
.md-hover-preview .md-hover-download:hover {
  background: #4f46e5;
  text-decoration: none;
}
.md-hover-preview .md-hover-loading {
  color: #9ca3af;
  font-size: 13px;
  padding: 16px 20px;
}
.md-hover-preview .md-hover-body {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
  word-wrap: break-word;
}
:root.dark .md-hover-preview {
  background: #1f2937;
  border-color: #374151;
  color: #e5e7eb;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 4px 10px rgba(0, 0, 0, 0.3);
}
:root.dark .md-hover-preview .md-hover-header {
  background: #111827;
  border-bottom-color: #374151;
}
:root.dark .md-hover-preview .md-hover-title { color: #e5e7eb; }
:root.dark .md-hover-preview .md-hover-loading { color: #6b7280; }
</style>
