<template>
  <div class="flex flex-col gap-2.5 w-32 select-none" title="按优先级筛选">
    <div class="relative">
      <!-- 可见轨道独立成层并以 top:50% 居中,与玻璃 thumb 共用同一垂直基准对齐;
           原生 range 的可见轨道并不落在 input 盒子的几何中心,直接用 input 背景会让轨道偏高 -->
      <div class="priority-track" :style="{ background: trackGradient }" aria-hidden="true" />
      <input
        type="range"
        min="0"
        :max="STOPS.length - 1"
        step="1"
        :value="index"
        class="priority-range"
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
        :bezel-depth="0.05"
        :bezel-width="0.1"
        :blur="0.5"
        :saturation="160"
      />
    </div>
    <!-- relative 让 span 的 offsetParent 是本行,offsetLeft 才是行内坐标(供 thumb 对齐测量) -->
    <div ref="labelsRow" class="relative flex justify-between text-[10px] leading-none text-gray-400">
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

// 轨道本身就是优先级色系渐变: 全部(crystal-400,比 thumb 浅一档) → 各档主色(低→高),均匀分布
const trackGradient = computed(() => {
  const colors = STOPS.value.map((s, i) => (i === 0 ? 'var(--color-crystal-400)' : s.cssColor))
  const n = colors.length - 1
  return `linear-gradient(to right, ${colors.map((c, i) => `${c} ${n ? Math.round(i * 100 / n) : 0}%`).join(', ')})`
})

const index = computed(() => {
  const i = STOPS.value.findIndex(s => s.value === props.modelValue)
  return i === -1 ? 0 : i
})

// 玻璃 thumb 对齐当前档 label 的正上方:实测各 label 中心 x(labels 行与轨道同宽)
const labelsRow = ref<HTMLElement | null>(null)
const labelCenters = ref<number[]>([])

function measureLabels() {
  const kids = labelsRow.value ? (Array.from(labelsRow.value.children) as HTMLElement[]) : []
  labelCenters.value = kids.map(el => el.offsetLeft + el.offsetWidth / 2)
}
onMounted(() => nextTick(measureLabels))
watch(STOPS, () => nextTick(measureLabels))  // 站点设置加载后 label 文案会变,重新测量

const thumbLeft = computed(() => {
  const c = labelCenters.value[index.value]
  if (c) return `${c}px`
  // 测量前兜底:近似两端 2 字 label 的半宽(10px)做内缩
  const n = STOPS.value.length - 1
  const t = n ? index.value / n : 0
  return `calc(${t * 100}% + ${(0.5 - t) * 20}px)`
})

function onInput(e: Event) {
  const i = Number((e.target as HTMLInputElement).value)
  emit('update:modelValue', STOPS.value[i]?.value ?? '')
}
</script>

<style scoped>
/* 可见轨道:绝对定位 + top:50% 居中,与玻璃 thumb 同一垂直中心,规避原生轨道偏高 */
.priority-track {
  position: absolute;
  top: 50%;
  left: 0;
  width: 100%;
  height: 6px;
  transform: translateY(-50%);
  border-radius: 9999px;
  pointer-events: none;
}
/* input 仅保留交互(透明),可见外观交给上方 .priority-track 与叠加的 .priority-thumb */
.priority-range {
  position: relative;
  appearance: none;
  -webkit-appearance: none;
  display: block;
  width: 100%;
  height: 6px;
  margin: 0;
  background: transparent;
  border-radius: 9999px;
  cursor: pointer;
}
/* 原生 thumb 只留交互,外观全部交给叠加的 .priority-thumb;
   宽 20px 时浏览器的行程内缩(半 thumb=10px)正好贴近两端 2 字 label 的中心,
   按下/拖拽的位置映射与玻璃 thumb 的 label 对齐定位基本一致 */
.priority-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 9999px;
  background: transparent;
  border: none;
}
.priority-range::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 9999px;
  background: transparent;
  border: none;
}
/* 原生 thumb 透明化后键盘焦点不可见,补一圈轨道外焦点环 */
.priority-range:focus-visible {
  outline: 2px solid var(--color-crystal-500);
  outline-offset: 4px;
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
