# GitHub Rich Card Enhancement — Implementation Plan

> **For agentic workers:** subagent-driven, TDD, on branch `feat/markdown-link-hover-preview`. Steps use `- [ ]`.

**Goal:** External GitHub PR/issue links show a rich card (title, state, author) via the existing backend GitHub integration; all other external links show a clean domain+favicon card; the live `<iframe>` is retired (it blanked on `X-Frame-Options` sites like GitHub).

**Design decisions (approved):**
- GitHub `pull`/`issues` URLs → rich card. Other external → domain+favicon card. Internal → unchanged (issue cards only).
- Retire the iframe entirely (and its 3s fallback timer) — replaced by the domain card for non-GitHub external links.

**Tech:** Django REST (reuse `apps/repos`), Nuxt 4 + Vue 3, pytest (mock `apps.repos.services.requests.get`), vitest/@nuxt/test-utils.

---

## Task GP-1 (backend): GitHub preview service + endpoint

**Files:**
- Modify `backend/apps/repos/services.py` (add `parse_github_ref` + `GitHubPreviewService`)
- Modify `backend/apps/repos/views.py` (add `GitHubPreviewView`)
- Modify `backend/apps/repos/urls.py` (register route)
- Create `backend/tests/test_github_preview.py`

- [ ] **Step 1: failing tests** — create `backend/tests/test_github_preview.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from tests.factories import RepoFactory
from apps.repos.services import parse_github_ref, GitHubPreviewService


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_parse_github_ref_pull():
    assert parse_github_ref("https://github.com/octocat/hello/pull/42") == {
        "owner": "octocat", "repo": "hello", "kind": "pull", "number": 42,
    }


def test_parse_github_ref_issue_with_query():
    assert parse_github_ref("https://github.com/octocat/hello/issues/7?x=1") == {
        "owner": "octocat", "repo": "hello", "kind": "issues", "number": 7,
    }


def test_parse_github_ref_rejects_non_github_and_bare_repo():
    assert parse_github_ref("https://example.com/a/b/pull/1") is None
    assert parse_github_ref("https://github.com/octocat/hello") is None
    assert parse_github_ref("") is None


@pytest.mark.django_db
def test_fetch_preview_pr_merged_uses_repo_token():
    RepoFactory(full_name="octocat/hello", github_token="ghp_x")
    payload = {"number": 42, "title": "Add feature", "state": "closed", "merged": True,
               "html_url": "https://github.com/octocat/hello/pull/42",
               "user": {"login": "alice", "avatar_url": "https://a/x.png"}}
    with patch("apps.repos.services.requests.get") as mg:
        mg.return_value = MagicMock(status_code=200, json=lambda: payload)
        data = GitHubPreviewService().fetch_preview("octocat", "hello", "pull", 42)
    assert data["kind"] == "pr"
    assert data["state"] == "merged"
    assert data["author_login"] == "alice"
    assert data["repo_full_name"] == "octocat/hello"
    assert mg.call_args.kwargs["headers"].get("Authorization") == "Bearer ghp_x"


@pytest.mark.django_db
def test_fetch_preview_issue_open_unauthenticated():
    payload = {"number": 7, "title": "Bug", "state": "open", "html_url": "u",
               "user": {"login": "bob", "avatar_url": "av"}}
    with patch("apps.repos.services.requests.get") as mg:
        mg.return_value = MagicMock(status_code=200, json=lambda: payload)
        data = GitHubPreviewService().fetch_preview("octocat", "hello", "issues", 7)
    assert data["kind"] == "issue"
    assert data["state"] == "open"
    assert "Authorization" not in mg.call_args.kwargs["headers"]


@pytest.mark.django_db
def test_fetch_preview_none_on_404():
    with patch("apps.repos.services.requests.get") as mg:
        mg.return_value = MagicMock(status_code=404, json=lambda: {})
        assert GitHubPreviewService().fetch_preview("o", "r", "pull", 1) is None


@pytest.mark.django_db
def test_endpoint_returns_card(auth_client):
    payload = {"number": 42, "title": "T", "state": "open", "html_url": "u",
               "user": {"login": "a", "avatar_url": "av"}}
    with patch("apps.repos.services.requests.get") as mg:
        mg.return_value = MagicMock(status_code=200, json=lambda: payload)
        resp = auth_client.get("/api/repos/github-preview/",
                               {"url": "https://github.com/octocat/hello/pull/42"})
    assert resp.status_code == 200
    assert resp.data["kind"] == "pr"


@pytest.mark.django_db
def test_endpoint_unsupported_for_non_github(auth_client):
    resp = auth_client.get("/api/repos/github-preview/", {"url": "https://example.com/x"})
    assert resp.status_code == 200
    assert resp.data == {"supported": False}
```

