<template>
  <div
    class="grid gap-4"
    :class="scrollable ? 'h-full min-h-0 auto-rows-[minmax(0,1fr)]' : ''"
    :style="{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }"
  >
    <div
      v-for="col in columns"
      :key="col.key"
      class="rounded-xl p-4 transition-colors bg-gray-50 dark:bg-gray-800 border border-gray-200/80 dark:border-gray-700"
      :class="[
        draggable && dragOverTarget === col.key ? 'ring-2 ring-crystal-300 dark:ring-crystal-700' : '',
        scrollable ? 'flex flex-col min-h-0 overflow-hidden' : '',
      ]"
      @dragover.prevent="draggable && onDragOver(col.key)"
      @dragleave="draggable && onDragLeave()"
      @drop="draggable && onDrop(col.key)"
    >
      <div class="flex items-center justify-between mb-3" :class="scrollable ? 'shrink-0' : ''">
        <div class="flex items-center gap-2">
          <div v-if="col.color" class="w-2.5 h-2.5 rounded-full" :style="{ backgroundColor: col.color }" />
          <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300">{{ col.label }}</h4>
        </div>
        <UBadge color="neutral" variant="subtle" size="xs">{{ col.count ?? col.items.length }}</UBadge>
      </div>
      <div
        class="space-y-2"
        :class="scrollable ? 'flex-1 min-h-0 overflow-y-auto overscroll-contain pr-0.5 -mr-1' : ''"
        @scroll.passive="scrollable && onColumnScroll($event, col)"
      >
        <div
          v-for="item in col.items"
          :key="itemKey(item)"
          :draggable="draggable"
          class="rounded-lg border p-3 hover:shadow-sm transition-shadow"
          :class="[
            cardClass?.(item) || 'bg-white dark:bg-gray-900 border-gray-100 dark:border-gray-800',
            draggable ? 'cursor-grab active:cursor-grabbing' : '',
            draggable && draggingId === itemKey(item) ? 'opacity-40' : '',
          ]"
          :style="cardStyle?.(item)"
          @dragstart="draggable && onDragStart(itemKey(item))"
          @dragend="draggable && onDragEnd()"
        >
          <slot name="card" :item="item" :column="col.key" />
        </div>
        <div v-if="col.loading" class="py-2 text-center text-xs text-gray-400 dark:text-gray-500">
          加载中...
        </div>
        <!-- 列内容不足一屏滚不动时,提供手动加载入口兜底 -->
        <button
          v-else-if="scrollable && col.hasMore"
          class="w-full py-1.5 text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
          @click="emit('loadMore', col.key)"
        >
          加载更多
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface KanbanColumn {
  key: string
  label: string
  items: any[]
  color?: string
  // 以下三项仅 scrollable 分页模式使用;不传时计数回退为 items.length
  count?: number
  hasMore?: boolean
  loading?: boolean
}

const props = withDefaults(defineProps<{
  columns: KanbanColumn[]
  itemKey?: (item: any) => string | number
  draggable?: boolean
  // 可选:按 item 返回卡片容器的覆盖类(返回空串则用默认白底);用于高亮特定卡片
  cardClass?: (item: any) => string
  // 可选:按 item 返回卡片容器的行内样式;配合 cardClass 注入 CSS 变量(如优先级主色)
  cardStyle?: (item: any) => Record<string, string> | undefined
  // 定高模式:列内独立滚动,滚动到底部触发 loadMore(学 GitHub Projects)
  scrollable?: boolean
}>(), {
  itemKey: (item: any) => item.id,
  draggable: true,
  scrollable: false,
})

const emit = defineEmits<{
  drop: [payload: { itemId: string | number; fromColumn: string; toColumn: string }]
  loadMore: [columnKey: string]
}>()

const { draggingId, dragOverTarget, onDragStart, onDragEnd, onDragOver, onDragLeave } = useDragDrop<string | number>()

function onDrop(toColumn: string) {
  const itemId = draggingId.value
  if (itemId == null) return

  const fromCol = props.columns.find(c => c.items.some(i => props.itemKey(i) === itemId))
  if (fromCol && fromCol.key !== toColumn) {
    emit('drop', { itemId, fromColumn: fromCol.key, toColumn })
  }
  onDragEnd()
}

// 距底部不足 120px 视为触底,续取下一页
function onColumnScroll(e: Event, col: KanbanColumn) {
  if (!col.hasMore || col.loading) return
  const el = e.target as HTMLElement
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 120) {
    emit('loadMore', col.key)
  }
}
</script>
