<template>
  <div class="flex flex-col gap-1 w-32 select-none" title="按优先级筛选">
    <input
      type="range"
      min="0"
      :max="STOPS.length - 1"
      step="1"
      :value="index"
      class="priority-range"
      :style="{ '--thumb-color': STOPS[index]?.cssColor, background: trackGradient }"
      aria-label="优先级筛选"
      @input="onInput"
    >
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

function onInput(e: Event) {
  const i = Number((e.target as HTMLInputElement).value)
  emit('update:modelValue', STOPS.value[i]?.value ?? '')
}
</script>

<style scoped>
.priority-range {
  appearance: none;
  -webkit-appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 9999px;
  cursor: pointer;
}
.priority-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 9999px;
  background-color: var(--thumb-color, var(--color-crystal-500));
  border: 2px solid white;
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.35);
  transition: background-color 0.15s ease;
}
.priority-range::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 9999px;
  background-color: var(--thumb-color, var(--color-crystal-500));
  border: 2px solid white;
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.35);
  transition: background-color 0.15s ease;
}
:root.dark .priority-range::-webkit-slider-thumb {
  border-color: var(--color-gray-900);
}
:root.dark .priority-range::-moz-range-thumb {
  border-color: var(--color-gray-900);
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