- [ ] **Step 2:** run `uv run pytest tests/test_github_preview.py` → FAIL (imports missing).

- [ ] **Step 3: implement** — in `backend/apps/repos/services.py`, add near the top (after imports, before `GitHubSyncService`):

```python
from django.core.cache import cache

GITHUB_REF_RE = re.compile(
    r"^https?://github\.com/([\w.-]+)/([\w.-]+)/(pull|issues)/(\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)


def parse_github_ref(url):
    """解析 GitHub PR/issue 链接 → {owner, repo, kind, number};非法返回 None。"""
    m = GITHUB_REF_RE.match(url or "")
    if not m:
        return None
    return {
        "owner": m.group(1),
        "repo": m.group(2),
        "kind": m.group(3).lower(),
        "number": int(m.group(4)),
    }


class GitHubPreviewService:
    """单条 GitHub PR/issue 取数用于悬停预览卡片(仅调 api.github.com 固定主机,无 SSRF)。"""
    GITHUB_API = "https://api.github.com"
    CACHE_TTL = 300

    def fetch_preview(self, owner, repo, kind, number):
        cache_key = f"gh-preview:{owner}/{repo}/{kind}/{number}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        api_path = "pulls" if kind == "pull" else "issues"
        token = (
            Repo.objects.filter(full_name=f"{owner}/{repo}")
            .exclude(github_token="")
            .values_list("github_token", flat=True)
            .first()
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = requests.get(
                f"{self.GITHUB_API}/repos/{owner}/{repo}/{api_path}/{number}",
                headers=headers,
                timeout=10,
            )
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        item = resp.json()
        if kind == "pull":
            state = "merged" if item.get("merged") else item.get("state", "open")
            norm_kind = "pr"
        else:
            state = item.get("state", "open")
            norm_kind = "issue"
        user = item.get("user") or {}
        data = {
            "kind": norm_kind,
            "number": number,
            "title": item.get("title") or "",
            "state": state,
            "author_login": user.get("login") or "",
            "author_avatar": user.get("avatar_url") or "",
            "repo_full_name": f"{owner}/{repo}",
            "html_url": item.get("html_url") or "",
        }
        cache.set(cache_key, data, self.CACHE_TTL)
        return data
```

In `backend/apps/repos/views.py`, add the import update and view:

```python
# add to the .services import line:
from .services import GitHubSyncService, RepoCloneService, GitHubPreviewService, parse_github_ref


class GitHubPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ref = parse_github_ref(request.query_params.get("url", ""))
        if not ref:
            return Response({"supported": False})
        data = GitHubPreviewService().fetch_preview(**ref)
        if not data:
            return Response({"supported": False})
        return Response(data)
```

In `backend/apps/repos/urls.py`, add the import (`GitHubPreviewView`) and a route alongside the other static paths:

```python
    path("github-preview/", GitHubPreviewView.as_view(), name="github-preview"),
```

- [ ] **Step 4:** run `uv run pytest tests/test_github_preview.py` → PASS.

- [ ] **Step 5: commit**

```bash
git add apps/repos/services.py apps/repos/views.py apps/repos/urls.py tests/test_github_preview.py
git commit -F - <<'EOF'
feat(repos): GitHub PR/issue 悬停预览取数接口

新增 parse_github_ref + GitHubPreviewService(复用 Repo token,失败/私有回退
未认证),GET /api/repos/github-preview/?url= 返回卡片数据或 {supported:false};
仅调 api.github.com 固定主机,5 分钟缓存。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task GP-2 (frontend logic): github match + fetch

**Files:** Modify `frontend/app/composables/useLinkPreview.ts`; modify `frontend/tests/linkPreview.test.ts`. Run from `frontend/`.

- [ ] **Step 1: failing tests** — append to `frontend/tests/linkPreview.test.ts`:

```ts
import { fetchGithubPreview, clearGithubPreviewCache } from '../app/composables/useLinkPreview'

