<template>
  <div data-mobile-tabbar class="fixed bottom-0 left-0 right-0 z-40 md:hidden flex justify-center px-3" style="padding-bottom: env(safe-area-inset-bottom)">
    <ClientOnly>
      <LiquidGlassBottomNavBar
        v-model="selectedTabId"
        :items="tabItems"
        size="large"
        :item-width-override="dynamicItemWidth"
        :always-show-glass="false"
        :specular-opacity="0.4"
        :specular-saturation="10"
        :base-refraction="-0.4"
        color="#7c3aed"
        class="mb-3"
      />
    </ClientOnly>
    <MobileMoreSheet v-model:open="moreOpen" :items="moreNavItems" />
  </div>
</template>

<script setup lang="ts">
import LiquidGlassBottomNavBar from '~/components/liquid-glass/LiquidGlassBottomNavBar.vue'
import type { NavItem } from '~/composables/useNavigation'

const router = useRouter()
const { filteredNavItems, currentPath } = useNavigation()
// 全局消息收件箱:手机端入口收进底部栏「消息」Tab(桌面端仍走右下角 FAB)
const { unreadTotal, toggleChat, open: chatOpen } = useChat()

// 动态计算每个 tab 宽度，使导航栏接近全屏宽度
const screenWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 393)
onMounted(() => {
  const onResize = () => { screenWidth.value = window.innerWidth }
  window.addEventListener('resize', onResize)
  onUnmounted(() => window.removeEventListener('resize', onResize))
})

const primaryRoutes = ['/app/issues', '/app/dashboard', '/app/repos']

const primaryTabs = computed(() => {
  const tabs: NavItem[] = []
  for (const route of primaryRoutes) {
    const item = filteredNavItems.value.find(i => i.to === route)
    if (item) tabs.push(item)
  }
  return tabs
})

const moreNavItems = computed(() =>
  filteredNavItems.value.filter(item => item.to && !primaryRoutes.includes(item.to))
)

// All tabs including "消息" + "更多" inside one unified pill
const tabItems = computed(() => [
  ...primaryTabs.value.map(tab => ({
    id: tab.to!,
    label: tab.label,
    icon: tab.icon,
  })),
  { id: '_chat', label: '消息', icon: 'i-heroicons-chat-bubble-oval-left-ellipsis', badge: unreadTotal.value },
  { id: '_more', label: '更多', icon: 'i-heroicons-ellipsis-horizontal' },
])

// 24px = 左右 px-3 padding
const dynamicItemWidth = computed(() => {
  const availableWidth = screenWidth.value - 24
  const count = tabItems.value.length
  return Math.floor(availableWidth / count)
})

const moreOpen = ref(false)

const currentRealTab = computed(() => {
  const match = primaryTabs.value.find(t => t.to && (currentPath.value === t.to || currentPath.value.startsWith(t.to + '/')))
  return match?.to || ''
})

// Prevent re-entrancy when resetting the slider after a "command" tab tap (消息/更多)
let resetting = false
// 防抖:一次物理点击在触屏上会派发多个事件(touchstart + 兼容 mousedown/click),
// 即便上游去重失效,也保证「消息」面板每次点击只切换一次(否则会开→关而闪现)。
let lastChatTapAt = 0

const selectedTabId = computed({
  get: () => currentRealTab.value,
  set: (id: string) => {
    if (resetting) return
    if (id === '_chat') {
      // 消息是命令式 Tab:开关聊天面板,滑块选中态回弹到当前路由 Tab(不停留在「消息」)
      const now = Date.now()
      if (now - lastChatTapAt > 350) {
        lastChatTapAt = now
        toggleChat()
      }
      resetting = true
      nextTick(() => { resetting = false })
      return
    }
    // 切到其它 Tab 时先关闭聊天面板(若开着),避免叠层
    if (chatOpen.value) chatOpen.value = false
    if (id === '_more') {
      // Delay sheet open so the touch event completes before the drawer renders
      // This prevents the finger-up from hitting a sheet item
      setTimeout(() => {
        moreOpen.value = true
      }, 150)
      // Reset the liquid glass back to the real active tab
      resetting = true
      nextTick(() => { resetting = false })
      return
    }
    router.push(id)
  },
})
</script>
