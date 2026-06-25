# HTML Attachment Upload + File-Card Hover Preview — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow uploading `.html`/`.htm` files as issue attachments and render them as a file card whose hover popup previews the HTML in a sandboxed iframe — in the description and comment bodies.

**Architecture:** Backend adds `text/html` to the upload allowlist only (storage keeps serving HTML as `octet-stream` + `attachment`, so the public URL can never be rendered as XSS). Frontend adds an `html` file-card category and extracts the existing `.md` hover-preview (today only in `MarkdownEditor.vue`) into a shared composable + popup component, extended to also render `.html`/`.htm` via `<iframe srcdoc sandbox="allow-scripts">`. The shared unit is adopted by both `MarkdownEditor.vue` (description) and `MarkdownView.vue` (comments), so comments gain preview too.

**Tech Stack:** Django REST Framework (backend), pytest + factory-boy (backend tests), Nuxt 4 SPA / Vue 3 `<script setup>` (frontend), markdown-it (rendering), MinIO/S3 (storage).

## Global Constraints

- **Backend package manager:** `uv` (never pip). Run tests with `uv run python -m pytest` from `backend/` — plain `uv run pytest` fails to spawn on this machine.
- **Frontend has no JS unit-test runner.** The automated gate is `npx nuxi typecheck` (run from `frontend/`); behaviour is confirmed by manual browser check. Dev server: `TMPDIR=/tmp npm run dev` (macOS + Node 26 socket-crash workaround). Browser test account: `bot` / `password123`.
- **Language:** UI text and code comments in Chinese; identifiers/code in English.
- **Keep the three upload allowlists mirrored** — they carry explicit "Mirror this allowlist" comments: `backend/apps/tools/services.py`, `frontend/app/components/MarkdownEditor.vue`, `frontend/app/pages/app/issues/[id].vue`.
- **Security (non-negotiable):** Never map `html`/`htm` → `text/html` in `storage.EXT_TO_MIME`. HTML must be served `application/octet-stream` + `Content-Disposition: attachment`. Preview HTML only via a sandboxed iframe with `sandbox="allow-scripts"` and **no** `allow-same-origin` (scripts run in a null origin; cannot touch parent page, cookies, or storage).
- **Commit after each task. Do NOT push** — the user gates all pushes (`env/test`, `env/prod`).

---

### Task 1: Allow HTML upload (backend)

**Files:**
- Modify: `backend/apps/tools/services.py` (`ALLOWED_TYPES`, `EXTENSION_FALLBACK`)
- Test: `backend/tests/test_upload.py`

**Interfaces:**
- Consumes: `services.is_allowed(file)`, `services.MAX_SIZE`, `storage.EXT_TO_MIME` (existing).
- Produces: no new symbols; `is_allowed` now returns `True` for `text/html` and for `.html`/`.htm` by extension.

- [ ] **Step 1: Write the failing tests**

Add to the `TestImageUpload` class in `backend/tests/test_upload.py`:

```python
    @patch("apps.tools.storage.upload_image")
    def test_html_upload_succeeds(self, mock_upload, auth_client):
        from apps.tools.models import Attachment
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/06/25/abc.html",
            "2026/06/25/abc.html",
        )
        f = SimpleUploadedFile(
            "root-cause.html",
            b"<!doctype html><h1>hi</h1>",
            content_type="text/html",
        )
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200
        assert response.data["filename"] == "root-cause.html"
        att = Attachment.objects.get(id=response.data["id"])
        assert att.mime_type == "text/html"

    @patch("apps.tools.storage.upload_image")
    def test_htm_with_empty_type_succeeds_via_extension(self, mock_upload, auth_client):
        """个别浏览器对 .htm 上报空 content_type — 靠扩展名兜底放行。"""
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/06/25/abc.htm",
            "2026/06/25/abc.htm",
        )
        f = SimpleUploadedFile("page.htm", b"<html></html>", content_type="")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200
```

Add this new top-level class at the end of `backend/tests/test_upload.py` (no `@pytest.mark.django_db` — it touches no DB):

