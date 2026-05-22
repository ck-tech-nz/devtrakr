<template>
  <div class="flex flex-col h-screen">
    <SystemAlertBanner />
    <div class="flex flex-1 min-h-0 bg-gray-50/50 dark:bg-gray-950">
      <AppSidebar />
      <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
        <AppHeader />
        <main class="flex-1 overflow-y-auto overscroll-contain p-3 md:p-6 lg:p-8 pb-20 md:pb-6 lg:pb-8">
          <slot />
        </main>
        <AppFooter />
      </div>
    </div>
  </div>
  <AppBottomTabBar />
</template>

<script setup lang="ts">
onErrorCaptured((err) => {
  console.error('[PAGE ERROR]', err)
  return false
})

onMounted(() => {
  useBroadcastPopup().start()
})
</script>