describe('matchPreviewAnchor github', () => {
  function anchorEl(html: string): HTMLAnchorElement {
    const d = document.createElement('div'); d.innerHTML = html; return d.querySelector('a')!
  }
  it('classifies a github PR link as github', () => {
    const a = anchorEl('<a class="external-link" href="https://github.com/octocat/hello/pull/42">PR</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'github', url: 'https://github.com/octocat/hello/pull/42' })
  })
  it('classifies a github issue link as github', () => {
    const a = anchorEl('<a class="external-link" href="https://github.com/octocat/hello/issues/7">x</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'github', url: 'https://github.com/octocat/hello/issues/7' })
  })
  it('a non-PR github link stays external', () => {
    const a = anchorEl('<a class="external-link" href="https://github.com/octocat/hello">repo</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'external', url: 'https://github.com/octocat/hello' })
  })
})

describe('fetchGithubPreview', () => {
  beforeEach(() => clearGithubPreviewCache())
  it('maps the endpoint payload', async () => {
    const fetcher = vi.fn().mockResolvedValue({ kind: 'pr', number: 42, title: 'T', state: 'merged', author_login: 'a', author_avatar: 'av', repo_full_name: 'o/r', html_url: 'u' })
    const r = await fetchGithubPreview('https://github.com/o/r/pull/42', fetcher)
    expect(fetcher).toHaveBeenCalledWith('/api/repos/github-preview/?url=' + encodeURIComponent('https://github.com/o/r/pull/42'))
    expect(r).toMatchObject({ kind: 'pr', number: 42, state: 'merged' })
  })
  it('returns null when backend says unsupported', async () => {
    const fetcher = vi.fn().mockResolvedValue({ supported: false })
    expect(await fetchGithubPreview('https://github.com/o/r/pull/1', fetcher)).toBeNull()
  })
  it('caches by url', async () => {
    const fetcher = vi.fn().mockResolvedValue({ kind: 'pr', number: 1, title: '', state: 'open', author_login: '', author_avatar: '', repo_full_name: '', html_url: '' })
    await fetchGithubPreview('u1', fetcher); await fetchGithubPreview('u1', fetcher)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2:** `npm run test -- tests/linkPreview.test.ts` → FAIL.

- [ ] **Step 3: implement** — in `frontend/app/composables/useLinkPreview.ts`:

Change the type union:
```ts
export type HoverPreviewType = 'issue' | 'external' | 'github'
```

Add the github regex above `matchPreviewAnchor`:
```ts
const GITHUB_REF_RE = /^https?:\/\/github\.com\/[\w.-]+\/[\w.-]+\/(pull|issues)\/\d+(?:[/?#]|$)/i
```

Replace the `external-link` branch of `matchPreviewAnchor` with:
```ts
  if (a.classList.contains('external-link')) {
    try {
      const u = new URL(a.href)
      if (u.host === location.host) return null
      if (u.hostname === 'github.com' && GITHUB_REF_RE.test(a.href)) {
        return { type: 'github', url: a.href }
      }
      return { type: 'external', url: a.href }
    } catch {
      // 无法解析的 href 不预览
    }
  }
```

Append the github fetch (after `fetchIssuePreview`):
```ts
export interface GithubPreview {
  kind: 'pr' | 'issue'
  number: number
  title: string
  state: 'open' | 'closed' | 'merged'
  author_login: string
  author_avatar: string
  repo_full_name: string
  html_url: string
}

const githubCache = new Map<string, Promise<GithubPreview | null>>()

export function clearGithubPreviewCache() {
  githubCache.clear()
}

export function fetchGithubPreview(
  url: string,
  fetcher: (u: string) => Promise<unknown>,
): Promise<GithubPreview | null> {
  const cached = githubCache.get(url)
  if (cached) return cached
  const p = fetcher(`/api/repos/github-preview/?url=${encodeURIComponent(url)}`).then((raw) => {
    const d = raw as Record<string, unknown>
    if (!d || d.supported === false) return null
    return {
      kind: d.kind === 'pr' ? 'pr' : 'issue',
      number: Number(d.number),
      title: String(d.title ?? ''),
      state: (d.state as GithubPreview['state']) ?? 'open',
      author_login: String(d.author_login ?? ''),
      author_avatar: String(d.author_avatar ?? ''),
      repo_full_name: String(d.repo_full_name ?? ''),
      html_url: String(d.html_url ?? ''),
    } as GithubPreview
  })
  p.catch(() => githubCache.delete(url))
  githubCache.set(url, p)
  return p
}
```

- [ ] **Step 4:** `npm run test -- tests/linkPreview.test.ts` → PASS.

- [ ] **Step 5: commit**

```bash
git add app/composables/useLinkPreview.ts tests/linkPreview.test.ts
git commit -F - <<'EOF'
feat(preview): GitHub 链接识别与取数

matchPreviewAnchor 把 github.com PR/issue 链接归类为 github;
fetchGithubPreview 调后端预览接口并按 url 缓存,unsupported 返回 null。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task GP-3 (frontend card): LinkHoverCard github branch + retire iframe

**Files:** Modify `frontend/app/components/LinkHoverCard.vue`; modify `frontend/tests/linkHoverCard.test.ts`.

Goal: add a `github` card branch; change the `external` branch to a domain+favicon card (REMOVE the `<iframe>`, the `iframe-fallback` prop, and the `iframe-load` emit). Keep the issue branch unchanged.

- [ ] **Step 1: update tests** — in `frontend/tests/linkHoverCard.test.ts`:

DELETE the existing `describe('LinkHoverCard (external)', ...)` block (the iframe + fallback tests) and REPLACE with:

```ts
describe('LinkHoverCard (external)', () => {
  it('renders a domain card with an open-in-new-tab link (no iframe)', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'external',
      issue: null, issueLoading: false, issueError: false,
      github: null, githubLoading: false,
      url: 'https://example.com/docs',
    } })
    expect(document.body.querySelector('iframe')).toBeNull()
    expect(document.body.textContent).toContain('example.com')
    const open = document.body.querySelector('a.lhc-open') as HTMLAnchorElement
    expect(open.getAttribute('target')).toBe('_blank')
    expect(open.getAttribute('rel')).toContain('noopener')
    w.unmount()
  })
})

describe('LinkHoverCard (github)', () => {
  const pr = {
    kind: 'pr' as const, number: 42, title: '添加悬停预览', state: 'merged' as const,
    author_login: 'alice', author_avatar: '', repo_full_name: 'octocat/hello',
    html_url: 'https://github.com/octocat/hello/pull/42',
  }
  it('renders a github PR card with state and author', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'github',
      issue: null, issueLoading: false, issueError: false,
      github: pr, githubLoading: false, url: pr.html_url,
    } })
    expect(document.body.textContent).toContain('添加悬停预览')
    expect(document.body.textContent).toContain('#42')
    expect(document.body.textContent).toContain('octocat/hello')
    expect(document.body.textContent).toContain('alice')
    expect(document.body.textContent?.toLowerCase()).toContain('merged')
    w.unmount()
  })
  it('shows a loading state for github', async () => {
    const w = await mountSuspended(LinkHoverCard, { props: {
      visible: true, top: 0, left: 0, type: 'github',
      issue: null, issueLoading: false, issueError: false,
      github: null, githubLoading: true, url: pr.html_url,
    } })
    expect(document.body.textContent).toContain('加载中')
    w.unmount()
  })
})
```

(Also update the three issue-branch test prop objects and the not-visible test to include `github: null, githubLoading: false` and drop `iframeFallback`. Every `mountSuspended(LinkHoverCard, ...)` call must pass the full new prop set.)

- [ ] **Step 2:** `npm run test -- tests/linkHoverCard.test.ts` → FAIL.

- [ ] **Step 3: implement** — in `frontend/app/components/LinkHoverCard.vue`:

Props (replace the `defineProps` block): drop `iframeFallback`, add `github`/`githubLoading`, widen `type`:
```ts
import type { IssuePreview, GithubPreview } from '~/composables/useLinkPreview'

