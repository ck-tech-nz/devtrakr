<template>
  <section class="spotlight">
    <div class="bg-mesh" aria-hidden="true" />
    <div class="bg-grain" aria-hidden="true" />
    <img class="bg-mark" src="~/assets/images/matrix-ai-mark.svg" aria-hidden="true" />

    <div class="grid-wrap">
      <!-- LEFT — copy -->
      <div class="copy reveal" style="--d:0ms">
        <div class="badge">
          <span class="badge-pulse" />
          <span class="badge-brand">MATRIX&nbsp;AI</span>
          <span class="badge-sep">／</span>
          <span class="badge-new">NEW</span>
        </div>

        <h2 class="headline">
          <span class="line">描述一下问题，</span>
          <span class="line">AI&nbsp;<em>替你写完</em></span>
          <span class="line">整张工单。</span>
        </h2>

        <p class="lede">
          一句话、一段日志、几张截图——<br />
          自动生成<b>标题 · 模块 · 优先级 · 标签 · 指派</b>，并检测重复工单。
        </p>

        <ul class="caps">
          <li><span class="tick" /><span>自然语言理解</span></li>
          <li><span class="tick" /><span>粘贴截图识别</span></li>
          <li><span class="tick" /><span>智能分类指派</span></li>
          <li><span class="tick" /><span>重复工单检测</span></li>
        </ul>

        <div class="cta-row">
          <NuxtLink to="/login" class="cta-primary">
            <span>试用&nbsp;AI&nbsp;助手</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="cta-icon">
              <path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3z" />
            </svg>
          </NuxtLink>
          <a href="#how" class="cta-ghost">了解工作原理 →</a>
        </div>
      </div>

      <!-- RIGHT — live demo -->
      <div class="demo reveal" style="--d:120ms">
        <div class="demo-card">
          <!-- Step 1: input -->
          <div class="card-stage" :class="{ 'is-active': stage === 'typing' || stage === 'send' }">
            <div class="stage-tag">1 · 描述</div>
            <div class="input-box" :class="{ 'is-pressing': stage === 'send' }">
              <div class="input-text">
                <span class="typed">{{ typedText }}</span><span class="caret" :class="{ blink: stage === 'typing' || stage === 'idle' }" />
              </div>
              <div class="input-toolbar">
                <span class="tool"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg></span>
                <span class="tool"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/></svg></span>
                <span class="tool tool-project">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/></svg>
                  DevTrack
                </span>
                <span class="tool-spacer" />
                <span class="send" :class="{ fire: stage === 'send' || stage === 'analyzing' }">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
                </span>
              </div>
            </div>
          </div>

          <!-- Connector -->
          <div class="connector">
            <span class="conn-line" />
            <span class="conn-pill" :class="connPillClass">
              <template v-if="stage === 'analyzing'">
                <span class="dots"><i /><i /><i /></span>
                <span>AI&nbsp;分析中</span>
              </template>
              <template v-else-if="stage === 'draft' || stage === 'done'">
                <svg viewBox="0 0 24 24" class="spark" fill="currentColor"><path d="M12 2l1.6 4.4L18 8l-4.4 1.6L12 14l-1.6-4.4L6 8l4.4-1.6L12 2z"/></svg>
                <span>已生成草稿</span>
              </template>
              <template v-else>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12l7 7 7-7"/></svg>
              </template>
            </span>
          </div>

          <!-- Step 2: draft -->
          <div class="card-stage stage-draft" :class="{ 'is-active': stage === 'draft' || stage === 'done' }">
            <div class="stage-tag">2 · AI 草稿</div>
            <div class="draft">
              <div v-for="(row, i) in draftRows" :key="row.k" class="row" :class="{ inview: shownFields > i }" :style="`--i:${i}`">
                <span class="row-k">{{ row.k }}</span>
                <span class="row-v">
                  <template v-if="row.k === '标题'">{{ row.v }}</template>
                  <template v-else-if="row.k === '项目'">
                    <span class="pill pill-violet">{{ row.v }}</span>
                  </template>
                  <template v-else-if="row.k === '模块'">
                    <span class="pill">{{ row.v }}</span>
                  </template>
                  <template v-else-if="row.k === '优先级'">
                    <span class="pill pill-amber">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M17 7H9M17 7v8"/></svg>
                      {{ row.v }}
                    </span>
                  </template>
                  <template v-else-if="row.k === '标签'">
                    <span class="pill pill-rose">bug</span>
                    <span class="pill pill-blue">auth</span>
                    <span class="pill pill-emerald">frontend</span>
                  </template>
                  <template v-else-if="row.k === '指派'">
                    <span class="avatar">CK</span>
                    <span class="assignee">陈昆</span>
                  </template>
                </span>
              </div>
            </div>
            <div class="duplicate-note" :class="{ inview: stage === 'done' }">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="dup-icon"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
              <span>未发现重复工单</span>
            </div>
          </div>
        </div>

        <!-- Floating tag chips around the card -->
        <span class="float-tag float-tag-a">priority: high</span>
        <span class="float-tag float-tag-b">duplicate? ×0</span>
        <span class="float-tag float-tag-c">vision&nbsp;✓</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
