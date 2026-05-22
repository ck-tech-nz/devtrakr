<template>
  <footer class="hidden md:flex items-center px-6 h-9 border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 text-xs text-gray-400 dark:text-gray-500 flex-shrink-0 relative">
    <div class="absolute left-1/2 -translate-x-1/2 flex items-center gap-4">
      <span>© MatrixAI</span>
      <NuxtLink to="/app/about" class="hover:text-gray-600 dark:hover:text-gray-300 transition-colors">关于系统</NuxtLink>
      <NuxtLink to="/app/roadmap" class="hover:text-gray-600 dark:hover:text-gray-300 transition-colors">产品路线图</NuxtLink>
    </div>

    <span class="ml-auto font-mono">{{ config.public.version }}</span>
  </footer>
</template>

<script setup lang="ts">
const config = useRuntimeConfig()
const year = new Date().getFullYear()
</script>
