<script setup lang="ts">
import type { ChatIncoming } from '~/composables/useChat'
const props = defineProps<{ event: ChatIncoming | null }>()
const emit = defineEmits<{ open: [issueId: number] }>()
const { resolveAvatarUrl } = useAvatars()
const visible = ref(false)
let timer: any = null

// 合成"叮"提示音(无需音频资源),受浏览器自动播放策略限制(首次交互后才响)。
function ding() {
  try {
    const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext
    const ac = new Ctx(); const now = ac.currentTime
    ;[[880, 0], [1320, 0.09]].forEach(([f, t]) => {
      const o = ac.createOscillator(), g = ac.createGain()
      o.type = 'sine'; o.frequency.value = f as number
      o.connect(g); g.connect(ac.destination)
      g.gain.setValueAtTime(0, now + (t as number))
      g.gain.linearRampToValueAtTime(0.18, now + (t as number) + 0.015)
      g.gain.exponentialRampToValueAtTime(0.0001, now + (t as number) + 0.32)
      o.start(now + (t as number)); o.stop(now + (t as number) + 0.34)
    })
  } catch { /* autoplay blocked */ }
}

watch(() => props.event, (ev) => {
  if (!ev) return
  visible.value = true
  ding()
  clearTimeout(timer)
  timer = setTimeout(() => (visible.value = false), 5000)
})
</script>

<template>
  <Transition name="chat-toast">
    <div v-if="visible && event" class="chat-toast" data-test="preview-toast"
         @click="emit('open', event.issue_id); visible = false">
      <div class="ct-av" :class="{ 'ct-av--img': event.comment.author_avatar }">
        <img v-if="event.comment.author_avatar" :src="resolveAvatarUrl(event.comment.author_avatar)" alt="" class="ct-av-img" />
        <template v-else>{{ (event.comment.author_name || '?').slice(0, 1) }}</template>
      </div>
      <div class="ct-body">
        <div class="ct-name">{{ event.comment.author_name }}<span class="ct-iss">ISS-{{ event.issue_id }}</span></div>
        <div class="ct-msg">{{ event.comment.content }}</div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.chat-toast { position: fixed; right: 24px; bottom: 104px; z-index: 45; width: 320px; display: flex; gap: 11px;
  background: var(--ui-bg, #fff); border: 1px solid var(--ui-border, #e4e8ef); border-radius: 14px; padding: 13px 14px;
  box-shadow: 0 24px 60px -16px rgba(15,23,42,.32); cursor: pointer; }
.ct-av { width: 38px; height: 38px; border-radius: 11px; flex: none; display: grid; place-items: center;
  color: #fff; font-weight: 700; background: linear-gradient(135deg,#34d399,#0d9488); overflow: hidden; }
.ct-av--img { background: #fff; }
.ct-av-img { width: 100%; height: 100%; object-fit: cover; }
.ct-body { min-width: 0; }
.ct-name { font-weight: 700; font-size: 13.5px; display: flex; gap: 8px; align-items: baseline; }
.ct-iss { font-size: 11px; font-weight: 700; color: var(--ui-primary, #2f55ea); }
.ct-msg { font-size: 13px; color: #64748b; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chat-toast-enter-active, .chat-toast-leave-active { transition: all .3s ease; }
.chat-toast-enter-from, .chat-toast-leave-to { opacity: 0; transform: translateY(20px); }
</style>
