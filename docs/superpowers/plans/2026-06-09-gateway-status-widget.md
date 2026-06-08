# 电话线路状态 Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dashboard block to the work home (首页) that shows SIP-gateway phone-line connectivity + today's call stats, auto-refreshing every 15s only while the tab is visible.

**Architecture:** Frontend polls a new auth-required backend proxy `/api/dashboard/gateway-status/` (never the upstream directly — the upstream is plain-HTTP, needs a secret `X-API-Key`, and has no CORS). The proxy fetches the upstream server-side with the key from a backend env var and caches the result ~12s (with a 1h "last-good" fallback for graceful staleness). A singleton Vue composable (mirroring the existing `useUptimeMonitors`) drives one 15s, visibility-aware timer regardless of how many components mount.

**Tech Stack:** Django REST Framework + `requests` + `django.core.cache` (backend); Nuxt 4 / Vue 3 composable + component (frontend). No new dependencies.

**Reference spec:** `docs/superpowers/specs/2026-06-08-gateway-status-widget-design.md`

---

### Task 0: Create feature branch

We are on `main`. Branch first.

- [ ] **Step 1: Branch**

```bash
cd /Users/ck/Git/matrix/devtrack
git checkout -b feat/gateway-status-widget
```

---

### Task 1: Backend proxy endpoint

**Files:**
- Modify: `backend/config/settings.py` (add env vars after the `DEVTRAKR_*` block, ~line 197)
- Modify: `backend/apps/issues/views.py` (add imports + `GatewayStatusView`)
- Modify: `backend/apps/issues/dashboard_urls.py` (register route)
- Test: `backend/tests/test_gateway_status.py` (create)

- [ ] **Step 1: Add settings env vars**

In `backend/config/settings.py`, immediately after the `DEVTRAKR_PROD_KEY = ...` line, add:

```python
# 电话线路(SIP 网关)状态代理 — 前端经 /api/dashboard/gateway-status/ 拉取。
# API_KEY 是密钥,只写 .env 不入库;后端主机需能出网访问该 URL。
GATEWAY_STATUS_URL = os.environ.get("GATEWAY_STATUS_URL", "")
GATEWAY_STATUS_API_KEY = os.environ.get("GATEWAY_STATUS_API_KEY", "")
GATEWAY_STATUS_CACHE_TTL = int(os.environ.get("GATEWAY_STATUS_CACHE_TTL", "12"))
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_gateway_status.py`:

```python
import pytest
import requests
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from apps.issues.views import _GW_CACHE_KEY

pytestmark = pytest.mark.django_db

URL = "/api/dashboard/gateway-status/"

UPSTREAM_OK = {
    "code": 0,
    "data": [
        {"id": 3, "name": "ippbx", "proxy_ip_list": "111.59.23.221", "port": 5060,
         "online": True, "ping_latency_ms": 13, "active_calls": 0,
         "today_calls": 6, "today_answered": 1, "today_answer_rate": 16.66,
         "ping_error": "", "last_ping_at": "2026-06-08T08:48:45Z"},
        {"id": 5, "name": "yd_test_in", "proxy_ip_list": "172.16.1.29", "port": 5060,
         "online": False, "ping_latency_ms": 3000, "active_calls": 0,
         "today_calls": 0, "today_answered": 0, "today_answer_rate": 0,
         "ping_error": "no response within timeout", "last_ping_at": "2026-06-08T08:48:48Z"},
    ],
}


def _ok_resp(payload):
    m = MagicMock()
    m.json.return_value = payload
    m.raise_for_status.return_value = None
    return m


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _configure(settings):
    settings.GATEWAY_STATUS_URL = "http://upstream.test/api/external/gateway-status"
    settings.GATEWAY_STATUS_API_KEY = "testkey"
    settings.GATEWAY_STATUS_CACHE_TTL = 12


def test_requires_auth(api_client):
    resp = api_client.get(URL)
    assert resp.status_code in (401, 403)


def test_unconfigured_returns_configured_false(auth_client, settings):
    settings.GATEWAY_STATUS_URL = ""
    settings.GATEWAY_STATUS_API_KEY = ""
    resp = auth_client.get(URL)
    assert resp.status_code == 200
    assert resp.json() == {"configured": False, "lines": []}


def test_success_normalizes_and_sends_key(auth_client, settings):
    _configure(settings)
    with patch("apps.issues.views.requests.get", return_value=_ok_resp(UPSTREAM_OK)) as mock_get:
        resp = auth_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["stale"] is False
    assert "fetched_at" in body
    assert [l["name"] for l in body["lines"]] == ["ippbx", "yd_test_in"]
    mock_get.assert_called_once_with(
        settings.GATEWAY_STATUS_URL,
        headers={"X-API-Key": "testkey"},
        timeout=8,
    )


def test_second_request_served_from_cache(auth_client, settings):
    _configure(settings)
    with patch("apps.issues.views.requests.get", return_value=_ok_resp(UPSTREAM_OK)) as mock_get:
        auth_client.get(URL)
        resp2 = auth_client.get(URL)
    assert resp2.status_code == 200
    assert mock_get.call_count == 1  # 第二次命中 12s 短缓存


def test_stale_fallback_to_last_good(auth_client, settings):
    _configure(settings)
    # 第一次成功 → 写 last-good
    with patch("apps.issues.views.requests.get", return_value=_ok_resp(UPSTREAM_OK)):
        auth_client.get(URL)
    cache.delete(_GW_CACHE_KEY)  # 模拟 12s 短缓存过期,last-good 仍在
    # 第二次上游失败 → 回退 last-good
    with patch("apps.issues.views.requests.get", side_effect=requests.RequestException("boom")):
        resp = auth_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    assert [l["name"] for l in body["lines"]] == ["ippbx", "yd_test_in"]


def test_upstream_error_without_cache(auth_client, settings):
    _configure(settings)
    with patch("apps.issues.views.requests.get", side_effect=requests.RequestException("boom")):
        resp = auth_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"configured": True, "stale": True, "lines": [], "error": "upstream_unavailable"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_gateway_status.py -v`
