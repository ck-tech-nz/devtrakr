<template>
  <div
    v-if="pool.length"
    class="relative flex items-center justify-center h-9 max-w-full overflow-hidden text-sm"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
  >
    <Transition name="bulletin-fade" mode="out-in">
      <component
        :is="current.link_url ? 'a' : 'div'"
        :key="current.id"
        :href="current.link_url || undefined"
        :target="current.link_url ? '_blank' : undefined"
        rel="noopener noreferrer"
        class="flex items-center gap-2 max-w-full px-3 py-1 rounded-full"
        :class="meta.wrapClass"
      >
        <UIcon :name="meta.icon" class="w-4 h-4 shrink-0" :class="meta.iconClass" />
        <span class="truncate" :title="current.content">{{ current.content }}</span>
        <span v-if="current.source" class="shrink-0 text-xs opacity-60">—— {{ current.source }}</span>
      </component>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import type { Bulletin } from '~/composables/useBulletins'

const { announcements, rotating } = useBulletins()

// 轮播状态需在下方 immediate watch 之前声明 —— 该 watch 会在 setup 同步执行时
// 立刻回调并写 index.value,若 index 尚未声明会触发 TDZ ReferenceError。
const index = ref(0)
const paused = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

// 非公告池在内容加载后打乱一次,避免每次进页面都同序
const shuffled = ref<Bulletin[]>([])
watch(rotating, (list) => {
  const arr = [...list]
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j]!, arr[i]!]
  }
  shuffled.value = arr
  index.value = 0
}, { immediate: true })

// 有公告时:公告置顶常驻(多条在公告间轮播);无公告:轮播其余四类
const pool = computed<Bulletin[]>(() => (announcements.value.length ? announcements.value : shuffled.value))

const current = computed<Bulletin>(() => pool.value[index.value % Math.max(1, pool.value.length)] ?? pool.value[0]!)

const CATEGORY_META: Record<Bulletin['category'], { icon: string; wrapClass: string; iconClass: string }> = {
  quote:        { icon: 'i-heroicons-sparkles',             wrapClass: 'text-gray-600 dark:text-gray-300', iconClass: 'text-crystal-500' },
  prompt:       { icon: 'i-heroicons-command-line',         wrapClass: 'text-gray-600 dark:text-gray-300', iconClass: 'text-blue-500' },
  pitfall:      { icon: 'i-heroicons-exclamation-triangle', wrapClass: 'text-gray-600 dark:text-gray-300', iconClass: 'text-orange-500' },
  value:        { icon: 'i-heroicons-heart',                wrapClass: 'text-gray-600 dark:text-gray-300', iconClass: 'text-rose-500' },
  announcement: { icon: 'i-heroicons-megaphone',            wrapClass: 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300', iconClass: 'text-amber-500' },
}
const meta = computed(() => CATEGORY_META[current.value.category])

function start() {
  stop()
  timer = setInterval(() => {
    if (paused.value || pool.value.length <= 1) return
    index.value = (index.value + 1) % pool.value.length
  }, 8000)
}
function stop() {
  if (timer) { clearInterval(timer); timer = null }
}

watch(() => pool.value.length, () => { if (index.value >= pool.value.length) index.value = 0 })

onMounted(start)
onUnmounted(stop)
</script>

<style scoped>
.bulletin-fade-enter-active,
.bulletin-fade-leave-active { transition: opacity 0.4s ease; }
.bulletin-fade-enter-from,
.bulletin-fade-leave-to { opacity: 0; }
</style>
