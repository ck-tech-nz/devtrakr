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
    const anchors = root.querySelectorAll<HTMLAnchorElement>('a.mention-issue, a.external-link')
    anchors.forEach((a) => {
      const match = matchPreviewAnchor(a)
      if (!match) return
      const block = (a.closest(BLOCK_SEL) as HTMLElement | null) ?? a
      const host = document.createElement('div')
      host.className = 'inline-link-card-host'
      block.insertAdjacentElement('afterend', host)
      const vnode = h(InlineLinkCardItem, { match })
      if (instance) vnode.appContext = instance.appContext
      render(vnode, host)
      hosts.push(host)
    })
  }

  watch([containerRef, htmlGetter], () => nextTick(build), { immediate: true, flush: 'post' })
  onBeforeUnmount(cleanup)
}