Expected: FAIL — `ImportError: cannot import name '_GW_CACHE_KEY'` / view + route don't exist yet.

- [ ] **Step 4: Implement the view**

In `backend/apps/issues/views.py`, add to the imports at the top (after the existing `from django.utils import timezone` line):

```python
import requests
from django.conf import settings as django_settings
from django.core.cache import cache
```

Then add the view (place it next to `DashboardRecentActivityView`):

```python
_GW_CACHE_KEY = "gateway_status:payload"
_GW_LAST_GOOD_KEY = "gateway_status:last_good"
_GW_LAST_GOOD_TTL = 3600  # 1h:上游短时不可达时回退展示的"上次正常"数据


class GatewayStatusView(APIView):
    """电话线路(SIP 网关)连通 + 今日话务状态代理。

    服务端持密钥拉上游并短缓存(默认 12s),避免前端暴露 X-API-Key、
    混合内容(上游为 http)与 CORS。上游不可达时回退 last-good 并标记 stale。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        url = django_settings.GATEWAY_STATUS_URL
        key = django_settings.GATEWAY_STATUS_API_KEY
        if not url or not key:
            return Response({"configured": False, "lines": []})

        cached = cache.get(_GW_CACHE_KEY)
        if cached is not None:
            return Response({"configured": True, "stale": False, **cached})

        try:
            resp = requests.get(url, headers={"X-API-Key": key}, timeout=8)
            resp.raise_for_status()
            body = resp.json()
            if not isinstance(body, dict) or body.get("code") != 0:
                raise ValueError(f"unexpected upstream body: {body!r}")
            payload = {
                "fetched_at": timezone.now().isoformat(),
                "lines": body.get("data") or [],
            }
            cache.set(_GW_CACHE_KEY, payload, django_settings.GATEWAY_STATUS_CACHE_TTL)
            cache.set(_GW_LAST_GOOD_KEY, payload, _GW_LAST_GOOD_TTL)
            return Response({"configured": True, "stale": False, **payload})
        except Exception:
            last_good = cache.get(_GW_LAST_GOOD_KEY)
            if last_good is not None:
                return Response({"configured": True, "stale": True, **last_good})
            return Response({
                "configured": True,
                "stale": True,
                "lines": [],
                "error": "upstream_unavailable",
            })
```

- [ ] **Step 5: Register the route**

In `backend/apps/issues/dashboard_urls.py`, add `GatewayStatusView` to the import block and a path:

