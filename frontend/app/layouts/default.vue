<template>
  <div class="flex flex-col h-screen">
    <SystemAlertBanner />
    <div class="flex flex-1 min-h-0 bg-gray-50/50 dark:bg-gray-950">
      <AppSidebar />
      <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
        <AppHeader />
        <!-- 手机底部留白需容纳固定的玻璃底栏(栏体≈58 + mb-3 + 安全区),否则分页等底部内容被遮挡 -->
        <main class="flex-1 overflow-y-auto overscroll-contain p-3 md:p-6 lg:p-8 pb-[calc(7rem+env(safe-area-inset-bottom))] md:pb-6 lg:pb-8">
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
