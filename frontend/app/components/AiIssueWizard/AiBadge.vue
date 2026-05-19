<template>
  <span class="ai-badge" :class="kindClass">{{ label }}</span>
</template>

<script setup lang="ts">
const props = defineProps<{ kind: 'generated' | 'inferred' }>()

const label = computed(() => (props.kind === 'generated' ? 'AI 生成' : 'AI 推断'))
const kindClass = computed(() => `ai-badge--${props.kind}`)
</script>

<style scoped>
.ai-badge {
  display: inline-flex;
  align-items: center;
  margin-left: 0.5rem;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.6875rem;
  font-weight: 500;
  line-height: 1;
}
.ai-badge--generated {
  color: #2563eb;
  background-color: #dbeafe;
}
.ai-badge--inferred {
  color: #7c3aed;
  background-color: #ede9fe;
}
:root.dark .ai-badge--generated {
  color: #93c5fd;
  background-color: rgba(37, 99, 235, 0.15);
}
:root.dark .ai-badge--inferred {
  color: #c4b5fd;
  background-color: rgba(124, 58, 237, 0.15);
}
</style>
