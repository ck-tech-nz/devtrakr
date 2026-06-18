<template>
  <div
    v-if="visible && items.length > 0"
    ref="containerRef"
    class="absolute z-50 w-64 max-h-48 overflow-y-auto bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg"
    :style="dropdownStyle"
  >
    <button
      v-for="(item, idx) in items"
      :key="item.id"
      :ref="(el) => { if (el) itemRefs[idx] = el as HTMLElement }"
      class="w-full text-left px-3 py-2 text-sm transition-colors flex items-center gap-2"
      :class="idx === selectedIndex
        ? 'bg-primary-50 dark:bg-primary-950 text-primary-700 dark:text-primary-300'
        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'"
      @mousedown.prevent="selectItem(idx)"
    >
      <template v-if="type === 'user'">
        <UIcon name="i-heroicons-user-circle" class="w-4 h-4 text-gray-400 flex-shrink-0" />
        <span class="truncate">{{ item.label }}</span>
      </template>
      <template v-else>
        <span class="text-xs font-mono text-gray-400 flex-shrink-0">{{ item.prefix }}</span>
        <span class="truncate">{{ item.label }}</span>
      </template>
    </button>
  </div>
</template>

<script setup lang="ts">
export interface MentionItem {
  id: number
  label: string
  prefix?: string
}

const props = withDefaults(defineProps<{
  visible: boolean
  items: MentionItem[]
  position: { top: number; left: number }
  type: 'user' | 'issue'
  // 'bottom'(默认):锚定在输入下方;'top':向上展开(用于贴近视口底部的输入框,如聊天气泡)
  placement?: 'top' | 'bottom'
}>(), { placement: 'bottom' })

// top 放置时贴在定位父级顶部向上展开(bottom:100%),避免被底部容器裁切
const dropdownStyle = computed(() => props.placement === 'top'
  ? { bottom: '100%', left: `${props.position.left}px`, marginBottom: '6px' }
  : { top: `${props.position.top}px`, left: `${props.position.left}px` })

const emit = defineEmits<{
  select: [item: MentionItem]
}>()

const selectedIndex = ref(0)
const containerRef = ref<HTMLElement | null>(null)
const itemRefs = ref<HTMLElement[]>([])

watch(() => props.items, () => {
  selectedIndex.value = 0
  itemRefs.value = []
})

watch(selectedIndex, (idx) => {
  nextTick(() => {
    const item = itemRefs.value[idx]
    const container = containerRef.value
    if (!item || !container) return
    const itemTop = item.offsetTop
    const itemBottom = itemTop + item.offsetHeight
    if (itemTop < container.scrollTop) {
      container.scrollTop = itemTop
    } else if (itemBottom > container.scrollTop + container.clientHeight) {
      container.scrollTop = itemBottom - container.clientHeight
    }
  })
})

function selectItem(idx: number) {
  emit('select', props.items[idx])
}

function moveUp() {
  selectedIndex.value = Math.max(0, selectedIndex.value - 1)
}

function moveDown() {
  selectedIndex.value = Math.min(props.items.length - 1, selectedIndex.value + 1)
}

function confirmSelection() {
  if (props.items.length > 0) {
    emit('select', props.items[selectedIndex.value])
  }
}

defineExpose({ moveUp, moveDown, confirmSelection })
</script>
