<template>
  <div class="flex items-center gap-[1px]">
    <UTooltip
      v-for="(check, idx) in displayChecks"
      :key="`${check.checked_at}-${idx}`"
      :text="tooltipFor(check)"
    >
      <div
        class="w-[4px] h-5 rounded-[1px]"
        :class="check.is_up ? 'bg-green-500' : 'bg-red-500'"
      />
    </UTooltip>
    <div
      v-for="n in placeholderCount"
      :key="`p-${n}`"
      class="w-[4px] h-5 rounded-[1px] bg-gray-200 dark:bg-gray-700"
    />
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
  maxBars?: number
}>()

const maxBars = computed(() => props.maxBars ?? 60)

const displayChecks = computed(() => {
  // Caller sends newest first; reverse so oldest is on the left.
  return [...props.checks].reverse().slice(-maxBars.value)
})

const placeholderCount = computed(() => Math.max(0, maxBars.value - displayChecks.value.length))

function tooltipFor(check: Check): string {
  const ts = new Date(check.checked_at).toLocaleString('zh-CN', { hour12: false })
  if (check.is_up) return `已恢复 - ${ts}`
  const err = check.error ? ` (${check.error})` : ''
  return `宕机 - ${ts}${err}`
}
</script>
