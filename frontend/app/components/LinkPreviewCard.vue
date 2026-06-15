<template>
  <div class="link-preview-card" :class="`is-${type}`">
    <template v-if="type === 'issue'">
      <div v-if="issueLoading" class="lpc-state">加载中…</div>
      <div v-else-if="issueError || !issue" class="lpc-state">加载失败</div>
      <a v-else class="lpc-issue" :href="`/app/issues/${issue.id}`" @click.prevent="goIssue">
        <div class="lpc-head">
          <span class="lpc-no">#问题-{{ String(issue.id).padStart(3, '0') }}</span>
          <span class="lpc-title">{{ issue.title }}</span>
        </div>
        <div class="lpc-meta">
          <span class="lpc-pill" :style="{ background: statusColor, color: '#fff' }">{{ statusText }}</span>
          <span class="lpc-pill" :style="{ background: prioColor, color: '#fff' }">{{ prioText }}</span>
        </div>
        <div class="lpc-foot">
          <img v-if="issueAvatarUrl" class="lpc-avatar" :src="issueAvatarUrl" alt="">
          <span v-else class="lpc-avatar lpc-avatar-fallback">{{ (issue.assignee_name || '?').slice(0, 1) }}</span>
          <span class="lpc-assignee">{{ issue.assignee_name || '未分配' }}</span>
          <span class="lpc-time">{{ timeText }}</span>
        </div>
      </a>
    </template>

    <template v-else-if="type === 'github'">
      <div v-if="githubLoading || !github" class="lpc-state">{{ githubLoading ? '加载中…' : '加载失败' }}</div>
      <a v-else class="lpc-issue" :href="github.html_url" target="_blank" rel="noopener noreferrer" @click.prevent="goGithub">
        <div class="lpc-head">
          <span class="lpc-no">{{ github.kind === 'pr' ? 'PR' : 'Issue' }} #{{ github.number }}</span>
          <span class="lpc-title">{{ github.title }}</span>
        </div>
        <div class="lpc-meta">
          <span class="lpc-pill" :style="{ background: ghStateColor, color: '#fff' }">{{ ghStateText }}</span>
        </div>
        <div class="lpc-foot">
          <img v-if="github.author_avatar" class="lpc-avatar" :src="github.author_avatar" alt="">
          <span v-else class="lpc-avatar lpc-avatar-fallback">{{ (github.author_login || '?').slice(0, 1) }}</span>
          <span class="lpc-assignee">{{ github.author_login }}</span>
          <span class="lpc-time">{{ github.repo_full_name }}</span>
        </div>
      </a>
    </template>

    <template v-else-if="type === 'external'">
      <div class="lpc-urlbar">
        <img v-if="faviconUrl" class="lpc-favicon" :src="faviconUrl" alt="">
        <span class="lpc-host" :title="url || ''">{{ host }}</span>
        <a class="lpc-open" :href="url || '#'" target="_blank" rel="noopener noreferrer">在新标签打开 ↗</a>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { IssuePreview, GithubPreview } from '~/composables/useLinkPreview'

const props = defineProps<{
  type: 'issue' | 'external' | 'github' | null
  issue: IssuePreview | null
  issueLoading: boolean
  issueError: boolean
  github: GithubPreview | null
  githubLoading: boolean
  url: string | null
}>()

const { resolveAvatarUrl } = useAvatars()
const issueAvatarUrl = computed(() => (props.issue?.assignee_avatar ? resolveAvatarUrl(props.issue.assignee_avatar) : ''))

const statusColor = computed(() => (props.issue ? statusMainColor(props.issue.status) : '#9ca3af'))
const statusText = computed(() => (props.issue ? statusLabel(props.issue.status) : ''))
const prioColor = computed(() => (props.issue && priorityBadgeStyle(props.issue.priority)?.['--prio']) || '#9ca3af')
const prioText = computed(() => (props.issue ? priorityLabel(props.issue.priority) : ''))
const timeText = computed(() => (props.issue ? formatDate(props.issue.updated_at || props.issue.created_at) : ''))
const host = computed(() => { try { return new URL(props.url || '').host } catch { return props.url || '' } })
const faviconUrl = computed(() => { try { const u = new URL(props.url || ''); return `${u.origin}/favicon.ico` } catch { return '' } })

const ghStateColor = computed(() => {
  const s = props.github?.state
  return s === 'merged' ? '#8957e5' : s === 'closed' ? '#cf222e' : '#1a7f37'
})
const ghStateText = computed(() => {
  const s = props.github?.state
  return s === 'merged' ? 'Merged' : s === 'closed' ? 'Closed' : 'Open'
})
function goGithub() { if (props.github?.html_url) window.open(props.github.html_url, '_blank', 'noopener') }

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
.link-preview-card {
  width: 360px;
  max-width: calc(100vw - 32px);
  margin: 0.4em 0;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  font-size: 0.85rem;
  color: #374151;
  overflow: hidden;
}
:root.dark .link-preview-card { background: #1f2937; border-color: #374151; color: #d1d5db; }

.lpc-state { padding: 0.75rem 0.9rem; color: #6b7280; }
.lpc-issue { display: block; padding: 0.75rem 0.9rem; text-decoration: none; color: inherit; }
.lpc-issue:hover { background: #f9fafb; }
:root.dark .lpc-issue:hover { background: #374151; }
.lpc-head { display: flex; gap: 0.5rem; align-items: baseline; }
.lpc-no { font-size: 0.75rem; font-weight: 600; color: #15803d; flex-shrink: 0; }
:root.dark .lpc-no { color: #86efac; }
.lpc-title { font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .lpc-title { color: #f3f4f6; }
.lpc-meta { display: flex; gap: 0.4rem; margin: 0.5rem 0; }
.lpc-pill { padding: 0.1em 0.5em; border-radius: 999px; font-size: 0.72rem; font-weight: 600; }
.lpc-foot { display: flex; gap: 0.4rem; align-items: center; color: #6b7280; font-size: 0.75rem; }
.lpc-avatar { width: 1.1rem; height: 1.1rem; border-radius: 999px; object-fit: cover; }
.lpc-avatar-fallback {
  display: inline-flex; align-items: center; justify-content: center;
  background: #e5e7eb; color: #4b5563; font-size: 0.7rem; font-weight: 600;
}
:root.dark .lpc-avatar-fallback { background: #374151; color: #d1d5db; }
.lpc-time { margin-left: auto; }
.lpc-urlbar { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.6rem; }
:root.dark .lpc-urlbar { border-color: #374151; background: #111827; }
.lpc-host { font-size: 0.75rem; color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lpc-open { margin-left: auto; flex-shrink: 0; font-size: 0.72rem; color: #2563eb; text-decoration: none; }
:root.dark .lpc-open { color: #60a5fa; }
.lpc-favicon { width: 1rem; height: 1rem; flex-shrink: 0; }
</style>
