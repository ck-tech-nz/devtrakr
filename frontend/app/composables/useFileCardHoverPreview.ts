import type { Ref } from 'vue'

export type FileHoverKind = 'md' | 'html'

export interface FileHoverState {
  visible: boolean
  loading: boolean
  kind: FileHoverKind
  content: string   // 渲染后的 markdown HTML (kind==='md')
  rawHtml: string   // 原始 HTML 源码,用于 iframe srcdoc (kind==='html')
  tooLarge: boolean // HTML 超过内联渲染上限
  // 定位(视口坐标,position:fixed)。放在卡片下方时设 top、上方时设 bottom,
  // 让弹层紧贴卡片对应边缘;maxHeight 按所在侧可用空间收口。
  top: number | null
  bottom: number | null
  left: number
  maxHeight: number
  url: string
  filename: string
}

const MD_FETCH_CAP = 200 * 1024          // 200KB,markdown 可安全截断
const HTML_RENDER_CAP = 2 * 1024 * 1024  // 2MB,超过则不内联渲染(截断会破坏标签)
const FETCH_ERROR = '__FETCH_ERROR__'

/**
 * 给已渲染的 markdown 容器内的文件卡片绑定悬停预览:
 *  - `.md-file-text` 且 href 以 .md 结尾  → 拉取文本、markdown 渲染
 *  - `.md-file-html` 且 href 以 .html/.htm 结尾 → 拉取文本、沙箱 iframe 渲染
 * 取内容沿用跨源 fetch(MinIO 公网 URL,CORS 已放行),不依赖公网 URL 的 content-type。
 */
export function useFileCardHoverPreview(
  rootRef: Ref<HTMLElement | null>,
  htmlGetter: () => string,
  options: { enabled?: () => boolean } = {},
) {
  const { md } = useMentionMarkdown()
  const enabled = options.enabled ?? (() => true)

  const hover = ref<FileHoverState>({
    visible: false, loading: false, kind: 'md',
    content: '', rawHtml: '', tooLarge: false,
    top: 0, bottom: null, left: 0, maxHeight: 0, url: '', filename: '',
  })

  const cache = new Map<string, string>() // url -> 已拉取文本(按 kind 的上限封顶)
  let showTimer: ReturnType<typeof setTimeout> | null = null
  let hideTimer: ReturnType<typeof setTimeout> | null = null

  // 拉取文本,最多读到 ceiling 个字符(用于判断截断/过大);单个 url 的 kind 固定,ceiling 也固定。
  async function fetchText(url: string, ceiling: number): Promise<string> {
    if (cache.has(url)) return cache.get(url)!
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const reader = res.body?.getReader()
      if (!reader) {
        const text = await res.text()
        cache.set(url, text)
        return text
      }
      const decoder = new TextDecoder()
      let received = ''
      while (received.length < ceiling) {
        const { done, value } = await reader.read()
        if (done) break
        received += decoder.decode(value, { stream: true })
      }
      // 命中上限后提前结束读取:取消 reader,避免浏览器继续在后台缓冲剩余响应体
      await reader.cancel()
      received += decoder.decode() // flush 解码器尾部残留的多字节字符
      cache.set(url, received)
      return received
    } catch {
      cache.set(url, FETCH_ERROR)
      return FETCH_ERROR
    }
  }

  function kindFor(el: HTMLAnchorElement): FileHoverKind | null {
    const href = (el.href || '').toLowerCase().split('?')[0]!.split('#')[0]!
    if (el.classList.contains('md-file-text') && href.endsWith('.md')) return 'md'
    if (el.classList.contains('md-file-html') && (href.endsWith('.html') || href.endsWith('.htm'))) return 'html'
    return null
  }

  function show(el: HTMLAnchorElement, kind: FileHoverKind) {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
    if (showTimer) clearTimeout(showTimer)
    const ceiling = kind === 'md' ? MD_FETCH_CAP : HTML_RENDER_CAP
    // 预取:在弹层出现前就开始拉,500ms 内点击下载的用户不会产生无用 UI。
    void fetchText(el.href, ceiling)
    showTimer = setTimeout(async () => {
      // 视口坐标(position:fixed)。选可用空间更大的一侧放置,并紧贴卡片对应边缘:
      // 下方 → top 贴卡片底边;上方 → bottom 贴卡片顶边。高度按该侧可用空间收口,
      // 不再预留固定高度,避免弹层与卡片之间出现空隙。
      const rect = el.getBoundingClientRect()
      const margin = 8
      const gap = 4
      const popupWidth = Math.min(window.innerWidth - 32, 720)
      const cap = Math.min(window.innerHeight * 0.7, 640)
      const spaceBelow = window.innerHeight - rect.bottom - margin
      const spaceAbove = rect.top - margin
      const placeBelow = spaceBelow >= spaceAbove
      const left = Math.max(margin, Math.min(rect.left, window.innerWidth - popupWidth - margin))
      const maxHeight = Math.max(160, Math.min(cap, (placeBelow ? spaceBelow : spaceAbove) - gap))
      const filename = el.getAttribute('download') || (el.textContent || '').trim() || el.href.split('/').pop() || 'file'
      hover.value = {
        visible: true, loading: true, kind,
        content: '', rawHtml: '', tooLarge: false,
        top: placeBelow ? rect.bottom + gap : null,
        bottom: placeBelow ? null : window.innerHeight - rect.top + gap,
        left, maxHeight,
        url: el.href, filename,
      }
      const text = await fetchText(el.href, ceiling)
      if (!hover.value.visible) return
      hover.value.loading = false
      if (text === FETCH_ERROR) {
        hover.value.kind = 'md'
        hover.value.content = md.render('加载失败')
        return
      }
      if (kind === 'md') {
        const capped = text.length >= MD_FETCH_CAP ? text.slice(0, MD_FETCH_CAP) + '\n\n...(已截断)' : text
        hover.value.content = md.render(capped)
      } else if (text.length >= HTML_RENDER_CAP) {
        hover.value.tooLarge = true
      } else {
        hover.value.rawHtml = text
      }
    }, 500)
  }

  function hide() {
    if (showTimer) { clearTimeout(showTimer); showTimer = null }
    if (hideTimer) clearTimeout(hideTimer)
    hideTimer = setTimeout(() => { hover.value.visible = false }, 150)
  }

  function onPopupEnter() {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
  }
  function onPopupLeave() { hide() }

  function attach() {
    if (!enabled() || !rootRef.value) return
    const cards = rootRef.value.querySelectorAll<HTMLAnchorElement>('a.md-file-card')
    cards.forEach((card) => {
      if (card.dataset.fcHoverBound === '1') return
      const kind = kindFor(card)
      if (!kind) return
      card.dataset.fcHoverBound = '1'
      card.addEventListener('mouseenter', () => show(card, kind))
      card.addEventListener('mouseleave', hide)
    })
  }

  function maybeAttach() {
    if (!enabled()) return
    nextTick(attach)
  }

  onMounted(maybeAttach)
  watch([htmlGetter, () => enabled()], maybeAttach, { flush: 'post' })

  onBeforeUnmount(() => {
    if (showTimer) clearTimeout(showTimer)
    if (hideTimer) clearTimeout(hideTimer)
  })

  return { hover, onPopupEnter, onPopupLeave }
}
