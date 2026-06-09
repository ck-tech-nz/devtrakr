<template>
  <div class="section-card gw">
    <!-- 头部:可点击折叠整卡;标题 + 过期角标 + 实时更新指示 -->
    <button
      type="button"
      class="gw-head gw-head--toggle"
      :class="{ 'gw-head--collapsed': !expanded }"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <h3 class="gw-title">
        <UIcon name="i-heroicons-signal" class="gw-title-icon" />
        电话线路状态
        <span v-if="stale" class="gw-stale" title="上游暂时不可达,展示的是上次数据">
          <UIcon name="i-heroicons-exclamation-triangle" class="w-3 h-3" /> 数据可能过期
        </span>
      </h3>
      <span class="gw-head-right">
        <span v-if="configured && lines.length" class="gw-live" :class="{ 'gw-live--stale': stale }">
          <span class="gw-live-dot" />
          {{ updatedText || '实时' }}
        </span>
        <UIcon :name="expanded ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="gw-head-chev" />
      </span>
    </button>

    <div v-show="expanded" class="gw-body">

    <!-- 未配置 -->
    <p v-if="!configured" class="gw-muted">
      <UIcon name="i-heroicons-signal-slash" class="w-4 h-4" /> 未配置网关状态接口
    </p>

    <!-- 首拉加载中 -->
    <p v-else-if="loading && !lines.length" class="gw-muted gw-muted--pulse">加载线路状态…</p>

    <!-- 拉不到任何线路 -->
    <p v-else-if="!lines.length" class="gw-muted">
      <UIcon name="i-heroicons-exclamation-circle" class="w-4 h-4" /> 暂时无法获取线路状态
    </p>

    <template v-else>
      <!-- 汇总条:数值/标签的统计单元 -->
      <div class="gw-summary">
        <div class="gw-stat gw-stat--lead">
          <div class="gw-stat-val">
            <span class="gw-ok">{{ summary.online }}</span><span class="gw-stat-sub">/ {{ summary.total }}</span>
          </div>
          <div class="gw-stat-label">在线</div>
        </div>
        <div class="gw-stat">
          <div class="gw-stat-val">{{ summary.avgLatency }}<span class="gw-unit">ms</span></div>
          <div class="gw-stat-label">平均延迟</div>
        </div>
        <div class="gw-stat">
          <div class="gw-stat-val">{{ summary.todayCalls }}</div>
          <div class="gw-stat-label">今日呼叫</div>
        </div>
        <div class="gw-stat">
          <div class="gw-stat-val">{{ summary.answerRate }}<span class="gw-unit">%</span></div>
          <div class="gw-stat-label">接通率</div>
        </div>
        <div class="gw-stat">
          <div class="gw-stat-val" :class="{ 'gw-accent': summary.activeCalls > 0 }">{{ summary.activeCalls }}</div>
          <div class="gw-stat-label">当前并发</div>
        </div>
      </div>

      <!-- 在线占比细条 -->
      <div class="gw-health" :class="{ 'gw-health--down': summary.offline }" :title="`在线 ${summary.online} / 共 ${summary.total}`">
        <div class="gw-health-fill" :style="{ width: healthPct + '%' }" />
      </div>

      <!-- 离线/异常:始终展开,告警条样式 -->
      <div v-if="offlineLines.length" class="gw-block gw-block--alert">
        <div class="gw-block-label gw-warn">
          <UIcon name="i-heroicons-exclamation-triangle" class="w-3.5 h-3.5" /> 离线 ({{ offlineLines.length }})
        </div>
        <ul class="gw-list gw-list--down">
          <li v-for="l in offlineLines" :key="l.id" class="gw-row gw-row--down">
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
        <button type="button" class="gw-toggle" :aria-expanded="showOnline" @click="showOnline = !showOnline">
          <UIcon :name="showOnline ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'" class="gw-toggle-chev" />
          正常线路 <span class="gw-count">{{ onlineLines.length }}</span>
        </button>
        <ul v-show="showOnline" class="gw-list gw-list--up">
          <li v-for="l in onlineLines" :key="l.id" class="gw-row">
            <span class="gw-dot gw-dot--up" />
            <span class="gw-name">{{ l.name }}</span>
            <span class="gw-lat" :class="latencyClass(l.ping_latency_ms)">{{ l.ping_latency_ms }}<span class="gw-unit">ms</span></span>
            <span class="gw-calls">今日 <b>{{ l.today_calls }}</b> · 接通 {{ Math.round(l.today_answer_rate) }}%</span>
            <span class="gw-active" :class="{ 'gw-active--on': l.active_calls > 0 }">
              <template v-if="l.active_calls > 0">并发 {{ l.active_calls }}</template>
            </span>
          </li>
        </ul>
      </div>
    </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { timeAgo } from '~/utils/timeAgo'

const { lines, configured, stale, fetchedAt, loading } = useGatewayStatus()
const expanded = ref(true)   // 整卡折叠,默认展开
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

// 在线占比(细条宽度)
const healthPct = computed(() => (summary.value.total ? Math.round((summary.value.online / summary.value.total) * 100) : 0))

