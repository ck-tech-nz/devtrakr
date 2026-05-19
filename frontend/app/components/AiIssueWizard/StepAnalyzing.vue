<template>
  <div class="step-analyzing">
    <div class="spinner-row">
      <UIcon name="i-heroicons-cpu-chip" class="w-5 h-5 text-crystal-500 animate-spin" />
      <span class="title">AI 正在分析…</span>
      <span class="latency-hint">通常 6-8 秒</span>
    </div>

    <div class="step-list">
      <div v-for="s in steps" :key="s.step" class="step-line" :class="`step-line--${s.status}`">
        <UIcon v-if="s.status === 'done'" name="i-heroicons-check-circle" class="w-4 h-4 text-emerald-500" />
        <UIcon v-else-if="s.status === 'error'" name="i-heroicons-x-circle" class="w-4 h-4 text-rose-500" />
        <span v-else class="dot" />
        <span class="label">{{ s.label }}{{ s.status === 'pending' ? '…' : '' }}</span>
      </div>
    </div>

    <p v-if="errorMessage" class="error-msg">{{ errorMessage }}</p>

    <div v-if="errorMessage" class="actions">
      <UButton variant="outline" color="neutral" size="sm" @click="emit('retry')">重试</UButton>
      <UButton variant="ghost" color="neutral" size="sm" @click="emit('back')">重新描述</UButton>
    </div>
  </div>
</template>

<script setup lang="ts">
type StepStatus = 'pending' | 'running' | 'done' | 'error'
type StepProgress = { step: 1 | 2 | 3; label: string; status: StepStatus }

defineProps<{ steps: StepProgress[]; errorMessage: string }>()
const emit = defineEmits<{ retry: []; back: [] }>()
</script>

<style scoped>
.step-analyzing { display: flex; flex-direction: column; gap: 1rem; padding: 1rem 0; }
.spinner-row { display: flex; align-items: center; gap: 0.5rem; }
.title { font-size: 0.875rem; font-weight: 500; color: #374151; }
:root.dark .title { color: #e5e7eb; }

.step-list { display: flex; flex-direction: column; gap: 0.5rem; padding-left: 1.5rem; }
.step-line { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8125rem; color: #6b7280; }
.step-line--done { color: #059669; }
.step-line--error { color: #dc2626; }
.dot {
  width: 0.5rem; height: 0.5rem; border-radius: 9999px;
  background-color: #d1d5db; animation: pulse 1s infinite alternate;
}
@keyframes pulse { from { opacity: 0.4; } to { opacity: 1; } }

.error-msg { font-size: 0.8125rem; color: #dc2626; }
.actions { display: flex; gap: 0.5rem; }
.latency-hint {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-left: auto;
}
:root.dark .latency-hint { color: #6b7280; }
</style>
