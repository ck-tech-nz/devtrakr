<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import Filter from '~/components/liquid-glass/Filter.vue'

// Types
interface NavItem {
  id: string
  label: string
  icon?: string // SVG path content or iconify class name (e.g. "i-heroicons-xxx")
  badge?: number // 可选:在图标右上角显示的未读数(>0 才渲染)
}

// Props
const props = withDefaults(defineProps<{
  modelValue: string
  items: NavItem[]
  size?: 'small' | 'medium' | 'large' | 'XL'
  disabled?: boolean
  itemWidthOverride?: number
  // Glass customization props
  specularOpacity?: number
  specularSaturation?: number
  blur?: number
  baseRefraction?: number
  color?: string
  alwaysShowGlass?: boolean
}>(), {
  modelValue: '',
  size: 'medium',
  disabled: false,
  itemWidthOverride: 0,
  specularOpacity: 0.4,
  specularSaturation: 10,
  blur: 0, // Default blur
  baseRefraction: -0.4,
  color: 'red',
  alwaysShowGlass: false,
})

// Emits
const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// Size presets
const sizePresets = {
  small: {
    height: 42,
    itemWidth: 60,
    thumbHeight: 38,
    bezelWidth: 6,
    bazelWidthBg: 15,
    glassThickness: 100,
    fontSize: '0.5rem',
    iconSize: 16,
    thumbScale: 1.4,
    thumbScaleY: 1.2,
  },
  medium: {
    height: 58,
    itemWidth: 85,
    thumbHeight: 52,
    bezelWidth: 8,
    bazelWidthBg: 30,
    glassThickness: 110,
    fontSize: '0.7rem',
    iconSize: 20,
    thumbScale: 1.3,
    thumbScaleY: 1.1,
  },
  large: {
    height: 58,
    itemWidth: 100,
    thumbHeight: 44,
    bezelWidth: 10,
    bazelWidthBg: 25,
    glassThickness: 110,
    fontSize: '0.6rem',
    iconSize: 20,
    thumbScale: 1.38,
    thumbScaleY: 1.18,
  },
  XL: {
    height: 80,
    itemWidth: 120,
    thumbHeight: 72,
    bezelWidth: 15,
    bazelWidthBg: 30,
    glassThickness: 160,
    fontSize: '0.8rem',
    iconSize: 28,
    thumbScale: 1.3,
    thumbScaleY: 1.25,
  },
}

// Computed dimensions
const dimensions = computed(() => sizePresets[props.size])
const sliderHeight = computed(() => dimensions.value.height)
const itemWidth = computed(() => props.itemWidthOverride > 0 ? props.itemWidthOverride : dimensions.value.itemWidth)
const sliderWidth = computed(() => itemWidth.value * props.items.length)
const thumbWidth = computed(() => itemWidth.value - 16)
const thumbHeight = computed(() => dimensions.value.thumbHeight)
const thumbRadius = computed(() => thumbHeight.value / 2)
const bezelWidth = computed(() => dimensions.value.bezelWidth)
const bazelWidthBg = computed(() => dimensions.value.bazelWidthBg)
const glassThickness = computed(() => dimensions.value.glassThickness)

// Generate unique filter ID
const filterId = `liquid-glass-navbar-${Math.random().toString(36).substr(2, 9)}`
const bgFilterId = `liquid-glass-navbar-bg-${Math.random().toString(36).substr(2, 9)}`

// Constants for animation
const THUMB_REST_SCALE = 1
const THUMB_ACTIVE_SCALE = dimensions.value.thumbScale
const THUMB_ACTIVE_SCALE_Y = dimensions.value.thumbScaleY

// Internal state
const internalValue = ref(props.modelValue)
const selectedIndex = computed(() => props.items.findIndex(item => item.id === internalValue.value))
const hasSelection = computed(() => selectedIndex.value !== -1)
const pointerDown = ref(0)
const initialPointerX = ref(0)
const initialThumbX = ref(0) // Thumb position at start of drag
const currentThumbX = ref(0) // Current visual position (px)
const isMounted = ref(false)

