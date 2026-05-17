<template>
  <header class="h-16 bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between px-3 md:px-6 lg:px-8 flex-shrink-0">
    <nav class="hidden md:flex items-center space-x-2 text-sm">
      <template v-for="(crumb, idx) in breadcrumbs" :key="idx">
        <UIcon v-if="idx > 0" name="i-heroicons-chevron-right-20-solid" class="w-4 h-4 text-gray-300" />
        <NuxtLink v-if="crumb.to" :to="crumb.to" class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
          {{ crumb.label }}
        </NuxtLink>
        <span v-else class="text-gray-900 dark:text-gray-100 font-medium">{{ crumb.label }}</span>
      </template>
    </nav>
    <span class="md:hidden text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
      {{ breadcrumbs[breadcrumbs.length - 1]?.label || '' }}
    </span>

    <div class="flex items-center space-x-3">
      <UButton
        :icon="themeIcon"
        variant="ghost"
        color="neutral"
        size="sm"
        @click="cycleTheme"
      />
      <NotificationBell />

      <UDropdownMenu :items="userMenuItems" :content="{ align: 'end' as const }">
        <button class="flex items-center space-x-2 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg px-2 py-1.5 transition-colors">
          <img v-if="user?.avatar" :src="resolveAvatarUrl(user.avatar)" class="w-8 h-8 rounded-full" />
          <div v-else class="w-8 h-8 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center">
            <span class="text-crystal-600 dark:text-crystal-400 text-sm font-medium">{{ displayInitial }}</span>
          </div>
          <span class="text-sm text-gray-700 dark:text-gray-300 font-medium hidden sm:inline">{{ displayName }}</span>
          <UIcon name="i-heroicons-chevron-down-20-solid" class="w-4 h-4 text-gray-400" />
        </button>
      </UDropdownMenu>
    </div>
  </header>
</template>

<script setup lang="ts">
const { breadcrumbs } = useNavigation()
const { user, logout } = useAuth()
const { settings, update } = useUserSettings()
const { resolveAvatarUrl } = useAvatars()
const { api } = useApi()

async function openAdmin() {
  try {
    await api('/api/auth/admin-session/', { method: 'POST', credentials: 'include' })
  } catch {
    // 鉴权失败仍打开，由 admin 自身处理登录页
  }
  window.open('/api/admin/', '_blank')
}

const displayName = computed(() => user.value?.name || '用户')
const displayInitial = computed(() => (user.value?.name || '?').slice(0, 1))

const themeIcon = computed(() => {
  const t = settings.value.theme
  return t === 'dark' ? 'i-heroicons-moon' : t === 'auto' ? 'i-heroicons-computer-desktop' : 'i-heroicons-sun'
})

const themeOrder: Array<'light' | 'dark' | 'auto'> = ['light', 'dark', 'auto']

function cycleTheme() {
  const idx = themeOrder.indexOf(settings.value.theme)
  update('theme', themeOrder[(idx + 1) % themeOrder.length])
}

const userMenuItems = computed(() => {
  const items: any[][] = [
    [
      {
        label: '个人资料',
        icon: 'i-heroicons-user-circle',
        onSelect: () => navigateTo('/app/profile'),
      },
      {
        label: '我的提升计划',
        icon: 'i-heroicons-clipboard-document-check',
        onSelect: () => navigateTo('/app/ai/my-plan'),
      },
    ],
  ]
  if (user.value?.is_superuser) {
    items.push([{
      label: '系统管理',
      icon: 'i-heroicons-cog-6-tooth',
      onSelect: () => openAdmin(),
    }])
  }
  items.push([{
    label: '退出登录',
    icon: 'i-heroicons-arrow-right-on-rectangle',
    onSelect: () => logout(),
  }])
  return items
})
</script>
