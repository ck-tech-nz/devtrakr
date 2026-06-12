<template>
  <time v-if="text" :datetime="date" :title="fullTitle">{{ text }}</time>
</template>

<script setup lang="ts">
// 智能时间标签:今天显示时分,昨天/前天显示文字,更早显示具体日期;悬停展示完整时间。
const props = defineProps<{ date: string }>()

const text = computed(() => formatCardTime(props.date))
const fullTitle = computed(() => {
  const d = new Date(props.date)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('zh-CN')
})
</script>