// iOS Safari 不支持 backdrop-filter: url(#svgFilter)，需要 CSS fallback
const useCssFallback = ref(false)

onMounted(() => {
  isMounted.value = true
  // 检测是否为移动端或不支持 SVG backdrop-filter 的浏览器
  const ua = navigator.userAgent
  const isIOS = /iPad|iPhone|iPod/.test(ua)
  const isAndroid = /Android/.test(ua)
  useCssFallback.value = isIOS || isAndroid
})

// Initialize position
watch(() => props.modelValue, (newVal) => {
  internalValue.value = newVal
  const index = props.items.findIndex(item => item.id === newVal)
  // Only snap on initial load. Subsequent updates should animate via selectedIndex watch.
  if (index !== -1 && pointerDown.value === 0 && !isMounted.value) {
    targetThumbX(index)
  }
}, { immediate: true })

function targetThumbX(index: number) {
   const centerOffset = (itemWidth.value - thumbWidth.value) / 2
   const target = index * itemWidth.value + centerOffset
   currentThumbX.value = target
}

// Physics Loop
const isAnimating = ref(false)
let animationFrame: number

// Glass visibility with fast fadeout (280ms max)
const glassVisible = ref(false)
let hideGlassTimeout: ReturnType<typeof setTimeout> | null = null

// Wobble state
const wobbleScaleX = ref(1)
const wobbleScaleY = ref(1)
const velocity = ref(0) // Track velocity for wobble

function updatePhysics() {
  if (pointerDown.value > 0) {
     // Reset wobble when dragging manually
     wobbleScaleX.value = lerp(wobbleScaleX.value, 1, 0.2)
     wobbleScaleY.value = lerp(wobbleScaleY.value, 1, 0.2)
     return 
  }

  const index = selectedIndex.value
  const centerOffset = (itemWidth.value - thumbWidth.value) / 2
  const dest = (index === -1 ? 0 : index) * itemWidth.value + centerOffset
  
  // Spring-ish lerp for position
  const diff = dest - currentThumbX.value
  const newVelocity = diff * 0.5
  
  // Update position
  currentThumbX.value += newVelocity
  
  // Calculate Wobble (Squash & Stretch)
  // Higher velocity = more stretch in X, squash in Y
  // Max stretch 1.3, min squash 0.8
  const speed = Math.abs(newVelocity)
  const stretchFactor = 1 + Math.min(speed * 0.02, 0.5) // Factor to add to X
  const squashFactor = 1 / stretchFactor // Preserve area/volume roughly
  
  // Lerp wobble scales towards target
  // We use a separate springiness for wobble to make it "jelly" like
  // It should react fast to speed, but settle dampened.
  wobbleScaleX.value = lerp(wobbleScaleX.value, stretchFactor, 0.2)
  wobbleScaleY.value = lerp(wobbleScaleY.value, squashFactor, 0.2)
  
  const isSettled = Math.abs(diff) < 0.1 && Math.abs(wobbleScaleX.value - 1) < 0.01

  if (isSettled) {
    currentThumbX.value = dest
    wobbleScaleX.value = 1
    wobbleScaleY.value = 1
    isAnimating.value = false
    return
  }
  
  animationFrame = requestAnimationFrame(updatePhysics)
}

function lerp(start: number, end: number, t: number) {
  return start * (1 - t) + end * t
}

watch(selectedIndex, () => {
  if (pointerDown.value === 0) {
     isAnimating.value = true
     cancelAnimationFrame(animationFrame)
     updatePhysics()
  }
})

// Visual Computed Props (Matching Switch.vue logic)
// Glass effect is controlled by glassVisible (fast fadeout) not isAnimating
// If alwaysShowGlass is true, glass is always visible
const isActive = computed(() => props.alwaysShowGlass || pointerDown.value > 0.5 || glassVisible.value)

