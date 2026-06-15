<template>
  <LinkHoverCard
    :visible="state.visible"
    :top="state.top"
    :left="state.left"
    :type="state.type"
    :issue="state.issue"
    :issue-loading="state.issueLoading"
    :issue-error="state.issueError"
    :url="state.url"
    :iframe-fallback="state.iframeFallback"
    @enter="cancelHide"
    @leave="scheduleHide"
    @iframe-load="onIframeLoad"
  />
</template>

<script setup lang="ts">
import LinkHoverCard from '~/components/LinkHoverCard.vue'
import { matchPreviewAnchor, fetchIssuePreview, type IssuePreview } from '~/composables/useLinkPreview'

const props = defineProps<{ container: HTMLElement | null }>()
const { api } = useApi()

const HOVER_DELAY = 500
const HIDE_DELAY = 300
const IFRAME_TIMEOUT = 3000

const state = reactive<{
  visible: boolean; top: number; left: number
  type: 'issue' | 'external' | null
  issue: IssuePreview | null; issueLoading: boolean; issueError: boolean
  url: string | null; iframeFallback: boolean
}>({
  visible: false, top: 0, left: 0, type: null,
  issue: null, issueLoading: false, issueError: false,
  url: null, iframeFallback: false,
})

let showTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null
let iframeTimer: ReturnType<typeof setTimeout> | null = null
let activeAnchor: HTMLAnchorElement | null = null

function clearShow() { if (showTimer) { clearTimeout(showTimer); showTimer = null } }
function clearIframeTimer() { if (iframeTimer) { clearTimeout(iframeTimer); iframeTimer = null } }
function cancelHide() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null } }

function scheduleHide() {
  cancelHide()
  hideTimer = setTimeout(() => {
    state.visible = false
    state.type = null
    state.issue = null
    state.url = null
    state.issueLoading = false
    state.issueError = false
    state.iframeFallback = false
    activeAnchor = null
    clearIframeTimer()
  }, HIDE_DELAY)
}

function position(anchor: HTMLAnchorElement) {
  const rect = anchor.getBoundingClientRect()
  const w = Math.min(window.innerWidth - 32, 480)
  const h = Math.min(window.innerHeight * 0.7, 400)
  const wantBelow = rect.bottom + h + 8 < window.innerHeight
  state.top = wantBelow
    ? rect.bottom + window.scrollY + 4
    : Math.max(8 + window.scrollY, rect.top + window.scrollY - h - 4)
  const rawLeft = rect.left + window.scrollX
  state.left = Math.max(window.scrollX + 8, Math.min(rawLeft, window.scrollX + window.innerWidth - w - 16))
}

function showFor(anchor: HTMLAnchorElement) {
  const match = matchPreviewAnchor(anchor)
  if (!match) return
  position(anchor)
  cancelHide()
  if (match.type === 'issue' && match.issueId) {
    state.type = 'issue'
    state.url = null
    state.issue = null
    state.issueError = false
    state.issueLoading = true
    state.visible = true
    fetchIssuePreview(match.issueId, api)
      .then((data) => { if (activeAnchor === anchor) { state.issue = data; state.issueLoading = false } })
      .catch(() => { if (activeAnchor === anchor) { state.issueError = true; state.issueLoading = false } })
  } else if (match.type === 'external' && match.url) {
    state.type = 'external'
    state.issue = null
    state.url = match.url
    state.iframeFallback = false
    state.visible = true
    clearIframeTimer()
    iframeTimer = setTimeout(() => { if (activeAnchor === anchor) state.iframeFallback = true }, IFRAME_TIMEOUT)
  }
}

function onIframeLoad() { clearIframeTimer() }

function onMouseOver(e: Event) {
  const target = e.target as HTMLElement
  const anchor = (target.closest?.('a') as HTMLAnchorElement | null) ?? null
  if (!anchor || !matchPreviewAnchor(anchor)) return
  if (anchor === activeAnchor && state.visible) { cancelHide(); return }
  activeAnchor = anchor
  clearShow()
  showTimer = setTimeout(() => showFor(anchor), HOVER_DELAY)
}

function onMouseOut(e: Event) {
  const related = (e as MouseEvent).relatedTarget as HTMLElement | null
  if (activeAnchor && (!related || !activeAnchor.contains(related))) {
    clearShow()
    scheduleHide()
  }
}

function attach(el: HTMLElement) {
  el.addEventListener('mouseover', onMouseOver)
  el.addEventListener('mouseout', onMouseOut)
}
function detach(el: HTMLElement) {
  el.removeEventListener('mouseover', onMouseOver)
  el.removeEventListener('mouseout', onMouseOut)
}

watch(() => props.container, (el, prev) => {
  if (prev) detach(prev)
  if (el) attach(el)
}, { immediate: true })

onBeforeUnmount(() => {
  if (props.container) detach(props.container)
  clearShow(); cancelHide(); clearIframeTimer()
})
</script>
