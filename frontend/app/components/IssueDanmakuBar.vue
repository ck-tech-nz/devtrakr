<template>
  <div
    class="danmaku-bar relative w-full overflow-hidden rounded-xl border border-black/5"
    role="log"
    aria-label="问题动态"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
  >
    <span class="danmaku-tag">动态</span>

    <!-- 减少动态效果:静态展示最近若干条 -->
    <div v-if="reduced" class="reduced-list">
      <button
        v-for="e in recent"
        :key="`${e.kind}:${e.issue_id}`"
        class="bullet"
        type="button"
        @click="go(e)"
      >
        <span class="pill" :class="e.kind">{{ e.kind === 'created' ? '新建' : '完成' }}</span>
        <span class="iss">{{ e.issue_number }}</span>
        <span class="ttl">{{ e.title }}</span>
        <span v-if="e.actor_name" class="who">· {{ e.actor_name }}</span>
      </button>
    </div>

    <!-- 多轨弹幕 -->
    <div v-else class="lanes" :style="{ height: `${lanes * LANE_H}px` }">
      <div v-for="(laneBullets, li) in laneModel" :key="li" class="lane" :style="{ height: `${LANE_H}px` }">
        <button
          v-for="b in laneBullets"
          :key="b.id"
          class="bullet flying"
          :class="{ paused }"
          type="button"
          :style="{ animationDuration: `${b.duration}s` }"
          @click="go(b.event)"
          @animationend="removeBullet(li, b.id)"
        >
          <span class="pill" :class="b.event.kind">{{ b.event.kind === 'created' ? '新建' : '完成' }}</span>
          <span class="iss">{{ b.event.issue_number }}</span>
          <span class="ttl">{{ b.event.title }}</span>
          <span v-if="b.event.actor_name" class="who">· {{ b.event.actor_name }}</span>
        </button>
      </div>
    </div>

    <button class="danmaku-close" type="button" aria-label="关闭动态弹幕" @click="close">
      <UIcon name="i-heroicons-x-mark" class="w-3.5 h-3.5" />
    </button>
  </div>
</template>

<script setup lang="ts">
import type { DanmakuEvent } from '~/composables/useIssueDanmaku'

interface Bullet { id: number; event: DanmakuEvent; duration: number }

const LANE_H = 34            // 每轨高度(px)
const DURATION = 14          // 单条滚过时长(s),恒定速度感
const MIN_GAP_MS = 3500      // 同轨两条最小间隔,避免重叠
const TICK_MS = 400          // 调度间隔

const { queue } = useIssueDanmaku()
const { update } = useUserSettings()

const reduced = ref(false)
const paused = ref(false)
const lanes = ref(3)
const recent = ref<DanmakuEvent[]>([])
const laneModel = ref<Bullet[][]>([[], [], []])
const laneNextFree = [0, 0, 0]
let bulletSeq = 0
let timer: ReturnType<typeof setInterval> | null = null
let mql: MediaQueryList | null = null
let mobileMql: MediaQueryList | null = null

function go(e: DanmakuEvent) {
  navigateTo(`/app/issues/${e.issue_id}`)
}

function close() {
  update('danmaku_enabled', false)  // 页面 watcher 会随之 disable()
}

function removeBullet(laneIndex: number, id: number) {
  const lane = laneModel.value[laneIndex]
  if (lane) laneModel.value[laneIndex] = lane.filter(b => b.id !== id)
}

function now() { return Date.now() }

function spawn() {
  if (reduced.value) return  // 减少动态模式下由 watch(queue) 负责静态收纳,调度器不出队
  if (paused.value) return
  if (typeof document !== 'undefined' && document.hidden) return
  if (!queue.value.length) return
  // 找一条空闲轨道(上一条已发射足够久)
  for (let li = 0; li < lanes.value; li++) {
    if (now() < (laneNextFree[li] ?? 0)) continue
    const event = queue.value[0]
    if (!event) return
    queue.value = queue.value.slice(1)  // 出队
    const bullet: Bullet = { id: ++bulletSeq, event, duration: DURATION }
    laneModel.value[li] = [...(laneModel.value[li] || []), bullet]
    laneNextFree[li] = now() + MIN_GAP_MS
    return  // 每 tick 至多发射一条,保持稀疏
  }
}