```python
class TestStorageMimeSafety:
    """安全约定: HTML 绝不能以 text/html 从公网 URL 下发, 否则公网链接 = 存储型 XSS。
    storage 按扩展名推导 Content-Type; html/htm 必须落到 octet-stream(走默认兜底)。"""

    def test_html_never_served_as_text_html(self):
        from apps.tools import storage
        assert storage.EXT_TO_MIME.get("html", "application/octet-stream") == "application/octet-stream"
        assert storage.EXT_TO_MIME.get("htm", "application/octet-stream") == "application/octet-stream"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_upload.py::TestImageUpload::test_html_upload_succeeds tests/test_upload.py::TestImageUpload::test_htm_with_empty_type_succeeds_via_extension -v`
Expected: both FAIL with status 400 (`不支持的文件类型`) instead of 200.
(The `TestStorageMimeSafety` test should already PASS — it guards a property that must stay true.)

- [ ] **Step 3: Add `text/html` to the allowlist**

In `backend/apps/tools/services.py`, inside `ALLOWED_TYPES`, after the `application/json` line in the `# Text / data` group, add:

```python
    # HTML
    "text/html",
```

And change `EXTENSION_FALLBACK` from:

```python
EXTENSION_FALLBACK = {
    "md", "txt", "csv", "json", "zip",
}
```

to:

```python
EXTENSION_FALLBACK = {
    "md", "txt", "csv", "json", "zip", "html", "htm",
}
```

Leave `backend/apps/tools/storage.py` `EXT_TO_MIME` **unchanged** (security: `.html` must fall through to `application/octet-stream`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_upload.py -v`
Expected: all PASS (existing tests + the 2 new HTML tests + `TestStorageMimeSafety`).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/tools/services.py backend/tests/test_upload.py
git commit -m "$(cat <<'EOF'
feat(tools): 允许上传 HTML 附件 (text/html + .html/.htm 扩展名兜底)

存储仍以 octet-stream + attachment 下发 HTML(不改 EXT_TO_MIME),
防止公网 URL 被当作 text/html 渲染造成存储型 XSS。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Mirror the HTML allowlist on the frontend

**Files:**
- Modify: `frontend/app/components/MarkdownEditor.vue` (`ALLOWED_TYPES`, `EXTENSION_FALLBACK`, `<input accept>`)
- Modify: `frontend/app/pages/app/issues/[id].vue` (`ATTACHMENT_ALLOWED_TYPES`, `ATTACHMENT_EXTENSION_FALLBACK`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `isAllowed(file)` (MarkdownEditor) and `handleAttachmentSelect` (`[id].vue`) now accept `text/html` and `.html`/`.htm`.

- [ ] **Step 1: Update `MarkdownEditor.vue` allowlist constants**

In `frontend/app/components/MarkdownEditor.vue`, change the `ALLOWED_TYPES` Set — replace the line:

```js
  // Archive
  'application/zip', 'application/x-zip-compressed',
])
```

with:

```js
  // Archive
  'application/zip', 'application/x-zip-compressed',
  // HTML
  'text/html',
])
```

Change `EXTENSION_FALLBACK` from:

```js
const EXTENSION_FALLBACK = new Set(['md', 'txt', 'csv', 'json', 'zip'])
```

to:

```js
const EXTENSION_FALLBACK = new Set(['md', 'txt', 'csv', 'json', 'zip', 'html', 'htm'])
```

- [ ] **Step 2: Update the `<input accept>` attribute**

In `frontend/app/components/MarkdownEditor.vue`, the file input's `accept` attribute currently ends with `...,.md,.txt,.csv,.json,.zip`. Append HTML to the end so it becomes:

```
...,.md,.txt,.csv,.json,.zip,text/html,.html,.htm
```

(Edit only the tail of the `accept` string; leave the rest intact.)

- [ ] **Step 3: Update `[id].vue` allowlist constants**

In `frontend/app/pages/app/issues/[id].vue`, change `ATTACHMENT_ALLOWED_TYPES` — replace:

```js
  'application/zip', 'application/x-zip-compressed',
])
```

with:

```js
  'application/zip', 'application/x-zip-compressed',
  'text/html',
])
```

Change `ATTACHMENT_EXTENSION_FALLBACK` from:

```js
const ATTACHMENT_EXTENSION_FALLBACK = new Set(['md', 'txt', 'csv', 'json', 'zip'])
```

to:

```js
const ATTACHMENT_EXTENSION_FALLBACK = new Set(['md', 'txt', 'csv', 'json', 'zip', 'html', 'htm'])
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: no new errors (clean, or unchanged from baseline).

