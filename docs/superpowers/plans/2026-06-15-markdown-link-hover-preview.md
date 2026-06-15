# Markdown Link Hover Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a hover-triggered preview popup for links inside rendered markdown — an issue card for internal issue references and a live iframe for external URLs — delivered as a reusable component used by every markdown render surface.

**Architecture:** A markdown-renderer change tags previewable anchors (`data-issue-id` on issue mentions, `external-link` class on external links). Pure logic (`useLinkPreview.ts`) matches anchors and fetches/caches issue data. A presentational `LinkHoverCard.vue` renders the popup. A host `MarkdownHoverPreview.vue` wires hover delegation + timers + positioning onto a given container element and drives the card. Consumers drop in `<MarkdownHoverPreview :container="ref">`.

**Tech Stack:** Nuxt 4 SPA, Vue 3 `<script setup lang="ts">`, markdown-it, Vitest + @vue/test-utils + @nuxt/test-utils (happy-dom), scoped CSS + Tailwind, dark mode via `:root.dark`.

---

## File Structure

- **Modify** `frontend/app/composables/useMentionMarkdown.ts` — tag issue mentions with `data-issue-id`; tag external http(s) links with `external-link` class + `target`/`rel`.
- **Create** `frontend/app/composables/useLinkPreview.ts` — pure logic: `matchPreviewAnchor`, `IssuePreview` type, `fetchIssuePreview` + cache.
- **Create** `frontend/app/components/LinkHoverCard.vue` — presentational popup (issue branch + external iframe/fallback branch).
- **Create** `frontend/app/components/MarkdownHoverPreview.vue` — host: hover delegation, timers, positioning, state; renders `LinkHoverCard`.
- **Modify** `frontend/app/components/MarkdownView.vue` — wire host onto its render container.
- **Modify** `frontend/app/components/MarkdownEditor.vue` — wire host onto the preview container.
- **Modify** `frontend/app/pages/app/issues/[id].vue` — wire host onto the AI-analysis result container.
- **Modify** `frontend/tests/mentionMarkdown.test.ts` — renderer tagging tests.
- **Create** `frontend/tests/linkPreview.test.ts` — matching + fetch/cache tests.
- **Create** `frontend/tests/linkHoverCard.test.ts` — card rendering tests.
- **Create** `frontend/tests/markdownHoverPreview.test.ts` — host wiring tests.

All commands run from `frontend/`. Commit messages are Chinese conventional-commit style and end with the `Co-Authored-By` trailer (see Task 1 step 5 for the exact trailer).

---

### Task 1: Tag previewable anchors in the markdown renderer

**Files:**
- Modify: `frontend/app/composables/useMentionMarkdown.ts` (`mentionPlugin` issue renderer ~130-135; `fileCardPlugin` `link_open` `!category` branch ~50-53)
- Test: `frontend/tests/mentionMarkdown.test.ts`

- [ ] **Step 1: Write the failing tests** — append to `frontend/tests/mentionMarkdown.test.ts` inside the existing `describe('useMentionMarkdown 渲染', ...)` block:

```ts
  it('问题提及带 data-issue-id 供悬浮预览取数', () => {
    const html = md.render('#[#问题-042](issue:42)')
    expect(html).toContain('data-issue-id="42"')
    expect(html).toContain('class="mention-issue"')
  })

  it('外部 URL 链接带 external-link class 与安全 rel/target', () => {
    const html = md.render('见 https://example.com/docs 说明')
    expect(html).toContain('class="external-link"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('站内根相对链接不应标记为 external-link', () => {
    const html = md.render('[详情](/app/issues/3)')
    expect(html).not.toContain('external-link')
  })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- tests/mentionMarkdown.test.ts`
Expected: FAIL — `data-issue-id` / `external-link` not present.

- [ ] **Step 3: Implement the renderer changes**

In `frontend/app/composables/useMentionMarkdown.ts`, replace the `mention_issue` renderer (the function body at ~130-135) so the anchor carries `data-issue-id`:

