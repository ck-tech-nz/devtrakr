<template>
  <UPopover>
    <UButton
      icon="i-heroicons-view-columns"
      :size="size"
      variant="ghost"
      color="neutral"
      aria-label="显示/隐藏表格列"
      title="显示/隐藏表格列"
    />
    <template #content>
      <div class="w-52 p-0">
        <div class="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
          <p class="text-xs font-semibold text-gray-900 dark:text-gray-100">表格列</p>
          <p class="text-[11px] text-gray-400 dark:text-gray-500">勾选 = 显示该列</p>
        </div>
        <div class="max-h-72 overflow-y-auto py-1">
          <!-- 锁定列:恒显,灰显且不可点击 -->
          <div
            v-for="c in lockedColumns"
            :key="c.key"
            class="flex items-center gap-2 w-full px-3 py-1.5 text-left opacity-50 cursor-not-allowed"
            title="该列始终显示"
          >
            <UIcon name="i-heroicons-check" class="w-4 h-4 shrink-0 text-gray-400 dark:text-gray-500" />
            <span class="flex-1 text-sm text-gray-900 dark:text-gray-100">{{ c.label }}</span>
            <span class="text-[10px] text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 rounded px-1.5 py-0.5">必显</span>
          </div>
          <div v-if="lockedColumns.length && toggleableColumns.length" class="my-1 border-t border-gray-100 dark:border-gray-800" />
          <!-- 可切换列:点击切换显隐 -->
          <button
            v-for="c in toggleableColumns"
            :key="c.key"
            type="button"
            class="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            @click="toggle(c.key)"
          >
            <UIcon
              :name="isVisible(c.key) ? 'i-heroicons-check' : ''"
              class="w-4 h-4 shrink-0"
              :class="isVisible(c.key) ? 'text-primary-600 dark:text-primary-400' : 'text-transparent'"
            />
            <span class="text-sm text-gray-900 dark:text-gray-100">{{ c.label }}</span>
          </button>
        </div>
      </div>
    </template>
  </UPopover>
</template>

<script setup lang="ts">
// 表格列显示/隐藏编辑器:列出全部表格列,勾选=显示该列。
// locked 列(ID/标题/状态)恒显,灰显且不可切换;其余列点击切换。
// 选择以「被隐藏的列 key 数组」(hidden)对外暴露,由父组件持久化到 localStorage。
interface ColumnOption { key: string; label: string; locked?: boolean }

const props = withDefaults(defineProps<{
  columns: ColumnOption[]
  hidden: string[]
  size?: 'xs' | 'sm' | 'md'
}>(), { size: 'sm' })

const emit = defineEmits<{ 'update:hidden': [string[]] }>()

// 锁定列分组到顶部展示;可切换列保持原有顺序
const lockedColumns = computed(() => props.columns.filter(c => c.locked))
const toggleableColumns = computed(() => props.columns.filter(c => !c.locked))

function isVisible(key: string): boolean {
  return !props.hidden.includes(key)
}

function toggle(key: string) {
  if (isVisible(key)) {
    emit('update:hidden', [...props.hidden, key])
  } else {
    emit('update:hidden', props.hidden.filter(k => k !== key))
  }
}
</script>
