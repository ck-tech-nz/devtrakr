<template>
  <Transition name="vigil">
    <div v-if="visible" class="vigil-strip" role="alert" aria-live="polite">
      <div class="vigil-grain" aria-hidden="true" />
      <div class="vigil-content">
        <div class="vigil-indicator" aria-hidden="true">
          <span class="vigil-diamond" />
          <span class="vigil-diamond-glow" />
        </div>

        <div class="vigil-text">
          <span class="vigil-headline">生产环境异常</span>
          <span class="vigil-count">{{ activeMonitors.length }}</span>
          <span class="vigil-divider">·</span>
          <span class="vigil-names" :title="allNames">{{ displayNames }}</span>
        </div>

        <NuxtLink :to="primaryLink" class="vigil-action">
          <span>立即查看</span>
          <UIcon name="i-heroicons-arrow-up-right" class="vigil-action-icon" />
        </NuxtLink>

        <button class="vigil-dismiss" type="button" aria-label="忽略本次警报" @click="dismiss">
          <UIcon name="i-heroicons-x-mark" />
        </button>
      </div>
      <div class="vigil-underline" aria-hidden="true" />
    </div>
  </Transition>
</template>

<script setup lang="ts">
interface MonitorRow {
  id: number
  project: number
  project_name: string
  name: string
  environment: string
  last_status: string
  outage_started_at: string | null
}

const { api } = useApi()
const { user } = useAuth()

const monitors = ref<MonitorRow[]>([])
const dismissedSignature = ref<string>('')
let pollTimer: ReturnType<typeof setInterval> | null = null

const DISMISS_KEY = 'vigil_dismissed_signature_v1'

const activeMonitors = computed(() =>
  monitors.value.filter(
    m => m.environment === 'production' && m.last_status === 'down',
  ),
)

const signature = computed(() =>
  [...activeMonitors.value]
    .map(m => `${m.id}:${m.outage_started_at || ''}`)
    .sort()
    .join('|'),
)

const visible = computed(() =>
  activeMonitors.value.length > 0 && signature.value !== dismissedSignature.value,
)

const allNames = computed(() =>
  activeMonitors.value.map(m => `${m.name} · ${m.project_name}`).join('、'),
)

const displayNames = computed(() => {
  const list = activeMonitors.value
  if (list.length === 0) return ''
  if (list.length === 1) return `${list[0]!.name} · ${list[0]!.project_name}`
  if (list.length === 2) return `${list[0]!.name}、${list[1]!.name}`
  return `${list[0]!.name}、${list[1]!.name} 等 ${list.length} 个`
})

const primaryLink = computed(() => {
  const first = activeMonitors.value[0]
  return first ? `/app/projects/${first.project}` : '/app/home'
})

async function fetchMonitors() {
  if (!user.value) return
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
  try {
    const data = await api<MonitorRow[]>('/api/uptime/monitors/')
    monitors.value = data ?? []
  } catch (e) {
    // silent fail — banner is informational, don't disrupt the app
  }
}

function dismiss() {
  dismissedSignature.value = signature.value
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(DISMISS_KEY, signature.value)
  }
}