```ts
  md.renderer.rules.mention_issue = (tokens, idx) => {
    const id = tokens[idx]?.meta?.id as string | undefined
    if (!id) return ''
    const label = `#问题-${String(id).padStart(3, '0')}`
    return `<a href="/app/issues/${id}" class="mention-issue" data-issue-id="${id}">${label}</a>`
  }
```

Add a helper above `fileCardPlugin` (after `getFileCategory`, ~line 34):

```ts
function isExternalHttpLink(href: string | undefined): boolean {
  return !!href && /^https?:\/\//i.test(href)
}
```

In `fileCardPlugin`'s `link_open` rule, replace the early `if (!category)` return (currently `if (!category) { return defaultLinkOpen(tokens, idx, options, env, self) }`) with:

```ts
    if (!category) {
      if (isExternalHttpLink(href)) {
        token.attrJoin('class', 'external-link')
        token.attrSet('target', '_blank')
        token.attrSet('rel', 'noopener noreferrer')
      }
      return defaultLinkOpen(tokens, idx, options, env, self)
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test -- tests/mentionMarkdown.test.ts`
Expected: PASS (all tests in the file, including the pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add app/composables/useMentionMarkdown.ts tests/mentionMarkdown.test.ts
git commit -F - <<'EOF'
feat(markdown): 给问题引用/外链打标记供悬浮预览

问题引用锚点加 data-issue-id;外部 http(s) 链接加 external-link class
与 target=_blank/rel,站内根相对链接不受影响。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: Anchor matching logic

**Files:**
- Create: `frontend/app/composables/useLinkPreview.ts`
- Create: `frontend/tests/linkPreview.test.ts`

- [ ] **Step 1: Write the failing test** — create `frontend/tests/linkPreview.test.ts`:

```ts
// @vitest-environment nuxt
import { describe, it, expect } from 'vitest'
import { matchPreviewAnchor } from '../app/composables/useLinkPreview'

function anchor(html: string): HTMLAnchorElement {
  const d = document.createElement('div')
  d.innerHTML = html
  return d.querySelector('a')!
}

describe('matchPreviewAnchor', () => {
  it('matches an issue mention by data-issue-id', () => {
    const a = anchor('<a class="mention-issue" data-issue-id="42" href="/app/issues/42">#问题-042</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'issue', issueId: '42' })
  })

  it('matches an external link to a different host', () => {
    const a = anchor('<a class="external-link" href="https://example.com/docs">x</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'external', url: 'https://example.com/docs' })
  })

  it('does not match a same-host external-link', () => {
    const a = anchor(`<a class="external-link" href="${location.origin}/x">x</a>`)
    expect(matchPreviewAnchor(a)).toBeNull()
  })

  it('returns null for a plain anchor', () => {
    const a = anchor('<a href="/app/issues/3">x</a>')
    expect(matchPreviewAnchor(a)).toBeNull()
  })

  it('returns null for null input', () => {
    expect(matchPreviewAnchor(null)).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- tests/linkPreview.test.ts`
Expected: FAIL — module `useLinkPreview` does not exist.

- [ ] **Step 3: Implement matching** — create `frontend/app/composables/useLinkPreview.ts`:

```ts
export type HoverPreviewType = 'issue' | 'external'

export interface PreviewMatch {
  type: HoverPreviewType
  issueId?: string
  url?: string
}

// 判断渲染后的锚点是否可预览,以及属于哪类(供悬浮预览取数)
export function matchPreviewAnchor(a: HTMLAnchorElement | null): PreviewMatch | null {
  if (!a) return null
  if (a.classList.contains('mention-issue')) {
    const id = a.dataset.issueId || ''
    if (id) return { type: 'issue', issueId: id }
  }
  if (a.classList.contains('external-link')) {
    try {
      if (new URL(a.href).host !== location.host) return { type: 'external', url: a.href }
    } catch {
      // 无法解析的 href 不预览
    }
  }
  return null
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- tests/linkPreview.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/composables/useLinkPreview.ts tests/linkPreview.test.ts
git commit -F - <<'EOF'
feat(preview): 锚点可预览类型匹配

matchPreviewAnchor 识别问题引用(data-issue-id)与跨站外链。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: Issue data fetch with cache

**Files:**
- Modify: `frontend/app/composables/useLinkPreview.ts`
- Modify: `frontend/tests/linkPreview.test.ts`

- [ ] **Step 1: Write the failing test** — append to `frontend/tests/linkPreview.test.ts`:

```ts
import { fetchIssuePreview, clearIssuePreviewCache } from '../app/composables/useLinkPreview'
import { beforeEach, vi } from 'vitest'

describe('fetchIssuePreview', () => {
  beforeEach(() => clearIssuePreviewCache())

  it('maps the API payload to an IssuePreview', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      id: 7, title: 'T', status: '进行中', priority: 'P1',
      assignee_name: '张三', assignee_avatar: 'a.png', created_by_name: '李四',
      created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00',
    })
    const r = await fetchIssuePreview('7', fetcher)
    expect(fetcher).toHaveBeenCalledWith('/api/issues/7/')
    expect(r).toMatchObject({ id: 7, title: 'T', status: '进行中', priority: 'P1', assignee_name: '张三' })
  })

  it('caches by id — a second call does not refetch', async () => {
    const fetcher = vi.fn().mockResolvedValue({ id: 7, title: 'T', status: '进行中', priority: 'P1', created_at: '', updated_at: '' })
    await fetchIssuePreview('7', fetcher)
    await fetchIssuePreview('7', fetcher)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('drops the cache entry on failure so a retry refetches', async () => {
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({ id: 7, title: 'T', status: '进行中', priority: 'P1', created_at: '', updated_at: '' })
    await expect(fetchIssuePreview('7', fetcher)).rejects.toThrow('boom')
    const r = await fetchIssuePreview('7', fetcher)
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(r.id).toBe(7)
  })
})
```

(Note: `describe`/`it`/`expect` are already imported at the top of the file from Task 2; only add the `fetchIssuePreview`, `clearIssuePreviewCache`, `beforeEach`, `vi` imports.)

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- tests/linkPreview.test.ts`
Expected: FAIL — `fetchIssuePreview` not exported.

- [ ] **Step 3: Implement fetch + cache** — append to `frontend/app/composables/useLinkPreview.ts`:

```ts
export interface IssuePreview {
  id: number
  title: string
  status: string
  priority: string
  assignee_name: string | null
  assignee_avatar: string | null
  created_by_name: string | null
  created_at: string
  updated_at: string
}

// 同一 id 去重:缓存 Promise,并发悬浮只取一次;失败时清除缓存以便重试
const issueCache = new Map<string, Promise<IssuePreview>>()

export function clearIssuePreviewCache() {
  issueCache.clear()
}

export function fetchIssuePreview(
  id: string,
  fetcher: (url: string) => Promise<unknown>,
): Promise<IssuePreview> {
  const cached = issueCache.get(id)
  if (cached) return cached
  const p = fetcher(`/api/issues/${id}/`).then((raw) => {
    const d = raw as Record<string, unknown>
    return {
      id: Number(d.id),
      title: String(d.title ?? ''),
      status: String(d.status ?? ''),
      priority: String(d.priority ?? ''),
      assignee_name: (d.assignee_name as string) ?? null,
      assignee_avatar: (d.assignee_avatar as string) ?? null,
      created_by_name: (d.created_by_name as string) ?? null,
      created_at: String(d.created_at ?? ''),
      updated_at: String(d.updated_at ?? ''),
    } satisfies IssuePreview
  })
  p.catch(() => issueCache.delete(id))
  issueCache.set(id, p)
  return p
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- tests/linkPreview.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/composables/useLinkPreview.ts tests/linkPreview.test.ts
git commit -F - <<'EOF'
feat(preview): issue 预览取数与去重缓存

fetchIssuePreview 调 /api/issues/{id}/ 映射为 IssuePreview,
Promise 缓存去重,失败清缓存以便重试。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 4: LinkHoverCard — issue branch

**Files:**
- Create: `frontend/app/components/LinkHoverCard.vue`
- Create: `frontend/tests/linkHoverCard.test.ts`

- [ ] **Step 1: Write the failing test** — create `frontend/tests/linkHoverCard.test.ts`:

```ts
// @vitest-environment nuxt
import { describe, it, expect, afterEach } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import LinkHoverCard from '../app/components/LinkHoverCard.vue'

const issue = {
  id: 7, title: '登录页报错', status: '进行中', priority: 'P1',
  assignee_name: '张三', assignee_avatar: '', created_by_name: '李四',
  created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00',
}

afterEach(() => { document.body.innerHTML = '' })

describe('LinkHoverCard (issue)', () => {
  it('renders the issue card fields', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 10, left: 10, type: 'issue',
      issue, issueLoading: false, issueError: false, url: null, iframeFallback: false,
    } })
    expect(document.body.textContent).toContain('登录页报错')
    expect(document.body.textContent).toContain('#问题-007')
    expect(document.body.textContent).toContain('进行中')
    expect(document.body.textContent).toContain('高') // P1 标签
    expect(document.body.textContent).toContain('张三')
    w.unmount()
  })

  it('shows a loading state', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'issue',
      issue: null, issueLoading: true, issueError: false, url: null, iframeFallback: false,
    } })
    expect(document.body.textContent).toContain('加载中')
    w.unmount()
  })

  it('renders nothing when not visible', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: false, top: 0, left: 0, type: 'issue',
      issue, issueLoading: false, issueError: false, url: null, iframeFallback: false,
    } })
    expect(document.body.querySelector('.link-hover-card')).toBeNull()
    w.unmount()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- tests/linkHoverCard.test.ts`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement the card (issue branch + shell)** — create `frontend/app/components/LinkHoverCard.vue`:

```vue
<template>
  <Teleport to="body">
    <div
      v-if="visible"
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
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- tests/linkHoverCard.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/components/LinkHoverCard.vue tests/linkHoverCard.test.ts
git commit -F - <<'EOF'
feat(preview): LinkHoverCard 问题卡片

悬浮卡渲染问题标题/编号、状态+优先级胶囊、负责人+时间,
整卡点击 SPA 跳转;加载/失败状态。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 5: LinkHoverCard — external iframe branch + degradation

**Files:**
- Modify: `frontend/app/components/LinkHoverCard.vue`
- Modify: `frontend/tests/linkHoverCard.test.ts`

- [ ] **Step 1: Write the failing tests** — append a new describe block to `frontend/tests/linkHoverCard.test.ts`:

```ts
describe('LinkHoverCard (external)', () => {
  it('renders an iframe with a safe sandbox', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'external',
      issue: null, issueLoading: false, issueError: false,
      url: 'https://example.com/docs', iframeFallback: false,
    } })
    const iframe = document.body.querySelector('iframe.lhc-iframe') as HTMLIFrameElement
    expect(iframe).toBeTruthy()
    expect(iframe.getAttribute('src')).toBe('https://example.com/docs')
    expect(iframe.getAttribute('sandbox')).toContain('allow-scripts')
    expect(iframe.getAttribute('sandbox')).not.toContain('allow-top-navigation')
    expect(iframe.getAttribute('referrerpolicy')).toBe('no-referrer')
    expect(document.body.textContent).toContain('example.com')
    w.unmount()
  })

  it('shows the fallback when framing is blocked', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'external',
      issue: null, issueLoading: false, issueError: false,
      url: 'https://blocked.example.com/', iframeFallback: true,
    } })
    expect(document.body.querySelector('iframe')).toBeNull()
    expect(document.body.textContent).toContain('不允许内嵌预览')
    w.unmount()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- tests/linkHoverCard.test.ts`
Expected: FAIL — no external branch yet.

- [ ] **Step 3: Implement the external branch**

In `frontend/app/components/LinkHoverCard.vue`, add the external `<template>` block immediately after the closing `</template>` of the issue branch, inside the `.link-hover-card` div:

```vue
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
        <iframe
          v-else
          class="lhc-iframe"
          :src="url || ''"
          sandbox="allow-scripts allow-same-origin allow-popups"
          referrerpolicy="no-referrer"
          @load="emit('iframe-load')"
        />
      </template>
```

Add these computed values to `<script setup>` (after `timeText`):

```ts
const host = computed(() => { try { return new URL(props.url || '').host } catch { return props.url || '' } })
const faviconUrl = computed(() => { try { const u = new URL(props.url || ''); return `${u.origin}/favicon.ico` } catch { return '' } })
```

Add to `<style scoped>`:

```css
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
```

(Merge the new CSS into the existing `<style scoped>` block — do not create a second one.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test -- tests/linkHoverCard.test.ts`
Expected: PASS (issue + external describes).

- [ ] **Step 5: Commit**

```bash
git add app/components/LinkHoverCard.vue tests/linkHoverCard.test.ts
git commit -F - <<'EOF'
feat(preview): LinkHoverCard 外链 iframe 内嵌与降级

外链实时 iframe(sandbox 不含 allow-top-navigation、no-referrer),
顶部 URL 栏+新标签打开;被拦截时降级为域名+favicon 提示。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 6: MarkdownHoverPreview — host wiring

**Files:**
- Create: `frontend/app/components/MarkdownHoverPreview.vue`
- Create: `frontend/tests/markdownHoverPreview.test.ts`

- [ ] **Step 1: Write the failing test** — create `frontend/tests/markdownHoverPreview.test.ts`:

```ts
// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import MarkdownHoverPreview from '../app/components/MarkdownHoverPreview.vue'
import { clearIssuePreviewCache } from '../app/composables/useLinkPreview'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

function makeContainer(html: string): HTMLElement {
  const el = document.createElement('div')
  el.innerHTML = html
  document.body.appendChild(el)
  return el
}

beforeEach(() => { apiMock.mockReset(); clearIssuePreviewCache(); document.body.innerHTML = '' })
afterEach(() => { vi.useRealTimers() })

describe('MarkdownHoverPreview', () => {
  it('hovering an issue mention fetches and shows the issue card', async () => {
    apiMock.mockResolvedValue({
      id: 7, title: '登录页报错', status: '进行中', priority: 'P1',
      assignee_name: '张三', assignee_avatar: '', created_by_name: '李四',
      created_at: '2026-06-10T08:00:00+08:00', updated_at: '2026-06-11T09:00:00+08:00',
    })
    const container = makeContainer('<a class="mention-issue" data-issue-id="7" href="/app/issues/7">#问题-007</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/issues/7/')
    expect(document.body.textContent).toContain('登录页报错')
    expect(document.body.textContent).toContain('进行中')
    w.unmount()
  })

  it('hovering an external link shows an iframe', async () => {
    const container = makeContainer('<a class="external-link" href="https://example.com/docs">example</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    const iframe = document.body.querySelector('iframe.lhc-iframe') as HTMLIFrameElement | null
    expect(iframe).toBeTruthy()
    expect(iframe!.getAttribute('src')).toBe('https://example.com/docs')
    w.unmount()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- tests/markdownHoverPreview.test.ts`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement the host** — create `frontend/app/components/MarkdownHoverPreview.vue`:

```vue
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- tests/markdownHoverPreview.test.ts`
Expected: PASS.

If the issue-card assertion is flaky under fake timers, mount the component, then wrap only the dispatch+advance in fake timers (as written), and rely on `flushPromises()` after switching back to real timers — the cache promise resolves on the microtask queue.

- [ ] **Step 5: Commit**

```bash
git add app/components/MarkdownHoverPreview.vue tests/markdownHoverPreview.test.ts
git commit -F - <<'EOF'
feat(preview): MarkdownHoverPreview 悬停宿主组件

容器事件委托 + 延迟/隐藏计时 + 定位翻转,驱动 LinkHoverCard;
issue 走取数,外链走 iframe + 3s 超时降级。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 7: Wire the host into the three render surfaces

**Files:**
- Modify: `frontend/app/components/MarkdownView.vue`
- Modify: `frontend/app/components/MarkdownEditor.vue`
- Modify: `frontend/app/pages/app/issues/[id].vue`

- [ ] **Step 1: MarkdownView.vue** — replace the `<template>` (currently a single `<div class="markdown-view" v-html="html" />`) with:

```vue
<template>
  <div ref="rootEl" class="markdown-view" v-html="html" />
  <MarkdownHoverPreview :container="rootEl" />
</template>
```

In `<script setup>`, add a ref after `const { md } = useMentionMarkdown()`:

```ts
const rootEl = ref<HTMLElement | null>(null)
```

(`MarkdownHoverPreview` is auto-imported as a component; no manual import needed in the template. `ref` is auto-imported.)

- [ ] **Step 2: MarkdownEditor.vue** — the preview container already has `ref="previewRef"`. Add the host as a sibling. Immediately after the closing `</Teleport>` (the `.md` file hover block, ~line 112), add:

```vue
  <MarkdownHoverPreview :container="previewRef" />
```

No script changes are needed (`previewRef` already exists).

- [ ] **Step 3: issues/[id].vue (AI analysis result)** — open the file and locate the `v-html` element that renders the AI analysis result (around line 116). Add a template ref to that element, e.g. `ref="aiResultRef"`, and add immediately after it:

```vue
  <MarkdownHoverPreview :container="aiResultRef" />
```

In the page's `<script setup>`, add:

```ts
const aiResultRef = ref<HTMLElement | null>(null)
```

(If the AI result element is rendered conditionally with `v-if`, place the `<MarkdownHoverPreview>` inside the same `v-if` block so the container element exists when the host mounts.)

- [ ] **Step 4: Typecheck**

Run: `npx nuxi typecheck`
Expected: no new type errors introduced by these files. (Pre-existing errors elsewhere, if any, are out of scope — confirm none reference the new/changed files.)

- [ ] **Step 5: Commit**

```bash
git add app/components/MarkdownView.vue app/components/MarkdownEditor.vue app/pages/app/issues/[id].vue
git commit -F - <<'EOF'
feat(preview): 三处 markdown 渲染面接入悬停预览

MarkdownView(评论/只读)、MarkdownEditor 预览页、issue 详情 AI 结果区
各自把渲染容器交给 MarkdownHoverPreview。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole frontend test suite**

Run: `npm run test`
Expected: all tests pass (existing + new).

- [ ] **Step 2: Typecheck the project**

Run: `npx nuxi typecheck`
Expected: no new errors from changed files.

- [ ] **Step 3: Manual smoke (dev server)**

Run: `npm run dev` and open an issue whose description/comments contain a `#问题-NNN` reference and an external `https://` link.
Verify:
- Hovering the `#问题-NNN` chip for ~0.5s shows the issue card (title, status, priority, assignee, time); clicking navigates.
- Hovering an external link shows the live iframe; a framing-blocked site degrades to the domain + "在新标签打开" within ~3s.
- Moving the pointer from link into the card keeps it open; leaving dismisses it.

- [ ] **Step 4: Final commit (only if Step 3 required fixes)**

```bash
git add -A
git commit -F - <<'EOF'
fix(preview): 手测修正

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Self-Review

**Spec coverage:**
- Shared component + resolver shell → Tasks 2, 4, 5, 6 (`useLinkPreview` matching is the resolver seam; `MarkdownHoverPreview` is the shell).
- Internal issue preview (title+number, status+priority, assignee+time; cached fetch) → Tasks 3, 4, 6.
- External iframe + security sandbox + degradation → Task 5 (+ 3s timeout in Task 6).
- Reuse of `usePriority`/`useStatus` colors → Task 4.
- Integration on all markdown surfaces → Task 7.
- Renderer tagging (`data-issue-id`, `external-link`) → Task 1.
- Edge cases (rapid hover, keep-open-on-card, dark mode) → Task 6 wiring + Task 4/5 styles.
- Testing → every task is TDD; Task 8 runs the full suite.

**Placeholder scan:** No TBD/TODO; every code step has complete code. The only "locate it yourself" step is Task 7 Step 3 (AI-result element), which is unavoidable without reading that large page file and is bounded with explicit guidance.

**Type consistency:** `IssuePreview` defined in Task 3, imported in Tasks 4 and 6. `PreviewMatch`/`matchPreviewAnchor` defined in Task 2, used in Task 6. `fetchIssuePreview(id, fetcher)` signature consistent across Tasks 3 and 6 (`api` is the fetcher). `LinkHoverCard` prop names (`issue-loading`, `iframe-fallback`, etc.) consistent between Task 4/5 definition and Task 6 usage. Emits `enter`/`leave`/`iframe-load` consistent.
