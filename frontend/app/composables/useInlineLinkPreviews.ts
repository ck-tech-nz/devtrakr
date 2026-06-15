import { render, h, getCurrentInstance, watch, nextTick, onBeforeUnmount, type Ref } from 'vue'
import InlineLinkCardItem from '~/components/InlineLinkCardItem.vue'
import { matchPreviewAnchor, type PreviewMatch } from '~/composables/useLinkPreview'

const BLOCK_SEL = 'p,li,blockquote,td,th,h1,h2,h3,h4,h5,h6,pre'
// 这些标签后面不能直接接 <div> 兄弟(div 作为 ul/ol/tr 的子元素非法),
// 卡片宿主需上溯到最近的合法块级祖先之后再插入。
const NON_DIV_SIBLING = new Set(['LI', 'TD', 'TH', 'TR', 'THEAD', 'TBODY', 'TFOOT', 'DT', 'DD'])

// 卡片宿主的合法插入参照点:从块级元素上溯,跳过不能接 <div> 兄弟的标签。
function cardInsertAnchor(block: HTMLElement): HTMLElement {
  let el: HTMLElement = block
  while (el.parentElement && NON_DIV_SIBLING.has(el.tagName)) {
    el = el.parentElement
  }
  return el
}

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

    // 每个锚点只匹配一次,匹配结果随锚点带走供后续复用。
    const matched: { a: HTMLAnchorElement; match: PreviewMatch }[] = []
    root.querySelectorAll<HTMLAnchorElement>('a.mention-issue, a.external-link').forEach((a) => {
      const match = matchPreviewAnchor(a)
      if (match) matched.push({ a, match })
    })
    if (!matched.length) return

    const byBlock = new Map<HTMLElement, { a: HTMLAnchorElement; match: PreviewMatch }[]>()
    for (const item of matched) {
      const block = (item.a.closest(BLOCK_SEL) as HTMLElement | null) ?? item.a
      const list = byBlock.get(block) ?? []
      list.push(item)
      byBlock.set(block, list)
    }

    // 同一插入参照点(如同一 <ul>)下多块卡片按文档顺序续接,避免逆序。
    const lastHostByAnchor = new Map<Element, Element>()
    for (const [block, blockItems] of byBlock) {
      const blockText = (block.textContent || '').replace(/\s/g, '')
      const refsText = blockItems.map((it) => it.a.textContent || '').join('').replace(/\s/g, '')
      if (blockText === refsText) {
        block.style.display = 'none' // 整块只是引用 → 连块一起隐藏(无空行)
      } else {
        blockItems.forEach((it) => { it.a.style.display = 'none' }) // 夹在文字中 → 只隐藏 chip
      }
      const target = cardInsertAnchor(block)
      for (const { match } of blockItems) {
        const host = document.createElement('div')
        host.className = 'inline-link-card-host'
        const prev = lastHostByAnchor.get(target) ?? target
        prev.insertAdjacentElement('afterend', host)
        lastHostByAnchor.set(target, host)
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