onMounted(async () => {
  if (typeof localStorage !== 'undefined') {
    dismissedSignature.value = localStorage.getItem(DISMISS_KEY) || ''
  }
  await fetchMonitors()
  pollTimer = setInterval(fetchMonitors, 5_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.vigil-strip {
  position: relative;
  width: 100%;
  background:
    linear-gradient(180deg, #5e1313 0%, #7c1d1d 45%, #5e1313 100%);
  color: #f5e7d3;
  border-bottom: 1px solid #3a0a0a;
  box-shadow:
    inset 0 1px 0 rgba(245, 184, 66, 0.12),
    inset 0 -1px 0 rgba(0, 0, 0, 0.4),
    0 6px 18px -8px rgba(124, 29, 29, 0.55);
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
    "Microsoft YaHei", "Segoe UI", "Hiragino Sans GB", sans-serif;
  overflow: hidden;
  isolation: isolate;
  user-select: none;
}

.vigil-grain {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.09;
  mix-blend-mode: overlay;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='160' height='160' filter='url(%23n)' opacity='0.7'/></svg>");
}

.vigil-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 1.1rem;
  padding: 0.7rem 1.4rem 0.75rem;
  max-width: 100%;
}

/* indicator */
.vigil-indicator {
  position: relative;
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.vigil-diamond {
  width: 10px;
  height: 10px;
  background: #f5b842;
  transform: rotate(45deg);
  box-shadow:
    0 0 0 1px rgba(245, 184, 66, 0.35),
    0 0 10px 1px rgba(245, 184, 66, 0.45);
  animation: vigil-pulse 1.8s ease-in-out infinite;
}

.vigil-diamond-glow {
  position: absolute;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(245, 184, 66, 0.35) 0%,
    rgba(245, 184, 66, 0) 70%
  );
  animation: vigil-halo 1.8s ease-in-out infinite;
}

@keyframes vigil-pulse {
  0%, 100% {
    transform: rotate(45deg) scale(1);
    opacity: 0.95;
  }
  50% {
    transform: rotate(45deg) scale(1.15);
    opacity: 1;
  }
}

@keyframes vigil-halo {
  0%, 100% { transform: scale(0.7); opacity: 0.5; }
  50% { transform: scale(1.4); opacity: 0; }
}

/* text */
.vigil-text {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  white-space: nowrap;
  overflow: hidden;
}

.vigil-headline {
  flex-shrink: 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.18em;
  color: #f5e7d3;
  padding-right: 0.7rem;
  border-right: 1px solid rgba(245, 231, 211, 0.22);
  line-height: 1.4;
}

.vigil-count {
  flex-shrink: 0;
  font-family: "Georgia", "Songti SC", "STSong", "SimSun", serif;
  font-style: italic;
  font-weight: 400;
  font-size: 1.55rem;
  color: #f5b842;
  line-height: 1;
  letter-spacing: -0.02em;
}

.vigil-divider {
  flex-shrink: 0;
  color: rgba(245, 231, 211, 0.45);
  font-size: 0.85rem;
}

.vigil-names {
  flex: 1;
  min-width: 0;
  font-size: 0.86rem;
  color: rgba(245, 231, 211, 0.85);
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.01em;
}

/* action button */
.vigil-action {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.82rem;
  font-weight: 500;
  color: #f5e7d3;
  background: rgba(245, 231, 211, 0.08);
  border: 1px solid rgba(245, 231, 211, 0.18);
  padding: 0.36rem 0.85rem;
  border-radius: 999px;
  transition: all 0.2s ease;
  text-decoration: none;
}
.vigil-action:hover {
  background: rgba(245, 184, 66, 0.15);
  border-color: rgba(245, 184, 66, 0.55);
  color: #fff5d6;
}
.vigil-action-icon {
  width: 0.85rem;
  height: 0.85rem;
  transition: transform 0.2s ease;
}
.vigil-action:hover .vigil-action-icon {
  transform: translate(1px, -1px);
}

/* dismiss */
.vigil-dismiss {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: rgba(245, 231, 211, 0.55);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.vigil-dismiss:hover {
  color: rgba(245, 231, 211, 0.95);
  background: rgba(0, 0, 0, 0.25);
  border-color: rgba(245, 231, 211, 0.15);
}
.vigil-dismiss :deep(svg) {
  width: 0.95rem;
  height: 0.95rem;
}

/* underline glow */
.vigil-underline {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(245, 184, 66, 0.45) 30%,
    rgba(245, 184, 66, 0.7) 50%,
    rgba(245, 184, 66, 0.45) 70%,
    transparent 100%
  );
}

/* entrance / exit */
.vigil-enter-active,
.vigil-leave-active {
  transition:
    max-height 0.4s cubic-bezier(0.16, 1, 0.3, 1),
    opacity 0.3s ease;
  overflow: hidden;
}
.vigil-enter-from,
.vigil-leave-to {
  max-height: 0;
  opacity: 0;
}
.vigil-enter-to,
.vigil-leave-from {
  max-height: 80px;
  opacity: 1;
}

/* narrow viewport — hide the names, keep the count and action visible */
@media (max-width: 640px) {
  .vigil-content {
    gap: 0.7rem;
    padding: 0.6rem 0.8rem 0.65rem;
  }
  .vigil-headline {
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    padding-right: 0.5rem;
  }
  .vigil-count {
    font-size: 1.25rem;
  }
  .vigil-divider,
  .vigil-names {
    display: none;
  }
}
</style>