const props = defineProps<{
  visible: boolean
  top: number
  left: number
  type: 'issue' | 'external' | 'github' | null
  issue: IssuePreview | null
  issueLoading: boolean
  issueError: boolean
  github: GithubPreview | null
  githubLoading: boolean
  url: string | null
}>()

const emit = defineEmits<{ enter: []; leave: [] }>()
```

Add github state-pill color + label helpers in `<script setup>`:
```ts
const ghStateColor = computed(() => {
  const s = props.github?.state
  return s === 'merged' ? '#8957e5' : s === 'closed' ? '#cf222e' : '#1a7f37'
})
const ghStateText = computed(() => {
  const s = props.github?.state
  return s === 'merged' ? 'Merged' : s === 'closed' ? 'Closed' : 'Open'
})
function goGithub() { if (props.github?.html_url) window.open(props.github.html_url, '_blank', 'noopener') }
```

Template — keep the issue `<template v-if="type === 'issue'">` block. Add a github branch and REPLACE the external branch:
```vue
      <!-- GitHub PR/issue -->
      <template v-else-if="type === 'github'">
        <div v-if="githubLoading || !github" class="lhc-state">{{ githubLoading ? '加载中…' : '加载失败' }}</div>
        <a v-else class="lhc-issue" :href="github.html_url" target="_blank" rel="noopener noreferrer" @click.prevent="goGithub">
          <div class="lhc-issue-head">
            <span class="lhc-no">{{ github.kind === 'pr' ? 'PR' : 'Issue' }} #{{ github.number }}</span>
            <span class="lhc-title">{{ github.title }}</span>
          </div>
          <div class="lhc-meta">
            <span class="lhc-pill" :style="{ background: ghStateColor, color: '#fff' }">{{ ghStateText }}</span>
          </div>
          <div class="lhc-foot">
            <img v-if="github.author_avatar" class="lhc-avatar" :src="github.author_avatar" alt="">
            <span class="lhc-assignee">{{ github.author_login }}</span>
            <span class="lhc-time">{{ github.repo_full_name }}</span>
          </div>
        </a>
      </template>

      <!-- 外部 URL:域名卡片(无 iframe) -->
      <template v-else-if="type === 'external'">
        <div class="lhc-urlbar">
          <img v-if="faviconUrl" class="lhc-favicon" :src="faviconUrl" alt="">
          <span class="lhc-host" :title="url || ''">{{ host }}</span>
          <a class="lhc-open" :href="url || '#'" target="_blank" rel="noopener noreferrer">在新标签打开 ↗</a>
        </div>
      </template>
