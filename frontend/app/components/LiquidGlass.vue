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
  bezelDepth?: number   // 边缘最大位移强度. 短边 (min(w,h)) 的比例 — 0.16 = 短边 16%, 约 6px on 37px 胶囊
  bezelWidth?: number   // 折射作用区域宽度. 短边比例 — 0.12 = 短边 12%, 约 4-5px 边缘带
  blur?: number         // 叠加的高斯模糊 px
  saturation?: number   // 背景饱和度增强 (%)
}>(), {
  bezelDepth: 0.16,
  bezelWidth: 0.2,
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

// 圆角矩形 SDF — 像素空间. halfInnerW/halfInnerH 是 (按钮半宽 - 圆角半径) 等, r 是圆角半径
// 返回到边的有符号距离 (内为负, 外为正), 单位是像素
function roundedRectSDF(px: number, py: number, halfInnerW: number, halfInnerH: number, r: number) {
  const qx = Math.abs(px) - halfInnerW
  const qy = Math.abs(py) - halfInnerH
  return Math.min(Math.max(qx, qy), 0) + Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) - r
}

function generate() {
  if (!btn.value) return
  const rect = btn.value.getBoundingClientRect()
  const w = Math.max(1, Math.round(rect.width))
  const h = Math.max(1, Math.round(rect.height))
  size.w = w
  size.h = h

  const cssRadius = parseFloat(getComputedStyle(btn.value).borderTopLeftRadius) || 0
  const radius = Math.min(cssRadius, w / 2, h / 2)
  // SDF 用的内矩形 (圆角扣除后) 的半边长 — pill 形式 halfInnerH 会接近 0
  const halfInnerW = w / 2 - radius
  const halfInnerH = h / 2 - radius

  // bezel 区域宽度 + 最大位移 — 都按短边比例算, 保证上下左右一致
  const minDim = Math.min(w, h)
  const bezelPx = Math.max(1, minDim * props.bezelWidth)
  const displPx = minDim * props.bezelDepth

  const cvs = document.createElement('canvas')
  cvs.width = w
  cvs.height = h
  const ctx = cvs.getContext('2d')
  if (!ctx) return
  const img = ctx.createImageData(w, h)

  const rawDx = new Float32Array(w * h)
  const rawDy = new Float32Array(w * h)
  let maxScale = 0

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      // 中心相对像素坐标 (+ 0.5 让坐标落在像素中心)
      const px = x + 0.5 - w / 2
      const py = y + 0.5 - h / 2
      const qx = Math.abs(px) - halfInnerW
      const qy = Math.abs(py) - halfInnerH
      const dist = Math.min(Math.max(qx, qy), 0) + Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) - radius

      // edgeT: bezel 区掩码, 0 (深处) → 1 (临边)
      const strength = smoothStep(-bezelPx, 0, dist)

      // 外法线方向 — 哪条边/角最近, 法线就指那里. 这样上下左右位移幅度一致, 不会因 aspect 失衡
      let nx = 0
      let ny = 0
      if (qx > 0 && qy > 0) {
        // 在四个圆角的弧带, 法线沿 (qx, qy) 方向
        const len = Math.hypot(qx, qy) || 1
        nx = (Math.sign(px) * qx) / len
        ny = (Math.sign(py) * qy) / len
      } else if (qx > qy) {
        // 靠近左右长边
        nx = Math.sign(px)
        ny = 0
      } else {
        // 靠近上下短边
        nx = 0
        ny = Math.sign(py)
      }

      // 折射方向: 沿法线向内拉 (像凸透镜把外部光线汇向中心)
      // 反向 = 朝外 (撑开式) — 这里选向内, Apple 风格更像凸透镜
      const displ = strength * displPx
      const dx = -nx * displ
      const dy = -ny * displ

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