// 延迟分级配色:≤60ms 优,≤150ms 良,其余偏高
function latencyClass(ms: number) {
  if (ms <= 60) return 'gw-lat--good'
  if (ms <= 150) return 'gw-lat--ok'
  return 'gw-lat--high'
}
</script>

<style scoped>
/* 卡片外壳与其他仪表盘区块保持一致(scoped,故本组件内自带一份) */
.section-card {
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 1.25rem;
}
:root.dark .section-card { background-color: #1f2937; border-color: #374151; }

/* ── 头部 ── */
.gw-head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: 1rem; }
/* 整卡折叠开关:整行可点 */
.gw-head--toggle { width: 100%; background: transparent; border: 0; cursor: pointer; padding: 0; font: inherit; color: inherit; text-align: left; }
.gw-head--collapsed { margin-bottom: 0; }
.gw-head--toggle:hover .gw-title,
.gw-head--toggle:hover .gw-head-chev { color: #7c3aed; }
:root.dark .gw-head--toggle:hover .gw-title,
:root.dark .gw-head--toggle:hover .gw-head-chev { color: #c4b5fd; }
.gw-head-right { display: inline-flex; align-items: center; gap: 0.625rem; flex-shrink: 0; }
.gw-head-chev { width: 1rem; height: 1rem; color: #9ca3af; transition: color 0.12s ease; }
.gw-title { font-size: 0.875rem; font-weight: 600; color: #111827; display: flex; align-items: center; gap: 0.5rem; }
:root.dark .gw-title { color: #f3f4f6; }
.gw-title-icon { width: 1rem; height: 1rem; color: #7c3aed; }
:root.dark .gw-title-icon { color: #a78bfa; }
.gw-stale {
  display: inline-flex; align-items: center; gap: 0.25rem;
  font-size: 0.6875rem; font-weight: 500; color: #b45309;
  background: #fffbeb; border: 1px solid #fde68a; border-radius: 0.375rem; padding: 0.0625rem 0.375rem;
}
:root.dark .gw-stale { color: #fbbf24; background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3); }

/* 实时指示:脉冲圆点 */
.gw-live { display: inline-flex; align-items: center; gap: 0.375rem; font-size: 0.75rem; color: #9ca3af; font-variant-numeric: tabular-nums; }
.gw-live-dot { width: 0.4375rem; height: 0.4375rem; border-radius: 9999px; background: #10b981; box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5); animation: gw-pulse 2s ease-out infinite; }
.gw-live--stale .gw-live-dot { background: #f59e0b; animation: none; box-shadow: none; }
@keyframes gw-pulse {
  0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.45); }
  70% { box-shadow: 0 0 0 0.375rem rgba(16, 185, 129, 0); }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}
@media (prefers-reduced-motion: reduce) { .gw-live-dot { animation: none; } }

/* ── 空/未配置状态 ── */
.gw-muted { display: flex; align-items: center; gap: 0.375rem; font-size: 0.8125rem; color: #9ca3af; padding: 0.5rem 0; }
.gw-muted--pulse { animation: gw-fade 1.4s ease-in-out infinite; }
@keyframes gw-fade { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }

/* ── 汇总条 ── */
.gw-summary { display: flex; flex-wrap: wrap; align-items: stretch; gap: 0.25rem 0; }
.gw-stat { display: flex; flex-direction: column; gap: 0.125rem; padding: 0 1.125rem; }
.gw-stat:first-child { padding-left: 0; }
.gw-stat + .gw-stat { border-left: 1px solid #f0f0f3; }
:root.dark .gw-stat + .gw-stat { border-left-color: #374151; }
.gw-stat-val { font-size: 1.0625rem; font-weight: 700; color: #111827; line-height: 1.1; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
:root.dark .gw-stat-val { color: #f3f4f6; }
.gw-stat-sub { font-size: 0.8125rem; font-weight: 500; color: #9ca3af; margin-left: 0.125rem; }
.gw-unit { font-size: 0.6875rem; font-weight: 600; color: #9ca3af; margin-left: 0.0625rem; }
.gw-stat-label { font-size: 0.6875rem; color: #9ca3af; letter-spacing: 0.02em; }
.gw-stat--lead .gw-stat-val { font-size: 1.25rem; }
.gw-accent { color: #7c3aed !important; }
:root.dark .gw-accent { color: #c4b5fd !important; }
.gw-ok { color: #059669; }
.gw-warn { color: #dc2626; }
:root.dark .gw-ok { color: #34d399; }
:root.dark .gw-warn { color: #f87171; }

/* 在线占比细条 */
.gw-health { position: relative; height: 0.25rem; margin-top: 0.875rem; border-radius: 9999px; background: #eef0f3; overflow: hidden; }
:root.dark .gw-health { background: #374151; }
.gw-health--down { background: rgba(220, 38, 38, 0.18); }
:root.dark .gw-health--down { background: rgba(248, 113, 113, 0.22); }
.gw-health-fill { height: 100%; border-radius: 9999px; background: #10b981; transition: width 0.5s cubic-bezier(0.22, 1, 0.36, 1); }

/* ── 线路分组 ── */
.gw-block { margin-top: 1rem; }
.gw-block--alert {
  border-left: 2px solid #ef4444; padding: 0.625rem 0 0.625rem 0.75rem; margin-left: -0.125rem;
  background: linear-gradient(to right, rgba(239, 68, 68, 0.05), transparent 60%);
  border-radius: 0 0.5rem 0.5rem 0;
}
:root.dark .gw-block--alert { background: linear-gradient(to right, rgba(248, 113, 113, 0.08), transparent 60%); }
.gw-block-label { display: inline-flex; align-items: center; gap: 0.3125rem; font-size: 0.75rem; font-weight: 600; margin-bottom: 0.5rem; }

/* 折叠按钮 */
.gw-toggle {
  display: inline-flex; align-items: center; gap: 0.375rem;
  font-size: 0.8125rem; font-weight: 500; color: #4b5563;
  background: transparent; border: 0; cursor: pointer; padding: 0.25rem 0;
}
:root.dark .gw-toggle { color: #d1d5db; }
.gw-toggle:hover { color: #7c3aed; }
:root.dark .gw-toggle:hover { color: #c4b5fd; }
.gw-toggle-chev { width: 0.875rem; height: 0.875rem; transition: transform 0.15s ease; }
.gw-count {
  font-size: 0.6875rem; font-weight: 600; color: #6b7280;
  background: #f3f4f6; border-radius: 9999px; padding: 0.0625rem 0.4375rem; font-variant-numeric: tabular-nums;
}
:root.dark .gw-count { color: #9ca3af; background: #374151; }

/* ── 列表行(网格对齐,便于纵向扫读) ── */
.gw-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.125rem; }
.gw-list--up { margin-top: 0.375rem; }
.gw-row {
  display: grid; align-items: center; column-gap: 0.75rem;
  font-size: 0.8125rem; color: #374151;
  padding: 0.3125rem 0.5rem; border-radius: 0.4375rem;
  transition: background-color 0.12s ease;
}
:root.dark .gw-row { color: #d1d5db; }
.gw-list--up .gw-row { grid-template-columns: 0.5rem minmax(4rem, 1fr) 4.75rem minmax(8rem, auto) 4.5rem; }
.gw-list--down .gw-row { grid-template-columns: 0.5rem minmax(4rem, auto) auto 1fr auto; }
.gw-list--up .gw-row:hover { background: #f9fafb; }
:root.dark .gw-list--up .gw-row:hover { background: rgba(255, 255, 255, 0.03); }
.gw-row--down { background: rgba(239, 68, 68, 0.04); }
:root.dark .gw-row--down { background: rgba(248, 113, 113, 0.06); }

.gw-dot { width: 0.5rem; height: 0.5rem; border-radius: 9999px; flex-shrink: 0; }
.gw-dot--up { background: #10b981; box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.15); }
.gw-dot--down { background: #ef4444; box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2); }
.gw-name { font-weight: 500; color: #1f2937; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .gw-name { color: #e5e7eb; }

/* 技术字段用等宽 + 表格数字,刷新时不抖动 */
.gw-addr {
  font-family: ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: 0.75rem; color: #9ca3af; font-variant-numeric: tabular-nums; white-space: nowrap;
}
.gw-time { color: #9ca3af; font-size: 0.75rem; text-align: right; white-space: nowrap; }
.gw-err { color: #dc2626; font-size: 0.75rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:root.dark .gw-err { color: #f87171; }

.gw-lat {
  font-family: ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: 0.75rem; font-weight: 600; font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap;
}
.gw-lat--good { color: #059669; }
.gw-lat--ok { color: #6b7280; }
.gw-lat--high { color: #d97706; }
:root.dark .gw-lat--good { color: #34d399; }
:root.dark .gw-lat--ok { color: #9ca3af; }
:root.dark .gw-lat--high { color: #fbbf24; }
.gw-lat .gw-unit { font-weight: 500; }

.gw-calls { color: #6b7280; font-size: 0.75rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
.gw-calls b { font-weight: 600; color: #4b5563; }
:root.dark .gw-calls { color: #9ca3af; }
:root.dark .gw-calls b { color: #d1d5db; }

.gw-active { font-size: 0.6875rem; text-align: right; white-space: nowrap; }
.gw-active--on {
  color: #7c3aed; font-weight: 600;
  background: #f5f3ff; border-radius: 9999px; padding: 0.0625rem 0.4375rem; justify-self: end;
}
:root.dark .gw-active--on { color: #c4b5fd; background: rgba(124, 58, 237, 0.18); }

/* 窄屏:让今日/并发列自然回收,避免溢出 */
@media (max-width: 640px) {
  .gw-list--up .gw-row { grid-template-columns: 0.5rem 1fr 4.5rem; }
  .gw-list--up .gw-calls, .gw-list--up .gw-active { display: none; }
  .gw-list--down .gw-row { grid-template-columns: 0.5rem 1fr auto; }
  .gw-list--down .gw-addr { display: none; }
}
</style>
