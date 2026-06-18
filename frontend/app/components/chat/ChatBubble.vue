<script setup lang="ts">
const chat = useChat()
const { conversations, unreadTotal, activeIssueId, messages, lastIncoming } = chat
const { user } = useAuth()

const open = ref(false)
const view = ref<'list' | 'thread'>('list')
const meId = computed(() => (user.value ? Number(user.value.id) : null))
const activeTitle = computed(() => conversations.value.find(c => c.issue_id === activeIssueId.value)?.issue_title || '消息')

const rootEl = ref<HTMLElement | null>(null)
function onClickOutside(e: MouseEvent) {
  // 点击气泡/面板以外区域时收起(FAB 与面板都在 rootEl 内,不会误关)
  if (open.value && rootEl.value && !rootEl.value.contains(e.target as Node)) {
    open.value = false
  }
}
onMounted(() => {
  chat.loadConversations()
  chat.connect()
  document.addEventListener('click', onClickOutside)
})
onUnmounted(() => {
  chat.disconnect()
  document.removeEventListener('click', onClickOutside)
})

function toggle() { open.value = !open.value }
async function openConv(id: number) { await chat.openConversation(id); view.value = 'thread' }
function back() { view.value = 'list'; activeIssueId.value = null }
function send(content: string) { if (activeIssueId.value) chat.sendReply(activeIssueId.value, content) }
function onPreviewOpen(id: number) { open.value = true; openConv(id) }
</script>

<template>
  <ClientOnly>
    <div ref="rootEl" class="chat-root">
      <ChatPreviewToast v-if="!open" :event="lastIncoming" @open="onPreviewOpen" />

      <button class="chat-fab" data-test="fab" aria-label="聊天" @click="toggle">
        <span>{{ open ? '✕' : '💬' }}</span>
        <span v-if="unreadTotal > 0" class="chat-fab-badge" data-test="fab-badge">{{ unreadTotal }}</span>
      </button>

      <div v-if="open" class="chat-panel" data-test="chat-panel">
        <header class="chat-head">
          <button v-if="view === 'thread'" class="chat-back" @click="back">‹</button>
          <strong>{{ view === 'thread' ? activeTitle : '消息' }}</strong>
          <button class="chat-x" @click="toggle">✕</button>
        </header>

        <div v-if="view === 'list'" class="chat-list">
          <div class="chat-list-hd">有我参与且有评论的</div>
          <button v-for="c in conversations" :key="c.issue_id" class="chat-conv"
                  data-test="conv" @click="openConv(c.issue_id)">
            <div class="cc-main">
              <div class="cc-top"><span class="cc-iss">ISS-{{ c.issue_id }}</span><span class="cc-title">{{ c.issue_title }}</span></div>
              <div class="cc-snip">{{ c.last_comment?.content }}</div>
            </div>
            <span v-if="c.unread_count > 0" class="cc-unread">{{ c.unread_count }}</span>
          </button>
        </div>

        <ChatThread v-else :messages="messages" :me-id="meId" @send="send" />
      </div>
    </div>
  </ClientOnly>
</template>

<style scoped>
.chat-fab { position: fixed; right: 24px; bottom: 24px; z-index: 46; width: 60px; height: 60px; border-radius: 20px;
  border: none; cursor: pointer; color: #fff; font-size: 24px; background: linear-gradient(140deg, var(--ui-primary,#2f55ea), #5b7bff);
  box-shadow: 0 14px 30px -8px rgba(47,85,234,.55); }
.chat-fab-badge { position: absolute; top: -6px; right: -6px; min-width: 22px; height: 22px; padding: 0 6px; border-radius: 11px;
  background: #ef4444; color: #fff; font-size: 12px; font-weight: 800; display: grid; place-items: center; border: 2.5px solid #eef1f6; }
.chat-panel { position: fixed; right: 24px; bottom: 96px; z-index: 47; width: 384px; height: min(584px, calc(100vh - 132px));
  background: #fff; border: 1px solid #e4e8ef; border-radius: 16px; box-shadow: 0 24px 60px -16px rgba(15,23,42,.32);
  display: flex; flex-direction: column; overflow: hidden; }
.chat-head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid #e4e8ef; }
.chat-head strong { flex: 1; }
.chat-back, .chat-x { border: none; background: transparent; font-size: 18px; cursor: pointer; color: #64748b; }
.chat-list { flex: 1; min-height: 0; overflow-y: auto; padding: 6px; }
.chat-list-hd { padding: 10px 12px 6px; font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: #94a3b8; }
.chat-conv { display: flex; gap: 11px; width: 100%; text-align: left; padding: 11px 12px; border: none; background: transparent; border-radius: 12px; cursor: pointer; }
.chat-conv:hover { background: #f7f8fb; }
.cc-main { flex: 1; min-width: 0; }
.cc-iss { font-size: 11px; font-weight: 700; color: var(--ui-primary,#2f55ea); margin-right: 8px; }
.cc-title { font-weight: 700; font-size: 13.5px; }
.cc-snip { font-size: 13px; color: #64748b; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cc-unread { align-self: center; min-width: 19px; height: 19px; padding: 0 5px; border-radius: 10px; background: var(--ui-primary,#2f55ea); color: #fff; font-size: 11px; font-weight: 800; display: grid; place-items: center; }
</style>
