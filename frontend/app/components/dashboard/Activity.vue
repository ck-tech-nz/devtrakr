<template>
  <div class="section-card">
    <button
      class="section-header section-toggle"
      :class="{ 'section-toggle--collapsed': !show }"
      type="button"
      @click="show = !show"
    >
      <h3 class="section-title">
        最近动态
        <span class="section-badge">{{ items.length }}</span>
      </h3>
      <div class="section-toggle-right">
        <NuxtLink to="/app/issues" class="section-link" @click.stop>查看全部</NuxtLink>
        <UIcon :name="show ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
      </div>
    </button>
    <div v-if="show" class="activity-list">
      <NuxtLink
        v-for="item in items"
        :key="item.id"
        :to="item.issue_id ? `/app/issues/${item.issue_id}` : '#'"
        class="activity-row"
      >
        <div class="activity-avatar" :style="{ backgroundColor: avatarColor(item.user_name) }">
          {{ avatarInitial(item.user_name) }}
        </div>
        <span class="activity-message">{{ activityMessage(item) }}</span>
        <span class="activity-time">{{ item.created_at ? timeAgo(item.created_at) : '' }}</span>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { timeAgo } from '~/utils/timeAgo'
defineProps<{ items: any[] }>()
const show = ref(false)

function activityMessage(item: any): string {
  const name = item.user_name || '未知用户'
  const issueRef = item.issue_id ? `#${item.issue_id}` : ''
  const title = item.issue_title ? `「${item.issue_title}」` : ''
  switch (item.action) {
    case 'created': return `${name} 创建了 ${issueRef}${title}`
    case 'resolved': return `${name} 解决了 ${issueRef}${title}`
    case 'status_changed': return `${name} 更新了 ${issueRef} 的状态${item.detail ? '：' + item.detail : ''}`
    case 'assigned': return `${name} 分配了 ${issueRef}${item.detail ? ' 给 ' + item.detail : ''}`
    case 'priority_changed': return `${name} 修改了 ${issueRef} 的优先级${item.detail ? '：' + item.detail : ''}`
    case 'commented': return `${name} 评论了 ${issueRef}${title}`
    default: return `${name} ${item.action} ${issueRef} ${item.detail || ''}`.trim()
  }
}

const AVATAR_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899']
function avatarColor(name?: string): string {
  const text = name || '?'
  let hash = 0
  for (const c of text) hash = (hash + c.charCodeAt(0)) % AVATAR_COLORS.length
  return AVATAR_COLORS[hash] ?? AVATAR_COLORS[0]!
}
function avatarInitial(name?: string): string {
  const text = (name || '?').trim()
  return text.slice(0, 1) || '?'
}
</script>

<style scoped>
.section-card { background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 1.25rem; }
:root.dark .section-card { background-color: #1f2937; border-color: #374151; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
.section-title { font-size: 0.875rem; font-weight: 600; color: #111827; display: flex; align-items: center; gap: 0.5rem; }
:root.dark .section-title { color: #f3f4f6; }
.section-badge { font-size: 0.75rem; font-weight: 500; color: #9ca3af; }
.section-link { font-size: 0.75rem; color: #7c3aed; transition: color 0.15s; }
.section-link:hover { color: #6d28d9; }
.section-toggle { width: 100%; background: transparent; border: 0; cursor: pointer; padding: 0; font: inherit; color: inherit; text-align: left; }
.section-toggle--collapsed { margin-bottom: 0; }
.section-toggle:hover .section-title { color: #7c3aed; }
:root.dark .section-toggle:hover .section-title { color: #c4b5fd; }
.section-toggle-right { display: flex; align-items: center; gap: 0.625rem; }
.activity-list { display: flex; flex-direction: column; max-height: 24rem; overflow-y: auto; }
.activity-row { display: flex; align-items: center; gap: 0.75rem; padding: 0.625rem 0.5rem; margin: 0 -0.5rem; border-radius: 0.375rem; transition: background-color 0.15s; }
.activity-row:not(:last-child) { border-bottom: 1px solid #f3f4f6; border-radius: 0; }
:root.dark .activity-row:not(:last-child) { border-bottom-color: rgba(255, 255, 255, 0.04); }
.activity-row:hover { background-color: #f9fafb; }
:root.dark .activity-row:hover { background-color: rgba(255, 255, 255, 0.03); }
.activity-avatar { width: 1.75rem; height: 1.75rem; border-radius: 9999px; display: flex; align-items: center; justify-content: center; color: #ffffff; font-size: 0.6875rem; font-weight: 600; flex-shrink: 0; }
.activity-message { flex: 1; font-size: 0.8125rem; color: #4b5563; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .activity-message { color: #9ca3af; }
.activity-time { font-size: 0.6875rem; color: #9ca3af; flex-shrink: 0; white-space: nowrap; }
</style>
