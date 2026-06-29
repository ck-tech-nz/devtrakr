<script setup lang="ts">
const chat = useChat()
// open/view 上提到 useChat:手机端底部栏「消息」Tab 与此 FAB 共用同一面板
const { conversations, unreadTotal, activeIssueId, messages, lastIncoming, open, view } = chat
const { user } = useAuth()
const meId = computed(() => (user.value ? Number(user.value.id) : null))
const activeTitle = computed(() => conversations.value.find(c => c.issue_id === activeIssueId.value)?.issue_title || '消息')

const rootEl = ref<HTMLElement | null>(null)
function onClickOutside(e: MouseEvent) {
  // 用 composedPath 而非 contains(target):返回按钮点击后会因 v-if 立即从 DOM 移除,
  // contains(已脱离的 target) 会误判为"点击外部"而关掉弹窗;composedPath 在事件派发时
  // 已固定路径,即使节点随后被移除仍包含 rootEl。
  if (!open.value || !rootEl.value) return
  const path = e.composedPath()
  if (path.includes(rootEl.value)) return
  // 手机端「消息」Tab 触发 toggleChat 是在 mousedown/touchstart,而随后的 click 会冒泡到此处;
  // 跳过来自底部栏的点击,避免点击穿透把刚打开的面板立刻关掉(开关交给底部栏的 toggleChat)。
  if (path.some(el => el instanceof HTMLElement && el.dataset.mobileTabbar !== undefined)) return
  open.value = false
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
// 点击标题跳到案件详情页(SPA 导航,弹窗常驻 app.vue 根节点不会卸载,保持打开)
function goToIssue() { if (activeIssueId.value != null) navigateTo(`/app/issues/${activeIssueId.value}`) }
function send(content: string) { if (activeIssueId.value) chat.sendReply(activeIssueId.value, content) }
function onPreviewOpen(id: number) { open.value = true; openConv(id) }
</script>

<template>
  <ClientOnly>
    <div ref="rootEl" class="chat-root">
      <ChatPreviewToast v-if="!open" :event="lastIncoming" @open="onPreviewOpen" />

      <button class="chat-fab" :class="{ 'is-open': open, 'has-unread': unreadTotal > 0 }"
              data-test="fab" aria-label="聊天" @click="toggle">
        <svg v-if="!open" class="chat-fab__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M20.5 11.4a8 8 0 0 1-11.7 7.1L4 20l1.5-4.6A8 8 0 1 1 20.5 11.4Z" />
          <circle cx="8.6" cy="11.5" r=".9" fill="currentColor" stroke="none" />
          <circle cx="12" cy="11.5" r=".9" fill="currentColor" stroke="none" />
          <circle cx="15.4" cy="11.5" r=".9" fill="currentColor" stroke="none" />
        </svg>
        <svg v-else class="chat-fab__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
          <path d="M6 6l12 12M18 6 6 18" />
        </svg>
        <span v-if="unreadTotal > 0" class="chat-fab-badge" data-test="fab-badge">{{ unreadTotal }}</span>
      </button>

      <div v-if="open" class="chat-panel" data-test="chat-panel">
        <header class="chat-head">
          <button v-if="view === 'thread'" class="chat-back" @click="back">‹</button>
          <button v-if="view === 'thread'" class="chat-title-link" :title="activeTitle"
                  data-test="chat-title-link" @click="goToIssue">{{ activeTitle }}</button>
          <strong v-else>消息</strong>
          <button class="chat-x" @click="toggle">✕</button>
        </header>

        <div v-if="view === 'list'" class="chat-list">
          <div class="chat-list-hd">有我参与且有评论的</div>
          <button v-for="c in conversations" :key="c.issue_id" class="chat-conv"
                  data-test="conv" @click="openConv(c.issue_id)">
            <div class="cc-main">
              <div class="cc-top">
                <span class="cc-iss">ISS-{{ c.issue_id }}</span>
                <span v-if="c.issue_status" class="cc-status" :style="{ backgroundColor: statusMainColor(c.issue_status) }">{{ statusLabel(c.issue_status) }}</span>
                <span class="cc-title">{{ c.issue_title }}</span>
              </div>
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
/* 消息悬浮按钮:深翠→墨青渐变 + 玻璃高光 + 环境辉光,替代原扁平亮绿+emoji */
.chat-fab { position: fixed; right: 24px; bottom: 24px; z-index: 46; width: 58px; height: 58px; padding: 0;
  border: none; cursor: pointer; color: #fff; border-radius: 18px; display: grid; place-items: center;
  background:
    radial-gradient(125% 125% at 28% 20%, rgba(255,255,255,.40) 0%, rgba(255,255,255,0) 44%),
    linear-gradient(152deg, #10b981 0%, #0d9488 50%, #0f766e 100%);
  box-shadow:
    0 14px 30px -10px rgba(13,148,136,.60),
    0 4px 10px -3px rgba(4,47,46,.45),
    inset 0 1px 0 rgba(255,255,255,.50),
    inset 0 -12px 20px rgba(3,42,42,.34);
  transition: transform .26s cubic-bezier(.2,.9,.3,1.35), box-shadow .26s; }
.chat-fab::before { content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background: linear-gradient(180deg, rgba(255,255,255,.20), transparent 52%); }
.chat-fab::after { content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; z-index: -1; }
.chat-fab.has-unread::after { animation: fab-pulse 2.4s ease-out infinite; }
@keyframes fab-pulse {
  0% { box-shadow: 0 0 0 0 rgba(16,185,129,.45); }
  70% { box-shadow: 0 0 0 13px rgba(16,185,129,0); }
  100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); } }
