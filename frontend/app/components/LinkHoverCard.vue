<template>
  <Teleport to="body">
    <div
      v-if="visible && type"
      class="link-hover-card"
      :class="`is-${type}`"
      :style="{ top: top + 'px', left: left + 'px' }"
      @mouseenter="emit('enter')"
      @mouseleave="emit('leave')"
    >
      <!-- 内部问题引用 -->
      <template v-if="type === 'issue'">
        <div v-if="issueLoading" class="lhc-state">加载中…</div>
        <div v-else-if="issueError || !issue" class="lhc-state">加载失败</div>
        <a v-else class="lhc-issue" :href="`/app/issues/${issue.id}`" @click.prevent="goIssue">
          <div class="lhc-issue-head">
            <span class="lhc-no">#问题-{{ String(issue.id).padStart(3, '0') }}</span>
            <span class="lhc-title">{{ issue.title }}</span>
          </div>
          <div class="lhc-meta">
            <span class="lhc-pill" :style="{ background: statusColor, color: '#fff' }">{{ statusText }}</span>
            <span class="lhc-pill" :style="{ background: prioColor, color: '#fff' }">{{ prioText }}</span>
          </div>
          <div class="lhc-foot">
            <img v-if="issue.assignee_avatar" class="lhc-avatar" :src="issue.assignee_avatar" alt="">
            <span class="lhc-assignee">{{ issue.assignee_name || '未分配' }}</span>
            <span class="lhc-time">{{ timeText }}</span>
          </div>
        </a>
      </template>

      <!-- 外部 URL -->
      <template v-else-if="type === 'external'">
        <div class="lhc-urlbar">
          <span class="lhc-host" :title="url || ''">{{ host }}</span>
          <a class="lhc-open" :href="url || '#'" target="_blank" rel="noopener noreferrer">在新标签打开 ↗</a>
        </div>
        <div v-if="iframeFallback" class="lhc-fallback">
          <img v-if="faviconUrl" class="lhc-favicon" :src="faviconUrl" alt="">
          <span>该站点不允许内嵌预览</span>
        </div>
        <!-- allow-same-origin 在此安全:外链经 matchPreviewAnchor 保证跨源,
             框架无法访问父页面源资源;allow-scripts 是实时预览所必需。
             刻意不含 allow-top-navigation,防止被嵌页面劫持顶层标签。 -->
        <iframe
          v-else
          class="lhc-iframe"
          :src="url || ''"
          :title="`外部预览: ${host || url || ''}`"
          sandbox="allow-scripts allow-same-origin allow-popups"
          referrerpolicy="no-referrer"
          @load="emit('iframe-load')"
        />
      </template>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { IssuePreview } from '~/composables/useLinkPreview'

const props = defineProps<{
  visible: boolean
  top: number
  left: number
  type: 'issue' | 'external' | null
  issue: IssuePreview | null
  issueLoading: boolean
  issueError: boolean
  url: string | null
  iframeFallback: boolean
}>()

const emit = defineEmits<{ enter: []; leave: []; 'iframe-load': [] }>()

const statusColor = computed(() => (props.issue ? statusMainColor(props.issue.status) : '#9ca3af'))
const statusText = computed(() => (props.issue ? statusLabel(props.issue.status) : ''))
const prioColor = computed(() => (props.issue && priorityBadgeStyle(props.issue.priority)?.['--prio']) || '#9ca3af')
const prioText = computed(() => (props.issue ? priorityLabel(props.issue.priority) : ''))
const timeText = computed(() => (props.issue ? formatDate(props.issue.updated_at || props.issue.created_at) : ''))
const host = computed(() => { try { return new URL(props.url || '').host } catch { return props.url || '' } })
const faviconUrl = computed(() => { try { const u = new URL(props.url || ''); return `${u.origin}/favicon.ico` } catch { return '' } })

function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function goIssue() {
  if (props.issue) navigateTo(`/app/issues/${props.issue.id}`)
}
</script>

<style scoped>
.link-hover-card {
  position: absolute;
  z-index: 60;
  width: 360px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  font-size: 0.85rem;
  color: #374151;
  overflow: hidden;
}
:root.dark .link-hover-card { background: #1f2937; border-color: #374151; color: #d1d5db; }

.lhc-state { padding: 0.75rem 0.9rem; color: #6b7280; }
.lhc-issue { display: block; padding: 0.75rem 0.9rem; text-decoration: none; color: inherit; }
.lhc-issue:hover { background: #f9fafb; }
:root.dark .lhc-issue:hover { background: #374151; }
.lhc-issue-head { display: flex; gap: 0.5rem; align-items: baseline; }
.lhc-no { font-size: 0.75rem; font-weight: 600; color: #15803d; flex-shrink: 0; }
:root.dark .lhc-no { color: #86efac; }
.lhc-title { font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .lhc-title { color: #f3f4f6; }
.lhc-meta { display: flex; gap: 0.4rem; margin: 0.5rem 0; }
.lhc-pill { padding: 0.1em 0.5em; border-radius: 999px; font-size: 0.72rem; font-weight: 600; }
.lhc-foot { display: flex; gap: 0.4rem; align-items: center; color: #6b7280; font-size: 0.75rem; }
.lhc-avatar { width: 1.1rem; height: 1.1rem; border-radius: 999px; object-fit: cover; }
.lhc-time { margin-left: auto; }
.is-external { width: 480px; }
.lhc-urlbar { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e5e7eb; background: #f9fafb; }
:root.dark .lhc-urlbar { border-color: #374151; background: #111827; }
.lhc-host { font-size: 0.75rem; color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lhc-open { margin-left: auto; flex-shrink: 0; font-size: 0.72rem; color: #2563eb; text-decoration: none; }
:root.dark .lhc-open { color: #60a5fa; }
.lhc-iframe { display: block; width: 100%; height: 320px; border: 0; background: #fff; }
.lhc-fallback { display: flex; align-items: center; gap: 0.5rem; padding: 1rem; color: #6b7280; }
.lhc-favicon { width: 1.1rem; height: 1.1rem; }
</style>