- [ ] **Step 5: Manual verification**

Run `cd frontend && TMPDIR=/tmp npm run dev`, log in as `bot`/`password123`, open any issue, drag a `.html` file onto the description editor.
Expected: **no** `不支持的文件类型` toast; the file uploads and a `[name](url)` link is inserted.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/MarkdownEditor.vue frontend/app/pages/app/issues/[id].vue
git commit -m "$(cat <<'EOF'
feat(editor): 前端放行 HTML 上传 (三处白名单镜像同步)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Render HTML attachments as a file card

**Files:**
- Modify: `frontend/app/composables/useMentionMarkdown.ts` (`FILE_EXT_CATEGORY`)
- Modify: `frontend/app/components/MarkdownEditor.vue` (file-card CSS)
- Modify: `frontend/app/components/MarkdownView.vue` (file-card CSS)

**Interfaces:**
- Consumes: existing `fileCardPlugin` (categorises links by `FILE_EXT_CATEGORY[ext]`, emits `<a class="md-file-card md-file-<category>">`).
- Produces: `.html`/`.htm` links now get category `html` → class `md-file-html`, styled with a 🌐 icon and a purple `HTML` badge.

- [ ] **Step 1: Add the `html` category**

In `frontend/app/composables/useMentionMarkdown.ts`, change `FILE_EXT_CATEGORY` — after the `zip: 'archive',` line, add:

```ts
  html: 'html',
  htm: 'html',
```

- [ ] **Step 2: Add `.md-file-html` styles to `MarkdownEditor.vue`**

In `frontend/app/components/MarkdownEditor.vue`, after the line `.markdown-body .md-file-archive .md-file-icon::before { content: '📦'; }`, add:

```css
.markdown-body .md-file-html .md-file-icon::before { content: '🌐'; }
```

After the line `.markdown-body .md-file-archive .md-file-ext { background: #e5e7eb; color: #374151; }`, add:

```css
.markdown-body .md-file-html .md-file-ext { background: #ede9fe; color: #6d28d9; }
```

After the dark-mode line `:root.dark .markdown-body .md-file-archive .md-file-ext { background: #4b5563; color: #f3f4f6; }`, add:

```css
:root.dark .markdown-body .md-file-html .md-file-ext { background: #3b2f5e; color: #d6c7ff; }
```

- [ ] **Step 3: Add `.md-file-html` styles to `MarkdownView.vue`**

In `frontend/app/components/MarkdownView.vue`, mirror the same three rules with the `.markdown-view` prefix. After `.markdown-view .md-file-archive .md-file-icon::before { content: '📦'; }` add:

```css
.markdown-view .md-file-html .md-file-icon::before { content: '🌐'; }
```

After `.markdown-view .md-file-archive .md-file-ext { background: #e5e7eb; color: #374151; }` add:

```css
.markdown-view .md-file-html .md-file-ext { background: #ede9fe; color: #6d28d9; }
```

After `:root.dark .markdown-view .md-file-archive .md-file-ext { background: #4b5563; color: #f3f4f6; }` add:

```css
:root.dark .markdown-view .md-file-html .md-file-ext { background: #3b2f5e; color: #d6c7ff; }
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: no new errors.

- [ ] **Step 5: Manual verification**

With the dev server running, upload a `.html` file to a description and switch to the 预览 tab; post a comment containing an uploaded `.html` link.
Expected: in both places the link renders as a file card showing a 🌐 icon, the filename, and a purple `HTML` badge.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/composables/useMentionMarkdown.ts frontend/app/components/MarkdownEditor.vue frontend/app/components/MarkdownView.vue
git commit -m "$(cat <<'EOF'
feat(markdown): HTML 附件渲染为文件卡片 (🌐 + 紫色徽章)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Create the shared hover-preview composable + popup component

**Files:**
- Create: `frontend/app/composables/useFileCardHoverPreview.ts`
- Create: `frontend/app/components/FileCardHoverPopup.vue`

**Interfaces:**
- Consumes: `useMentionMarkdown()` (for the markdown renderer), `ref`/`watch`/`onMounted`/`onBeforeUnmount`/`nextTick` (Nuxt auto-imports).
- Produces:
  - `useFileCardHoverPreview(rootRef: Ref<HTMLElement | null>, htmlGetter: () => string, options?: { enabled?: () => boolean }): { hover: Ref<FileHoverState>, onPopupEnter: () => void, onPopupLeave: () => void }`
  - `export interface FileHoverState { visible: boolean; loading: boolean; kind: 'md' | 'html'; content: string; rawHtml: string; tooLarge: boolean; top: number; left: number; url: string; filename: string }`
  - `FileCardHoverPopup` component — props `{ hover: FileHoverState }`, emits `enter`, `leave`.

- [ ] **Step 1: Create the composable**

Create `frontend/app/composables/useFileCardHoverPreview.ts`:

```ts
import type { Ref } from 'vue'

