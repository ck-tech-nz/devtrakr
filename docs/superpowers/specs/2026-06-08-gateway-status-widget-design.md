# 电话线路状态 Widget — 设计文档

**日期**: 2026-06-08
**目标**: 在工作台首页(work home)新增一个仪表盘区块,展示电话线路(SIP 网关)的连通状态与今日话务,每 15 秒刷新一次(仅当页面/标签可见时)。

## 背景

上游接口返回所有线路的连通性与话务数据:

```
GET http://121.31.38.35:9090/api/external/gateway-status
Header: X-API-Key: <secret>

→ { "code": 0, "data": [ {
      "id": 3, "name": "ippbx", "proxy_ip_list": "111.59.23.221", "port": 5060,
      "transport": "udp", "status": 1, "concurrency_limit": 100,
      "active_calls": 0, "today_calls": 6, "today_answered": 1, "today_answer_rate": 16.66,
      "description": "", "online": true, "ping_latency_ms": 13,
      "last_ping_at": "2026-06-08T08:48:45Z", "ping_error": "..."  // 仅离线时出现
   }, ... ] }
```

核心连通信号为 `online` (bool) 与 `ping_latency_ms`;离线线路 `ping_latency_ms` 为超时值(如 3000)并带 `ping_error`。同时返回今日话务:`active_calls`(当前并发)、`today_calls`、`today_answered`、`today_answer_rate`。

## 关键架构决策

**前端不能直接调用上游**,原因有三:
1. `X-API-Key` 是密钥,直连会暴露在浏览器流量/打包代码中。
2. 混合内容 —— 上游是 `http://`,HTTPS 站点(如 prod `monitor.cktech.hk`)会阻止明文 HTTP 请求。
3. CORS —— 上游大概率不会放行本站来源。

**方案:后端代理 + 短 TTL 缓存(Approach B,已确认)。**
后端新增鉴权接口 `/api/dashboard/gateway-status/`,服务端持密钥拉取上游,结果缓存 ~12s。所有用户/轮询共享缓存值,无论多少人开着仪表盘,上游每 ~12s 最多被打一次,并把 UI 的 15s 刷新与可能很慢的上游(离线网关每条 ping 超时 3000ms,聚合响应可达数秒)解耦。

## 数据流

```
GatewayStatus.vue ──uses──> useGatewayStatus()  (模块级单例 composable)
      │ 15s 定时器 · 仅可见时拉 · in-flight 去重 · 多处挂载只跑一个定时器
      ▼
GET /api/dashboard/gateway-status/   (IsAuthenticated)
      ▼
后端代理视图 ──12s django cache──> 上游 (X-API-Key 来自后端 env, requests timeout 8s)
```

## 后端设计

### Settings (`backend/config/settings.py`)
新增三个环境变量(沿用现有 `os.environ.get` 风格):

```python
GATEWAY_STATUS_URL = os.environ.get("GATEWAY_STATUS_URL", "")
GATEWAY_STATUS_API_KEY = os.environ.get("GATEWAY_STATUS_API_KEY", "")
GATEWAY_STATUS_CACHE_TTL = int(os.environ.get("GATEWAY_STATUS_CACHE_TTL", "12"))
```

密钥是 secret,只写进 `.env`,**不入库、不进仓库**。

### 视图 (`backend/apps/issues/views.py`)
与现有仪表盘视图(`dashboard/stats`、`dashboard/recent-activity`)同处一文件,`permission_classes = [IsAuthenticated]`(与其他仪表盘聚合接口一致;本接口非 model-backed,故不用 `FullDjangoModelPermissions`)。

逻辑:
1. 若 `GATEWAY_STATUS_URL` 或 `GATEWAY_STATUS_API_KEY` 为空 → 返回 `{ "configured": false, "lines": [] }`(HTTP 200)。
2. 命中 12s 缓存 → 直接返回缓存(`stale: false`)。
3. 未命中 → `requests.get(url, headers={"X-API-Key": key}, timeout=8)`,校验 `body["code"] == 0`,取 `data`:
   - 成功 → 写 12s 短缓存 + 1h "last-good" 缓存,返回 `stale: false`。
   - 失败/超时/code≠0 → 回退到 "last-good":有则返回 `stale: true` + 旧数据;无则返回 `{ "configured": true, "stale": true, "lines": [], "error": "upstream_unavailable" }`(仍 HTTP 200)。

**始终返回 HTTP 200(已配置时)**,让前端只有一条代码路径,用 `stale`/`configured` 字段驱动展示。

### 响应结构(后端只做透传+元信息,汇总由前端算)
```json
{
  "configured": true,
  "stale": false,
  "fetched_at": "2026-06-08T08:48:45Z",
  "lines": [ { "name": "...", "online": true, "ping_latency_ms": 13,
               "active_calls": 0, "today_calls": 6, "today_answered": 1,
               "today_answer_rate": 16.66, "proxy_ip_list": "...", "port": 5060,
               "ping_error": "", "last_ping_at": "..." } ]
}
```

### 路由 (`backend/apps/issues/dashboard_urls.py`)
```python
path("gateway-status/", GatewayStatusView.as_view(), name="gateway-status"),
```
→ 实际暴露为 `/api/dashboard/gateway-status/`。

### 缓存说明
项目未显式配置 `CACHES`,Django 默认 LocMemCache(进程内)。多 gunicorn worker 时上游每 ~12s 最多被打 ~N 次(N=worker 数),仍有界、可接受。项目已有 redis(Celery broker),如需跨 worker 共享可后续把 Django `CACHES` 指向 redis —— **本设计不强制**,用 `from django.core.cache import cache` 默认缓存即可。

## 前端设计

