<template>
  <div class="rm-timeline">
    <div v-if="future.length" class="rm-edge rm-edge--top">
      <UIcon name="i-heroicons-arrow-up" class="rm-edge__icon" />
      <span class="rm-edge__label">未来</span>
    </div>

    <div
      v-for="(item, idx) in future"
      :key="item.id"
      class="rm-row"
      :class="rowSide(idx)"
      :style="{ '--rm-i': idx }"
    >
      <div class="rm-connector" aria-hidden="true" />
      <div class="rm-node" :class="nodeClass(item)" aria-hidden="true">
        <UIcon
          v-if="item.type === '里程碑'"
          name="i-heroicons-star-20-solid"
          class="rm-node__icon"
        />
      </div>
      <div class="rm-card-wrap">
        <RoadmapItem :item="item" />
      </div>
    </div>

    <div v-if="showTodayDivider" class="rm-today" :style="{ '--rm-i': future.length }">
      <span class="rm-today__pill">
        <span class="rm-today__mark">今天</span>
        <span class="rm-today__sep">·</span>
        <span class="rm-today__date">{{ todayFormatted }}</span>
      </span>
    </div>

    <div
      v-for="(item, idx) in past"
      :key="item.id"
      class="rm-row"
      :class="rowSide(future.length + idx)"
      :style="{ '--rm-i': future.length + (showTodayDivider ? 1 : 0) + idx }"
    >
      <div class="rm-connector" aria-hidden="true" />
      <div class="rm-node" :class="nodeClass(item)" aria-hidden="true">
        <UIcon
          v-if="item.type === '里程碑'"
          name="i-heroicons-star-20-solid"
          class="rm-node__icon"
        />
      </div>
      <div class="rm-card-wrap">
        <RoadmapItem :item="item" />
      </div>
    </div>

    <div v-if="past.length" class="rm-edge rm-edge--bottom">
      <UIcon name="i-heroicons-arrow-down" class="rm-edge__icon" />
      <span class="rm-edge__label">过去</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RoadmapItem, RoadmapType } from '~/types/roadmap'

const props = defineProps<{
  future: RoadmapItem[]
  past: RoadmapItem[]
  todayIso: string
}>()

function rowSide(idx: number) {
  return idx % 2 === 0 ? 'rm-row--left' : 'rm-row--right'
}

const nodeClassMap: Record<RoadmapType, string> = {
  功能: 'rm-node--feature',
  优化: 'rm-node--improve',
  修复: 'rm-node--fix',
  里程碑: 'rm-node--milestone',
}
function nodeClass(item: RoadmapItem) {
  return nodeClassMap[item.type]
}

const showTodayDivider = computed(() => props.future.length > 0 && props.past.length > 0)
const todayFormatted = computed(() => props.todayIso.replace(/-/g, '.'))
</script>

<style scoped>
.rm-timeline {
  --rm-serif: 'Songti SC', 'STSong', 'Noto Serif CJK SC', 'Source Han Serif SC', 'Times New Roman', serif;
  --rm-mono: 'JetBrains Mono', 'SF Mono', 'Menlo', 'Consolas', monospace;
  --rm-bg: rgb(255 255 255);
  --rm-bg-deep: rgb(17 24 39);

  position: relative;
  padding: 1.25rem 0 1.75rem;
}

/* === 脊线: 纵向冷紫→石墨 渐变 === */
.rm-timeline::before {
  content: '';
  position: absolute;
  left: 1rem;
  top: 0;
  bottom: 0;
  width: 1px;
  background: linear-gradient(
    to bottom,
    rgb(139 92 246 / 0)        0%,
    rgb(139 92 246 / 0.55)     6%,
    rgb(167 139 250 / 0.55)    30%,
    rgb(196 181 253 / 0.65)    48%,
    rgb(196 181 253 / 0.4)     52%,
    rgb(156 163 175 / 0.45)    70%,
    rgb(107 114 128 / 0.45)    94%,
    rgb(107 114 128 / 0)       100%
  );
  z-index: 0;
}
@media (min-width: 768px) {
  .rm-timeline::before {
    left: 50%;
    transform: translateX(-50%);
  }
}
:global(.dark) .rm-timeline::before {
  background: linear-gradient(
    to bottom,
    rgb(139 92 246 / 0)        0%,
    rgb(139 92 246 / 0.5)      6%,
    rgb(139 92 246 / 0.4)      30%,
    rgb(196 181 253 / 0.4)     48%,
    rgb(196 181 253 / 0.25)    52%,
    rgb(75 85 99 / 0.45)       70%,
    rgb(55 65 81 / 0.55)       94%,
    rgb(55 65 81 / 0)          100%
  );
}

