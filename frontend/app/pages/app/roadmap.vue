<template>
  <div class="rm-page">
    <RoadmapHero :stats="stats" />

    <div v-if="!sorted.length" class="rm-empty">
      <div class="rm-empty__rule" aria-hidden="true" />
      <p class="rm-empty__text">暂无路线图条目</p>
      <div class="rm-empty__rule" aria-hidden="true" />
    </div>

    <RoadmapTimeline
      v-else
      :future="future"
      :past="past"
      :today-iso="todayIso"
    />
  </div>
</template>

<script setup lang="ts">
import roadmapData from '~/data/roadmap.json'
import type { RoadmapData, RoadmapItem, RoadmapStatus } from '~/types/roadmap'

definePageMeta({ layout: 'default' })

const data = roadmapData as RoadmapData

const todayIso = computed(() => {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
})

// 按日期倒序（新→旧），同日按 id 升序保证稳定
const sorted = computed<RoadmapItem[]>(() =>
  [...data.items].sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? 1 : -1
    return a.id < b.id ? -1 : 1
  }),
)

const future = computed<RoadmapItem[]>(() =>
  sorted.value.filter(i => i.date > todayIso.value),
)

const past = computed<RoadmapItem[]>(() =>
  sorted.value.filter(i => i.date <= todayIso.value),
)

const stats = computed(() => {
  const init: Record<RoadmapStatus, number> = { 计划中: 0, 进行中: 0, 已完成: 0 }
  for (const item of sorted.value) init[item.status] += 1
  return init
})
</script>

<style scoped>
.rm-page {
  max-width: 64rem;
  margin: 0 auto;
  padding: 0 0.25rem;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}
@media (min-width: 768px) {
  .rm-page {
    gap: 2.5rem;
    padding: 0 1rem;
  }
}

.rm-empty {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 4rem 1rem;
  color: rgb(156 163 175);
}
:global(.dark) .rm-empty {
  color: rgb(107 114 128);
}

.rm-empty__rule {
  flex: 1;
  height: 1px;
  background: linear-gradient(to right, transparent, rgb(229 231 235), transparent);
}
:global(.dark) .rm-empty__rule {
  background: linear-gradient(to right, transparent, rgb(55 65 81), transparent);
}

.rm-empty__text {
  font-family: 'Songti SC', 'STSong', 'Noto Serif CJK SC', serif;
  font-size: 0.9375rem;
  letter-spacing: 0.05em;
  margin: 0;
}
</style>
