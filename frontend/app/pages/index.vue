<template>
  <div class="page-container relative overflow-hidden min-h-screen">
    <div class="page-mesh" aria-hidden="true" />
    <div class="w-full max-w-5xl mx-auto px-6 relative z-10 self-start py-10 md:py-14 animate-fade-in-up">
      <!-- 01 — AI Spotlight: latest feature -->
    <AiSpotlight class="mb-16 md:mb-24" />

    <!-- 02 — Platform overview -->
    <section class="overview">
      <!-- Left: copy + features + CTAs -->
      <div class="copy">
        <div class="section-badge">
          <span class="num">02</span>
          <span class="sep">／</span>
          <span class="kicker">DEVTRAKR · 平台</span>
        </div>

        <div class="brand">
          <img src="~/assets/images/logo-icon.svg" alt="DevTrakr" class="brand-logo" />
          <span class="brand-name">DevTrakr</span>
        </div>

        <h1 class="display">
          <span class="line">团队项目管理，</span>
          <span class="line"><em>高效</em>&nbsp;协作。</span>
        </h1>

        <p class="lede">
          从 <b>问题追踪</b> 到 <b>团队交付</b>——<br />
          一站式管理你的开发流程。
        </p>

        <ol class="features">
          <li>
            <span class="f-num">01</span>
            <span class="f-rule" />
            <div class="f-text">
              <span class="f-title">Issue 追踪</span>
              <span class="f-desc">创建、分配、跟踪问题</span>
            </div>
          </li>
          <li>
            <span class="f-num">02</span>
            <span class="f-rule" />
            <div class="f-text">
              <span class="f-title">数据看板</span>
              <span class="f-desc">实时统计与分析</span>
            </div>
          </li>
          <li>
            <span class="f-num">03</span>
            <span class="f-rule" />
            <div class="f-text">
              <span class="f-title">团队协作</span>
              <span class="f-desc">权限与角色管理</span>
            </div>
          </li>
          <li>
            <span class="f-num">04</span>
            <span class="f-rule" />
            <div class="f-text">
              <span class="f-title">仓库集成</span>
              <span class="f-desc">Git 仓库关联</span>
            </div>
          </li>
        </ol>

        <div class="cta-row">
          <NuxtLink to="/login" class="cta-primary">
            <span>登录</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="cta-arrow"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
          </NuxtLink>
          <NuxtLink to="/register" class="cta-secondary">创建账号</NuxtLink>
        </div>
      </div>

      <!-- Right: app preview mockup -->
      <div class="preview">
        <div class="preview-card">
          <div class="preview-head">
            <div class="head-dots">
              <span /><span /><span />
            </div>
            <span class="head-label">DevTrakr · 项目 #001</span>
            <span class="head-spacer" />
            <span class="head-time">实时</span>
          </div>

          <div class="kanban">
            <div class="k-title">
              <span>Issue 看板</span>
              <span class="k-meta">7 进行中</span>
            </div>
            <div class="k-grid">
              <div class="col col-amber">
                <div class="col-h">
                  <span class="col-dot" />
                  <span>待分配</span>
                  <span class="col-c">2</span>
                </div>
                <div class="card"><span class="card-id">ISS-104</span>页面优化</div>
                <div class="card"><span class="card-id">ISS-108</span>权限修复</div>
              </div>
              <div class="col col-blue">
                <div class="col-h">
                  <span class="col-dot" />
                  <span>进行中</span>
                  <span class="col-c">3</span>
                </div>
                <div class="card"><span class="card-id">ISS-097</span>API 开发</div>
                <div class="card"><span class="card-id">ISS-099</span>数据迁移</div>
                <div class="card"><span class="card-id">ISS-101</span>单元测试</div>
              </div>
              <div class="col col-emerald">
                <div class="col-h">
                  <span class="col-dot" />
                  <span>已完成</span>
                  <span class="col-c">2</span>
                </div>
                <div class="card"><span class="card-id">ISS-088</span>用户认证</div>
                <div class="card"><span class="card-id">ISS-091</span>部署配置</div>
              </div>
            </div>
          </div>

          <div class="trend">
            <div class="t-head">
              <span class="t-title">本周趋势</span>
              <span class="t-delta">▲&nbsp;<em>+24%</em></span>
            </div>
            <div class="t-chart">
              <span class="t-bar" style="height:30%"><i /></span>
              <span class="t-bar" style="height:50%"><i /></span>
              <span class="t-bar" style="height:40%"><i /></span>
              <span class="t-bar" style="height:70%"><i /></span>
              <span class="t-bar" style="height:55%"><i /></span>
              <span class="t-bar" style="height:80%"><i /></span>
              <span class="t-bar" style="height:65%"><i /></span>
              <svg class="t-line" viewBox="0 0 140 56" preserveAspectRatio="none" aria-hidden="true">
                <path d="M0,40 L20,30 L40,34 L60,18 L80,26 L100,8 L120,16 L140,12" fill="none" stroke="#7c3aed" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" opacity="0.65"/>
                <circle cx="100" cy="8" r="2.4" fill="#7c3aed"/>
              </svg>
            </div>
            <div class="t-labels">
              <span>周一</span><span>周二</span><span>周三</span><span>周四</span><span>周五</span><span>周六</span><span>今天</span>
            </div>
          </div>
        </div>

        <!-- Floating accent -->
        <span class="ov-tag ov-tag-a"><em>shipping daily</em></span>
        <span class="ov-tag ov-tag-b">·&nbsp;7&nbsp;active&nbsp;·</span>
      </div>
    </section>

    <footer class="page-foot">
      <span class="foot-rule" />
      <span class="foot-text">&copy; 2026 DevTrakr&nbsp;<em>·</em>&nbsp;项目管理平台</span>
      <span class="foot-rule" />
    </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth' })

