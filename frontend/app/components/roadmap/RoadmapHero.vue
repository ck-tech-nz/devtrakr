<template>
  <section class="rm-hero">
    <div class="rm-hero__lede">
      <div class="rm-hero__eyebrow">
        <span class="rm-hero__eyebrow-rule" aria-hidden="true" />
        <span class="rm-hero__eyebrow-text">DevTrack · Roadmap</span>
      </div>
      <h1 class="rm-hero__title">产品路线图</h1>
      <p class="rm-hero__subtitle">我们做过什么，正在做什么，未来要做什么。</p>
    </div>
    <dl class="rm-hero__stats" aria-label="路线图统计">
      <div class="rm-stat rm-stat--planned">
        <dt class="rm-stat__label">计划中</dt>
        <dd class="rm-stat__value">{{ pad(stats.计划中) }}</dd>
      </div>
      <div class="rm-stat rm-stat--inprogress">
        <dt class="rm-stat__label">进行中</dt>
        <dd class="rm-stat__value">{{ pad(stats.进行中) }}</dd>
      </div>
      <div class="rm-stat rm-stat--done">
        <dt class="rm-stat__label">已完成</dt>
        <dd class="rm-stat__value">{{ pad(stats.已完成) }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import type { RoadmapStatus } from '~/types/roadmap'

defineProps<{ stats: Record<RoadmapStatus, number> }>()

function pad(n: number) {
  return String(n).padStart(2, '0')
}
</script>

<style scoped>
.rm-hero {
  --rm-serif: 'Songti SC', 'STSong', 'Noto Serif CJK SC', 'Source Han Serif SC', 'Times New Roman', serif;
  --rm-mono: 'JetBrains Mono', 'SF Mono', 'Menlo', 'Consolas', monospace;

  position: relative;
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.75rem;
  padding: 2.5rem 0 0.5rem;
  isolation: isolate;
}
@media (min-width: 768px) {
  .rm-hero {
    grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
    align-items: end;
    gap: 3rem;
    padding: 3rem 0 1rem;
  }
}

/* 背景柔光 */
.rm-hero::before {
  content: '';
  position: absolute;
  inset: -2rem -2rem auto;
  height: 9rem;
  background:
    radial-gradient(60% 100% at 22% 60%, rgb(196 181 253 / 0.28), transparent 70%),
    radial-gradient(50% 100% at 88% 40%, rgb(253 224 71 / 0.18), transparent 70%);
  filter: blur(20px);
  z-index: -1;
  pointer-events: none;
}
:global(.dark) .rm-hero::before {
  background:
    radial-gradient(60% 100% at 22% 60%, rgb(139 92 246 / 0.22), transparent 70%),
    radial-gradient(50% 100% at 88% 40%, rgb(202 138 4 / 0.14), transparent 70%);
}

/* 标题块 */
.rm-hero__lede {
  min-width: 0;
}

.rm-hero__eyebrow {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  margin-bottom: 1.125rem;
}
.rm-hero__eyebrow-rule {
  display: block;
  width: 1.75rem;
  height: 1px;
  background: linear-gradient(to right, rgb(139 92 246), rgb(196 181 253 / 0.2));
}
:global(.dark) .rm-hero__eyebrow-rule {
  background: linear-gradient(to right, rgb(196 181 253), rgb(139 92 246 / 0.2));
}
.rm-hero__eyebrow-text {
  font-family: var(--rm-mono);
  font-size: 0.6875rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgb(124 58 237);
  font-weight: 500;
}
:global(.dark) .rm-hero__eyebrow-text {
  color: rgb(196 181 253);
}

.rm-hero__title {
  font-family: var(--rm-serif);
  font-size: clamp(2.25rem, 1.5rem + 2.5vw, 3.25rem);
  line-height: 1.05;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: rgb(17 24 39);
  margin: 0;
  font-feature-settings: "ss01" 1, "kern" 1;
}
:global(.dark) .rm-hero__title {
  color: rgb(243 244 246);
}

.rm-hero__subtitle {
  margin: 0.75rem 0 0;
  font-size: 0.95rem;
  line-height: 1.7;
  color: rgb(75 85 99);
  max-width: 30rem;
}
:global(.dark) .rm-hero__subtitle {
  color: rgb(156 163 175);
}

/* 统计：编辑式三列,中间细线分隔,不再使用方块卡 */
.rm-hero__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  margin: 0;
  padding: 1rem 0 0.25rem;
  border-top: 1px solid rgb(229 231 235);
}
:global(.dark) .rm-hero__stats {
  border-top-color: rgb(31 41 55);
}

.rm-stat {
  position: relative;
  padding: 0.5rem 0.75rem 0.25rem;
  display: flex;
  flex-direction: column-reverse;
  gap: 0.25rem;
}
.rm-stat + .rm-stat {
  border-left: 1px solid rgb(229 231 235);
}
:global(.dark) .rm-stat + .rm-stat {
  border-left-color: rgb(31 41 55);
}

.rm-stat__label {
  font-size: 0.6875rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgb(107 114 128);
  font-family: var(--rm-mono);
  font-weight: 500;
}
:global(.dark) .rm-stat__label {
  color: rgb(156 163 175);
}

.rm-stat__value {
  margin: 0;
  font-family: var(--rm-serif);
  font-size: clamp(1.85rem, 1.4rem + 1.4vw, 2.5rem);
  line-height: 1;
  font-weight: 600;
  font-variant-numeric: tabular-nums lining-nums;
  letter-spacing: -0.015em;
}

.rm-stat--planned    .rm-stat__value { color: rgb(75 85 99); }
.rm-stat--inprogress .rm-stat__value {
  color: rgb(37 99 235);
  position: relative;
}
.rm-stat--done       .rm-stat__value { color: rgb(22 163 74); }

:global(.dark) .rm-stat--planned    .rm-stat__value { color: rgb(209 213 219); }
:global(.dark) .rm-stat--inprogress .rm-stat__value { color: rgb(96 165 250); }
:global(.dark) .rm-stat--done       .rm-stat__value { color: rgb(74 222 128); }

/* 进行中的数字带极轻微的呼吸高亮 */
.rm-stat--inprogress .rm-stat__value::after {
  content: '';
  position: absolute;
  left: -0.25rem;
  top: 50%;
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 9999px;
  background: rgb(59 130 246);
  transform: translateY(-50%);
  animation: rm-pulse 2.6s ease-in-out infinite;
  box-shadow: 0 0 0 0 rgb(59 130 246 / 0.4);
}
@keyframes rm-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgb(59 130 246 / 0.45); }
  50%      { box-shadow: 0 0 0 5px rgb(59 130 246 / 0); }
}
</style>
