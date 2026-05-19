<template>
  <div ref="containerEl" class="flex items-center gap-[1px] w-full overflow-hidden">
    <div
      v-for="n in placeholderCount" :key="`p-${n}`"
      class="w-[4px] h-5 rounded-[1px] bg-gray-200 dark:bg-gray-700 shrink-0"
    />
    <UTooltip
      v-for="(check, idx) in displayChecks" :key="`${check.checked_at}-${idx}`"
      :text="tooltipFor(check)"
    >
      <div
        class="w-[4px] h-5 rounded-[1px] shrink-0"
        :class="check.is_up ? 'bg-green-500' : 'bg-red-500'"
      />
    </UTooltip>
  </div>
</template>

<script setup lang="ts">
interface Check {
  checked_at: string
  is_up: boolean
  status_code: number | null
  response_ms: number | null
  error: string
}

const props = defineProps<{
  checks: Check[]
  /** Hard cap on bars regardless of container width. Defaults to 120. */
  maxBars?: number
}>()

const BAR_WIDTH = 4
const BAR_GAP = 1
const SLOT_WIDTH = BAR_WIDTH + BAR_GAP

const containerEl = ref<HTMLElement | null>(null)
const containerWidth = ref(0)
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!containerEl.value) return
  containerWidth.value = containerEl.value.clientWidth
  observer = new ResizeObserver((entries) => {
    for (const entry of entries) {
      containerWidth.value = entry.contentRect.width
    }
  })
  observer.observe(containerEl.value)
})

onUnmounted(() => {
  if (observer) {
    observer.disconnect()
    observer = null
  }
})

const hardCap = computed(() => props.maxBars ?? 120)

/** How many bars fit in the current container width. */
const fitCount = computed(() => {
  if (containerWidth.value <= 0) return hardCap.value
  return Math.max(1, Math.floor((containerWidth.value + BAR_GAP) / SLOT_WIDTH))
})

/** Effective visible bar count: bounded by both the container fit and the hard cap. */
const visibleCount = computed(() => Math.min(fitCount.value, hardCap.value))

/** Newest-first input reversed to oldest-left/newest-right, keeping only the newest `visibleCount`. */
const displayChecks = computed(() => {
  const newestFirst = props.checks.slice(0, visibleCount.value)
  return newestFirst.reverse()
})

/** Pad the left side with neutral placeholders when there aren't enough real checks yet. */
const placeholderCount = computed(() =>
  Math.max(0, visibleCount.value - displayChecks.value.length),
)

function tooltipFor(check: Check): string {
  const ts = new Date(check.checked_at).toLocaleString('zh-CN', { hour12: false })
  if (check.is_up) return `已恢复 - ${ts}`
  const err = check.error ? ` (${check.error})` : ''
  return `宕机 - ${ts}${err}`
}
</script>