const { getToken } = useApi()

onMounted(() => {
  if (getToken()) {
    navigateTo('/app/home')
  }
})
</script>

<style scoped>
/* ────────── Custom Additions ────────── */
.page-mesh {
  position: absolute; inset: 0;
  background:
    radial-gradient(60% 50% at 90% 10%, rgba(236, 72, 153, 0.06), transparent 60%),
    radial-gradient(50% 50% at 10% 90%, rgba(124, 58, 237, 0.06), transparent 60%);
  pointer-events: none;
  z-index: 0;
  animation: page-mesh-drift 15s infinite alternate ease-in-out;
}
@keyframes page-mesh-drift {
  0% { transform: scale(1) translate(0,0); opacity: 0.8; }
  100% { transform: scale(1.1) translate(-2%, 2%); opacity: 1; }
}
@keyframes shine {
  100% { left: 200%; }
}
.animate-fade-in-up {
  animation: fadeInUp 0.8s ease-out forwards;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ────────── Layout ────────── */
.overview {
  display: grid;
  grid-template-columns: 1fr 1.05fr;
  gap: 64px;
  align-items: center;
}
@media (max-width: 880px) {
  .overview { grid-template-columns: 1fr; gap: 48px; }
}

/* ────────── Copy ────────── */
.section-badge {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.16em;
  color: #6d28d9;
  text-transform: uppercase;
  margin-bottom: 28px;
}
.section-badge .num {
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  font-size: 24px;
  letter-spacing: 0;
  color: #1a1530;
  line-height: 1;
}
.section-badge .sep { color: #c4b5fd; font-weight: 400; }

.brand {
  display: inline-flex; align-items: center; gap: 12px;
  margin-bottom: 22px;
}
.brand-logo { width: 40px; height: 40px; }
.brand-name {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #1a1530;
}

.display {
  font-size: clamp(34px, 4vw, 50px);
  line-height: 1.08;
  letter-spacing: -0.012em;
  font-weight: 700;
  color: #1a1530;
  margin: 0 0 18px;
}
.display .line { display: block; }
.display em {
  font-family: 'Instrument Serif', 'Songti SC', 'STSong', serif;
  font-style: italic;
  font-weight: 400;
  font-size: 1.22em;
  background: linear-gradient(135deg, #7c3aed 0%, #ec4899 60%, #f43f5e 100%);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.02em;
  padding: 0 4px;
}

.lede {
  font-size: 15.5px;
  line-height: 1.65;
  color: #5b5872;
  margin: 0 0 32px;
  max-width: 440px;
}
.lede b { color: #2e1065; font-weight: 600; }

.features {
  list-style: none;
  margin: 0 0 36px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.features li {
  display: grid;
  grid-template-columns: auto 28px 1fr;
  align-items: center;
  gap: 14px;
}
.f-num {
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  font-size: 20px;
  color: #8b5cf6;
  line-height: 1;
  letter-spacing: 0;
  font-weight: 400;
  min-width: 26px;
}
.f-rule {
  height: 1px;
  background: linear-gradient(90deg, #c4b5fd, transparent);
  width: 100%;
}
.f-text { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.f-title { font-size: 14.5px; font-weight: 600; color: #1a1530; }
.f-desc { font-size: 13px; color: #7a7691; }

.cta-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.cta-primary {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 12px 22px;
  font-size: 14.5px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #7c3aed 0%, #6366f1 100%);
  border-radius: 12px;
  text-decoration: none;
  position: relative;
  overflow: hidden;
  transition: transform 200ms ease, box-shadow 200ms ease;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.25) inset,
    0 8px 22px -8px rgba(76, 29, 149, 0.55),
    0 2px 0 rgba(76, 29, 149, 0.25);
}
.cta-primary::before {
  content: '';
  position: absolute; top: 0; left: -100%; width: 50%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
  transform: skewX(-20deg);
}
.cta-primary:hover {
  transform: translateY(-1px);
  box-shadow:
    0 1px 0 rgba(255,255,255,0.3) inset,
    0 12px 28px -8px rgba(76, 29, 149, 0.65),
    0 0 20px rgba(124, 58, 237, 0.35),
    0 2px 0 rgba(76, 29, 149, 0.3);
}
.cta-primary:hover::before {
  animation: shine 0.7s;
}
.cta-primary .cta-arrow {
  width: 15px; height: 15px;
  transition: transform 200ms ease;
}
.cta-primary:hover .cta-arrow { transform: translateX(2px); }
.cta-secondary {
  display: inline-flex; align-items: center;
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 600;
  color: #4c1d95;
  background: #fff;
  border: 1px solid rgba(124, 58, 237, 0.22);
  border-radius: 12px;
  text-decoration: none;
  transition: background 180ms ease, border-color 180ms ease, transform 180ms ease;
}
.cta-secondary:hover {
  background: #f7f3ff;
  border-color: rgba(124, 58, 237, 0.4);
  transform: translateY(-1px);
}

/* ────────── Preview card ────────── */
.preview { position: relative; }
.preview-card {
  position: relative;
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.9);
  padding: 0;
  overflow: hidden;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.9) inset,
    0 24px 48px -24px rgba(76, 29, 149, 0.25),
    0 6px 16px -10px rgba(76, 29, 149, 0.12);
}

/* macOS-style title bar */
.preview-head {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid #efeaf9;
  background: #fafaff;
}
.head-dots { display: inline-flex; gap: 6px; }
.head-dots span {
  width: 9px; height: 9px; border-radius: 999px;
  background: #e5e0f3;
}
.head-dots span:nth-child(1) { background: #fbbfb1; }
.head-dots span:nth-child(2) { background: #fde08c; }
.head-dots span:nth-child(3) { background: #b5e8b5; }
.head-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #4c1d95;
}
.head-spacer { flex: 1; }
.head-time {
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  font-size: 12px;
  color: #8b5cf6;
}
.head-time::before {
  content: '';
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 999px;
  background: #10b981;
  margin-right: 6px;
  vertical-align: 1px;
  box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5);
  animation: live-pulse 2s infinite;
}

/* Kanban */
.kanban {
  padding: 16px;
}
.k-title {
  display: flex; align-items: baseline; gap: 10px;
  font-size: 12px;
  font-weight: 700;
  color: #1a1530;
  letter-spacing: 0.02em;
  margin-bottom: 10px;
}
.k-meta {
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  font-size: 13px;
  color: #8b5cf6;
  font-weight: 400;
  letter-spacing: 0;
}
.k-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.col {
  border-radius: 10px;
  padding: 10px;
}
.col-amber   { background: linear-gradient(180deg, #fef3c7 0%, #fffaeb 100%); }
.col-blue    { background: linear-gradient(180deg, #dbeafe 0%, #eff6ff 100%); }
.col-emerald { background: linear-gradient(180deg, #d1fae5 0%, #ecfdf5 100%); }
.col-h {
  display: flex; align-items: center; gap: 6px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}
.col-amber .col-h   { color: #92400e; }
.col-blue .col-h    { color: #1e40af; }
.col-emerald .col-h { color: #047857; }
.col-dot { width: 6px; height: 6px; border-radius: 999px; background: currentColor; }
.col-c {
  margin-left: auto;
  font-size: 9.5px;
  background: rgba(255,255,255,0.7);
  padding: 1px 6px;
  border-radius: 999px;
  font-weight: 600;
}

.col .card {
  background: #fff;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 10.5px;
  color: #1f1b34;
  font-weight: 500;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 5px;
  box-shadow: 0 1px 0 rgba(0,0,0,0.04), 0 1px 3px -1px rgba(76, 29, 149, 0.08);
}
.col .card:last-child { margin-bottom: 0; }
.card-id {
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  font-size: 9.5px;
  color: #8b5cf6;
  letter-spacing: 0;
  line-height: 1;
}

/* Trend */
.trend {
  padding: 14px 16px 16px;
  border-top: 1px dashed #efeaf9;
  background: linear-gradient(180deg, #fafaff 0%, #fff 100%);
}
.t-head {
  display: flex; align-items: baseline; gap: 8px;
  margin-bottom: 8px;
}
.t-title {
  font-size: 12px;
  font-weight: 700;
  color: #1a1530;
  letter-spacing: 0.02em;
}
.t-delta {
  margin-left: auto;
  font-size: 11px;
  color: #047857;
  font-weight: 600;
  display: inline-flex; align-items: baseline; gap: 4px;
}
.t-delta em {
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  font-weight: 400;
  font-size: 13px;
}
.t-chart {
  position: relative;
  height: 56px;
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
  align-items: end;
  padding: 0 2px;
}
.t-bar {
  position: relative;
  display: block;
  border-radius: 4px 4px 0 0;
  background: linear-gradient(180deg, #c4b5fd 0%, #ede9fe 100%);
  width: 100%;
  overflow: hidden;
}
.t-bar i {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(124,58,237,0.7) 0%, rgba(196,181,253,0) 100%);
  transform: scaleY(0);
  transform-origin: bottom;
  animation: bar-rise 1.2s 200ms ease-out forwards;
}
.t-bar:nth-child(2) i { animation-delay: 280ms; }
.t-bar:nth-child(3) i { animation-delay: 360ms; }
.t-bar:nth-child(4) i { animation-delay: 440ms; }
.t-bar:nth-child(5) i { animation-delay: 520ms; }
.t-bar:nth-child(6) i { animation-delay: 600ms; }
.t-bar:nth-child(7) i { animation-delay: 680ms; }
.t-line {
  position: absolute;
  inset: 0;
  width: 100%; height: 100%;
  pointer-events: none;
}
.t-labels {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
  margin-top: 6px;
  font-size: 9.5px;
  color: #8a86a4;
  text-align: center;
  letter-spacing: 0.02em;
}
.t-labels span:last-child { color: #7c3aed; font-weight: 600; }

/* Floating accents around preview */
.ov-tag {
  position: absolute;
  font-size: 13px;
  color: #6d28d9;
  background: rgba(255, 255, 255, 0.85);
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(124, 58, 237, 0.18);
  box-shadow: 0 4px 10px -4px rgba(76, 29, 149, 0.12);
  backdrop-filter: blur(4px);
  animation: drift 6s ease-in-out infinite;
  pointer-events: none;
}
.ov-tag em {
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  font-weight: 400;
  font-size: 14px;
}
.ov-tag-a { top: -14px; right: 36px; }
.ov-tag-b { bottom: -14px; left: 32px; font-size: 12px; letter-spacing: 0.12em; animation-delay: 1.4s; }
@media (max-width: 880px) {
  .ov-tag { display: none; }
}

/* ────────── Footer ────────── */
.page-foot {
  margin-top: 56px;
  display: flex; align-items: center; gap: 16px;
}
.foot-rule {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(124, 58, 237, 0.18), transparent);
}
.foot-text {
  font-size: 11.5px;
  color: #8a86a4;
  letter-spacing: 0.06em;
}
.foot-text em {
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  color: #8b5cf6;
  margin: 0 2px;
}

/* ────────── Animations ────────── */
@keyframes drift {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-6px); }
}
@keyframes bar-rise {
  to { transform: scaleY(1); }
}
@keyframes live-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5); }
  60%  { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

/* ────────── Dark mode ────────── */
:root.dark .section-badge { color: #c4b5fd; }
:root.dark .section-badge .num { color: #f3f0ff; }
:root.dark .section-badge .sep { color: #6d28d9; }
:root.dark .brand-name { color: #f3f0ff; }
:root.dark .display { color: #f3f0ff; }
:root.dark .display em { color: #c4b5fd; }
:root.dark .lede { color: #b8b3d4; }
:root.dark .lede b { color: #ede9fe; }
:root.dark .f-title { color: #f3f0ff; }
:root.dark .f-desc { color: #9d99b7; }
:root.dark .cta-secondary { background: #1a1432; color: #ddd6fe; border-color: rgba(167, 139, 250, 0.25); }
:root.dark .cta-secondary:hover { background: #251c40; border-color: rgba(167, 139, 250, 0.45); }
:root.dark .preview-card { background: rgba(26, 20, 50, 0.55); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); border-color: rgba(167, 139, 250, 0.25); box-shadow: 0 1px 0 rgba(255,255,255,0.05) inset, 0 24px 48px -24px rgba(76, 29, 149, 0.4); }
:root.dark .preview-head { background: #15102b; border-bottom-color: #2a2148; }
:root.dark .head-label { color: #ddd6fe; }
:root.dark .k-title { color: #f3f0ff; }
:root.dark .col .card { background: #15102b; color: #ede9fe; }
:root.dark .col-amber   { background: linear-gradient(180deg, rgba(146, 64, 14, 0.35) 0%, rgba(146, 64, 14, 0.12) 100%); }
:root.dark .col-blue    { background: linear-gradient(180deg, rgba(30, 64, 175, 0.35) 0%, rgba(30, 64, 175, 0.12) 100%); }
:root.dark .col-emerald { background: linear-gradient(180deg, rgba(4, 120, 87, 0.35) 0%, rgba(4, 120, 87, 0.12) 100%); }
:root.dark .col-amber .col-h   { color: #fcd34d; }
:root.dark .col-blue .col-h    { color: #93c5fd; }
:root.dark .col-emerald .col-h { color: #6ee7b7; }
:root.dark .col-c { background: rgba(0,0,0,0.3); color: #ede9fe; }
:root.dark .trend { background: linear-gradient(180deg, #15102b 0%, #1a1432 100%); border-top-color: #2a2148; }
:root.dark .t-title { color: #f3f0ff; }
:root.dark .t-labels { color: #9d99b7; }
:root.dark .t-labels span:last-child { color: #c4b5fd; }
:root.dark .ov-tag { background: rgba(26, 20, 50, 0.85); color: #c4b5fd; border-color: rgba(167, 139, 250, 0.2); }
:root.dark .foot-text { color: #9d99b7; }

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .t-bar i { animation: none; transform: scaleY(1); }
  .ov-tag, .head-time::before { animation: none; }
}
</style>
