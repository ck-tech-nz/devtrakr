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
      class="server-frame"
    />
  </div>
</template>

<script setup lang="ts">
// 基础设施资源监控:嵌入地址来自运行时环境变量,留空则整卡不渲染。
const colorMode = useColorMode()
const expanded = ref(true)

// 追加 &theme= 跟随应用主题:切换深浅色时 src 变化 → iframe 自动重载并渲染对应主题。
const url = computed(() => {
  const base = (useRuntimeConfig().public.serverMonitorUrl as string) || ''
  if (!base) return ''
  const theme = colorMode.value === 'dark' ? 'dark' : 'light'
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}theme=${theme}`
})
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
  height: 640px;
  border: 0;
  border-radius: 0.5rem;
  /* 监控页内容透明:容器背景随主题切换(与卡片同色),避免白底闪烁/穿透 */
  background-color: #ffffff;
  color-scheme: light;
}
:root.dark .server-frame {
  background-color: #1f2937;
  color-scheme: dark;
}
</style>
