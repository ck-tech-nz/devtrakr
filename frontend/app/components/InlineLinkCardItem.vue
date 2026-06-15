<template>
  <span class="inline-link-card">
    <LinkPreviewCard
      :type="state.type"
      :issue="state.issue"
      :issue-loading="state.issueLoading"
      :issue-error="state.issueError"
      :github="state.github"
      :github-loading="state.githubLoading"
      :url="state.url"
      @mouseenter="onEnter"
      @mouseleave="onLeave"
    />
    <Teleport to="body">
      <div
        v-if="iframe.visible"
        class="ilc-iframe-popup"
        :style="{ top: iframe.top + 'px', left: iframe.left + 'px' }"
        @mouseenter="cancelHide"
        @mouseleave="scheduleHide"
      >
        <div class="ilc-iframe-bar">
          <span>问题 #{{ match.issueId }}</span>
          <a :href="`/app/issues/${match.issueId}`" target="_blank" rel="noopener noreferrer">新标签打开 ↗</a>
        </div>
        <iframe class="ilc-iframe" :src="`/app/issues/${match.issueId}`" referrerpolicy="no-referrer" />
      </div>
    </Teleport>
  </span>
</template>

<script setup lang="ts">
import LinkPreviewCard from '~/components/LinkPreviewCard.vue'
import { fetchIssuePreview, fetchGithubPreview, type PreviewMatch, type IssuePreview, type GithubPreview } from '~/composables/useLinkPreview'

const props = defineProps<{ match: PreviewMatch }>()
const { api } = useApi()

const state = reactive<{
  type: 'issue' | 'external' | 'github' | null
  issue: IssuePreview | null; issueLoading: boolean; issueError: boolean
  github: GithubPreview | null; githubLoading: boolean
  url: string | null
}>({ type: null, issue: null, issueLoading: false, issueError: false, github: null, githubLoading: false, url: null })

onMounted(() => {
  const m = props.match
  if (m.type === 'issue' && m.issueId) {
    state.type = 'issue'; state.issueLoading = true
    fetchIssuePreview(m.issueId, api)
      .then((d) => { state.issue = d; state.issueLoading = false })
      .catch(() => { state.issueError = true; state.issueLoading = false })
  } else if (m.type === 'github' && m.url) {
    state.type = 'github'; state.githubLoading = true
    fetchGithubPreview(m.url, api)
      .then((d) => { if (d) { state.github = d; state.githubLoading = false } else { state.type = 'external'; state.url = m.url; state.githubLoading = false } })
      .catch(() => { state.type = 'external'; state.url = m.url ?? null; state.githubLoading = false })
  } else if (m.type === 'external' && m.url) {
    state.type = 'external'; state.url = m.url
  }
})

// 仅站内问题卡片悬停 → iframe 预览
const iframe = reactive({ visible: false, top: 0, left: 0 })
let showTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

function cancelHide() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null } }
function scheduleHide() {
  cancelHide()
  hideTimer = setTimeout(() => { iframe.visible = false }, 300)
}
function onEnter(e: MouseEvent) {
  if (props.match.type !== 'issue') return
  cancelHide()
  if (showTimer) clearTimeout(showTimer)
  const el = e.currentTarget as HTMLElement
  showTimer = setTimeout(() => {
    const rect = el.getBoundingClientRect()
    const w = Math.min(window.innerWidth - 32, 760)
    const h = Math.min(window.innerHeight * 0.75, 560)
    const below = rect.bottom + h + 8 < window.innerHeight
    iframe.top = below ? rect.bottom + window.scrollY + 4 : Math.max(8 + window.scrollY, rect.top + window.scrollY - h - 4)
    iframe.left = Math.max(window.scrollX + 8, Math.min(rect.left + window.scrollX, window.scrollX + window.innerWidth - w - 16))
    iframe.visible = true
  }, 500)
}
function onLeave() {
  if (showTimer) { clearTimeout(showTimer); showTimer = null }
  if (props.match.type === 'issue') scheduleHide()
}

onBeforeUnmount(() => { if (showTimer) clearTimeout(showTimer); cancelHide() })
</script>

<style scoped>
.inline-link-card { display: block; }
.ilc-iframe-popup {
  position: absolute; z-index: 70;
  width: 760px; max-width: calc(100vw - 32px);
  background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.18); overflow: hidden;
}
:root.dark .ilc-iframe-popup { background: #1f2937; border-color: #374151; }
.ilc-iframe-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.4rem 0.7rem; font-size: 0.75rem; color: #6b7280;
  border-bottom: 1px solid #e5e7eb;
}
:root.dark .ilc-iframe-bar { border-color: #374151; }
.ilc-iframe-bar a { color: #2563eb; text-decoration: none; }
:root.dark .ilc-iframe-bar a { color: #60a5fa; }
.ilc-iframe { display: block; width: 100%; height: 520px; border: 0; background: #fff; }
</style>
