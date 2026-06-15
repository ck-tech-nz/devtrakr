# Inline Preview Cards Redesign — Implementation Plan

> Subagent-driven, TDD, branch `feat/markdown-link-hover-preview`. Steps use `- [ ]`.

**Goal:** In rendered markdown (preview), previewable links render their card **inline (always visible)** instead of on hover. Hovering an **internal issue** inline card opens an **iframe** popup of the full app page. GitHub/external inline cards have no hover action.

**Design (approved):**
| Link | Inline (always shown in preview) | Hover |
|---|---|---|
| internal `#问题-NNN` | issue card | iframe popup of `/app/issues/{id}` (full app, 0.5s delay) |
| GitHub PR/issue | GitHub card | none |
| other external | domain card | none |

**Reuse principle (explicit user requirement):** ONE shared presentational card component (`LinkPreviewCard`) renders the issue/github/domain card; it is reused by the inline item. The fetch/match logic in `useLinkPreview.ts` is reused as-is. The old hover-popup host (`MarkdownHoverPreview.vue`) and `LinkHoverCard.vue` are replaced.

**Architecture:**
- `LinkPreviewCard.vue` — pure presentational card body (extracted from `LinkHoverCard.vue`; no teleport/positioning/visibility).
- `InlineLinkCardItem.vue` — given a `PreviewMatch`, fetches its data, renders `<LinkPreviewCard>`; for `issue` type, owns a hover→iframe popup.
- `useInlineLinkPreviews(containerRef, htmlRef)` — after each render, mounts one `InlineLinkCardItem` after each previewable anchor (preserving Nuxt app context), cleans up on rebuild/unmount.
- Markdown surfaces (`MarkdownView`, `MarkdownEditor` preview) call the composable instead of mounting `<MarkdownHoverPreview>`.

Markdown rendering stays `v-html` (unchanged); cards are mounted into the live DOM after render — this preserves all existing markdown features and the correct DOM tree (string-splitting HTML would break block nesting).

---

## Task IC-1: Extract shared `LinkPreviewCard.vue`

**Files:** Create `frontend/app/components/LinkPreviewCard.vue`; create `frontend/tests/linkPreviewCard.test.ts`.