// Scale Effect (Base Scale * Wobble)
const thumbScale = computed(() => {
  const base = THUMB_REST_SCALE + (THUMB_ACTIVE_SCALE - THUMB_REST_SCALE) * (isActive.value ? 1 : 0)
  return base * wobbleScaleX.value
})

const thumbScaleY = computed(() => {
  const base = THUMB_REST_SCALE + (THUMB_ACTIVE_SCALE_Y - THUMB_REST_SCALE) * (isActive.value ? 1 : 0)
  return base * wobbleScaleY.value
})

// Opacity Effect (White -> Glass)
// Rest: 1 (Opaque White). Active: 0.1 (Transparent Glass).
const backgroundOpacity = isActive.value

// Scale Ratio for Filter (Distortion intensity)
// Use props.baseRefraction as the base
// Scale Ratio for Filter (Distortion intensity)
// Use props.baseRefraction as the base
const scaleRatio = computed(() => 0.1)


// Event handlers
const handlePointerDown = (e: MouseEvent | TouchEvent) => {
  if (props.disabled) return
  
  const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
  
  pointerDown.value = 1
  initialPointerX.value = clientX
  initialThumbX.value = currentThumbX.value
  
  // Show glass immediately, cancel any pending hide
  if (hideGlassTimeout) clearTimeout(hideGlassTimeout)
  glassVisible.value = true
  
  isAnimating.value = false
  cancelAnimationFrame(animationFrame)
  
  // Add window listeners for drag/up
  window.addEventListener('mousemove', handlePointerMove)
  window.addEventListener('touchmove', handlePointerMove)
  window.addEventListener('mouseup', handlePointerUp)
  window.addEventListener('touchend', handlePointerUp)
}

const handlePointerMove = (e: PointerEvent | TouchEvent | MouseEvent) => {
  if (pointerDown.value === 0) return
  
  const clientX = 'touches' in e 
    ? e.touches[0].clientX 
    : e.clientX
  
  const delta = clientX - initialPointerX.value
  let newPos = initialThumbX.value + delta
  
  // Constrain with elasticity
  const maxPos = sliderWidth.value - thumbWidth.value - (itemWidth.value - thumbWidth.value)/2
  const minPos = (itemWidth.value - thumbWidth.value)/2
  
  // Damping at edges
  if (newPos < minPos) {
      const overflow = minPos - newPos
      newPos = minPos - (overflow / 3) // 1/3 damping
  }
  if (newPos > maxPos) {
      const overflow = newPos - maxPos
      newPos = maxPos + (overflow / 3)
  }
  
  // Manual Drag Velocity to add wobble during drag
  // Simple difference
  const velocity = newPos - currentThumbX.value
  const speed = Math.abs(velocity)
  const stretchFactor = 1 + Math.min(speed * 0.05, 0.4)
  const squashFactor = 1 / stretchFactor
  
  wobbleScaleX.value = lerp(wobbleScaleX.value, stretchFactor, 0.2)
  wobbleScaleY.value = lerp(wobbleScaleY.value, squashFactor, 0.2)

  currentThumbX.value = newPos
}

const handlePointerUp = (e: PointerEvent | TouchEvent | MouseEvent) => {
  pointerDown.value = 0
  
  const clientX = 'changedTouches' in e 
    ? e.changedTouches[0].clientX 
    : e.clientX
    
  // Cleanup listeners
  window.removeEventListener('mousemove', handlePointerMove)
  window.removeEventListener('touchmove', handlePointerMove)
  window.removeEventListener('mouseup', handlePointerUp)
  window.removeEventListener('touchend', handlePointerUp)

  // Determine selection
  const thumbCenter = currentThumbX.value + thumbWidth.value / 2
  let index = Math.floor(thumbCenter / itemWidth.value)
  index = Math.max(0, Math.min(index, props.items.length - 1))
  
  const isClick = Math.abs(clientX - initialPointerX.value) < 5

  const newItem = props.items[index]
  if (newItem && (isClick || newItem.id !== internalValue.value)) {
    internalValue.value = newItem.id
    emit('update:modelValue', newItem.id)
  }
  // Even if value didn't change, we need to snap back
  isAnimating.value = true
  updatePhysics()
  
  // Hide glass quickly (280ms) regardless of animation state
  hideGlassTimeout = setTimeout(() => {
    glassVisible.value = false
  }, 280)
}