```python
from django.urls import path
from .views import (
    DashboardStatsView,
    DashboardTrendsView,
    DashboardPriorityDistributionView,
    DashboardLeaderboardView,
    DashboardRecentActivityView,
    GatewayStatusView,
)

urlpatterns = [
    path("stats/", DashboardStatsView.as_view(), name="dashboard-stats"),
    path("trends/", DashboardTrendsView.as_view(), name="dashboard-trends"),
    path("priority-distribution/", DashboardPriorityDistributionView.as_view(), name="dashboard-priority"),
    path("developer-leaderboard/", DashboardLeaderboardView.as_view(), name="dashboard-leaderboard"),
    path("recent-activity/", DashboardRecentActivityView.as_view(), name="dashboard-activity"),
    path("gateway-status/", GatewayStatusView.as_view(), name="dashboard-gateway-status"),
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_gateway_status.py -v`
Expected: PASS — all 6 tests green.

- [ ] **Step 7: Commit**

```bash
git add backend/config/settings.py backend/apps/issues/views.py backend/apps/issues/dashboard_urls.py backend/tests/test_gateway_status.py
git commit -m "feat(dashboard): add gateway-status backend proxy with short cache

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Frontend polling composable

**Files:**
- Create: `frontend/app/composables/useGatewayStatus.ts`

- [ ] **Step 1: Create the composable**

Create `frontend/app/composables/useGatewayStatus.ts`:

```ts
import type { Ref } from 'vue'

// 电话线路状态:模块级单例 + 订阅者引用计数,对标 useUptimeMonitors。
// 首页只挂一个组件,但保持同一模式:全站只跑一个 15s 定时器,全部卸载后停。
export interface GatewayLine {
  name: string
  proxy_ip_list: string
  port: number
  online: boolean
  ping_latency_ms: number
  active_calls: number
  today_calls: number
  today_answered: number
  today_answer_rate: number
  ping_error?: string
  last_ping_at: string
}

interface GatewayPayload {
  configured: boolean
  stale?: boolean
  fetched_at?: string
  lines?: GatewayLine[]
  error?: string
}

const POLL_INTERVAL_MS = 15_000

const lines = ref<GatewayLine[]>([])
const configured = ref(true) // 乐观:首拉前按已配置渲染 loading,拿到 false 再显示"未配置"
const stale = ref(false)
const fetchedAt = ref('')
const loading = ref(true)

let subscribers = 0
let pollTimer: ReturnType<typeof setInterval> | null = null
let inFlight: Promise<void> | null = null
let apiFn: (<T>(url: string, options?: any) => Promise<T>) | null = null
let authUser: Ref<{ id: string } | null> | null = null

async function fetchOnce(): Promise<void> {
  if (!apiFn || !authUser) return
  if (!authUser.value) return
  // 后台标签跳过,避免白跑
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
  if (inFlight) return inFlight
  inFlight = (async () => {
    try {
      const data = await apiFn!<GatewayPayload>('/api/dashboard/gateway-status/')
      configured.value = data?.configured ?? false
      lines.value = data?.lines ?? []
      stale.value = !!data?.stale
      fetchedAt.value = data?.fetched_at ?? ''
    } catch {
      // 信息性接口 — 静默失败,保留上次数据
    } finally {
      loading.value = false
      inFlight = null
    }
  })()
  return inFlight
}

// 标签重新可见时立即刷新一次(不必等满 15s)
function onVisible() {
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
    fetchOnce()
  }
}

