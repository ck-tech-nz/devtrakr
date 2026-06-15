import { render, h, getCurrentInstance, watch, nextTick, onBeforeUnmount, type Ref } from 'vue'
import InlineLinkCardItem from '~/components/InlineLinkCardItem.vue'
import { matchPreviewAnchor } from '~/composables/useLinkPreview'

const BLOCK_SEL = 'p,li,blockquote,td,th,h1,h2,h3,h4,h5,h6,pre'

// 渲染后在每个可预览锚点所在块级元素之后挂载一张内联卡片(InlineLinkCardItem),
// 复用当前组件的 Nuxt app context;内容变更或卸载时清理已挂载实例。
export function useInlineLinkPreviews(containerRef: Ref<HTMLElement | null>, htmlGetter: () => string) {
  const instance = getCurrentInstance()
  const hosts: HTMLElement[] = []

  function cleanup() {
    for (const host of hosts.splice(0)) {
      render(null, host)
      host.remove()
    }
  }

  function build() {
    cleanup()
    const root = containerRef.value
    if (!root) return
    const anchors = Array.from(root.querySelectorAll<HTMLAnchorElement>('a.mention-issue, a.external-link'))
      .filter((a) => matchPreviewAnchor(a))
    if (!anchors.length) return

    const byBlock = new Map<HTMLElement, HTMLAnchorElement[]>()
    for (const a of anchors) {
      const block = (a.closest(BLOCK_SEL) as HTMLElement | null) ?? a
      const list = byBlock.get(block) ?? []
      list.push(a)
      byBlock.set(block, list)
    }

    for (const [block, blockAnchors] of byBlock) {
      const blockText = (block.textContent || '').replace(/\s/g, '')
      const refsText = blockAnchors.map((a) => a.textContent || '').join('').replace(/\s/g, '')
      if (blockText === refsText) {
        block.style.display = 'none' // 整块只是引用 → 连块一起隐藏(无空行)
      } else {
        blockAnchors.forEach((a) => { a.style.display = 'none' }) // 夹在文字中 → 只隐藏 chip
      }
      let insertAfter: Element = block
      for (const a of blockAnchors) {
        const match = matchPreviewAnchor(a)!
        const host = document.createElement('div')
        host.className = 'inline-link-card-host'
        insertAfter.insertAdjacentElement('afterend', host)
        insertAfter = host
        const vnode = h(InlineLinkCardItem, { match })
        if (instance) vnode.appContext = instance.appContext
        render(vnode, host)
        hosts.push(host)
      }
    }
  }

  watch([containerRef, htmlGetter], () => nextTick(build), { immediate: true, flush: 'post' })
  onBeforeUnmount(cleanup)
}