export type FileHoverKind = 'md' | 'html'

export interface FileHoverState {
  visible: boolean
  loading: boolean
  kind: FileHoverKind
  content: string   // 渲染后的 markdown HTML (kind==='md')
  rawHtml: string   // 原始 HTML 源码,用于 iframe srcdoc (kind==='html')
  tooLarge: boolean // HTML 超过内联渲染上限
  top: number
  left: number
  url: string
  filename: string
}

const MD_FETCH_CAP = 200 * 1024          // 200KB,markdown 可安全截断
const HTML_RENDER_CAP = 2 * 1024 * 1024  // 2MB,超过则不内联渲染(截断会破坏标签)
const FETCH_ERROR = '__FETCH_ERROR__'

/**
 * 给已渲染的 markdown 容器内的文件卡片绑定悬停预览:
 *  - `.md-file-text` 且 href 以 .md 结尾  → 拉取文本、markdown 渲染
 *  - `.md-file-html` 且 href 以 .html/.htm 结尾 → 拉取文本、沙箱 iframe 渲染
 * 取内容沿用跨源 fetch(MinIO 公网 URL,CORS 已放行),不依赖公网 URL 的 content-type。
 */
export function useFileCardHoverPreview(
  rootRef: Ref<HTMLElement | null>,
  htmlGetter: () => string,
  options: { enabled?: () => boolean } = {},
) {
  const { md } = useMentionMarkdown()
  const enabled = options.enabled ?? (() => true)

  const hover = ref<FileHoverState>({
    visible: false, loading: false, kind: 'md',
    content: '', rawHtml: '', tooLarge: false,
    top: 0, left: 0, url: '', filename: '',
  })

  const cache = new Map<string, string>() // url -> 已拉取文本(按 kind 的上限封顶)
  let showTimer: ReturnType<typeof setTimeout> | null = null
  let hideTimer: ReturnType<typeof setTimeout> | null = null

  // 拉取文本,最多读到 ceiling 个字符(用于判断截断/过大);单个 url 的 kind 固定,ceiling 也固定。
  async function fetchText(url: string, ceiling: number): Promise<string> {
    if (cache.has(url)) return cache.get(url)!
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const reader = res.body?.getReader()
      if (!reader) {
        const text = await res.text()
        cache.set(url, text)
        return text
      }
      const decoder = new TextDecoder()
      let received = ''
      while (received.length < ceiling) {
        const { done, value } = await reader.read()
        if (done) break
        received += decoder.decode(value, { stream: true })
      }
      cache.set(url, received)
      return received
    } catch {
      cache.set(url, FETCH_ERROR)
      return FETCH_ERROR
    }
  }

  function kindFor(el: HTMLAnchorElement): FileHoverKind | null {
    const href = (el.href || '').toLowerCase().split('?')[0]!.split('#')[0]!
    if (el.classList.contains('md-file-text') && href.endsWith('.md')) return 'md'
    if (el.classList.contains('md-file-html') && (href.endsWith('.html') || href.endsWith('.htm'))) return 'html'
    return null
  }

  function show(el: HTMLAnchorElement, kind: FileHoverKind) {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
    if (showTimer) clearTimeout(showTimer)
    const ceiling = kind === 'md' ? MD_FETCH_CAP : HTML_RENDER_CAP
    // 预取:在弹层出现前就开始拉,500ms 内点击下载的用户不会产生无用 UI。
    void fetchText(el.href, ceiling)
    showTimer = setTimeout(async () => {
      const rect = el.getBoundingClientRect()
      const popupHeight = Math.min(window.innerHeight * 0.7, 640)
      const popupWidth = Math.min(window.innerWidth - 32, 720)
      const wantBelow = rect.bottom + popupHeight + 8 < window.innerHeight
      const top = wantBelow
        ? rect.bottom + window.scrollY + 4
        : Math.max(8 + window.scrollY, rect.top + window.scrollY - popupHeight - 4)
      const rawLeft = rect.left + window.scrollX
      const left = Math.min(rawLeft, window.scrollX + window.innerWidth - popupWidth - 16)
      const filename = el.getAttribute('download') || (el.textContent || '').trim() || el.href.split('/').pop() || 'file'
      hover.value = {
        visible: true, loading: true, kind,
        content: '', rawHtml: '', tooLarge: false,
        top, left: Math.max(window.scrollX + 8, left),
        url: el.href, filename,
      }
      const text = await fetchText(el.href, ceiling)
      if (!hover.value.visible) return
      hover.value.loading = false
      if (text === FETCH_ERROR) {
        hover.value.kind = 'md'
        hover.value.content = md.render('加载失败')
        return
      }
      if (kind === 'md') {
        const capped = text.length >= MD_FETCH_CAP ? text.slice(0, MD_FETCH_CAP) + '\n\n...(已截断)' : text
        hover.value.content = md.render(capped)
      } else if (text.length >= HTML_RENDER_CAP) {
        hover.value.tooLarge = true
      } else {
        hover.value.rawHtml = text
      }
    }, 500)
  }

  function hide() {
    if (showTimer) { clearTimeout(showTimer); showTimer = null }
    if (hideTimer) clearTimeout(hideTimer)
    hideTimer = setTimeout(() => { hover.value.visible = false }, 150)
  }

  function onPopupEnter() {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
  }
  function onPopupLeave() { hide() }

  function attach() {
    if (!enabled() || !rootRef.value) return
    const cards = rootRef.value.querySelectorAll<HTMLAnchorElement>('a.md-file-card')
    cards.forEach((card) => {
      if (card.dataset.fcHoverBound === '1') return
      const kind = kindFor(card)
      if (!kind) return
      card.dataset.fcHoverBound = '1'
      card.addEventListener('mouseenter', () => show(card, kind))
      card.addEventListener('mouseleave', hide)
    })
  }

  function maybeAttach() {
    if (!enabled()) return
    nextTick(attach)
  }

  onMounted(maybeAttach)
  watch([htmlGetter, () => enabled()], maybeAttach, { flush: 'post' })

  onBeforeUnmount(() => {
    if (showTimer) clearTimeout(showTimer)
    if (hideTimer) clearTimeout(hideTimer)
  })

  return { hover, onPopupEnter, onPopupLeave }
}
```

- [ ] **Step 2: Create the popup component**

Create `frontend/app/components/FileCardHoverPopup.vue`:

```vue
<template>
  <Teleport to="body">
    <div
      v-if="hover.visible"
      class="fc-hover-preview"
      :style="{ top: hover.top + 'px', left: hover.left + 'px' }"
      @mouseenter="emit('enter')"
      @mouseleave="emit('leave')"
    >
      <div class="fc-hover-header">
        <span class="fc-hover-title" :title="hover.filename">{{ hover.filename }}</span>
        <a
          class="fc-hover-download"
          :href="hover.url"
          :download="hover.filename"
          target="_blank"
          rel="noopener noreferrer"
        >下载</a>
      </div>
      <div v-if="hover.loading" class="fc-hover-msg">加载中...</div>
      <div v-else-if="hover.tooLarge" class="fc-hover-msg">文件较大,请点击“下载”后查看</div>
      <!-- HTML: 沙箱 iframe,无 allow-same-origin → 脚本运行在 null 源,无法触达父页面/cookie -->
      <iframe
        v-else-if="hover.kind === 'html'"
        class="fc-hover-iframe"
        :srcdoc="hover.rawHtml"
        sandbox="allow-scripts"
        referrerpolicy="no-referrer"
      />
      <!-- Markdown: 渲染后的 HTML;样式自包含于本组件,不依赖宿主页 -->
      <div v-else class="fc-hover-md" v-html="hover.content" />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { FileHoverState } from '~/composables/useFileCardHoverPreview'

