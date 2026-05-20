<template>
  <button
    ref="btn"
    type="button"
    class="liquid-glass"
    :style="filterStyle"
  >
    <slot />
    <svg
      aria-hidden="true"
      class="liquid-glass-svg"
      width="0"
      height="0"
    >
      <defs>
        <filter
          :id="filterId"
          filterUnits="userSpaceOnUse"
          color-interpolation-filters="sRGB"
          x="0"
          y="0"
          :width="size.w"
          :height="size.h"
        >
          <feImage
            v-if="mapHref"
            :href="mapHref"
            :width="size.w"
            :height="size.h"
            preserveAspectRatio="none"
          />
          <feDisplacementMap
            in="SourceGraphic"
            :scale="scale"
            x-channel-selector="R"
            y-channel-selector="G"
          />
        </filter>
      </defs>
    </svg>
  </button>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'

const props = withDefaults(defineProps<{
  bezelDepth?: number   // 边缘折射强度 (0..1). 默认刻意调弱: 太强会把字符采样到错位, 看着像翻转
  bezelWidth?: number   // 边缘折射作用区域宽度 (0..0.5, UV 单位). 只在最外圈薄薄一层折射
  blur?: number         // 叠加的高斯模糊 px
  saturation?: number   // 背景饱和度增强 (%)
}>(), {
  bezelDepth: 0.1,
  bezelWidth: 0.08,
  blur: 0.4,
  saturation: 140,
})

const btn = ref<HTMLButtonElement | null>(null)
const filterId = `lg-${Math.random().toString(36).slice(2, 10)}`
const size = reactive({ w: 1, h: 1 })
const mapHref = ref('')
const scale = ref(0)

const filterStyle = computed(() => {
  const url = mapHref.value ? `url(#${filterId}) ` : ''
  const filter = `${url}blur(${props.blur}px) saturate(${props.saturation}%)`
  return { backdropFilter: filter, WebkitBackdropFilter: filter }
})

function smoothStep(a: number, b: number, t: number) {
  const x = Math.max(0, Math.min(1, (t - a) / (b - a)))
  return x * x * (3 - 2 * x)
}

// 圆角矩形 SDF — 单位是按钮尺寸的一半 (即 -0.5..0.5 UV 空间)
// halfW/halfH 是矩形半边长, r 是圆角半径; 返回到边的有符号距离 (内为负, 外为正)
function roundedRectSDF(x: number, y: number, halfW: number, halfH: number, r: number) {
  const qx = Math.abs(x) - halfW + r
  const qy = Math.abs(y) - halfH + r
  return Math.min(Math.max(qx, qy), 0) + Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) - r
}

function generate() {
  if (!btn.value) return
  const rect = btn.value.getBoundingClientRect()
  const w = Math.max(1, Math.round(rect.width))
  const h = Math.max(1, Math.round(rect.height))
  size.w = w
  size.h = h

  // CSS 圆角 (px) → 转 UV 比例 (相对 min(w,h)). border-radius:9999px 实际为 h/2 的胶囊形
  const cssRadius = parseFloat(getComputedStyle(btn.value).borderTopLeftRadius) || 0
  const rUV = Math.min(cssRadius / Math.min(w, h), 0.5)

  const cvs = document.createElement('canvas')
  cvs.width = w
  cvs.height = h
  const ctx = cvs.getContext('2d')
  if (!ctx) return
  const img = ctx.createImageData(w, h)

  // 第一遍: 算每个像素的位移 (像素单位), 同时记录 maxScale 以归一化到 0..255
  const rawDx = new Float32Array(w * h)
  const rawDy = new Float32Array(w * h)
  let maxScale = 0

  // 用 min(w,h) 把 SDF 调成各向同性 — 胶囊形按钮宽高差很大, 直接用 0.5 半边长会让宽边缘的位移过强
  const aspectScale = Math.min(w, h) / Math.max(w, h)
  const halfW = w >= h ? 0.5 : 0.5 * aspectScale
  const halfH = h >= w ? 0.5 : 0.5 * aspectScale

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      // 把像素坐标映射到 -0.5..0.5 UV 空间; 长边方向保留 0.5, 短边按 aspect 缩放
      const ix = (x / w - 0.5) * (w >= h ? 1 : aspectScale)
      const iy = (y / h - 0.5) * (h >= w ? 1 : aspectScale)
      const dist = roundedRectSDF(ix, iy, halfW, halfH, rUV * aspectScale)
      // dist: 圆心区域 ~-0.5, 边上 0; 在 [-bezelWidth, 0] 内 smoothstep 出 0..1 边缘掩码
      const edgeT = smoothStep(-props.bezelWidth, 0, dist)
      const strength = edgeT * props.bezelDepth
      // 折射方向: 把纹理向中心拉 (玻璃边缘把光线弯向法线)
      const dx = -ix * strength * w
      const dy = -iy * strength * h
      const idx = y * w + x
      rawDx[idx] = dx
      rawDy[idx] = dy
      const a = Math.max(Math.abs(dx), Math.abs(dy))
      if (a > maxScale) maxScale = a
    }
  }

  maxScale = Math.max(maxScale, 0.001)

  // 第二遍: 把位移编码进 RG 通道. feDisplacementMap 解码: dx = scale * (R - 0.5)
  // 我们存 R = dx / maxScale * 0.5 + 0.5, 所以 scale 取 2 * maxScale 才能还原 dx
  for (let i = 0; i < w * h; i++) {
    const r = (rawDx[i] / maxScale) * 0.5 + 0.5
    const g = (rawDy[i] / maxScale) * 0.5 + 0.5
    img.data[i * 4] = r * 255
    img.data[i * 4 + 1] = g * 255
    img.data[i * 4 + 2] = 0
    img.data[i * 4 + 3] = 255
  }

  ctx.putImageData(img, 0, 0)
  mapHref.value = cvs.toDataURL()
  scale.value = maxScale * 2
}

let ro: ResizeObserver | null = null

onMounted(() => {
  generate()
  if (typeof ResizeObserver !== 'undefined' && btn.value) {
    ro = new ResizeObserver(() => generate())
    ro.observe(btn.value)
  }
})

onBeforeUnmount(() => {
  ro?.disconnect()
})

watch(() => [props.bezelDepth, props.bezelWidth], generate)
</script>

<style scoped>
.liquid-glass-svg {
  position: absolute;
  width: 0;
  height: 0;
  pointer-events: none;
}
</style>
