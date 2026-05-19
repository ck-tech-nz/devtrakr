<template>
  <UApp>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
    <AppDialog />
  </UApp>
</template>

<script setup lang="ts">
const colorMode = useColorMode()
const { settings } = useUserSettings()

useHead({
  htmlAttrs: { lang: 'zh-CN' },
  bodyAttrs: { class: 'font-sans antialiased' },
  link: [
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
    { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap' },
  ]
})

watch(() => settings.value.theme, (theme) => {
  colorMode.preference = theme === 'auto' ? 'system' : theme
}, { immediate: true })
</script>

<style>
body {
  font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji";
}
</style>
