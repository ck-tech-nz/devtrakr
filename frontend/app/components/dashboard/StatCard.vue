<template>
  <NuxtLink v-if="to" :to="to" class="stat-card stat-card--link">
    <div class="stat-header">
      <span class="stat-label">{{ label }}</span>
      <UIcon :name="icon" class="stat-icon" :class="iconToneClass" />
    </div>
    <div class="stat-value">{{ value }}</div>
    <div v-if="deltaText" class="stat-delta" :class="deltaToneClass">
      <span class="stat-delta-arrow">{{ deltaArrow }}</span>
      <span>{{ deltaText }}</span>
    </div>
  </NuxtLink>
  <div v-else class="stat-card">
    <div class="stat-header">
      <span class="stat-label">{{ label }}</span>
      <UIcon :name="icon" class="stat-icon" :class="iconToneClass" />
    </div>
    <div class="stat-value">{{ value }}</div>
    <div v-if="deltaText" class="stat-delta" :class="deltaToneClass">
      <span class="stat-delta-arrow">{{ deltaArrow }}</span>
      <span>{{ deltaText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  label: string
  value: string | number
  icon: string
  // 图标色调：success / warning / info / primary
  tone?: 'success' | 'warning' | 'info' | 'primary'
  // 数值变化（正数 = 上升，负数 = 下降，null = 不显示）
  delta?: number | null
  // 变化说明（例如 "较上周"、"较昨日"、"本周新增"）
  deltaLabel?: string
  // delta 数值的展示单位："percent" | "absolute"
  deltaUnit?: 'percent' | 'absolute'
  // 当 delta > 0 时是否视为正面：解决数上涨为正面（绿色），待分配上涨为负面（红色）
  positiveDirection?: 'up' | 'down'
  // 点击跳转目标（如 "/app/issues?status=待分配"）；为空时不可点击
  to?: string
}>()

const iconToneClass = computed(() => {
  switch (props.tone) {
    case 'success': return 'stat-icon--success'
    case 'warning': return 'stat-icon--warning'
    case 'info': return 'stat-icon--info'
    case 'primary': return 'stat-icon--primary'
    default: return 'stat-icon--muted'
  }
})

const deltaText = computed(() => {
  if (props.delta === null || props.delta === undefined) return ''
  const unit = props.deltaUnit ?? 'percent'
  const value = Math.abs(props.delta)
  const formatted = unit === 'percent' ? `${value}%` : `${value}`
  const suffix = props.deltaLabel ? ` ${props.deltaLabel}` : ''
  return `${formatted}${suffix}`
})

const deltaArrow = computed(() => {
  if (props.delta === null || props.delta === undefined) return ''
  if (props.delta === 0) return '·'
  return props.delta > 0 ? '↑' : '↓'
})

const deltaToneClass = computed(() => {
  if (props.delta === null || props.delta === undefined || props.delta === 0) {
    return 'stat-delta--neutral'
  }
  const positive = props.positiveDirection ?? 'up'
  // 当 delta 与 positiveDirection 同向时显示绿色，反向显示红色
  const isPositive = (props.delta > 0 && positive === 'up') || (props.delta < 0 && positive === 'down')
  return isPositive ? 'stat-delta--up' : 'stat-delta--down'
})
</script>

<style scoped>
.stat-card {
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}
:root.dark .stat-card {
  background-color: #1f2937;
  border-color: #374151;
}
/* 可点击卡片：保留原视觉、添加 hover 反馈 */
.stat-card--link {
  text-decoration: none;
  color: inherit;
  cursor: pointer;
}
.stat-card--link:hover {
  box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}
:root.dark .stat-card--link:hover {
  box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.4);
}
.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.stat-label {
  font-size: 0.8125rem;
  color: #6b7280;
}
:root.dark .stat-label { color: #9ca3af; }
.stat-icon {
  width: 1.125rem;
  height: 1.125rem;
}
.stat-icon--success { color: #10b981; }
.stat-icon--warning { color: #f59e0b; }
.stat-icon--info { color: #3b82f6; }
.stat-icon--primary { color: #8b5cf6; }
.stat-icon--muted { color: #9ca3af; }
.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: #111827;
  line-height: 1.15;
  letter-spacing: -0.02em;
}
:root.dark .stat-value { color: #f3f4f6; }
.stat-delta {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
}
.stat-delta-arrow { font-weight: 600; }
.stat-delta--up { color: #10b981; }
.stat-delta--down { color: #ef4444; }
.stat-delta--neutral { color: #9ca3af; }
</style>