/* === 顶/底 边缘标签 === */
.rm-edge {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-family: var(--rm-mono);
  font-size: 0.6875rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  padding: 0.5rem 0;
  margin-left: 1rem;
  animation: rm-fade-in 0.6s ease-out backwards;
}
@media (min-width: 768px) {
  .rm-edge {
    margin-left: 0;
  }
}
.rm-edge--top    { color: rgb(124 58 237); animation-delay: 0s; }
.rm-edge--bottom { color: rgb(107 114 128); animation-delay: 0.15s; }
:global(.dark) .rm-edge--top    { color: rgb(196 181 253); }
:global(.dark) .rm-edge--bottom { color: rgb(156 163 175); }

.rm-edge__icon  { width: 0.875rem; height: 0.875rem; }
.rm-edge__label { font-weight: 500; }

/* === 行 === */
.rm-row {
  position: relative;
  display: grid;
  grid-template-columns: 2rem 1fr;
  align-items: start;
  margin: 1.125rem 0;
  min-height: 3rem;
  animation: rm-fade-up 0.55s cubic-bezier(0.16, 1, 0.3, 1) backwards;
  animation-delay: calc(var(--rm-i, 0) * 0.06s + 0.1s);
}
@media (min-width: 768px) {
  .rm-row {
    grid-template-columns: 1fr 2rem 1fr;
    margin: 1.25rem 0;
  }
}

/* === 节点 === */
.rm-node {
  position: relative;
  z-index: 3;
  width: 0.875rem;
  height: 0.875rem;
  border-radius: 9999px;
  margin: 1.125rem auto 0;
  border: 2px solid var(--rm-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.25s ease;
}
:global(.dark) .rm-node {
  border-color: var(--rm-bg-deep);
}

/* 节点外晕 */
.rm-node::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 9999px;
  background: currentColor;
  opacity: 0.15;
  filter: blur(4px);
  z-index: -1;
  transition: opacity 0.25s ease, inset 0.25s ease;
}
.rm-node:hover::after,
.rm-row:hover .rm-node::after {
  opacity: 0.3;
  inset: -8px;
}

.rm-node--feature   { background: rgb(139 92 246); color: rgb(139 92 246); }
.rm-node--improve   { background: rgb(59 130 246); color: rgb(59 130 246); }
.rm-node--fix       { background: rgb(245 158 11); color: rgb(245 158 11); }
.rm-node--milestone {
  background: linear-gradient(135deg, rgb(250 204 21), rgb(202 138 4));
  color: rgb(234 179 8);
  width: 1.375rem;
  height: 1.375rem;
  margin-top: calc(1.125rem - 0.25rem);
  box-shadow:
    inset 0 1px 0 rgb(255 255 255 / 0.4),
    inset 0 -1px 0 rgb(0 0 0 / 0.15);
}
.rm-node__icon {
  width: 0.8125rem;
  height: 0.8125rem;
  color: rgb(255 255 255);
  filter: drop-shadow(0 0.5px 0.5px rgb(0 0 0 / 0.2));
}

/* 移动端：节点固定在左侧 spine */
@media (max-width: 767px) {
  .rm-node {
    grid-column: 1;
    margin: 1.125rem 0 0;
    justify-self: center;
  }
}
/* 桌面：节点固定在中列 */
@media (min-width: 768px) {
  .rm-node {
    grid-column: 2;
  }
}

/* === 卡片包裹 === */
.rm-card-wrap {
  grid-column: 2;
}
@media (min-width: 768px) {
  .rm-row--left .rm-card-wrap {
    grid-column: 1;
    padding-right: 0.875rem;
  }
  .rm-row--right .rm-card-wrap {
    grid-column: 3;
    padding-left: 0.875rem;
  }
}

