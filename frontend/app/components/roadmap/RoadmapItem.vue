<template>
  <article class="rm-card" tabindex="0">
    <header class="rm-card__head">
      <time class="rm-card__date" :datetime="item.date">{{ formattedDate }}</time>
      <span :class="['rm-pill', 'rm-pill--type', typeClass]">{{ item.type }}</span>
    </header>
    <h3 class="rm-card__title">{{ item.title }}</h3>
    <p class="rm-card__desc">{{ item.description }}</p>
    <footer class="rm-card__foot">
      <span :class="['rm-pill', 'rm-pill--status', statusClass]">
        <span class="rm-pill__dot" aria-hidden="true" />
        {{ item.status }}
      </span>
    </footer>
  </article>
</template>

<script setup lang="ts">
import type { RoadmapItem, RoadmapStatus, RoadmapType } from '~/types/roadmap'

const props = defineProps<{ item: RoadmapItem }>()

const formattedDate = computed(() => props.item.date.replace(/-/g, '.'))

const typeClassMap: Record<RoadmapType, string> = {
  功能: 'rm-pill--feature',
  优化: 'rm-pill--improve',
  修复: 'rm-pill--fix',
  里程碑: 'rm-pill--milestone',
}
const typeClass = computed(() => typeClassMap[props.item.type])

const statusClassMap: Record<RoadmapStatus, string> = {
  计划中: 'rm-pill--planned',
  进行中: 'rm-pill--inprogress',
  已完成: 'rm-pill--done',
}
const statusClass = computed(() => statusClassMap[props.item.status])
</script>

<style scoped>
.rm-card {
  --rm-serif: 'Songti SC', 'STSong', 'Noto Serif CJK SC', 'Source Han Serif SC', 'Times New Roman', serif;
  --rm-mono: 'JetBrains Mono', 'SF Mono', 'Menlo', 'Consolas', monospace;
  --rm-card-border: rgb(229 231 235);
  --rm-card-border-hover: rgb(196 181 253);

  position: relative;
  background: rgb(255 255 255);
  border: 1px solid var(--rm-card-border);
  border-radius: 0.875rem;
  padding: 1rem 1.125rem 0.875rem;
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  isolation: isolate;
  overflow: hidden;
  outline: none;
}
:global(.dark) .rm-card {
  --rm-card-border: rgb(31 41 55);
  --rm-card-border-hover: rgb(91 33 182);
  background: rgb(17 24 39);
}

/* 顶部一道极细高光,呼应脊线的渐变色 */
.rm-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 1px;
  background: linear-gradient(
    to right,
    transparent,
    rgb(196 181 253 / 0.6) 30%,
    rgb(196 181 253 / 0.6) 70%,
    transparent
  );
  opacity: 0.5;
  transition: opacity 0.25s ease;
}
:global(.dark) .rm-card::before {
  background: linear-gradient(
    to right,
    transparent,
    rgb(139 92 246 / 0.55) 30%,
    rgb(139 92 246 / 0.55) 70%,
    transparent
  );
  opacity: 0.6;
}

.rm-card:hover,
.rm-card:focus-visible {
  border-color: var(--rm-card-border-hover);
  box-shadow:
    0 10px 24px -16px rgb(139 92 246 / 0.4),
    0 2px 6px -2px rgb(17 24 39 / 0.06);
  transform: translateY(-2px);
}
.rm-card:hover::before,
.rm-card:focus-visible::before {
  opacity: 1;
}
.rm-card:focus-visible {
  outline: 2px solid rgb(139 92 246 / 0.45);
  outline-offset: 3px;
}
:global(.dark) .rm-card:hover,
:global(.dark) .rm-card:focus-visible {
  box-shadow:
    0 12px 28px -16px rgb(0 0 0 / 0.65),
    0 0 0 1px rgb(139 92 246 / 0.25);
}

/* head */
.rm-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.rm-card__date {
  font-family: var(--rm-mono);
  font-size: 0.6875rem;
  letter-spacing: 0.12em;
  color: rgb(107 114 128);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
:global(.dark) .rm-card__date {
  color: rgb(156 163 175);
}

/* title */
.rm-card__title {
  font-family: var(--rm-serif);
  font-size: 1.0625rem;
  font-weight: 600;
  color: rgb(17 24 39);
  margin: 0;
  line-height: 1.35;
  letter-spacing: -0.005em;
}
:global(.dark) .rm-card__title {
  color: rgb(243 244 246);
}

/* description */
.rm-card__desc {
  font-size: 0.8125rem;
  line-height: 1.65;
  color: rgb(75 85 99);
  margin: 0;
}
:global(.dark) .rm-card__desc {
  color: rgb(156 163 175);
}

/* foot */
.rm-card__foot {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.125rem;
}

/* Pills - shared */
.rm-pill {
  font-size: 0.6875rem;
  padding: 0.1875rem 0.625rem;
  border-radius: 9999px;
  font-weight: 500;
  line-height: 1.4;
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  white-space: nowrap;
}

/* Type pill: outline-style (refined, editorial) */
.rm-pill--type {
  background: transparent;
  border: 1px solid currentColor;
  font-family: var(--rm-mono);
  font-size: 0.625rem;
  letter-spacing: 0.1em;
  padding: 0.125rem 0.5rem;
  opacity: 0.85;
}
.rm-pill--feature   { color: rgb(124 58 237); }
.rm-pill--improve   { color: rgb(37 99 235); }
.rm-pill--fix       { color: rgb(180 83 9); }
.rm-pill--milestone { color: rgb(161 98 7); }

:global(.dark) .rm-pill--feature   { color: rgb(196 181 253); }
:global(.dark) .rm-pill--improve   { color: rgb(147 197 253); }
:global(.dark) .rm-pill--fix       { color: rgb(252 211 77); }
:global(.dark) .rm-pill--milestone { color: rgb(253 224 71); }

/* Status pill: soft-fill with a leading dot */
.rm-pill--status {
  border: 1px solid transparent;
}
.rm-pill__dot {
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 9999px;
  background: currentColor;
  flex-shrink: 0;
}

.rm-pill--planned    { background: rgb(243 244 246); color: rgb(75 85 99); }
.rm-pill--inprogress {
  background: rgb(219 234 254);
  color: rgb(30 64 175);
  position: relative;
}
.rm-pill--inprogress .rm-pill__dot {
  animation: rm-card-pulse 2.2s ease-in-out infinite;
}
.rm-pill--done       { background: rgb(220 252 231); color: rgb(22 101 52); }

:global(.dark) .rm-pill--planned    { background: rgb(31 41 55); color: rgb(209 213 219); }
:global(.dark) .rm-pill--inprogress { background: rgb(30 58 138 / 0.5); color: rgb(147 197 253); }
:global(.dark) .rm-pill--done       { background: rgb(20 83 45 / 0.5); color: rgb(134 239 172); }

@keyframes rm-card-pulse {
  0%, 100% { box-shadow: 0 0 0 0 currentColor; opacity: 1; }
  50%      { box-shadow: 0 0 0 3px transparent; opacity: 0.55; }
}
</style>