// 触屏 tap 会先派发 touchstart,浏览器随后再合成一次 mousedown(兼容事件)。
// 本函数同时绑定到 touchstart 与 mousedown,若不去重,一次 tap 会触发两次 ——
// 对「开关」类命令 Tab(如消息面板)会被开→关而闪现。touchstart 后短时间内吞掉紧随的 mousedown。
let suppressMouse = false
const handleItemClick = (item: NavItem, e?: Event) => {
    if (e?.type === 'touchstart') {
      suppressMouse = true
      setTimeout(() => { suppressMouse = false }, 700)
    } else if (e?.type === 'mousedown' && suppressMouse) {
      return
    }
    internalValue.value = item.id
    emit('update:modelValue', item.id)

    // Show glass effect briefly when clicking items
    if (hideGlassTimeout) clearTimeout(hideGlassTimeout)
    glassVisible.value = true
    hideGlassTimeout = setTimeout(() => {
      glassVisible.value = false
    }, 280)
}

onUnmounted(() => {
  cancelAnimationFrame(animationFrame)
  if (hideGlassTimeout) clearTimeout(hideGlassTimeout)
  window.removeEventListener('mousemove', handlePointerMove)
  window.removeEventListener('touchmove', handlePointerMove)
  window.removeEventListener('mouseup', handlePointerUp)
  window.removeEventListener('touchend', handlePointerUp)
})

</script>