defineProps<{ hover: FileHoverState }>()
const emit = defineEmits<{ enter: []; leave: [] }>()
</script>

<style>
.fc-hover-preview {
  position: absolute;
  width: min(720px, calc(100vw - 32px));
  max-height: min(640px, 70vh);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12), 0 4px 10px rgba(0, 0, 0, 0.06);
  z-index: 9999;
  font-size: 14px;
  line-height: 1.6;
  color: #1f2937;
}
.fc-hover-preview .fc-hover-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 8px 8px 0 0;
}
.fc-hover-preview .fc-hover-title {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  font-size: 13px;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fc-hover-preview .fc-hover-download {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 4px;
  background: #6366f1;
  color: #ffffff;
  text-decoration: none;
  transition: background 0.15s;
}
.fc-hover-preview .fc-hover-download:hover { background: #4f46e5; text-decoration: none; }
.fc-hover-preview .fc-hover-msg { color: #9ca3af; font-size: 13px; padding: 16px 20px; }
.fc-hover-preview .fc-hover-iframe {
  flex: 1;
  width: 100%;
  min-height: 320px;
  border: 0;
  background: #ffffff;
}
.fc-hover-preview .fc-hover-md {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
  word-wrap: break-word;
}
/* 自包含的 markdown 内容样式(核心元素),不依赖宿主页是否加载了 .markdown-body/.markdown-view */
.fc-hover-md > :first-child { margin-top: 0; }
.fc-hover-md > :last-child { margin-bottom: 0; }
.fc-hover-md h1 { font-size: 1.4em; font-weight: 700; margin: 0.67em 0; }
.fc-hover-md h2 { font-size: 1.2em; font-weight: 600; margin: 0.75em 0; }
.fc-hover-md h3 { font-size: 1.05em; font-weight: 600; margin: 0.9em 0 0.4em; }
.fc-hover-md p { margin: 0.5em 0; }
.fc-hover-md ul { margin: 0.4em 0; padding-left: 1.5em; list-style-type: disc; }
.fc-hover-md ol { margin: 0.4em 0; padding-left: 1.5em; list-style-type: decimal; }
.fc-hover-md li { margin: 0.2em 0; }
.fc-hover-md strong { font-weight: 600; }
.fc-hover-md em { font-style: italic; }
.fc-hover-md code { background: #f3f4f6; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.875em; }
.fc-hover-md pre { background: #f3f4f6; padding: 0.85em; border-radius: 6px; overflow-x: auto; margin: 0.5em 0; }
.fc-hover-md pre code { background: none; padding: 0; }
.fc-hover-md blockquote { border-left: 3px solid #d1d5db; padding-left: 0.85em; color: #6b7280; margin: 0.5em 0; }
.fc-hover-md a { color: #2563eb; text-decoration: none; }
.fc-hover-md a:hover { text-decoration: underline; }
.fc-hover-md hr { border: none; border-top: 1px solid #e5e7eb; margin: 1em 0; }
.fc-hover-md table { border-collapse: collapse; margin: 0.5em 0; }
.fc-hover-md th, .fc-hover-md td { border: 1px solid #d1d5db; padding: 0.4em 0.6em; }
.fc-hover-md img { max-width: 100%; height: auto; border-radius: 6px; margin: 0.5em 0; }

:root.dark .fc-hover-preview {
  background: #1f2937;
  border-color: #374151;
  color: #e5e7eb;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 4px 10px rgba(0, 0, 0, 0.3);
}
:root.dark .fc-hover-preview .fc-hover-header { background: #111827; border-bottom-color: #374151; }
:root.dark .fc-hover-preview .fc-hover-title { color: #e5e7eb; }
:root.dark .fc-hover-preview .fc-hover-msg { color: #6b7280; }
:root.dark .fc-hover-preview .fc-hover-iframe { background: #ffffff; } /* 文档多为浅底,保持白底更可读 */
:root.dark .fc-hover-md code,
:root.dark .fc-hover-md pre { background: #111827; }
:root.dark .fc-hover-md blockquote { border-left-color: #4b5563; color: #9ca3af; }
:root.dark .fc-hover-md a { color: #60a5fa; }
:root.dark .fc-hover-md th, :root.dark .fc-hover-md td { border-color: #4b5563; }
</style>
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: no errors. (Both files compile; not yet referenced by any consumer.)

- [ ] **Step 4: Commit**

```bash
git add frontend/app/composables/useFileCardHoverPreview.ts frontend/app/components/FileCardHoverPopup.vue
git commit -m "$(cat <<'EOF'
feat(markdown): 新增文件卡片悬停预览共享 composable + 弹层组件

支持 .md(markdown 渲染)与 .html/.htm(沙箱 iframe)两类预览。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Adopt the shared preview in `MarkdownEditor.vue` (remove inline `.md` code)

**Files:**
- Modify: `frontend/app/components/MarkdownEditor.vue` (template + script + CSS)

**Interfaces:**
- Consumes: `useFileCardHoverPreview(previewRef, () => renderedHtml.value, { enabled: () => mode.value === 'preview' })`; `FileCardHoverPopup` (auto-imported).
- Produces: no new exports. `renderedHtml`, `mode`, `previewRef` and `useInlineLinkPreviews(previewRef, ...)` are preserved.

- [ ] **Step 1: Replace the hover popup in the template**

In `frontend/app/components/MarkdownEditor.vue`, delete the entire block:

```html
  <!-- Hover preview for .md attachments -->
  <Teleport to="body">
    <div
      v-if="mdHover.visible"
      class="md-hover-preview"
      :style="{ top: mdHover.top + 'px', left: mdHover.left + 'px' }"
      @mouseenter="cancelHideMdPreview"
      @mouseleave="hideMdPreview"
    >
      <div class="md-hover-header">
        <span class="md-hover-title" :title="mdHover.filename">{{ mdHover.filename }}</span>
        <a
          class="md-hover-download"
          :href="mdHover.url"
          :download="mdHover.filename"
          target="_blank"
          rel="noopener noreferrer"
        >下载</a>
      </div>
      <div v-if="mdHover.loading" class="md-hover-loading">加载中...</div>
      <div v-else class="markdown-body md-hover-body" v-html="mdHover.content" />
    </div>
  </Teleport>
```

and replace it with:

```html
  <FileCardHoverPopup :hover="fileHover" @enter="onPopupEnter" @leave="onPopupLeave" />
```

- [ ] **Step 2: Replace the inline `.md` hover script with the composable**

In the `<script setup>` block, find the section that starts at the comment `// --- .md hover preview ---` and runs through the `onBeforeUnmount(() => { ... })` that clears `showTimer`/`hideTimer`. Replace **everything from `const previewRef = ...` through that `onBeforeUnmount`** with:

```ts
const previewRef = ref<HTMLElement | null>(null)
useInlineLinkPreviews(previewRef, () => renderedHtml.value)

// 文件卡片悬停预览(.md / .html)— 仅预览模式下绑定
const { hover: fileHover, onPopupEnter, onPopupLeave } = useFileCardHoverPreview(
  previewRef,
  () => renderedHtml.value,
  { enabled: () => mode.value === 'preview' },
)
```

This removes: `mdHover`, `mdCache`, `MD_FETCH_CAP`, `showTimer`, `hideTimer`, `fetchMdContent`, `showMdPreview`, `hideMdPreview`, `cancelHideMdPreview`, `attachMdHoverHandlers`, `maybeAttachMdHoverHandlers`, the `onMounted(maybeAttachMdHoverHandlers)`, the `watch([renderedHtml, mode], ...)`, and the hover `onBeforeUnmount`. It keeps `previewRef` and the `useInlineLinkPreviews` call (which the `.md` block declared).

> Note: verify nothing else in the file still references `mdHover`, `showMdPreview`, etc. after this edit — there should be no remaining references.

- [ ] **Step 3: Remove the obsolete `.md-hover-*` CSS**

In the `<style>` block, delete the entire section beginning with the comment `/* Hover preview popup for .md attachments */` and all `.md-hover-preview …` / `:root.dark .md-hover-preview …` rules through the end of that section (the dark `.md-hover-loading` rule). These styles now live in `FileCardHoverPopup.vue` as `.fc-hover-*`.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: no errors, and no "unused variable" / "cannot find name" referencing removed symbols.

- [ ] **Step 5: Manual verification**

Dev server running, open an issue with both a `.md` and a `.html` attachment linked in the **description**, switch to 预览 tab:
- Hover the `.md` card → markdown-rendered popup appears (unchanged from before).
- Hover the `.html` card → sandboxed iframe renders the HTML; a `<script>` inside it (e.g. one that tries `parent.document`) must NOT affect the host page.
- Moving the mouse into the popup keeps it open; leaving hides it after a moment.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/MarkdownEditor.vue
git commit -m "$(cat <<'EOF'
refactor(editor): 改用共享悬停预览 composable,移除内联 .md 预览代码

描述预览区现同时支持 .md 与 .html 卡片悬停预览。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Adopt the shared preview in `MarkdownView.vue` (comments)

**Files:**
- Modify: `frontend/app/components/MarkdownView.vue` (template + script)

**Interfaces:**
- Consumes: `useFileCardHoverPreview(rootEl, () => html.value)` (enabled defaults to always-on); `FileCardHoverPopup` (auto-imported).
- Produces: no new exports.

- [ ] **Step 1: Add the popup to the template**

In `frontend/app/components/MarkdownView.vue`, change the template from:

```html
<template>
  <div ref="rootEl" class="markdown-view" v-html="html" />
</template>
```

to:

```html
<template>
  <div ref="rootEl" class="markdown-view" v-html="html" />
  <FileCardHoverPopup :hover="fileHover" @enter="onPopupEnter" @leave="onPopupLeave" />
</template>
```

- [ ] **Step 2: Wire the composable in the script**

In the `<script setup>` block, after the existing line:

```ts
useInlineLinkPreviews(rootEl, () => html.value)
```

add:

```ts
// 文件卡片悬停预览(.md / .html)— 评论正文此前无预览,经此获得
const { hover: fileHover, onPopupEnter, onPopupLeave } = useFileCardHoverPreview(rootEl, () => html.value)
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: no errors.

- [ ] **Step 4: Manual verification**

Dev server running, post (or open) a **comment** that contains an uploaded `.md` link and one containing a `.html` link:
- Hover the `.md` card → markdown popup (this is new for comments).
- Hover the `.html` card → sandboxed iframe renders the HTML.
- Confirm the description-area behaviour from Task 5 still works (no regression).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/MarkdownView.vue
git commit -m "$(cat <<'EOF'
feat(markdown): 评论正文文件卡片支持悬停预览 (.md/.html)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Spec §3 (backend allow HTML, don't touch EXT_TO_MIME) → Task 1 ✓
- Spec §4.1 (three allowlist mirrors) → Task 2 ✓
- Spec §4.2 (HTML file card: FILE_EXT_CATEGORY + CSS) → Task 3 ✓
- Spec §4.3 (extract shared composable + popup; both consumers; comments bonus) → Tasks 4, 5, 6 ✓
- Spec §4.4 (fetch text → iframe srcdoc; `sandbox="allow-scripts"`; ~2MB cap, no truncation; click = download) → Task 4 (composable caps + popup iframe) ✓
- Spec §5 (data flow) → realised across Tasks 4–6 ✓
- Spec §6 (backend pytest; frontend typecheck + manual) → Task 1 tests; manual steps in 2/3/5/6 ✓
- Spec §7 (out of scope) → honoured; `[id].vue` panel gains upload-permission only (consistent allowlist), not the card/preview ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". All code blocks are complete.

**Type consistency:** `FileHoverState` is defined once in `useFileCardHoverPreview.ts` and imported by `FileCardHoverPopup.vue`. Returned tuple `{ hover, onPopupEnter, onPopupLeave }` matches the props/emits the popup consumes (`:hover`, `@enter`, `@leave`) in Tasks 5 & 6. `kindFor` returns `'md' | 'html' | null`; `show` only called with non-null kind. Caps `MD_FETCH_CAP`/`HTML_RENDER_CAP` referenced consistently.

**Note on `[id].vue` scope:** Task 2 updates its allowlist for consistency (mirror comment), so HTML can be uploaded via the 关联附件 panel — but that panel keeps showing non-image files as plain list rows (no card/hover), which matches the spec's out-of-scope decision.
