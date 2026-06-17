<template>
  <UPopover>
    <UButton
      icon="i-heroicons-view-columns"
      :size="size"
      variant="ghost"
      color="neutral"
      aria-label="显示/隐藏看板列"
      title="显示/隐藏看板列"
    />
    <template #content>
      <div class="w-52 p-0">
        <div class="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
          <p class="text-xs font-semibold text-gray-900 dark:text-gray-100">看板列</p>
          <p class="text-[11px] text-gray-400 dark:text-gray-500">勾选 = 显示该状态列</p>
        </div>
        <div class="max-h-72 overflow-y-auto py-1">
          <button
            v-for="s in statuses"
            :key="s.value"
            type="button"
            class="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            :class="{ 'opacity-50 cursor-not-allowed': isVisible(s.value) && !canHide }"
            :title="isVisible(s.value) && !canHide ? '至少保留一列' : ''"
            @click="toggle(s.value)"
          >
            <UIcon
              :name="isVisible(s.value) ? 'i-heroicons-check' : ''"
              class="w-4 h-4 shrink-0"
              :class="isVisible(s.value) ? 'text-primary-600 dark:text-primary-400' : 'text-transparent'"
            />
            <span class="w-2.5 h-2.5 rounded-full shrink-0" :style="{ backgroundColor: s.color }" />
            <span class="text-sm text-gray-900 dark:text-gray-100">{{ s.label }}</span>
          </button>
          <div v-if="!statuses.length" class="px-3 py-4 text-center text-xs text-gray-400">无可配置的状态</div>
        </div>
      </div>
    </template>
  </UPopover>
</template>

<script setup lang="ts">
// 看板列显示/隐藏编辑器:列出所有可选状态(管理员禁用的不传入),勾选=显示该状态列。
// 选择以「被隐藏的状态值数组」(hidden)对外暴露,由父组件持久化到用户设置。
interface StatusOption { value: string; label: string; color: string }

const props = withDefaults(defineProps<{
  statuses: StatusOption[]
  hidden: string[]
  size?: 'xs' | 'sm' | 'md'
}>(), { size: 'sm' })

const emit = defineEmits<{ 'update:hidden': [string[]] }>()

function isVisible(v: string): boolean {
  return !props.hidden.includes(v)
}

// 至少保留一列:仅剩一个可见列时不允许再隐藏,避免空看板
const canHide = computed(() => props.statuses.filter(s => isVisible(s.value)).length > 1)

function toggle(v: string) {
  if (isVisible(v)) {
    if (!canHide.value) return // 守住最后一列
    emit('update:hidden', [...props.hidden, v])
  } else {
    emit('update:hidden', props.hidden.filter(x => x !== v))
  }
}
</script>