```

Remove from `<script setup>`: nothing else needed (`host`/`faviconUrl` computeds stay). Delete any now-unused iframe-only code if present.

CSS: keep existing styles. The `.is-external { width: 480px; }` can be removed or kept (domain card is small — change to a sensible width). Add:
```css
.lhc-favicon { width: 1rem; height: 1rem; flex-shrink: 0; }
```
(Remove the `.lhc-iframe` and `.lhc-fallback` rules — they're no longer used.)

- [ ] **Step 4:** `npm run test -- tests/linkHoverCard.test.ts` → PASS.

- [ ] **Step 5: commit**

```bash
git add app/components/LinkHoverCard.vue tests/linkHoverCard.test.ts
git commit -F - <<'EOF'
feat(preview): LinkHoverCard GitHub 卡片,外链改域名卡片

新增 GitHub PR/issue 富卡片(标题/编号/状态胶囊/作者/仓库);
外链分支改为域名+favicon+新标签打开卡片,移除 iframe 及其降级逻辑。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task GP-4 (frontend host): MarkdownHoverPreview github + external

**Files:** Modify `frontend/app/components/MarkdownHoverPreview.vue`; modify `frontend/tests/markdownHoverPreview.test.ts`.

Goal: handle `github` (fetch like issue; on null/error fall back to the external domain card); `external` shows the static domain card; REMOVE the iframe timeout/timer logic and the `iframe-load` binding.

- [ ] **Step 1: update tests** — in `frontend/tests/markdownHoverPreview.test.ts`:

Update the import to add github cache clear:
```ts
import { clearIssuePreviewCache, clearGithubPreviewCache } from '../app/composables/useLinkPreview'
```
In `beforeEach`, also call `clearGithubPreviewCache()`.

REPLACE the existing `'hovering an external link shows an iframe'` test with:

```ts
  it('hovering a non-github external link shows the domain card (no iframe)', async () => {
    const container = makeContainer('<a class="external-link" href="https://example.com/docs">example</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(document.body.querySelector('iframe')).toBeNull()
    expect(document.body.textContent).toContain('example.com')
    w.unmount()
  })

  it('hovering a github PR link fetches and shows the github card', async () => {
    apiMock.mockResolvedValue({ kind: 'pr', number: 42, title: 'PR标题', state: 'open', author_login: 'alice', author_avatar: '', repo_full_name: 'octocat/hello', html_url: 'https://github.com/octocat/hello/pull/42' })
    const container = makeContainer('<a class="external-link" href="https://github.com/octocat/hello/pull/42">PR</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/repos/github-preview/?url=' + encodeURIComponent('https://github.com/octocat/hello/pull/42'))
    expect(document.body.textContent).toContain('PR标题')
    w.unmount()
  })

  it('github link that backend marks unsupported falls back to the domain card', async () => {
    apiMock.mockResolvedValue({ supported: false })
    const container = makeContainer('<a class="external-link" href="https://github.com/octocat/hello/pull/99">PR</a>')
    const w = await mountSuspended(MarkdownHoverPreview, { props: { container } })
    vi.useFakeTimers()
    container.querySelector('a')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()
    await flushPromises()
    expect(document.body.textContent).toContain('github.com')
    w.unmount()
  })
```