.chat-fab:hover { transform: translateY(-3px);
  box-shadow: 0 20px 40px -10px rgba(13,148,136,.72), 0 6px 14px -3px rgba(4,47,46,.5),
    inset 0 1px 0 rgba(255,255,255,.55), inset 0 -12px 20px rgba(3,42,42,.34); }
.chat-fab:active { transform: translateY(-1px) scale(.95); }
.chat-fab__icon { width: 26px; height: 26px; position: relative; z-index: 1;
  transition: transform .3s cubic-bezier(.2,.9,.3,1.35); }
.chat-fab.is-open .chat-fab__icon { transform: rotate(90deg); }
.chat-fab-badge { position: absolute; top: -5px; right: -5px; min-width: 21px; height: 21px; padding: 0 6px; border-radius: 11px;
  background: linear-gradient(180deg, #fb7185, #ef4444); color: #fff; font-size: 11.5px; font-weight: 800; line-height: 1;
  display: grid; place-items: center; border: 2px solid #fff; box-shadow: 0 3px 7px -2px rgba(239,68,68,.6); z-index: 2; }
.chat-panel { position: fixed; right: 24px; bottom: 96px; z-index: 47; width: 384px; height: min(584px, calc(100vh - 132px));
  background: #fff; border: 1px solid #e4e8ef; border-radius: 16px; box-shadow: 0 24px 60px -16px rgba(15,23,42,.32);
  display: flex; flex-direction: column; overflow: hidden; }
.chat-head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid #e4e8ef; }
.chat-head strong { flex: 1; }
/* 标题可点击跳详情:沿用 strong 的加粗外观,截断至两行(超出省略号),hover 提示可点 */
.chat-title-link { flex: 1; min-width: 0; text-align: left; border: none; background: transparent; padding: 0;
  font: inherit; font-weight: 700; color: inherit; cursor: pointer; line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  transition: color .15s; }
.chat-title-link:hover { color: var(--ui-primary, #2f55ea); text-decoration: underline; }
.chat-back, .chat-x { display: grid; place-items: center; width: 30px; height: 30px; flex: none; border: none; background: transparent; border-radius: 8px; font-size: 20px; line-height: 1; cursor: pointer; color: #64748b; transition: background .15s, color .15s; }
.chat-back:hover, .chat-x:hover { background: #f1f5f9; color: #0f172a; }
.chat-back { margin-left: -4px; }
.chat-list { flex: 1; min-height: 0; overflow-y: auto; padding: 6px; }
.chat-list-hd { padding: 10px 12px 6px; font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: #94a3b8; }
.chat-conv { display: flex; gap: 11px; width: 100%; text-align: left; padding: 11px 12px; border: none; background: transparent; border-radius: 12px; cursor: pointer; }
.chat-conv:hover { background: #f7f8fb; }
.cc-main { flex: 1; min-width: 0; }
.cc-top { display: flex; align-items: center; gap: 6px; }
.cc-iss { font-size: 11px; font-weight: 700; color: var(--ui-primary,#2f55ea); flex: none; }
.cc-status { flex: none; font-size: 10px; line-height: 1.7; color: #fff; padding: 0 6px; border-radius: 6px; font-weight: 600; white-space: nowrap; }
.cc-title { font-weight: 700; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cc-snip { font-size: 13px; color: #64748b; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cc-unread { align-self: center; min-width: 19px; height: 19px; padding: 0 5px; border-radius: 10px; background: var(--ui-primary,#2f55ea); color: #fff; font-size: 11px; font-weight: 800; display: grid; place-items: center; }

/* 手机端:入口改由底部栏「消息」Tab 承担,隐藏 FAB;面板与预览条改为全宽并坐落在底部栏之上 */
@media (max-width: 767px) {
  .chat-fab { display: none; }
  /* bottom = 栏体≈58 + mb-3(12) + ~16 间隙 + 安全区 */
  .chat-panel { left: 12px; right: 12px; width: auto; bottom: calc(86px + env(safe-area-inset-bottom)); height: min(584px, calc(100vh - 180px)); }
}
</style>