/* === 节点到卡片的连接细线 === */
.rm-connector {
  display: none;
  position: absolute;
  top: calc(1.125rem + 6px);
  height: 1px;
  background: linear-gradient(
    to right,
    rgb(196 181 253 / 0.7),
    rgb(196 181 253 / 0)
  );
  z-index: 1;
}
:global(.dark) .rm-connector {
  background: linear-gradient(
    to right,
    rgb(139 92 246 / 0.55),
    rgb(139 92 246 / 0)
  );
}
@media (min-width: 768px) {
  .rm-connector {
    display: block;
    width: 1rem;
  }
  .rm-row--left .rm-connector {
    right: calc(50% + 0.5rem);
    background: linear-gradient(
      to left,
      rgb(196 181 253 / 0.7),
      rgb(196 181 253 / 0)
    );
  }
  :global(.dark) .rm-row--left .rm-connector {
    background: linear-gradient(
      to left,
      rgb(139 92 246 / 0.55),
      rgb(139 92 246 / 0)
    );
  }
  .rm-row--right .rm-connector {
    left: calc(50% + 0.5rem);
  }
}

/* === 今天分隔 === */
.rm-today {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 2.5rem 0;
  z-index: 2;
  animation: rm-fade-in 0.7s cubic-bezier(0.16, 1, 0.3, 1) backwards;
  animation-delay: calc(var(--rm-i, 0) * 0.06s + 0.1s);
}
.rm-today::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 1px;
  background: linear-gradient(
    to right,
    transparent,
    rgb(139 92 246 / 0.5) 18%,
    rgb(196 181 253 / 0.8) 50%,
    rgb(139 92 246 / 0.5) 82%,
    transparent
  );
  z-index: -1;
}
:global(.dark) .rm-today::before {
  background: linear-gradient(
    to right,
    transparent,
    rgb(139 92 246 / 0.45) 18%,
    rgb(196 181 253 / 0.6) 50%,
    rgb(139 92 246 / 0.45) 82%,
    transparent
  );
}

.rm-today__pill {
  display: inline-flex;
  align-items: baseline;
  gap: 0.5rem;
  background:
    linear-gradient(180deg, rgb(255 255 255), rgb(250 245 255));
  border: 1px solid rgb(196 181 253);
  color: rgb(91 33 182);
  padding: 0.4375rem 1.125rem;
  border-radius: 9999px;
  box-shadow:
    0 0 0 6px rgb(255 255 255 / 0.7),
    0 8px 24px -12px rgb(139 92 246 / 0.5),
    inset 0 1px 0 rgb(255 255 255 / 0.9);
  position: relative;
  animation: rm-today-glow 4s ease-in-out infinite;
}
:global(.dark) .rm-today__pill {
  background: linear-gradient(180deg, rgb(31 41 55), rgb(17 24 39));
  border-color: rgb(91 33 182);
  color: rgb(221 214 254);
  box-shadow:
    0 0 0 6px rgb(17 24 39 / 0.85),
    0 8px 24px -12px rgb(139 92 246 / 0.6),
    inset 0 1px 0 rgb(255 255 255 / 0.05);
}

.rm-today__mark {
  font-family: var(--rm-serif);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1;
}
.rm-today__sep {
  color: rgb(196 181 253);
  font-weight: 400;
  font-size: 0.875rem;
  line-height: 1;
  transform: translateY(-1px);
}
:global(.dark) .rm-today__sep {
  color: rgb(139 92 246);
}
.rm-today__date {
  font-family: var(--rm-mono);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  transform: translateY(-0.5px);
}

@keyframes rm-today-glow {
  0%, 100% {
    box-shadow:
      0 0 0 6px rgb(255 255 255 / 0.7),
      0 8px 24px -12px rgb(139 92 246 / 0.5),
      inset 0 1px 0 rgb(255 255 255 / 0.9);
  }
  50% {
    box-shadow:
      0 0 0 6px rgb(255 255 255 / 0.7),
      0 8px 32px -10px rgb(139 92 246 / 0.75),
      inset 0 1px 0 rgb(255 255 255 / 0.9);
  }
}
:global(.dark) .rm-today__pill {
  animation-name: rm-today-glow-dark;
}
@keyframes rm-today-glow-dark {
  0%, 100% {
    box-shadow:
      0 0 0 6px rgb(17 24 39 / 0.85),
      0 8px 24px -12px rgb(139 92 246 / 0.6),
      inset 0 1px 0 rgb(255 255 255 / 0.05);
  }
  50% {
    box-shadow:
      0 0 0 6px rgb(17 24 39 / 0.85),
      0 8px 32px -10px rgb(139 92 246 / 0.85),
      inset 0 1px 0 rgb(255 255 255 / 0.05);
  }
}

/* === 通用入场动画 === */
@keyframes rm-fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes rm-fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .rm-row,
  .rm-edge,
  .rm-today,
  .rm-today__pill,
  .rm-node {
    animation: none !important;
  }
  .rm-today__pill {
    transition: none;
  }
}
</style>
