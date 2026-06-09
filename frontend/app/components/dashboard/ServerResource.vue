<template>
  <div v-if="url" class="section-card">
    <button
      class="section-header section-toggle"
      :class="{ 'section-toggle--collapsed': !expanded }"
      type="button"
      @click="expanded = !expanded"
    >
      <h3 class="section-title">服务器资源</h3>
      <UIcon :name="expanded ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
    </button>
    <iframe
      v-if="expanded"
      :src="url"
      loading="lazy"
      sandbox="allow-scripts allow-same-origin"
      referrerpolicy="no-referrer"
      class="server-frame"
      :style="{ height: frameHeight + 'px' }"
    />
  </div>
</template>

<script setup lang="ts">
// 基础设施资源监控:嵌入地址来自运行时环境变量,留空则整卡不渲染。
const colorMode = useColorMode()
const expanded = ref(true)

// iframe 高度:不写死。默认贴合实测内容高度(桌面宽度下 3 台主机单行约 316px,
// 留少量余量),主机少时不再留大片空白;监控页若 postMessage 上报高度则精确自适应。
// 注:监控页 body 为 100vh,无法被父窗口直接量出内容高度,故默认值取实测经验值。
const DEFAULT_HEIGHT = 340
const MIN_HEIGHT = 200
const MAX_HEIGHT = 1400
const frameHeight = ref(DEFAULT_HEIGHT)

const base = computed(() => (useRuntimeConfig().public.serverMonitorUrl as string) || '')

// 追加 theme= 跟随应用主题:切换深浅色时 src 变化 → iframe 自动重载并渲染对应主题。
const url = computed(() => {
  if (!base.value) return ''
  const theme = colorMode.value === 'dark' ? 'dark' : 'light'
  try {
    const u = new URL(base.value)
    // 仅允许 http(s),挡住 javascript:/data: 等可疑 scheme
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return ''
    u.searchParams.set('theme', theme) // set 覆盖,避免已有 theme 参数重复
    return u.toString()
  } catch {
    return '' // 地址非法 → 整卡不渲染
  }
})

// 监控站来源(用于校验 postMessage,只接受它自己发来的高度上报)
const monitorOrigin = computed(() => {
  try { return new URL(base.value).origin } catch { return '' }
})

// 接受形如 { type:'monitor:resize', height } 或裸数字的高度上报,夹在合理区间内。
function onFrameMessage(e: MessageEvent) {
  if (!monitorOrigin.value || e.origin !== monitorOrigin.value) return
  const d = e.data as number | { height?: number, value?: number } | undefined
  const h = typeof d === 'number' ? d : (d?.height ?? d?.value)
  if (typeof h === 'number' && Number.isFinite(h)) {
    frameHeight.value = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, Math.round(h)))
  }
}
onMounted(() => window.addEventListener('message', onFrameMessage))
onBeforeUnmount(() => window.removeEventListener('message', onFrameMessage))
</script>

<style scoped>
.section-card {
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 1.25rem;
}
:root.dark .section-card {
  background-color: #1f2937;
  border-color: #374151;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.section-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
:root.dark .section-title { color: #f3f4f6; }
.section-toggle {
  width: 100%;
  background: transparent;
  border: 0;
  cursor: pointer;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: left;
}
.section-toggle--collapsed { margin-bottom: 0; }
.section-toggle:hover .section-title { color: #7c3aed; }
:root.dark .section-toggle:hover .section-title { color: #c4b5fd; }
.server-frame {
  width: 100%;
  /* 高度由 JS 动态控制(frameHeight),不写死;切换时平滑过渡 */
  display: block;
  border: 0;
  border-radius: 0.5rem;
  transition: height 0.3s ease;
  /* 监控页内容透明:容器背景随主题切换(与卡片同色),避免白底闪烁/穿透 */
  background-color: #ffffff;
  color-scheme: light;
}
:root.dark .server-frame {
  background-color: #1f2937;
  color-scheme: dark;
}
</style>
