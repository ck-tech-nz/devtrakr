<template>
  <div class="flex flex-col gap-2.5 w-32 select-none" title="按优先级筛选">
    <div class="relative">
      <input
        type="range"
        min="0"
        :max="STOPS.length - 1"
        step="1"
        :value="index"
        class="priority-range"
        :style="{ background: trackGradient }"
        aria-label="优先级筛选"
        @input="onInput"
      >
      <!-- 液态玻璃滑块(同 AI 对话「清空对话」按钮):原生 thumb 已透明化只留拖拽交互,
           这里按档位定位叠加 LiquidGlass 折射玻璃,当前档主色透进玻璃 -->
      <LiquidGlass
        aria-hidden="true"
        tabindex="-1"
        class="priority-thumb"
        :style="{ left: thumbLeft, '--thumb-color': STOPS[index]?.cssColor }"
        :bezel-depth="0.35"
        :bezel-width="0.35"
        :blur="0.5"
        :saturation="160"
      />
    </div>
    <div class="flex justify-between text-[10px] leading-none text-gray-400">
      <span
        v-for="(s, i) in STOPS"
        :key="s.value || 'all'"
        :class="i === index ? 'priority-stop-active' : ''"
        :style="i === index ? { '--stop-color': s.cssColor } : undefined"
      >{{ s.short }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const items = usePriorityItems()

// 低→紧急排列;'' 表示「全部」(不筛选,品牌色);各档主色来自站点设置(usePriority)
const STOPS = computed(() => [
  { value: '', short: '全部', cssColor: 'var(--color-crystal-500)' },
  ...items.value.slice().reverse().map(p => ({
    value: p.value,
    short: p.label,
    cssColor: isSafeHexColor(p.background) ? p.background : PRIORITY_FALLBACK_COLOR,
  })),
])

// 轨道本身就是优先级色系渐变: 全部(crystal) → 各档主色(低→高),均匀分布
const trackGradient = computed(() => {
  const colors = STOPS.value.map((s, i) => (i === 0 ? '#a78bfa' : s.cssColor))
  const n = colors.length - 1
  return `linear-gradient(to right, ${colors.map((c, i) => `${c} ${n ? Math.round(i * 100 / n) : 0}%`).join(', ')})`
})

const index = computed(() => {
  const i = STOPS.value.findIndex(s => s.value === props.modelValue)
  return i === -1 ? 0 : i
})

// 玻璃 thumb 以中心点定位:两端时中心点正好落在轨道最左/最右端(允许半个 thumb 悬出轨道)
const thumbLeft = computed(() => {
  const n = STOPS.value.length - 1
  const t = n ? index.value / n : 0
  return `${t * 100}%`
})

function onInput(e: Event) {
  const i = Number((e.target as HTMLInputElement).value)
  emit('update:modelValue', STOPS.value[i]?.value ?? '')
}
</script>

<style scoped>
.priority-range {
  appearance: none;
  -webkit-appearance: none;
  display: block;
  width: 100%;
  height: 6px;
  border-radius: 9999px;
  cursor: pointer;
}
/* 原生 thumb 只留交互,外观全部交给叠加的 .priority-thumb;
   做窄是因为浏览器把 thumb 限制在轨道内(行程 = 宽度 - thumb 宽),
   越窄按下/拖拽的位置映射越接近玻璃 thumb 的全程中心点定位 */
.priority-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 8px;
  height: 20px;
  border-radius: 9999px;
  background: transparent;
  border: none;
}
.priority-range::-moz-range-thumb {
  width: 8px;
  height: 20px;
  border-radius: 9999px;
  background: transparent;
  border: none;
}
/* iOS 26 Liquid Glass(同 .clear-btn 配方):折射由 LiquidGlass 的 backdrop-filter 提供,
   这里负责形态 — 当前档主色淡淡透进玻璃 + 上沿白高光/下沿暗线 + 浮起阴影 */
.priority-thumb {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 28px;
  height: 20px;
  padding: 0;
  border-radius: 9999px;
  pointer-events: none;
  background-image: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.12) 0%,
    rgba(180, 200, 220, 0.06) 50%,
    rgba(255, 255, 255, 0.14) 100%
  );
  background-color: color-mix(in srgb, var(--thumb-color, var(--color-crystal-500)) 30%, transparent);
  border: 1px solid rgba(0, 0, 0, 0.12);
  box-shadow:
    inset 0 1px 0.5px rgba(255, 255, 255, 0.65),
    inset 0 -1px 0.5px rgba(0, 0, 0, 0.08),
    0 4px 10px -2px rgba(15, 23, 42, 0.25),
    0 1px 3px rgba(15, 23, 42, 0.15);
  transition: left 0.15s ease, background-color 0.15s ease, transform 0.15s ease;
}
.priority-range:active + .priority-thumb {
  transform: translate(-50%, -50%) scale(1.12);
}
:root.dark .priority-thumb {
  border-color: rgba(255, 255, 255, 0.18);
  box-shadow:
    inset 0 1px 0.5px rgba(255, 255, 255, 0.25),
    inset 0 -1px 0.5px rgba(0, 0, 0, 0.3),
    0 4px 10px -2px rgba(0, 0, 0, 0.5);
}
/* 当前档位标签随档位主色着色;往深(浅)混一点保证可读性 */
.priority-stop-active {
  font-weight: 500;
  color: color-mix(in srgb, var(--stop-color) 60%, #374151);
}
:root.dark .priority-stop-active {
  color: color-mix(in srgb, var(--stop-color) 70%, #e5e7eb);
}
</style>
