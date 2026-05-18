<template>
  <aside
    class="h-screen bg-white dark:bg-gray-900 border-r border-gray-100 dark:border-gray-800 hidden md:flex flex-col transition-all duration-300 ease-in-out flex-shrink-0 relative z-30"
    :class="expanded ? 'w-60' : 'w-16'"
  >
    <div
      class="h-16 border-b border-gray-50 dark:border-gray-800 flex items-center"
      :class="expanded ? 'px-4 gap-2' : 'justify-center px-2'"
    >
      <img v-if="expanded" src="~/assets/images/logo-icon.svg" alt="DevTrakr" class="w-8 h-8 flex-shrink-0" />
      <transition name="fade">
        <span v-if="expanded" class="font-semibold text-gray-900 dark:text-gray-100 whitespace-nowrap">DevTrakr</span>
      </transition>
      <div v-if="expanded" class="flex-1" />
      <button
        class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 flex-shrink-0 p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
        :title="expanded ? '收起侧边栏' : '展开侧边栏'"
        @click.stop="expanded = !expanded"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2" />
          <path d="M9 3v18" />
        </svg>
      </button>
    </div>

    <nav class="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
      <template v-for="entry in groupedNavItems" :key="isNavGroup(entry) ? entry.label : entry.to">
        <!-- Group header -->
        <template v-if="isNavGroup(entry)">
          <button
            class="flex items-center w-full h-10 px-2 rounded-lg transition-colors"
            :class="isGroupActive(entry)
              ? 'text-crystal-600 dark:text-crystal-400'
              : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'"
            @click="toggleGroup(entry.label)"
          >
            <UIcon :name="entry.icon" class="w-5 h-5 flex-shrink-0" />
            <transition name="fade">
              <span v-if="expanded" class="ml-3 text-sm font-medium whitespace-nowrap flex-1 text-left">{{ entry.label }}</span>
            </transition>
            <transition name="fade">
              <UIcon
                v-if="expanded"
                :name="openGroups.has(entry.label) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                class="w-3.5 h-3.5 flex-shrink-0 opacity-50"
              />
            </transition>
          </button>
          <!-- Sub-items (only when sidebar is expanded) -->
          <template v-if="expanded && openGroups.has(entry.label)">
            <NuxtLink
              v-for="child in entry.children"
              :key="child.to"
              :to="child.to!"
              class="flex items-center h-9 pl-9 pr-2 rounded-lg transition-colors text-sm"
              :class="isChildActive(child)
                ? 'bg-crystal-50 dark:bg-crystal-950 text-crystal-600 dark:text-crystal-400'
                : 'text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200'"
            >
              {{ child.label }}
            </NuxtLink>
          </template>
        </template>

        <!-- Standalone item -->
        <NuxtLink
          v-else
          :to="entry.to!"
          class="flex items-center h-10 px-2 rounded-lg transition-colors group"
          :class="isChildActive(entry)
            ? 'bg-crystal-50 dark:bg-crystal-950 text-crystal-600 dark:text-crystal-400'
            : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'"
        >
          <UIcon :name="entry.icon" class="w-5 h-5 flex-shrink-0" />
          <transition name="fade">
            <span v-if="expanded" class="ml-3 text-sm font-medium whitespace-nowrap flex items-center gap-2">
              {{ entry.label }}
              <ServiceStatusDot
                v-if="entry.meta?.serviceKey"
                :online="isOnline(entry.meta.serviceKey)"
              />
            </span>
          </transition>
        </NuxtLink>
      </template>

      <MyTasksSidebar :expanded="expanded" />
    </nav>

    <div
      class="border-t border-gray-50 dark:border-gray-800 py-3 px-3"
      :class="expanded ? 'flex items-center justify-between gap-2' : 'flex flex-col items-center gap-2'"
    >
      <div :class="expanded ? 'flex items-center gap-2' : 'flex flex-col items-center gap-2'">
        <UTooltip
          v-for="key in ['github', 'ai']"
          :key="key"
          :text="getLabel(key) + (isOnline(key) ? ' · 在线' : ' · 离线')"
        >
          <button class="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800" @click="toggle(key)">
            <ServiceStatusDot :online="isOnline(key)" />
          </button>
        </UTooltip>
      </div>
      <a
        href="https://matrixai.xin/"
        target="_blank"
        rel="noopener"
        class="flex items-center hover:opacity-80 transition-opacity"
        title="MATRIX AI"
      >
        <img
          v-if="expanded"
          src="~/assets/images/matrix-ai-logo.svg"
          alt="MATRIX AI"
          class="h-5 w-auto"
        />
        <img
          v-else
          src="~/assets/images/matrix-ai-mark.svg"
          alt="MATRIX AI"
          class="h-5 w-auto"
        />
      </a>
    </div>

  </aside>
</template>

<script setup lang="ts">
import { isNavGroup } from '~/composables/useNavigation'
import type { NavItem, NavGroup } from '~/composables/useNavigation'

const { groupedNavItems, currentPath } = useNavigation()
const { isOnline, toggle, getLabel } = useServiceStatus()
const { settings, update } = useUserSettings()
const expanded = computed({
  get: () => !settings.value.sidebar_auto_collapse,
  set: (v: boolean) => update('sidebar_auto_collapse', !v),
})

// Track which groups are open
const openGroups = ref(new Set<string>())

function isChildActive(item: NavItem) {
  if (!item.to) return false
  return currentPath.value === item.to || currentPath.value.startsWith(item.to + '/')
}

function isGroupActive(group: NavGroup) {
  return group.children.some(c => isChildActive(c))
}

function toggleGroup(label: string) {
  if (openGroups.value.has(label)) {
    openGroups.value.delete(label)
  } else {
    openGroups.value.add(label)
  }
}

// Auto-open the group that contains the current route
watch([currentPath, groupedNavItems], () => {
  for (const entry of groupedNavItems.value) {
    if (isNavGroup(entry) && isGroupActive(entry)) {
      openGroups.value.add(entry.label)
    }
  }
}, { immediate: true })
</script>

<style scoped>
.fade-enter-active { transition: opacity 0.2s ease 0.1s; }
.fade-leave-active { transition: opacity 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