useHead({
  link: [
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
    { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap' },
  ],
})

type Stage = 'idle' | 'typing' | 'send' | 'analyzing' | 'draft' | 'done'

const sample = '登录页提交后偶发返回 404，新注册用户受影响'
const typedText = ref('')
const stage = ref<Stage>('idle')
const shownFields = ref(0)

const draftRows = [
  { k: '标题', v: '登录页提交后偶发 404，影响新注册用户' },
  { k: '项目', v: 'DevTrack' },
  { k: '模块', v: '认证 / Auth' },
  { k: '优先级', v: '高' },
  { k: '标签', v: '' },
  { k: '指派', v: '' },
]

const connPillClass = computed(() => ({
  'pill-pulse': stage.value === 'analyzing',
  'pill-done': stage.value === 'draft' || stage.value === 'done',
}))

let timers: number[] = []
function clear() {
  timers.forEach(clearTimeout)
  timers = []
}
function schedule(fn: () => void, ms: number) {
  timers.push(window.setTimeout(fn, ms))
}

async function runCycle() {
  // reset
  typedText.value = ''
  shownFields.value = 0
  stage.value = 'idle'

  // Phase 1 — typing
  schedule(() => { stage.value = 'typing' }, 600)
  for (let i = 0; i < sample.length; i++) {
    schedule(() => { typedText.value = sample.slice(0, i + 1) }, 600 + i * 65)
  }
  const typedEnd = 600 + sample.length * 65

  // Phase 2 — send button press
  schedule(() => { stage.value = 'send' }, typedEnd + 350)
  // Phase 3 — analyzing
  schedule(() => { stage.value = 'analyzing' }, typedEnd + 750)

  // Phase 4 — draft
  schedule(() => { stage.value = 'draft' }, typedEnd + 2200)
  for (let i = 0; i < draftRows.length; i++) {
    schedule(() => { shownFields.value = i + 1 }, typedEnd + 2200 + 220 + i * 320)
  }
  // duplicate check
  schedule(() => { stage.value = 'done' }, typedEnd + 2200 + 220 + draftRows.length * 320 + 200)

  // Hold then loop
  const cycleEnd = typedEnd + 2200 + 220 + draftRows.length * 320 + 200 + 3200
  schedule(() => { runCycle() }, cycleEnd)
}

onMounted(() => { runCycle() })
onBeforeUnmount(() => { clear() })
</script>

<style scoped>
/* ────────── Section frame ────────── */
.spotlight {
  position: relative;
  isolation: isolate;
  width: 100%;
  border-radius: 28px;
  padding: 56px 44px 52px;
  overflow: hidden;
  background:
    radial-gradient(120% 80% at 0% 0%, #f0ebff 0%, transparent 55%),
    radial-gradient(90% 60% at 100% 100%, #fff1e8 0%, transparent 55%),
    linear-gradient(180deg, #fafaff 0%, #f6f3ff 100%);
  border: 1px solid rgba(124, 58, 237, 0.10);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.9) inset,
    0 30px 60px -30px rgba(76, 29, 149, 0.18),
    0 8px 24px -12px rgba(76, 29, 149, 0.10);
}

/* aurora blobs */
.bg-mesh {
  position: absolute; inset: -10%;
  background:
    radial-gradient(40% 35% at 18% 22%, rgba(167, 139, 250, 0.35), transparent 70%),
    radial-gradient(28% 24% at 88% 18%, rgba(255, 182, 193, 0.28), transparent 70%),
    radial-gradient(36% 30% at 78% 92%, rgba(196, 181, 253, 0.40), transparent 70%),
    radial-gradient(22% 22% at 10% 90%, rgba(253, 230, 138, 0.25), transparent 70%);
  filter: blur(20px) saturate(115%);
  z-index: -2;
  pointer-events: none;
  animation: bg-mesh-swell 12s ease-in-out infinite alternate;
}
@keyframes bg-mesh-swell {
  0% { transform: scale(1) rotate(0deg); opacity: 0.8; }
  100% { transform: scale(1.1) rotate(3deg); opacity: 1; }
}

/* SVG noise grain */
.bg-grain {
  position: absolute; inset: 0;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.30 0 0 0 0 0.16 0 0 0 0 0.55 0 0 0 0.22 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
  opacity: 0.32;
  mix-blend-mode: overlay;
  z-index: -1;
  pointer-events: none;
}

/* MATRIX AI mark watermark */
.bg-mark {
  position: absolute;
  right: -60px; top: -50px;
  width: 320px; height: 320px;
  opacity: 0.045;
  transform: rotate(8deg);
  z-index: -1;
  pointer-events: none;
}

/* ────────── Grid ────────── */
.grid-wrap {
  position: relative;
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  gap: 56px;
  align-items: center;
}
@media (max-width: 880px) {
  .grid-wrap { grid-template-columns: 1fr; gap: 40px; }
  .spotlight { padding: 40px 28px; border-radius: 22px; }
  .bg-mark { width: 220px; height: 220px; right: -40px; top: -30px; }
}

/* ────────── Copy column ────────── */
.badge {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 12px 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(124, 58, 237, 0.18);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: #4c1d95;
  backdrop-filter: blur(6px);
  box-shadow: 0 1px 2px rgba(76, 29, 149, 0.05);
}
.badge-pulse {
  width: 6px; height: 6px; border-radius: 999px;
  background: #8b5cf6;
  box-shadow: 0 0 0 0 rgba(139, 92, 246, 0.55);
  animation: pulse 2.4s infinite;
}
.badge-brand { letter-spacing: 0.12em; }
.badge-sep { color: #c4b5fd; }
.badge-new {
  background: linear-gradient(135deg, #8b5cf6, #6366f1);
  color: #fff;
  padding: 2px 7px;
  border-radius: 6px;
  letter-spacing: 0.14em;
  font-size: 10px;
  box-shadow: 0 1px 2px rgba(99, 102, 241, 0.4);
}

.headline {
  margin: 18px 0 14px;
  font-size: clamp(34px, 4.2vw, 52px);
  line-height: 1.06;
  letter-spacing: -0.012em;
  color: #1a1530;
  font-weight: 700;
}
.headline .line { display: block; }
.headline em {
  font-family: 'Instrument Serif', 'Songti SC', 'STSong', serif;
  font-style: italic;
  font-weight: 400;
  font-size: 1.18em;
  color: #6d28d9;
  letter-spacing: -0.02em;
  padding: 0 2px;
}

.lede {
  font-size: 15.5px;
  line-height: 1.65;
  color: #5b5872;
  max-width: 460px;
  margin: 0 0 22px;
}
.lede b { color: #2e1065; font-weight: 600; }

.caps {
  list-style: none;
  margin: 0 0 28px;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 18px;
  font-size: 13.5px;
  color: #3f3a5b;
}
.caps li { display: flex; align-items: center; gap: 8px; }
.tick {
  width: 14px; height: 14px;
  border-radius: 4px;
  background: linear-gradient(135deg, #ede9fe, #ddd6fe);
  border: 1px solid rgba(124, 58, 237, 0.25);
  position: relative;
}
.tick::after {
  content: '';
  position: absolute;
  inset: 0;
  background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path d='M3.5 8.5l3 3 6-7' stroke='%237c3aed' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' fill='none'/></svg>") no-repeat center / 11px;
}

.cta-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
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
  transition: transform 200ms ease, box-shadow 200ms ease;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.25) inset,
    0 8px 22px -8px rgba(76, 29, 149, 0.55),
    0 2px 0 rgba(76, 29, 149, 0.25);
}
.cta-primary:hover {
  transform: translateY(-1px);
  box-shadow:
    0 1px 0 rgba(255,255,255,0.3) inset,
    0 12px 28px -8px rgba(76, 29, 149, 0.65),
    0 2px 0 rgba(76, 29, 149, 0.3);
}
.cta-icon {
  width: 16px; height: 16px;
  animation: twinkle 3.2s ease-in-out infinite;
}
.cta-ghost {
  font-size: 13.5px;
  font-weight: 500;
  color: #6d28d9;
  text-decoration: none;
  position: relative;
}
.cta-ghost::after {
  content: '';
  position: absolute; left: 0; right: 0; bottom: -2px;
  height: 1px;
  background: currentColor;
  opacity: 0.3;
  transition: opacity 180ms ease;
}
.cta-ghost:hover::after { opacity: 0.7; }

/* ────────── Demo column ────────── */
.demo {
  position: relative;
}
.demo-card {
  position: relative;
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.9);
  padding: 18px 18px 20px;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.9) inset,
    0 24px 48px -24px rgba(76, 29, 149, 0.25),
    0 6px 16px -10px rgba(76, 29, 149, 0.12);
}

.card-stage {
  position: relative;
  border-radius: 14px;
  padding: 12px 12px 12px;
  background: #fafaff;
  border: 1px solid #efeaf9;
  transition: border-color 300ms ease, background 300ms ease;
}
.card-stage.is-active {
  background: #f7f3ff;
  border-color: #d8c9ff;
}
.stage-tag {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: #7c3aed;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.input-box {
  background: #fff;
  border: 1px solid #eee9f8;
  border-radius: 10px;
  padding: 10px 12px 8px;
  transition: transform 160ms ease, box-shadow 160ms ease;
}
.input-box.is-pressing { transform: scale(0.985); box-shadow: 0 4px 14px -8px rgba(124,58,237,0.4); }
.input-text {
  font-size: 13.5px;
  line-height: 1.55;
  color: #1f1b34;
  min-height: 38px;
}
.typed { white-space: pre-wrap; }
.caret {
  display: inline-block;
  width: 2px; height: 14px;
  background: #7c3aed;
  vertical-align: text-bottom;
  margin-left: 1px;
  opacity: 0;
}
.caret.blink { opacity: 1; animation: blink 0.9s steps(2, end) infinite; }

.input-toolbar {
  display: flex; align-items: center; gap: 6px;
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px dashed #eee9f8;
}
.tool {
  width: 24px; height: 24px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 7px;
  background: #f6f3ff;
  color: #7c3aed;
}
.tool svg { width: 13px; height: 13px; }
.tool-project {
  width: auto;
  padding: 0 8px;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 500;
  color: #4c1d95;
  background: #ede9fe;
}
.tool-spacer { flex: 1; }
.send {
  width: 26px; height: 26px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 999px;
  background: linear-gradient(135deg, #8b5cf6, #6366f1);
  color: #fff;
  box-shadow: 0 2px 8px -2px rgba(124,58,237,0.5);
  transition: transform 160ms ease, box-shadow 160ms ease;
}
.send svg { width: 13px; height: 13px; }
.send.fire { animation: fire 600ms cubic-bezier(.34,1.56,.64,1); }

/* connector */
.connector {
  position: relative;
  display: flex; justify-content: center;
  padding: 14px 0 12px;
}
.conn-line {
  position: absolute;
  top: 0; bottom: 0;
  left: 50%;
  width: 1px;
  background: linear-gradient(180deg, transparent 0%, #d8c9ff 30%, #d8c9ff 70%, transparent 100%);
  transform: translateX(-0.5px);
}
.conn-pill {
  position: relative;
  z-index: 1;
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid #e9e2fa;
  color: #4c1d95;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  box-shadow: 0 4px 10px -4px rgba(76,29,149,0.18);
  transition: all 280ms ease;
}
.conn-pill svg { width: 13px; height: 13px; }
.conn-pill.pill-pulse {
  background: #f3eeff;
  border-color: #c4b5fd;
}
.conn-pill.pill-done {
  background: linear-gradient(135deg, #ede9fe, #e0e7ff);
  border-color: #c4b5fd;
  color: #4c1d95;
}
.conn-pill .spark { color: #7c3aed; animation: twinkle 1.4s infinite; }
.dots { display: inline-flex; gap: 3px; }
.dots i {
  width: 4px; height: 4px;
  background: #7c3aed;
  border-radius: 999px;
  animation: dot 1.2s infinite ease-in-out;
}
.dots i:nth-child(2) { animation-delay: 150ms; }
.dots i:nth-child(3) { animation-delay: 300ms; }

/* draft */
.stage-draft .draft {
  display: grid;
  gap: 8px;
  padding: 4px 2px 2px;
}
.row {
  display: grid;
  grid-template-columns: 56px 1fr;
  align-items: center;
  gap: 14px;
  padding: 6px 8px;
  font-size: 13px;
  border-radius: 8px;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 380ms ease, transform 380ms ease, background 280ms ease;
}
.row.inview {
  opacity: 1;
  transform: translateY(0);
  background: linear-gradient(90deg, rgba(237, 233, 254, 0.6), transparent 90%);
}
.row-k {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: #8b5cf6;
  text-transform: uppercase;
}
.row-v {
  display: inline-flex; align-items: center; gap: 6px;
  color: #1f1b34;
  font-weight: 500;
}

.pill {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 600;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #e5e7eb;
}
.pill svg { width: 11px; height: 11px; }
.pill-violet { background: #ede9fe; color: #5b21b6; border-color: #d8c9ff; }
.pill-amber  { background: #fef3c7; color: #92400e; border-color: #fde68a; }
.pill-rose   { background: #ffe4e6; color: #9f1239; border-color: #fecdd3; }
.pill-blue   { background: #dbeafe; color: #1e40af; border-color: #bfdbfe; }
.pill-emerald{ background: #d1fae5; color: #065f46; border-color: #a7f3d0; }

.avatar {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px;
  border-radius: 999px;
  background: linear-gradient(135deg, #8b5cf6, #6366f1);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.assignee { font-size: 12.5px; color: #1f1b34; }

.duplicate-note {
  margin-top: 8px;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(209, 250, 229, 0.5);
  border: 1px dashed #6ee7b7;
  font-size: 11.5px;
  font-weight: 500;
  color: #047857;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 320ms ease, transform 320ms ease;
}
.duplicate-note.inview { opacity: 1; transform: translateY(0); }
.dup-icon { width: 12px; height: 12px; }

/* floating tag chips */
.float-tag {
  position: absolute;
  font-family: 'Instrument Serif', serif;
  font-style: italic;
  font-size: 13px;
  color: #6d28d9;
  background: rgba(255, 255, 255, 0.65);
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 8px 24px -6px rgba(76, 29, 149, 0.2);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  animation: drift 6s ease-in-out infinite;
  pointer-events: none;
}
.float-tag-a { top: -14px; right: 24px; animation-delay: 0s; }
.float-tag-b { bottom: 60px; left: -28px; animation-delay: 1.2s; }
.float-tag-c { bottom: -14px; right: 80px; animation-delay: 2.4s; }
@media (max-width: 880px) {
  .float-tag { display: none; }
}

/* ────────── Animations ────────── */
.reveal {
  opacity: 0;
  transform: translateY(12px);
  animation: rise 700ms cubic-bezier(.2,.7,.2,1) forwards;
  animation-delay: var(--d, 0ms);
}
@keyframes rise {
  to { opacity: 1; transform: translateY(0); }
}
@keyframes pulse {
  0%   { box-shadow: 0 0 0 0 rgba(139, 92, 246, 0.6); }
  60%  { box-shadow: 0 0 0 6px rgba(139, 92, 246, 0); }
  100% { box-shadow: 0 0 0 0 rgba(139, 92, 246, 0); }
}
@keyframes blink {
  0%, 50%   { opacity: 1; }
  50.1%, 100% { opacity: 0; }
}
@keyframes dot {
  0%, 80%, 100% { transform: scale(0.5); opacity: 0.4; }
  40%           { transform: scale(1);   opacity: 1; }
}
@keyframes fire {
  0%   { transform: scale(1); }
  40%  { transform: scale(1.18); box-shadow: 0 0 0 8px rgba(139,92,246,0.18); }
  100% { transform: scale(1); }
}
@keyframes twinkle {
  0%, 100% { transform: scale(1) rotate(0deg); opacity: 1; }
  50%      { transform: scale(1.18) rotate(8deg); opacity: 0.85; }
}
@keyframes drift {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-6px); }
}

/* ────────── Dark mode ────────── */
:root.dark .spotlight {
  background:
    radial-gradient(120% 80% at 0% 0%, rgba(124, 58, 237, 0.18) 0%, transparent 55%),
    radial-gradient(90% 60% at 100% 100%, rgba(255, 145, 100, 0.10) 0%, transparent 55%),
    linear-gradient(180deg, #0f0a1f 0%, #15102b 100%);
  border-color: rgba(167, 139, 250, 0.15);
}
:root.dark .headline { color: #f3f0ff; }
:root.dark .headline em { color: #c4b5fd; }
:root.dark .lede { color: #b8b3d4; }
:root.dark .lede b { color: #ede9fe; }
:root.dark .caps { color: #c8c3e0; }
:root.dark .badge { background: rgba(76, 29, 149, 0.25); color: #ddd6fe; border-color: rgba(196, 181, 253, 0.25); }
:root.dark .badge-sep { color: #7c3aed; }
:root.dark .demo-card { background: rgba(26, 20, 50, 0.65); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); border-color: rgba(167, 139, 250, 0.25); box-shadow: 0 1px 0 rgba(255,255,255,0.05) inset, 0 24px 48px -24px rgba(76, 29, 149, 0.4); }
:root.dark .card-stage { background: #15102b; border-color: #2a2148; }
:root.dark .card-stage.is-active { background: #1c1638; border-color: #4c1d95; }
:root.dark .input-box { background: #0f0a1f; border-color: #2a2148; }
:root.dark .input-text { color: #ede9fe; }
:root.dark .input-toolbar { border-top-color: #2a2148; }
:root.dark .tool { background: #2a2148; color: #c4b5fd; }
:root.dark .tool-project { background: #3b2b6b; color: #ddd6fe; }
:root.dark .conn-pill { background: #1a1432; border-color: #2a2148; color: #ddd6fe; }
:root.dark .row.inview { background: linear-gradient(90deg, rgba(76, 29, 149, 0.25), transparent 90%); }
:root.dark .row-v { color: #ede9fe; }
:root.dark .assignee { color: #ede9fe; }
:root.dark .float-tag { background: rgba(26, 20, 50, 0.65); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); color: #c4b5fd; border-color: rgba(167, 139, 250, 0.35); box-shadow: 0 8px 24px -6px rgba(0, 0, 0, 0.6); }
:root.dark .duplicate-note { background: rgba(6, 95, 70, 0.18); border-color: #047857; color: #6ee7b7; }
:root.dark .bg-mark { opacity: 0.06; }
:root.dark .bg-grain { opacity: 0.18; }

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .reveal, .badge-pulse, .caret, .send, .dots i, .spark, .cta-icon, .float-tag {
    animation: none !important;
  }
  .row { opacity: 1; transform: none; }
  .duplicate-note { opacity: 1; transform: none; }
}
</style>