export function useGatewayStatus() {
  if (!apiFn) {
    const { api } = useApi()
    apiFn = api
  }
  if (!authUser) {
    const { user } = useAuth()
    authUser = user as unknown as Ref<{ id: string } | null>
  }

  onMounted(async () => {
    subscribers++
    if (subscribers === 1) {
      await fetchOnce()
      pollTimer = setInterval(fetchOnce, POLL_INTERVAL_MS)
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', onVisible)
      }
    }
  })

  onUnmounted(() => {
    subscribers = Math.max(0, subscribers - 1)
    if (subscribers === 0) {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisible)
      }
    }
  })

  return {
    lines: readonly(lines),
    configured: readonly(configured),
    stale: readonly(stale),
    fetchedAt: readonly(fetchedAt),
    loading: readonly(loading),
    refresh: fetchOnce,
  }
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: no new type errors referencing `useGatewayStatus.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/composables/useGatewayStatus.ts
git commit -m "feat(home): add useGatewayStatus 15s visibility-aware polling composable

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Frontend widget component

**Files:**
- Create: `frontend/app/components/dashboard/GatewayStatus.vue`

- [ ] **Step 1: Create the component**

Create `frontend/app/components/dashboard/GatewayStatus.vue`:

```vue
<template>
  <div class="section-card">
    <!-- 头部:标题 + 过期角标 + 更新时间 -->
    <div class="section-header">
      <h3 class="section-title">
        电话线路状态
        <span v-if="stale" class="gw-stale" title="上游暂时不可达,展示的是上次数据">⚠ 数据可能过期</span>
      </h3>
      <span v-if="updatedText" class="gw-updated">{{ updatedText }}</span>
    </div>

    <!-- 未配置 -->
    <p v-if="!configured" class="gw-muted">未配置网关状态接口</p>

    <!-- 首拉加载中 -->
    <p v-else-if="loading && !lines.length" class="gw-muted">加载中…</p>

    <!-- 拉不到任何线路 -->
    <p v-else-if="!lines.length" class="gw-muted">暂时无法获取线路状态</p>

    <template v-else>
      <!-- 汇总条 -->
      <div class="gw-summary">
        <span><b :class="summary.offline ? 'gw-warn' : 'gw-ok'">{{ summary.online }}</b>/{{ summary.total }} 在线</span>
        <span>平均延迟 {{ summary.avgLatency }}ms</span>
        <span>今日呼叫 {{ summary.todayCalls }}</span>
        <span>接通率 {{ summary.answerRate }}%</span>
        <span>并发 {{ summary.activeCalls }}</span>
      </div>

      <!-- 离线/异常:始终展开高亮 -->
      <div v-if="offlineLines.length" class="gw-block">
        <div class="gw-block-label gw-warn">⚠ 离线 ({{ offlineLines.length }})</div>
        <ul class="gw-list">
          <li v-for="l in offlineLines" :key="l.name" class="gw-row gw-row--down">
            <span class="gw-dot gw-dot--down" />
            <span class="gw-name">{{ l.name }}</span>
            <span class="gw-addr">{{ l.proxy_ip_list }}:{{ l.port }}</span>
            <span class="gw-err">{{ l.ping_error || '无响应' }}</span>
            <span class="gw-time">{{ timeAgo(l.last_ping_at) }}</span>
          </li>
        </ul>
      </div>

      <!-- 正常线路:默认折叠 -->
      <div v-if="onlineLines.length" class="gw-block">
        <button type="button" class="gw-toggle" @click="showOnline = !showOnline">
          <UIcon :name="showOnline ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'" class="w-4 h-4" />
          正常线路 ({{ onlineLines.length }})
        </button>
        <ul v-if="showOnline" class="gw-list">
          <li v-for="l in onlineLines" :key="l.name" class="gw-row">
            <span class="gw-dot gw-dot--up" />
            <span class="gw-name">{{ l.name }}</span>
            <span class="gw-lat">{{ l.ping_latency_ms }}ms</span>
            <span class="gw-calls">今日 {{ l.today_calls }} · 接通 {{ Math.round(l.today_answer_rate) }}%</span>
            <span v-if="l.active_calls > 0" class="gw-active">并发 {{ l.active_calls }}</span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { timeAgo } from '~/utils/timeAgo'

const { lines, configured, stale, fetchedAt, loading } = useGatewayStatus()
const showOnline = ref(false)

const updatedText = computed(() => {
  if (!fetchedAt.value) return ''
  const t = timeAgo(fetchedAt.value)
  return t ? `更新于 ${t}` : ''
})

// 离线置顶按名称排序;在线按今日呼叫量降序(忙线优先)
const offlineLines = computed(() =>
  lines.value.filter(l => !l.online).slice().sort((a, b) => a.name.localeCompare(b.name)),
)
const onlineLines = computed(() =>
  lines.value.filter(l => l.online).slice().sort((a, b) => b.today_calls - a.today_calls),
)

const summary = computed(() => {
  const all = lines.value
  const ups = onlineLines.value
  const total = all.length
  const online = ups.length
  const offline = offlineLines.value.length
  const avgLatency = ups.length
    ? Math.round(ups.reduce((s, l) => s + (l.ping_latency_ms || 0), 0) / ups.length)
    : 0
  const todayCalls = all.reduce((s, l) => s + (l.today_calls || 0), 0)
  const todayAnswered = all.reduce((s, l) => s + (l.today_answered || 0), 0)
  const activeCalls = all.reduce((s, l) => s + (l.active_calls || 0), 0)
  const answerRate = todayCalls ? Math.round((todayAnswered / todayCalls) * 100) : 0
  return { total, online, offline, avgLatency, todayCalls, answerRate, activeCalls }
})
</script>

