<template>
  <div>
    <div v-if="modelValue" class="flex items-center gap-3 mb-4">
      <img :src="resolveAvatarUrl(modelValue)" :alt="modelValue" class="w-16 h-16 rounded-full ring-2 ring-crystal-500 object-cover" />
      <span class="text-sm text-gray-500 dark:text-gray-400">{{ currentLabel }}</span>
    </div>
    <div v-for="grp in avatarGroups" :key="grp.id" class="mb-5 last:mb-0">
      <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-2">{{ grp.label }}</p>
      <div class="grid grid-cols-5 gap-3">
        <button
          v-for="avatar in grp.avatars"
          :key="avatar.id"
          type="button"
          class="relative group w-14 h-14 rounded-full overflow-hidden transition-all flex-shrink-0"
          :class="modelValue === avatar.id ? 'ring-3 ring-crystal-500 scale-110' : 'ring-1 ring-gray-200 dark:ring-gray-700 hover:ring-crystal-300'"
          @click="$emit('update:modelValue', avatar.id)"
        >
          <img :src="resolveAvatarUrl(avatar.id)" :alt="avatar.label" class="w-14 h-14 object-cover" />
          <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <span class="text-white text-[10px] font-medium">{{ avatar.label }}</span>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ modelValue: string }>()
defineEmits<{ 'update:modelValue': [value: string] }>()

const { avatarGroups, avatarList, resolveAvatarUrl, isUploadedAvatar } = useAvatars()

const currentLabel = computed(() => {
  if (isUploadedAvatar(props.modelValue)) return '自定义头像'
  return avatarList.find(a => a.id === props.modelValue)?.label
})
</script>
