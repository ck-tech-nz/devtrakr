<template>
  <!-- 可排序表头:点击三态切换(无 → 升 → 降 → 无);未排序时图标淡显,提示「可排序」 -->
  <button
    type="button"
    class="sort-header"
    :class="{ 'is-active': dir !== null }"
    :title="dir === 'asc' ? '升序(点击切换降序)' : dir === 'desc' ? '降序(点击取消排序)' : '点击升序排序'"
    @click.stop="$emit('toggle')"
  >
    <span>{{ label }}</span>
    <UIcon :name="icon" class="sort-icon" :class="{ 'sort-icon-idle': dir === null }" />
  </button>
</template>

<script setup lang="ts">
const props = defineProps<{
  label: string
  // 当前列排序方向:null 表示未参与排序
  dir: 'asc' | 'desc' | null
}>()
defineEmits<{ toggle: [] }>()

const icon = computed(() => {
  if (props.dir === 'asc') return 'i-heroicons-chevron-up'
  if (props.dir === 'desc') return 'i-heroicons-chevron-down'
  return 'i-heroicons-chevron-up-down'
})
</script>

<style scoped>
.sort-header {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  user-select: none;
  color: inherit;
  font: inherit;
  transition: color 0.12s;
}
.sort-header:hover {
  color: var(--color-crystal-600);
}
:root.dark .sort-header:hover {
  color: var(--color-crystal-400);
}
.sort-header.is-active {
  color: var(--color-crystal-600);
}
:root.dark .sort-header.is-active {
  color: var(--color-crystal-400);
}
.sort-icon {
  width: 0.875rem;
  height: 0.875rem;
  flex-shrink: 0;
}
/* 未排序:图标常驻但淡显,鼠标移入表头时点亮,明确「可排序」 */
.sort-icon-idle {
  opacity: 0;
  transition: opacity 0.12s;
}
.sort-header:hover .sort-icon-idle {
  opacity: 0.45;
}
</style>