function pushRecent(e: DanmakuEvent) {
  recent.value = [e, ...recent.value].slice(0, 6)
}

// 减少动态效果模式:直接把队列并入静态最近列表
watch(queue, (q) => {
  if (!reduced.value || !q.length) return
  for (const e of q) pushRecent(e)
  queue.value = []
}, { deep: true })

function onReducedChange(ev: MediaQueryListEvent) {
  reduced.value = ev.matches
}
// 断点变化时按最新轨道数重排 laneModel(保留已有弹幕),避免渲染轨道数与 lanes.value 脱节
function onMobileChange() {
  lanes.value = mobileMql!.matches ? 1 : 3
  laneModel.value = Array.from({ length: lanes.value }, (_, i) => laneModel.value[i] || [])
}

onMounted(() => {
  if (typeof window !== 'undefined' && window.matchMedia) {
    mql = window.matchMedia('(prefers-reduced-motion: reduce)')
    reduced.value = mql.matches
    mql.addEventListener('change', onReducedChange)

    mobileMql = window.matchMedia('(max-width: 767px)')
    onMobileChange()  // 挂载即按当前断点确定轨道数并初始化 laneModel
    mobileMql.addEventListener('change', onMobileChange)
  } else {
    // 无 matchMedia(SSR/降级)时按默认轨道数初始化
    laneModel.value = Array.from({ length: lanes.value }, (_, i) => laneModel.value[i] || [])
  }
  timer = setInterval(spawn, TICK_MS)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  mql?.removeEventListener('change', onReducedChange)
  mobileMql?.removeEventListener('change', onMobileChange)
})
</script>

<style scoped>
.danmaku-bar {
  background: rgba(139, 92, 246, 0.06);
  backdrop-filter: blur(10px) saturate(160%);
  -webkit-backdrop-filter: blur(10px) saturate(160%);
  padding: 8px 0;
}
.danmaku-tag {
  position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
  z-index: 3; font-size: 11px; font-weight: 700; letter-spacing: .12em;
  color: #6d28d9; padding-right: 12px;
  background: linear-gradient(90deg, rgba(255,255,255,.7) 70%, transparent);
}
.danmaku-close {
  position: absolute; right: 8px; top: 6px; z-index: 3;
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 6px; color: #9a97ab;
}
.danmaku-close:hover { background: rgba(0,0,0,.06); color: #4b5563; }
.lanes { position: relative; }
.lane { position: relative; }
.bullet {
  display: inline-flex; align-items: center; gap: 8px; white-space: nowrap;
  font-size: 13px; cursor: pointer;
}
.bullet.flying {
  position: absolute; left: 100%; top: 50%; transform: translateY(-50%);
  background: rgba(255,255,255,.78); border: 1px solid rgba(0,0,0,.06);
  padding: 4px 12px; border-radius: 999px;
  box-shadow: 0 4px 14px -8px rgba(33,29,51,.35);
  animation-name: danmaku-fly; animation-timing-function: linear; animation-iteration-count: 1;
  will-change: transform;
}
.bullet.flying.paused { animation-play-state: paused; }
@keyframes danmaku-fly {
  from { transform: translate(0, -50%); }
  to   { transform: translate(calc(-100vw - 100%), -50%); }
}
.reduced-list { display: flex; flex-wrap: wrap; gap: 8px 16px; padding: 2px 12px 2px 66px; }
.reduced-list .bullet { background: transparent; }
.pill { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
.pill.created { background: rgba(139,92,246,.12); color: #6d28d9; }
.pill.completed { background: rgba(16,185,129,.15); color: #047857; }
.iss { font-variant-numeric: tabular-nums; font-weight: 700; color: #211d33; }
.ttl { color: #211d33; max-width: 30ch; overflow: hidden; text-overflow: ellipsis; }
.who { color: #9a97ab; }
</style>