<template>
  <div
    class="inline-block select-none touch-none"
    :class="{ 'opacity-50 cursor-not-allowed': disabled }"
    :style="{transform: isActive ? 'scale(1.05)' : 'scale(1)',
      transition: 'transform 0.1s ease-out',
    }"
    
  > 
  <!-- Removed @mousemove here, using window listener for drag -->
    <div
      class="relative"
      :style="{
        width: `${sliderWidth}px`,
        height: `${sliderHeight}px`,
        borderRadius: `${sliderHeight / 2}px`,
      }"
    >
      <!-- Background Filter -->
      <Filter
        :id="bgFilterId"
        :width="sliderWidth"
        :height="sliderHeight"
        :radius="sliderHeight / 2"
        :bezel-width="bazelWidthBg"
        :glass-thickness="190"
        :refractive-index="1.3"
        bezel-type="convex_squircle"
        shape="pill"
        :blur="2"
        :scale-ratio="0.4"
        :specular-opacity="1"
        :specular-saturation="19"
      />

      <!-- Glass Background -->
      <div
         class="absolute inset-0 bg-[var(--glass-rgb)]/[var(--glass-bg-alpha)]"
         :style="{
            borderRadius: `${sliderHeight / 2}px`,
            backdropFilter: useCssFallback
              ? 'blur(16px) saturate(180%)'
              : `url(#${bgFilterId}) blur(16px)`,
            WebkitBackdropFilter: useCssFallback
              ? 'blur(16px) saturate(180%)'
              : undefined,
            boxShadow: `0 4px 20px rgba(0, 0, 0, 0.12), inset 0 0.5px 0 rgba(255,255,255,0.5)`,
            border: `0.5px solid rgba(0,0,0,0.08)`,
         }"
      ></div>
      
      <!-- Click Targets (Z-Index 30: Below Thumb but above background) -->
      <div class="absolute inset-0 flex z-30">
          <div
             v-for="item in items"
             :key="item.id"
             class="h-full cursor-pointer"
             :style="{ width: `${itemWidth}px` }"
             @mousedown="handleItemClick(item, $event)"
             @touchstart.passive="handleItemClick(item, $event)"
          ></div>
      </div>

     <!-- The Glass/White Thumb (Z-Index 40: Above Click Targets, Below Text) -->
      <div
        class="absolute cursor-pointer transition-all duration-[100ms] ease-out z-40"
        :style="{
          height: `${thumbHeight}px`,
          width: `${thumbWidth}px`,
          transform: `translateX(${currentThumbX}px) translateY(-50%) scale(${hasSelection ? thumbScale : 0}) scaleY(${hasSelection ? thumbScaleY : 0})`,
          opacity: hasSelection ? 1 : 0,
          top: `${sliderHeight / 2}px`,
          left: 0,
          pointerEvents: hasSelection ? 'auto' : 'none',
        }"
        @mousedown="handlePointerDown"
        @touchstart.stop="handlePointerDown" 
      >
        <!-- Filter/Visuals -->
        <div class="relative w-full h-full">
             <Filter
                :id="filterId"
                :width="thumbWidth"
                :height="thumbHeight"
                :radius="thumbRadius"
                :bezel-width="bezelWidth"
                :glass-thickness="glassThickness"
                :refractive-index="1.5"
                bezel-type="convex_circle"
                shape="pill"
                :blur="blur"
                :scale-ratio="scaleRatio"
                :specular-opacity="specularOpacity"
                :specular-saturation="specularSaturation"
              />
              
              <!-- Thumb Body -->
              <div class="absolute inset-0"
                   :class="!isActive ? 'bg-black/6 dark:bg-white/10 shadow-sm' : ''"
                   :style="{
                      borderRadius: `${thumbRadius}px`,
                      backdropFilter: isActive
                        ? (useCssFallback ? 'blur(12px) saturate(150%) brightness(1.05)' : `url(#${filterId})`)
                        : 'none',
                      WebkitBackdropFilter: isActive && useCssFallback
                        ? 'blur(12px) saturate(150%) brightness(1.05)'
                        : undefined,
                      transition: 'background-color 0.15s ease, box-shadow 0.15s ease, backdrop-filter 0.15s ease',
                   }"
              ></div>
        </div>
      </div>

      <!-- Items Layer (Dynamic Z-Index) -->
      <!-- At Rest: z-50 (Above Thumb z-40) because Thumb is Opaque White -->
      <!-- Dragging: z-20 (Below Thumb z-40) because Thumb is Glass and we want distortion -->
      <div 
         class="absolute inset-0 flex items-center justify-between pointer-events-none" 
         :class="isActive ? 'z-20' : 'z-50'"
         :style="{ gap: '0px' }"
      >
         <div 
            v-for="item in items" 
            :key="item.id"
            class="flex flex-col items-center justify-center transition-all duration-100"
            :style="{
               width: `${itemWidth}px`,
               height: '100%',
               opacity: !hasSelection ? 0.85 : (internalValue === item.id ? 1 : 0.85),
               transform: internalValue === item.id && hasSelection ? 'scale(1.05)' : 'scale(1)',
            }"
         >
             <span v-if="item.icon" class="relative mb-1">
               <UIcon
                 :name="item.icon"
                 :style="{
                  color: internalValue === item.id ? `${props.color}` : undefined,
                  width: `${dimensions.iconSize}px`,
                  height: `${dimensions.iconSize}px`,
                 }"
                 class="block transition-colors"
               />
               <span
                 v-if="item.badge && item.badge > 0"
                 class="absolute -top-1.5 -right-2 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-semibold leading-none flex items-center justify-center"
               >{{ item.badge > 99 ? '99+' : item.badge }}</span>
             </span>
             <span
               class="leading-none text-center truncate transition-colors"
               :class="internalValue === item.id ? 'font-semibold' : 'font-medium text-gray-500 dark:text-gray-400'"
               :style="{ fontSize: dimensions.fontSize, color: internalValue === item.id ? `${props.color}` : undefined }"
             >{{ item.label }}</span>
         </div>
      </div>
    </div>
  </div>
</template>