<style scoped>
/* 卡片/标题样式与 ServerResource.vue 保持一致(scoped,故本组件内自带一份) */
.section-card {
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 1.25rem;
}
:root.dark .section-card { background-color: #1f2937; border-color: #374151; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
.section-title { font-size: 0.875rem; font-weight: 600; color: #111827; display: flex; align-items: center; gap: 0.5rem; }
:root.dark .section-title { color: #f3f4f6; }
.gw-stale { font-size: 0.6875rem; font-weight: 500; color: #b45309; background: #fffbeb; border: 1px solid #fde68a; border-radius: 0.375rem; padding: 0.0625rem 0.375rem; }
:root.dark .gw-stale { color: #fbbf24; background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3); }
.gw-updated { font-size: 0.75rem; color: #9ca3af; }
.gw-muted { font-size: 0.8125rem; color: #9ca3af; padding: 0.25rem 0; }

.gw-summary { display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; font-size: 0.8125rem; color: #4b5563; margin-bottom: 0.875rem; }
:root.dark .gw-summary { color: #d1d5db; }
.gw-ok { color: #059669; }
.gw-warn { color: #dc2626; }
:root.dark .gw-ok { color: #34d399; }
:root.dark .gw-warn { color: #f87171; }

.gw-block { margin-top: 0.75rem; }
.gw-block-label { font-size: 0.75rem; font-weight: 600; margin-bottom: 0.375rem; }
.gw-toggle { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.8125rem; font-weight: 500; color: #4b5563; background: transparent; border: 0; cursor: pointer; padding: 0.25rem 0; }
:root.dark .gw-toggle { color: #d1d5db; }
.gw-toggle:hover { color: #7c3aed; }
:root.dark .gw-toggle:hover { color: #c4b5fd; }

.gw-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.25rem; }
.gw-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8125rem; color: #374151; padding: 0.25rem 0.5rem; border-radius: 0.375rem; }
:root.dark .gw-row { color: #d1d5db; }
.gw-row--down { background: #fef2f2; }
:root.dark .gw-row--down { background: rgba(220, 38, 38, 0.1); }
.gw-dot { width: 0.5rem; height: 0.5rem; border-radius: 9999px; flex-shrink: 0; }
.gw-dot--up { background: #10b981; }
.gw-dot--down { background: #ef4444; }
.gw-name { font-weight: 500; }
.gw-addr, .gw-time { color: #9ca3af; font-size: 0.75rem; }
.gw-err { color: #dc2626; font-size: 0.75rem; }
:root.dark .gw-err { color: #f87171; }
.gw-lat, .gw-calls { color: #6b7280; font-size: 0.75rem; }
:root.dark .gw-lat, :root.dark .gw-calls { color: #9ca3af; }
.gw-active { color: #7c3aed; font-size: 0.75rem; font-weight: 500; margin-left: auto; }
:root.dark .gw-active { color: #c4b5fd; }
</style>
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: no new type errors referencing `GatewayStatus.vue`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/dashboard/GatewayStatus.vue
git commit -m "feat(home): add 电话线路状态 widget component

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Register the block on the home dashboard

**Files:**
- Modify: `frontend/app/utils/dashboardLayout.ts:15-23` (append registry entry)
- Modify: `frontend/app/pages/app/home.vue` (import + `blockComponents` + `availability`)

- [ ] **Step 1: Add to the block registry**

In `frontend/app/utils/dashboardLayout.ts`, add the `gateway` entry to `DASHBOARD_BLOCKS` (after the `server` entry so it lands at the end of the default order):

```ts
export const DASHBOARD_BLOCKS: readonly DashboardBlockMeta[] = Object.freeze([
  { id: 'stats', title: '数据概览', defaultVisible: true },
  { id: 'uptime', title: '生产环境监控', defaultVisible: true },
  { id: 'todos', title: '我的待办', defaultVisible: true },
  { id: 'mentions', title: '提及我的', defaultVisible: true },
  { id: 'tasks', title: '我的任务', defaultVisible: true },
  { id: 'activity', title: '最近动态', defaultVisible: true },
  { id: 'server', title: '服务器资源', defaultVisible: true },
  { id: 'gateway', title: '电话线路状态', defaultVisible: true },
])
```

- [ ] **Step 2: Wire it into home.vue**

In `frontend/app/pages/app/home.vue`:

1. Add the import alongside the other dashboard component imports (after the `DashboardServerResource` import, ~line 52):

```ts
import DashboardGatewayStatus from '~/components/dashboard/GatewayStatus.vue'
```

2. Add to the `availability` computed (after the `server:` line, ~line 87). The widget self-manages its loading/unconfigured/empty/stale states, so it is always "available":

```ts
  server: !!serverMonitorUrl.value,
  gateway: true,
```

3. Add to the `blockComponents` map (after the `server:` entry, ~line 98):

```ts
  server: DashboardServerResource,
  gateway: DashboardGatewayStatus,
```

(`propsFor` needs no change — `gateway` falls through to the `default: return {}` branch since the widget fetches its own data.)

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx nuxi typecheck`
Expected: no new type errors.

- [ ] **Step 4: Manual verification**

Run the stack (`cd backend && uv run python manage.py runserver` + `cd frontend && npm run dev`), set `GATEWAY_STATUS_URL` + `GATEWAY_STATUS_API_KEY` in `backend/.env` (real values from the task brief), log in, open `/app/home`. Confirm:
- 「电话线路状态」card renders with summary (在线 X/总 Y, 平均延迟, 今日呼叫, 接通率, 并发).
- Offline lines appear highlighted at top; 「正常线路 (N)」expands/collapses.
- Network tab shows `GET /api/dashboard/gateway-status/` ~every 15s; switch to another tab → polling stops; switch back → an immediate refresh fires.
- Edit-layout mode lets you reorder/hide the block.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/utils/dashboardLayout.ts frontend/app/pages/app/home.vue
git commit -m "feat(home): register 电话线路状态 block on dashboard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Document deploy config

**Files:**
- Modify: `backend/.env.example` (append the new vars)

- [ ] **Step 1: Add the vars to `.env.example`**

Append to `backend/.env.example`:

```bash
# 电话线路(SIP 网关)状态代理 — 首页"电话线路状态"区块经后端拉取。
# API_KEY 是密钥(不入库);后端主机需能出网访问该 URL。留空则区块显示"未配置"。
GATEWAY_STATUS_URL=http://121.31.38.35:9090/api/external/gateway-status
GATEWAY_STATUS_API_KEY=
# 可选:上游短缓存秒数,所有用户共享(默认 12)
# GATEWAY_STATUS_CACHE_TTL=12
```

- [ ] **Step 2: Commit**

```bash
git add backend/.env.example
git commit -m "docs(deploy): document GATEWAY_STATUS_* env vars

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Deploy checklist (post-merge, not part of code tasks)

- Set `GATEWAY_STATUS_URL` and `GATEWAY_STATUS_API_KEY` in the **test** and **prod** backend `.env` (key is a secret — never commit it). The Watchtower auto-pull deploy model means the new image picks these up on container restart.
- **Verify backend egress**: confirm the test/prod backend host can reach `121.31.38.35:9090` (prod egress may be firewalled). If not reachable, the widget will show「未配置」/「暂时无法获取」rather than data — coordinate a firewall rule.
- Do **not** push to `env/prod` without explicit user approval.

---

## Self-Review

**1. Spec coverage:**
- Backend proxy + 12s cache + last-good fallback → Task 1 ✓
- Settings env vars (URL/KEY/TTL) → Task 1 Step 1 + Task 5 ✓
- `IsAuthenticated`, `/api/dashboard/gateway-status/` → Task 1 Steps 4-5 ✓
- Normalized response shape (`configured/stale/fetched_at/lines`) → Task 1 view + tests ✓
- Failure matrix (last-good stale / no-cache error / unconfigured) → Task 1 tests ✓
- 15s visibility-aware singleton composable (+ immediate refresh on re-visible) → Task 2 ✓
- Widget: summary, offline-first, busiest-first online sort, collapse, all states → Task 3 ✓
- Registration (registry + home wiring, defaultVisible true, all users) → Task 4 ✓
- Tests (backend pytest cases; frontend typecheck + manual) → Tasks 1-4 ✓
- Deploy prerequisites (env + egress) → Task 5 + deploy checklist ✓

**2. Placeholder scan:** No TBD/TODO/"handle errors"/"similar to" — every code step has complete code. ✓

**3. Type consistency:** `GatewayLine` fields used in `GatewayStatus.vue` (`online`, `ping_latency_ms`, `today_calls`, `today_answer_rate`, `active_calls`, `ping_error`, `last_ping_at`, `proxy_ip_list`, `port`, `name`) all match the interface in Task 2. Cache key constant `_GW_CACHE_KEY` defined in Task 1 view and imported in Task 1 test ✓. Endpoint string `/api/dashboard/gateway-status/` identical across route, composable, and tests ✓. `useGatewayStatus()` return keys (`lines/configured/stale/fetchedAt/loading`) match the destructure in Task 3 ✓.