### Composable (`frontend/app/composables/useGatewayStatus.ts`)
完全对标已验证的 `useUptimeMonitors.ts` 模式:

- 模块级单例状态:`lines`、`stale`、`configured`、`fetchedAt`、`loading`、`error`。
- 订阅者引用计数 → 全站只跑一个 15s 定时器;全部卸载后停。
- `POLL_INTERVAL_MS = 15_000`。
- in-flight 去重(`inFlight` promise)。
- 仅登录后轮询(懒捕获 `useApi` / `useAuth`)。
- **可见性感知**:`document.visibilityState !== 'visible'` 时跳过本次拉取;另加 `visibilitychange` 监听,标签重新可见时**立即**刷新一次(无需等满 15s)。
- 拉取 `api('/api/dashboard/gateway-status/')`,失败静默(信息性接口,不打扰用户),保留上一次数据。
- 导出 `{ lines, stale, configured, fetchedAt, loading, refresh }`(只读)。

### 组件 (`frontend/app/components/dashboard/GatewayStatus.vue`)
`section-card` 风格,适配深色模式(沿用现有 Tailwind 卡片类)。派生状态用 `computed`:

- `summary`:在线 X/总 Y、平均延迟(仅在线线路)、今日呼叫合计、整体接通率、当前并发合计。
- `sortedLines`:离线/异常置顶,在线线路按**今日呼叫量降序**(忙线优先,已确认)。
- 离线线路始终展开高亮(红);正常线路默认折叠在「正常线路 (N) ▸」内,点击展开。

每条线路展示:状态点(在线绿/离线红)、名称、`proxy_ip_list:port`(弱化副标题)、延迟 ms(离线显示「超时/错误原因」+ `last_ping_at` 相对时间)、今日呼叫·接通率、当前并发(>0 时高亮)。

**展示状态**:
- `loading`:骨架/「加载中」。
- `configured === false`:弱化提示「未配置网关状态接口」(不报错卡)。
- `stale === true`:标题旁「⚠ 数据可能过期」角标 + 仍展示上次数据。
- 空(`lines` 为空且非 loading):「暂时无法获取线路状态」。

### 布局示意
```
┌─ 电话线路状态 ────────────── 12秒前 · ⚠数据可能过期(stale时) ─┐
│  在线 17/22   平均延迟 28ms   今日呼叫 645   接通率 18%   并发 1 │
│                                                              │
│  ⚠ 离线 (5)                                                  │
│   ● yd_test_in        172.16.1.29:5060   超时·无响应  3分前   │
│   ● 信盛达            10.7.40.3:5063     超时   并发1 今日177  │
│   …                                                          │
│                                                              │
│  ▸ 正常线路 (17)                          ← 点击展开           │
│     (展开后) ● 深圳优诚  37ms  今日110·接通33%  并发0         │
└──────────────────────────────────────────────────────────┘
```

### 注册到首页
1. `frontend/app/utils/dashboardLayout.ts` 的 `DASHBOARD_BLOCKS` 追加:
   `{ id: 'gateway', title: '电话线路状态', defaultVisible: true }`
   (追加到末尾;`mergeLayout` 会把新块优雅补到现有用户布局尾部,用户可在编辑模式重排/隐藏。)
2. `frontend/app/pages/app/home.vue`:
   - `import DashboardGatewayStatus from '~/components/dashboard/GatewayStatus.vue'`
   - `blockComponents` 增 `gateway: DashboardGatewayStatus`
   - `availability` 增 `gateway: true`(**始终可用**;由组件自管 loading/未配置/空/过期状态。轮询生命周期因此与组件挂载绑定——块被用户隐藏即卸载停轮询,无浪费)
   - `propsFor`:走 `default` 分支 `return {}`(自取数据,无 props)

## 错误处理汇总

| 场景 | 后端 | 前端表现 |
|------|------|---------|
| 上游失败但有 last-good | 200 `stale:true` + 旧数据 | 展示数据 + 「数据可能过期」角标,继续轮询 |
| 上游失败且无 last-good | 200 `stale:true, lines:[]` | 空状态「暂时无法获取线路状态」 |
| 未配置 URL/KEY | 200 `configured:false` | 弱化「未配置」提示 |
| 401 | — | `useApi` 自动刷新 token |
| 后台标签 | — | 跳过轮询,重新可见时立即刷新 |

## 测试

- **后端 pytest**(`backend/tests/`,用现有 `auth_client`/`api_client` fixtures,mock `requests.get`):
  - 正常响应 → 规范化结构正确(`configured/stale/fetched_at/lines`)。
  - 第二次请求命中缓存,不再打上游(断言 `requests.get` 只调用一次)。
  - 上游异常 → 回退 last-good,`stale:true`。
  - 未配置 → `configured:false`。
  - 未鉴权 → 401。
- **前端**:`npx nuxi typecheck`;首页手动/QA 验证(数据展示、折叠展开、stale 角标、15s 刷新、切后台不刷)。

## 部署前置条件

1. 在 test/prod 后端 `.env` 设置 `GATEWAY_STATUS_URL`(= `http://121.31.38.35:9090/api/external/gateway-status`)与 `GATEWAY_STATUS_API_KEY`(secret,不入库)。
2. **后端主机需能出网访问 `121.31.38.35:9090`** —— prod 出网可能有防火墙,需提前确认连通性。

## 非目标 (YAGNI)

- 不做后台定时刷新任务(无需 Celery beat)。
- 不做线路详情页/历史趋势(本期只做首页区块的实时快照)。
- 不做按线路的告警/通知(仅展示)。
- 不引入 VueUse(项目未用,直接 `setInterval` + `visibilitychange`)。