Extract the card BODY from `app/components/LinkHoverCard.vue` (do NOT modify LinkHoverCard yet — it's removed in IC-4). `LinkPreviewCard` is the inner card with NO `<Teleport>`, NO `visible`/`top`/`left`, NO `enter`/`leave` emits.

- [ ] **Step 1: failing test** — `frontend/tests/linkPreviewCard.test.ts`:

```ts
// @vitest-environment nuxt
import { describe, it, expect, afterEach } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import LinkPreviewCard from '../app/components/LinkPreviewCard.vue'

const issue = { id: 7, title: '登录页报错', status: '进行中', priority: 'P1', assignee_name: '张三', assignee_avatar: '', created_by_name: '李四', created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00' }
const pr = { kind: 'pr' as const, number: 42, title: '加预览', state: 'merged' as const, author_login: 'alice', author_avatar: '', repo_full_name: 'octocat/hello', html_url: 'https://github.com/octocat/hello/pull/42' }

afterEach(() => { document.body.innerHTML = '' })

describe('LinkPreviewCard', () => {
  it('renders an issue card (no teleport — inline root)', async () => {
    const w = await mountSuspended(LinkPreviewCard, { props: { type: 'issue', issue, issueLoading: false, issueError: false, github: null, githubLoading: false, url: null } })
    expect(w.find('.link-preview-card').exists()).toBe(true)
    expect(w.text()).toContain('登录页报错')
    expect(w.text()).toContain('#问题-007')
    expect(w.text()).toContain('进行中')
    expect(w.text()).toContain('高')
    expect(w.find('.lpc-avatar-fallback').text()).toBe('张')
    w.unmount()
  })
  it('renders a github card', async () => {
    const w = await mountSuspended(LinkPreviewCard, { props: { type: 'github', issue: null, issueLoading: false, issueError: false, github: pr, githubLoading: false, url: pr.html_url } })
    expect(w.text()).toContain('加预览')
    expect(w.text()).toContain('#42')
    expect(w.text().toLowerCase()).toContain('merged')
    w.unmount()
  })
  it('renders a domain card for external', async () => {
    const w = await mountSuspended(LinkPreviewCard, { props: { type: 'external', issue: null, issueLoading: false, issueError: false, github: null, githubLoading: false, url: 'https://example.com/x' } })
    expect(w.find('iframe').exists()).toBe(false)
    expect(w.text()).toContain('example.com')
    expect(w.find('a.lpc-open').attributes('target')).toBe('_blank')
    w.unmount()
  })
  it('shows issue loading state', async () => {
    const w = await mountSuspended(LinkPreviewCard, { props: { type: 'issue', issue: null, issueLoading: true, issueError: false, github: null, githubLoading: false, url: null } })
    expect(w.text()).toContain('加载中')
    w.unmount()
  })
})
```

- [ ] **Step 2:** `npm run test -- tests/linkPreviewCard.test.ts` → FAIL.

- [ ] **Step 3: implement** — create `app/components/LinkPreviewCard.vue` by copying the BODY of `LinkHoverCard.vue` (lines 12–60: the three `<template v-if=...>` branches) into a non-teleported root, copying ALL the `<script setup>` computeds/functions (lines 83–113) and the styles (renaming the class prefix `lhc-`→`lpc-` and `.link-hover-card`→`.link-preview-card`, dropping `position/z-index/top/left` and the `enter`/`leave` mouseenter/leave). Concretely:

```vue
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

defineProps<{
  type: 'issue' | 'external' | 'github' | null
  issue: IssuePreview | null
  issueLoading: boolean
  issueError: boolean
  github: GithubPreview | null
  githubLoading: boolean
  url: string | null
}>()
</script>
```

For the `<script setup>` body, copy these from `LinkHoverCard.vue` verbatim (they reference `props.*`, so keep `const props = defineProps<...>()` form instead of bare `defineProps`): `issueAvatarUrl`, `statusColor`, `statusText`, `prioColor`, `prioText`, `timeText`, `host`, `faviconUrl`, `ghStateColor`, `ghStateText`, `goGithub`, `formatDate`, `goIssue`, and `const { resolveAvatarUrl } = useAvatars()`. (i.e. use `const props = defineProps<{...}>()`.)

For styles, copy the `<style scoped>` from `LinkHoverCard.vue`, rename `.link-hover-card`→`.link-preview-card` and every `.lhc-`→`.lpc-`, and from `.link-preview-card` REMOVE `position: absolute; z-index: 60;` and the `top`/`left` usage (it's now a normal inline-flow block). Keep width 360px, border, radius, shadow, bg, dark mode. Add `margin: 0.4em 0;` to `.link-preview-card` so stacked inline cards have breathing room.

- [ ] **Step 4:** `npm run test -- tests/linkPreviewCard.test.ts` → PASS.

- [ ] **Step 5: commit**

```bash
git add app/components/LinkPreviewCard.vue tests/linkPreviewCard.test.ts
git commit -F - <<'EOF'
refactor(preview): 抽出共享 LinkPreviewCard 卡片组件

从 LinkHoverCard 抽出纯展示卡片主体(问题/GitHub/域名),去掉 teleport/定位/
显隐,供内联与悬停复用。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task IC-2: `InlineLinkCardItem.vue`

**Files:** Create `frontend/app/components/InlineLinkCardItem.vue`; create `frontend/tests/inlineLinkCardItem.test.ts`.

Given a `PreviewMatch`, fetch its data and render `<LinkPreviewCard>`. For `issue` type, hovering the card shows a teleported iframe popup of `/app/issues/{id}` (0.5s show / 0.3s hide).

- [ ] **Step 1: failing test** — `frontend/tests/inlineLinkCardItem.test.ts`:

```ts
// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import InlineLinkCardItem from '../app/components/InlineLinkCardItem.vue'
import { clearIssuePreviewCache, clearGithubPreviewCache } from '../app/composables/useLinkPreview'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

beforeEach(() => { apiMock.mockReset(); clearIssuePreviewCache(); clearGithubPreviewCache(); document.body.innerHTML = '' })
afterEach(() => { vi.useRealTimers() })

describe('InlineLinkCardItem', () => {
  it('issue match fetches and renders the issue card', async () => {
    apiMock.mockResolvedValue({ id: 7, title: '登录页报错', status: '进行中', priority: 'P1', assignee_name: '张三', assignee_avatar: '', created_by_name: '李四', created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00' })
    const w = await mountSuspended(InlineLinkCardItem, { props: { match: { type: 'issue', issueId: '7' } } })
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/issues/7/')
    expect(w.text()).toContain('登录页报错')
    w.unmount()
  })
  it('external match renders a domain card without fetching', async () => {
    const w = await mountSuspended(InlineLinkCardItem, { props: { match: { type: 'external', url: 'https://example.com/x' } } })
    await flushPromises()
    expect(apiMock).not.toHaveBeenCalled()
    expect(w.text()).toContain('example.com')
    w.unmount()
  })
  it('github match fetches and renders the github card', async () => {
    apiMock.mockResolvedValue({ kind: 'pr', number: 42, title: 'PR标题', state: 'open', author_login: 'a', author_avatar: '', repo_full_name: 'o/r', html_url: 'u' })
    const w = await mountSuspended(InlineLinkCardItem, { props: { match: { type: 'github', url: 'https://github.com/o/r/pull/42' } } })
    await flushPromises()
    expect(w.text()).toContain('PR标题')
    w.unmount()
  })
  it('hovering an issue card opens an iframe popup after the delay', async () => {
    apiMock.mockResolvedValue({ id: 7, title: 'T', status: '进行中', priority: 'P1', assignee_name: '', assignee_avatar: '', created_by_name: '', created_at: '', updated_at: '' })
    const w = await mountSuspended(InlineLinkCardItem, { props: { match: { type: 'issue', issueId: '7' } } })
    await flushPromises()
    vi.useFakeTimers()
    await w.find('.link-preview-card').trigger('mouseenter')
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    const iframe = document.body.querySelector('iframe.ilc-iframe') as HTMLIFrameElement | null
    expect(iframe).toBeTruthy()
    expect(iframe!.getAttribute('src')).toBe('/app/issues/7')
    w.unmount()
  })
})
```

- [ ] **Step 2:** `npm run test -- tests/inlineLinkCardItem.test.ts` → FAIL.

- [ ] **Step 3: implement** — create `app/components/InlineLinkCardItem.vue`:

```vue
<template>
  <span class="inline-link-card" @mouseenter="onEnter" @mouseleave="onLeave">
    <LinkPreviewCard
      :type="state.type"
      :issue="state.issue"
      :issue-loading="state.issueLoading"
      :issue-error="state.issueError"
      :github="state.github"
      :github-loading="state.githubLoading"
      :url="state.url"
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
```

- [ ] **Step 4:** `npm run test -- tests/inlineLinkCardItem.test.ts` → PASS.

- [ ] **Step 5: commit**

```bash
git add app/components/InlineLinkCardItem.vue tests/inlineLinkCardItem.test.ts
git commit -F - <<'EOF'
feat(preview): InlineLinkCardItem 单链接内联卡片

按 PreviewMatch 取数并渲染 LinkPreviewCard;问题卡片悬停 0.5s 弹出
站内页面 iframe(同源,整页 App),0.3s 延时隐藏。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task IC-3: `useInlineLinkPreviews` composable

**Files:** Create `frontend/app/composables/useInlineLinkPreviews.ts`; create `frontend/tests/useInlineLinkPreviews.test.ts`.

After each render, mount one `InlineLinkCardItem` after each previewable anchor's nearest block ancestor, preserving the Nuxt app context; clean up mounted instances on rebuild/unmount.

- [ ] **Step 1: failing test** — `frontend/tests/useInlineLinkPreviews.test.ts`:

```ts
// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { useInlineLinkPreviews } from '../app/composables/useInlineLinkPreviews'
import { clearIssuePreviewCache } from '../app/composables/useLinkPreview'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

beforeEach(() => { apiMock.mockReset(); clearIssuePreviewCache(); document.body.innerHTML = '' })

const Harness = defineComponent({
  props: { html: { type: String, required: true } },
  setup(props) {
    const root = ref<HTMLElement | null>(null)
    const html = () => props.html
    useInlineLinkPreviews(root, html)
    return () => h('div', { ref: root, innerHTML: props.html })
  },
})

describe('useInlineLinkPreviews', () => {
  it('mounts an inline issue card after a mention-issue anchor', async () => {
    apiMock.mockResolvedValue({ id: 7, title: '内联问题标题', status: '进行中', priority: 'P1', assignee_name: '张三', assignee_avatar: '', created_by_name: '', created_at: '', updated_at: '' })
    const w = await mountSuspended(Harness, { props: { html: '<p>见 <a class="mention-issue" data-issue-id="7" href="/app/issues/7">#问题-007</a> 说明</p>' } })
    await flushPromises()
    await flushPromises()
    expect(w.element.querySelector('.link-preview-card')).toBeTruthy()
    expect(w.text()).toContain('内联问题标题')
    w.unmount()
  })

  it('mounts a domain card for an external link and none for plain text', async () => {
    const w = await mountSuspended(Harness, { props: { html: '<p><a class="external-link" href="https://example.com/a">x</a> and plain</p>' } })
    await flushPromises()
    expect(w.element.querySelectorAll('.link-preview-card').length).toBe(1)
    expect(w.text()).toContain('example.com')
    w.unmount()
  })
})
```

- [ ] **Step 2:** `npm run test -- tests/useInlineLinkPreviews.test.ts` → FAIL.

- [ ] **Step 3: implement** — create `app/composables/useInlineLinkPreviews.ts`:

```ts
import { render, h, getCurrentInstance, watch, nextTick, onBeforeUnmount, type Ref } from 'vue'
import InlineLinkCardItem from '~/components/InlineLinkCardItem.vue'
import { matchPreviewAnchor } from '~/composables/useLinkPreview'

const BLOCK_SEL = 'p,li,blockquote,td,th,h1,h2,h3,h4,h5,h6,pre'

// 渲染后在每个可预览锚点所在块级元素之后挂载一张内联卡片(InlineLinkCardItem),
// 复用当前组件的 Nuxt app context;内容变化或卸载时清理已挂载实例。
export function useInlineLinkPreviews(containerRef: Ref<HTMLElement | null>, htmlGetter: () => string) {
  const instance = getCurrentInstance()
  const hosts: HTMLElement[] = []

  function cleanup() {
    for (const host of hosts.splice(0)) {
      render(null, host)
      host.remove()
    }
  }

  function build() {
    cleanup()
    const root = containerRef.value
    if (!root) return
    const anchors = root.querySelectorAll<HTMLAnchorElement>('a.mention-issue, a.external-link')
    anchors.forEach((a) => {
      const match = matchPreviewAnchor(a)
      if (!match) return
      const block = (a.closest(BLOCK_SEL) as HTMLElement | null) ?? a
      const host = document.createElement('div')
      host.className = 'inline-link-card-host'
      block.insertAdjacentElement('afterend', host)
      const vnode = h(InlineLinkCardItem, { match })
      if (instance) vnode.appContext = instance.appContext
      render(vnode, host)
      hosts.push(host)
    })
  }

  watch([containerRef, htmlGetter], () => nextTick(build), { immediate: true, flush: 'post' })
  onBeforeUnmount(cleanup)
}
```

- [ ] **Step 4:** `npm run test -- tests/useInlineLinkPreviews.test.ts` → PASS. (If happy-dom needs an extra `await flushPromises()` for the mounted child's onMounted fetch, the test already double-flushes.)

- [ ] **Step 5: commit**

```bash
git add app/composables/useInlineLinkPreviews.ts tests/useInlineLinkPreviews.test.ts
git commit -F - <<'EOF'
feat(preview): useInlineLinkPreviews 渲染后内联挂载卡片

遍历容器内可预览锚点,在其所在块级元素后挂载 InlineLinkCardItem
(保留 Nuxt app context),内容变更/卸载时清理。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task IC-4: Integrate + remove the old hover host

**Files:** Modify `frontend/app/components/MarkdownView.vue`, `frontend/app/components/MarkdownEditor.vue`, `frontend/app/pages/app/issues/[id].vue`; delete `frontend/app/components/MarkdownHoverPreview.vue`, `frontend/app/components/LinkHoverCard.vue`, `frontend/tests/markdownHoverPreview.test.ts`, `frontend/tests/linkHoverCard.test.ts`.

- [ ] **Step 1: MarkdownView.vue** — remove the `<MarkdownHoverPreview>` element; keep the `ref="rootEl"` div; call the composable in `<script setup>`:

```vue
<template>
  <div ref="rootEl" class="markdown-view" v-html="html" />
</template>
```
```ts
const rootEl = ref<HTMLElement | null>(null)
useInlineLinkPreviews(rootEl, () => html.value)
```
(`html` is the existing computed. `useInlineLinkPreviews` is auto-imported.)

- [ ] **Step 2: MarkdownEditor.vue** — remove the `<MarkdownHoverPreview :container="previewRef" />` line. In `<script setup>`, after `previewRef` is defined, add:
```ts
useInlineLinkPreviews(previewRef, () => renderedHtml.value)
```
(`renderedHtml` is the existing computed; `previewRef` already exists.)

- [ ] **Step 3: issues/[id].vue** — remove the `<MarkdownHoverPreview :container="aiResultRef" />` line and the explanatory comment above it (the AI panel uses a separate renderer with no tagged anchors, so inline cards don't apply there). Leave `aiResultRef` if still referenced elsewhere, else remove it. Do not change other behavior.

- [ ] **Step 4: delete** the replaced files:
```bash
git rm app/components/MarkdownHoverPreview.vue app/components/LinkHoverCard.vue tests/markdownHoverPreview.test.ts tests/linkHoverCard.test.ts
```

- [ ] **Step 5: verify** — `npm run test` (full suite passes; the deleted tests are gone, the new IC tests pass) and `npx nuxi typecheck` (no NEW errors in the changed/new files; grep for `LinkPreviewCard|InlineLinkCardItem|useInlineLinkPreviews|MarkdownView|MarkdownEditor`). There must be NO remaining import/reference to `MarkdownHoverPreview` or `LinkHoverCard` anywhere — grep to confirm:
```bash
grep -rn "MarkdownHoverPreview\|LinkHoverCard" app/ tests/ || echo "clean"
```

- [ ] **Step 6: commit**

```bash
git add -A
git commit -F - <<'EOF'
feat(preview): markdown 预览内联渲染卡片,移除悬停弹窗

MarkdownView/MarkdownEditor 预览改用 useInlineLinkPreviews 内联挂载卡片;
删除 MarkdownHoverPreview 与 LinkHoverCard(由 LinkPreviewCard + 内联机制取代)。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task IC-5: Verify

- [ ] Full frontend suite green; backend untouched (still green).
- [ ] `npx nuxi typecheck` — no new errors from the new/changed files.
- [ ] Manual: in an issue with `#问题-NNN`, a GitHub link, and a plain external link, switch description to 预览 — each shows its inline card; hovering the issue card shows the iframe; GitHub/external cards have no hover popup.

## Notes / decisions
- Card placement: inserted after the link's nearest block element (avoids invalid block-in-`<p>` and gives clean stacked block layout). The inline chip/anchor stays in the text as the reference.
- Internal non-issue links remain un-previewed (only `mention-issue` + `external-link` are tagged). Future: add resolvers/cards for other internal entities.
- iframe only for same-origin issue pages (full app, no embed mode — per decision). GitHub/external never iframe.
