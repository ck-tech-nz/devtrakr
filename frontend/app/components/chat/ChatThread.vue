<script setup lang="ts">
import type { ChatComment } from '~/composables/useChat'
import type { MentionItem } from '~/components/MentionDropdown.vue'
import { detectMentionTrigger } from '~/composables/useMentionTrigger'

const props = defineProps<{ messages: ChatComment[]; meId: number | null }>()
const emit = defineEmits<{ send: [content: string] }>()

// 复用现有 markdown-it 实例（含 @[name](user:id) / #issue 渲染插件）
const { md } = useMentionMarkdown()
function renderContent(content: string) {
  return md.render(content)
}

const { api } = useApi()

const draft = ref('')
const scroller = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const mentionRef = ref<InstanceType<typeof MentionDropdown> | null>(null)

const mentionVisible = ref(false)
const mentionType = ref<'user' | 'issue'>('user')
const mentionItems = ref<MentionItem[]>([])
const mentionPosition = ref({ top: 0, left: 0 })
const mentionTriggerStart = ref(0)

let userCache: { id: number; name: string }[] | null = null

function isMine(m: ChatComment) { return props.meId != null && m.author === props.meId }

function submit() {
  const text = draft.value.trim()
  if (!text) return
  emit('send', text)
  draft.value = ''
  mentionVisible.value = false
}

function onKey(e: KeyboardEvent) {
  if (mentionVisible.value) {
    if (e.key === 'ArrowUp') { e.preventDefault(); mentionRef.value?.moveUp(); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); mentionRef.value?.moveDown(); return }
    if (e.key === 'Enter') { e.preventDefault(); mentionRef.value?.confirmSelection(); return }
    if (e.key === 'Escape') { mentionVisible.value = false; return }
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
}

watch(() => props.messages.length, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
})

// --- @-mention autocomplete ---

async function fetchUserSuggestions(query: string): Promise<MentionItem[]> {
  if (!userCache) {
    userCache = await api<{ id: number; name: string }[]>('/api/users/choices/')
  }
  const q = query.toLowerCase()
  return userCache
    .filter(u => u.name.toLowerCase().includes(q))
    .map(u => ({ id: u.id, label: u.name }))
}

async function fetchIssueSuggestions(query: string): Promise<MentionItem[]> {
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

async function handleMentionInput() {
  const ta = textareaRef.value
  if (!ta) return
  const trigger = detectMentionTrigger(draft.value, ta.selectionStart)
  if (!trigger) {
    mentionVisible.value = false
    return
  }
  mentionType.value = trigger.type
  mentionTriggerStart.value = trigger.start

  // 简单定位：在 textarea 左上角附近显示下拉
  const rect = ta.getBoundingClientRect()
  mentionPosition.value = { top: rect.height + 4, left: 0 }

  if (trigger.type === 'user') {
    mentionItems.value = await fetchUserSuggestions(trigger.query)
  } else {
    mentionItems.value = await fetchIssueSuggestions(trigger.query)
  }
  mentionVisible.value = mentionItems.value.length > 0
}

function onInput() {
  nextTick(handleMentionInput)
}

function insertMention(item: MentionItem) {
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
  const before = draft.value.slice(0, mentionTriggerStart.value)
  const after = draft.value.slice(cursor)
  draft.value = before + replacement + after
  mentionVisible.value = false
  nextTick(() => {
    if (ta) {
      const pos = mentionTriggerStart.value + replacement.length
      ta.selectionStart = ta.selectionEnd = pos
      ta.focus()
    }
  })
}
</script>

<template>
  <div class="ct-thread">
    <div ref="scroller" class="ct-scroll">
      <div v-for="m in messages" :key="m.id" class="ct-msg" :class="{ mine: isMine(m) }">
        <div class="ct-mav">{{ (m.author_name || '?').slice(0, 1) }}</div>
        <div class="ct-mwrap">
          <div class="ct-mname">{{ m.author_name }}</div>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="ct-bubble markdown-view" v-html="renderContent(m.content)" />
        </div>
      </div>
    </div>
    <div class="ct-composer">
      <div class="ct-input-wrap">
        <textarea ref="textareaRef" v-model="draft" rows="1" placeholder="回复… 输入 @ 提及成员"
                  data-test="reply-input" @keydown="onKey" @input="onInput" />
        <MentionDropdown
          ref="mentionRef"
          :visible="mentionVisible"
          :items="mentionItems"
          :position="mentionPosition"
          :type="mentionType"
          @select="insertMention"
        />
      </div>
      <button class="ct-send" :disabled="!draft.trim()" data-test="reply-send" @click="submit">发送</button>
    </div>
    <div class="ct-hint">回车发送 · @ 提及 · 回复即在该问题新增评论</div>
  </div>
</template>

<style scoped>
.ct-thread { display: flex; flex-direction: column; height: 100%; }
.ct-scroll { flex: 1; overflow-y: auto; padding: 16px 14px; background: var(--ui-bg-muted, #f7f8fb); }
.ct-msg { display: flex; gap: 9px; margin-bottom: 12px; max-width: 86%; }
.ct-msg.mine { margin-left: auto; flex-direction: row-reverse; }
.ct-mav { width: 30px; height: 30px; border-radius: 9px; flex: none; display: grid; place-items: center; color: #fff; font-size: 12px; font-weight: 700; background: linear-gradient(135deg,#34d399,#0d9488); }
.ct-bubble { padding: 9px 13px; border-radius: 14px; font-size: 14px; background: #fff; border: 1px solid #e4e8ef; }
.ct-msg.mine .ct-bubble { background: var(--ui-primary, #2f55ea); color: #fff; border: none; }
.ct-mname { font-size: 11.5px; font-weight: 700; color: #64748b; margin: 0 0 4px 3px; }
.ct-composer { display: flex; gap: 8px; padding: 11px 12px; border-top: 1px solid #e4e8ef; }
.ct-input-wrap { flex: 1; position: relative; }
.ct-input-wrap textarea { width: 100%; resize: none; border: 1px solid #e4e8ef; border-radius: 12px; padding: 9px 12px; font: inherit; }
.ct-send { border: none; background: var(--ui-primary, #2f55ea); color: #fff; border-radius: 10px; padding: 0 14px; cursor: pointer; }
.ct-send:disabled { background: #c3ccde; }
.ct-hint { font-size: 11px; color: #94a3b8; padding: 0 12px 10px; }
</style>