(Keep the existing issue-mention test and the anchor-swap test. The anchor-swap test still uses two issue mentions — unchanged.)

- [ ] **Step 2:** `npm run test -- tests/markdownHoverPreview.test.ts` → FAIL.

- [ ] **Step 3: implement** — in `frontend/app/components/MarkdownHoverPreview.vue`:

Update the import:
```ts
import { matchPreviewAnchor, fetchIssuePreview, fetchGithubPreview, type IssuePreview, type GithubPreview } from '~/composables/useLinkPreview'
```

State: drop `iframeFallback`, add `github`/`githubLoading`:
```ts
const state = reactive<{
  visible: boolean; top: number; left: number
  type: 'issue' | 'external' | 'github' | null
  issue: IssuePreview | null; issueLoading: boolean; issueError: boolean
  github: GithubPreview | null; githubLoading: boolean
  url: string | null
}>({
  visible: false, top: 0, left: 0, type: null,
  issue: null, issueLoading: false, issueError: false,
  github: null, githubLoading: false,
  url: null,
})
```

Remove `IFRAME_TIMEOUT`, the `iframeTimer` variable, `clearIframeTimer`, and `onIframeLoad`.

`scheduleHide` callback resets the new fields too:
```ts
  hideTimer = setTimeout(() => {
    state.visible = false
    state.type = null
    state.issue = null
    state.github = null
    state.url = null
    state.issueLoading = false
    state.issueError = false
    state.githubLoading = false
    activeAnchor = null
  }, HIDE_DELAY)
```

`showFor` — replace the issue/external branches with issue/github/external:
```ts
function showFor(anchor: HTMLAnchorElement) {
  const match = matchPreviewAnchor(anchor)
  if (!match) return
  position(anchor)
  cancelHide()
  if (match.type === 'issue' && match.issueId) {
    state.type = 'issue'; state.url = null; state.github = null
    state.issue = null; state.issueError = false; state.issueLoading = true; state.visible = true
    fetchIssuePreview(match.issueId, api)
      .then((data) => { if (activeAnchor === anchor) { state.issue = data; state.issueLoading = false } })
      .catch(() => { if (activeAnchor === anchor) { state.issueError = true; state.issueLoading = false } })
  } else if (match.type === 'github' && match.url) {
    state.type = 'github'; state.issue = null; state.github = null
    state.url = match.url; state.githubLoading = true; state.visible = true
    fetchGithubPreview(match.url, api)
      .then((data) => {
        if (activeAnchor !== anchor) return
        if (data) { state.github = data; state.githubLoading = false }
        else { state.type = 'external'; state.githubLoading = false } // 后端不支持 → 域名卡片
      })
      .catch(() => { if (activeAnchor === anchor) { state.type = 'external'; state.githubLoading = false } })
  } else if (match.type === 'external' && match.url) {
    state.type = 'external'; state.issue = null; state.github = null
    state.url = match.url; state.visible = true
  }
}
```

Template — bind the new props and drop the iframe-load handler:
```vue
  <LinkHoverCard
    :visible="state.visible"
    :top="state.top"
    :left="state.left"
    :type="state.type"
    :issue="state.issue"
    :issue-loading="state.issueLoading"
    :issue-error="state.issueError"
    :github="state.github"
    :github-loading="state.githubLoading"
    :url="state.url"
    @enter="cancelHide"
    @leave="scheduleHide"
  />
```

In `onBeforeUnmount`, remove the `clearIframeTimer()` call (keep `clearShow(); cancelHide()`).

- [ ] **Step 4:** `npm run test -- tests/markdownHoverPreview.test.ts` → PASS.

- [ ] **Step 5: commit**

```bash
git add app/components/MarkdownHoverPreview.vue tests/markdownHoverPreview.test.ts
git commit -F - <<'EOF'
feat(preview): 宿主接入 GitHub 卡片,外链改静态域名卡片

github 类型走 fetchGithubPreview(不支持则回退域名卡片);external 直接出
域名卡片;移除 iframe 超时/计时逻辑。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

## Verification (after GP-1..GP-4)

- `cd frontend && npm run test` → all pass.
- `cd frontend && npx nuxi typecheck` → no NEW errors in the changed files.
- `cd backend && TMPDIR=/tmp uv run pytest tests/test_github_preview.py` (and a quick `uv run pytest -q` smoke if fast) → pass.
- Manual: hover a GitHub PR link → rich card; hover a non-GitHub external link → domain card (no blank iframe).
