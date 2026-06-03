<template>
  <span class="inline-flex items-center gap-0.5">
    <UIcon
      v-for="n in 5"
      :key="n"
      name="i-heroicons-star-solid"
      :class="[
        sizeClass,
        n <= rounded ? 'text-amber-400' : 'text-gray-200 dark:text-gray-700',
      ]"
    />
    <span v-if="showValue && rounded > 0" class="ml-1 text-xs tabular-nums text-gray-500 dark:text-gray-400">{{ rounded }}</span>
  </span>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  value: number
  size?: 'xs' | 'sm'
  showValue?: boolean
}>(), {
  size: 'sm',
  showValue: false,
})

const rounded = computed(() => Math.max(0, Math.min(5, Math.round(Number(props.value) || 0))))
const sizeClass = computed(() => (props.size === 'xs' ? 'w-3 h-3' : 'w-3.5 h-3.5'))
</script>
