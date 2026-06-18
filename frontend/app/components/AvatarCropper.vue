<template>
  <UModal
    :open="modelValue"
    title="裁剪头像"
    :dismissible="false"
    :ui="{ content: 'sm:max-w-md' }"
    @update:open="emit('update:modelValue', $event)"
  >
    <template #body>
      <div class="space-y-4">
        <!-- 取景框:正方形,圆形遮罩提示头像最终为圆形 -->
        <div
          ref="viewportEl"
          class="relative mx-auto overflow-hidden bg-gray-100 dark:bg-gray-800 touch-none select-none cursor-move"
          :style="{ width: VIEW + 'px', height: VIEW + 'px' }"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
          @pointercancel="onPointerUp"
          @wheel.prevent="onWheel"
        >
          <img
            v-if="src"
            ref="imgEl"
            :src="src"
            alt=""
            draggable="false"
            class="absolute max-w-none origin-top-left pointer-events-none"
            :style="{ left: ox + 'px', top: oy + 'px', width: dw + 'px', height: dh + 'px' }"
            @load="onImageLoad"
          />
          <!-- 圆形取景遮罩:内切圆透明,四周压暗,提示头像最终为圆形 -->
          <div class="absolute inset-0 pointer-events-none rounded-sm" :style="MASK_STYLE" />
        </div>

        <!-- 缩放滑块 -->
        <div class="flex items-center gap-3 px-1">
          <UIcon name="i-heroicons-magnifying-glass-minus" class="w-4 h-4 text-gray-400 shrink-0" />
          <USlider v-model="zoom" :min="1" :max="MAX_ZOOM" :step="0.01" class="flex-1" />
          <UIcon name="i-heroicons-magnifying-glass-plus" class="w-4 h-4 text-gray-400 shrink-0" />
        </div>
        <p class="text-xs text-gray-400 text-center">拖动调整位置,滑动缩放</p>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" @click="emit('update:modelValue', false)">取消</UButton>
        <UButton color="primary" :disabled="!ready" @click="confirm">使用</UButton>
      </div>
    </template>
  </UModal>
</template>

<script setup lang="ts">
import { centerOffset, clampOffset, coverScale, offsetForZoomAtCenter, sourceRect } from '~/composables/useAvatarCrop'

const props = defineProps<{ modelValue: boolean; src: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  cropped: [file: File]
}>()

const VIEW = 288 // 取景框边长(逻辑像素)
const OUTPUT = 512 // 导出图边长
const MAX_ZOOM = 3
// 内切圆透明、外侧压暗(closest-side 让 100% = 到最近边的距离 = 内切圆半径)
const MASK_STYLE = {
  background: 'radial-gradient(circle closest-side at center, transparent 99%, rgba(0,0,0,0.45) 100%)',
}

const viewportEl = ref<HTMLElement | null>(null)
const imgEl = ref<HTMLImageElement | null>(null)

const iw = ref(0)
const ih = ref(0)
const base = ref(1) // cover 基准缩放
const zoom = ref(1)
const ox = ref(0)
const oy = ref(0)

const ready = computed(() => iw.value > 0 && ih.value > 0)
const scale = computed(() => base.value * zoom.value)
const dw = computed(() => iw.value * scale.value)
const dh = computed(() => ih.value * scale.value)

function onImageLoad() {
  const el = imgEl.value
  if (!el) return
  iw.value = el.naturalWidth
  ih.value = el.naturalHeight
  base.value = coverScale(iw.value, ih.value, VIEW)
  zoom.value = 1
  const c = centerOffset(dw.value, dh.value, VIEW)
  ox.value = c.ox
  oy.value = c.oy
}

// 缩放时锚定中心并夹紧
watch(zoom, (z, zOld) => {
  if (!ready.value) return
  const next = offsetForZoomAtCenter(ox.value, oy.value, base.value * zOld, base.value * z, iw.value, ih.value, VIEW)
  ox.value = next.ox
  oy.value = next.oy
})

// --- 拖动平移 ---
let dragging = false
let startX = 0
let startY = 0
let startOx = 0
let startOy = 0

function onPointerDown(e: PointerEvent) {
  if (!ready.value) return
  dragging = true
  startX = e.clientX
  startY = e.clientY
  startOx = ox.value
  startOy = oy.value
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!dragging) return
  const next = clampOffset(startOx + (e.clientX - startX), startOy + (e.clientY - startY), dw.value, dh.value, VIEW)
  ox.value = next.ox
  oy.value = next.oy
}

function onPointerUp(e: PointerEvent) {
  dragging = false
  ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
}

function onWheel(e: WheelEvent) {
  if (!ready.value) return
  const delta = -e.deltaY * 0.0015
  zoom.value = Math.min(MAX_ZOOM, Math.max(1, zoom.value + delta))
}

/** 画布是否含透明像素(任一 alpha < 255)。 */
function hasTransparency(ctx: CanvasRenderingContext2D): boolean {
  const data = ctx.getImageData(0, 0, OUTPUT, OUTPUT).data
  for (let i = 3; i < data.length; i += 4) {
    if (data[i]! < 255) return true
  }
  return false
}

function confirm() {
  const el = imgEl.value
  if (!el || !ready.value) return
  const { sx, sy, size } = sourceRect(ox.value, oy.value, scale.value, VIEW)
  const canvas = document.createElement('canvas')
  canvas.width = OUTPUT
  canvas.height = OUTPUT
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(el, sx, sy, size, size, 0, 0, OUTPUT, OUTPUT)
  // JPEG 无 alpha 通道,导出时会把透明像素压成黑色。透明图改用 PNG 保留透明,
  // 不透明图仍用 JPEG(体积更小)。
  const transparent = hasTransparency(ctx)
  const type = transparent ? 'image/png' : 'image/jpeg'
  canvas.toBlob(
    (blob) => {
      if (!blob) return
      const file = new File([blob], transparent ? 'avatar.png' : 'avatar.jpg', { type })
      emit('cropped', file)
      emit('update:modelValue', false)
    },
    type,
    transparent ? undefined : 0.92,
  )
}
</script>
