import MarkdownIt from 'markdown-it'
import taskLists from 'markdown-it-task-lists'

const FILE_EXT_CATEGORY: Record<string, string> = {
  pdf: 'pdf',
  doc: 'word',
  docx: 'word',
  xls: 'excel',
  xlsx: 'excel',
  csv: 'excel',
  ppt: 'ppt',
  pptx: 'ppt',
  txt: 'text',
  md: 'text',
  json: 'text',
  zip: 'archive',
}

function stripQueryAndHash(url: string): string {
  const q = url.indexOf('?')
  const h = url.indexOf('#')
  const end = q >= 0 && h >= 0 ? Math.min(q, h) : q >= 0 ? q : h >= 0 ? h : url.length
  return url.slice(0, end)
}

function getFileCategory(href: string | undefined): string | null {
  if (!href) return null
  const clean = stripQueryAndHash(href)
  const lastDot = clean.lastIndexOf('.')
  const lastSlash = clean.lastIndexOf('/')
  if (lastDot < 0 || lastDot < lastSlash) return null
  const ext = clean.slice(lastDot + 1).toLowerCase()
  return FILE_EXT_CATEGORY[ext] ?? null
}

function isExternalHttpLink(href: string | undefined): boolean {
  return !!href && /^https?:\/\//i.test(href)
}

function fileCardPlugin(md: MarkdownIt) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const defaultLinkOpen: any = md.renderer.rules.link_open
    ?? ((tokens: any, idx: any, options: any, _env: any, self: any) => self.renderToken(tokens, idx, options))
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const defaultLinkClose: any = md.renderer.rules.link_close
    ?? ((tokens: any, idx: any, options: any, _env: any, self: any) => self.renderToken(tokens, idx, options))

  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    if (!token) return defaultLinkOpen(tokens, idx, options, env, self)
    const hrefIndex = token.attrIndex('href')
    const attrPair = hrefIndex >= 0 && token.attrs ? token.attrs[hrefIndex] : null
    const href = attrPair ? attrPair[1] : undefined
    const category = getFileCategory(href)
    if (!category) {
      if (isExternalHttpLink(href)) {
        token.attrJoin('class', 'external-link')
        token.attrSet('target', '_blank')
        token.attrSet('rel', 'noopener noreferrer')
      }
      return defaultLinkOpen(tokens, idx, options, env, self)
    }
    // Use the link text (filename) as the download attribute value so the
    // browser saves with the original filename instead of the UUID-based
    // object key from the URL. Honored only for same-origin URLs.
    const nextToken = tokens[idx + 1]
    const filename = nextToken?.type === 'text' ? nextToken.content : ''
    token.attrJoin('class', `md-file-card md-file-${category}`)
    token.attrSet('target', '_blank')
    token.attrSet('rel', 'noopener noreferrer')
    token.attrSet('download', filename)
    // Spread preserves meta from earlier plugins; downstream plugins must do the same on link tokens
    token.meta = { ...(token.meta || {}), fileCategory: category }
    const opener = self.renderToken(tokens, idx, options)
    return `${opener}<span class="md-file-icon" aria-hidden="true"></span><span class="md-file-name">`
  }

  md.renderer.rules.link_close = (tokens, idx, options, env, self) => {
    // Find the matching link_open by walking backwards
    let depth = 1
    let openIdx = idx - 1
    while (openIdx >= 0) {
      const t = tokens[openIdx]
      if (t && t.type === 'link_close') depth++
      if (t && t.type === 'link_open') {
        depth--
        if (depth === 0) break
      }
      openIdx--
    }
    const openToken = openIdx >= 0 ? tokens[openIdx] : null
    const category = openToken?.meta?.fileCategory as string | undefined
    if (!category || !openToken) {
      return defaultLinkClose(tokens, idx, options, env, self)
    }
    const hrefIndex = openToken.attrIndex('href')
    const attrPair = hrefIndex >= 0 && openToken.attrs ? openToken.attrs[hrefIndex] : null
    const href = attrPair ? attrPair[1] : ''
    const clean = stripQueryAndHash(href)
    const ext = clean.slice(clean.lastIndexOf('.') + 1).toUpperCase()
    return `</span><span class="md-file-ext">${ext}</span>${self.renderToken(tokens, idx, options)}`
  }
}

function mentionPlugin(md: MarkdownIt) {
  md.inline.ruler.push('mention_user', (state, silent) => {
    if (state.src.charCodeAt(state.pos) !== 0x40) return false
    if (state.src.charCodeAt(state.pos + 1) !== 0x5B) return false
    const match = state.src.slice(state.pos).match(/^@\[([^\]]+)\]\(user:(\d+)\)/)
    if (!match) return false
    if (!silent) {
      const token = state.push('mention_user', '', 0)
      token.content = match[1] ?? ''
      token.meta = { id: match[2] }
    }
    state.pos += match[0].length
    return true
  })

  md.renderer.rules.mention_user = (tokens, idx) => {
    const name = md.utils.escapeHtml(tokens[idx]?.content ?? '')
    return `<span class="mention-user">@${name}</span>`
  }

  md.inline.ruler.push('mention_issue', (state, silent) => {
    if (state.src.charCodeAt(state.pos) !== 0x23) return false
    if (state.src.charCodeAt(state.pos + 1) !== 0x5B) return false
    const match = state.src.slice(state.pos).match(/^#\[([^\]]+)\]\(issue:(\d+)\)/)
    if (!match) return false
    if (!silent) {
      const token = state.push('mention_issue', '', 0)
      token.content = match[1] ?? ''
      token.meta = { id: match[2] }
    }
    state.pos += match[0].length
    return true
  })

  md.renderer.rules.mention_issue = (tokens, idx) => {
    const id = tokens[idx]?.meta?.id as string | undefined
    if (!id) return ''
    const label = `#问题-${String(id).padStart(3, '0')}`
    return `<a href="/app/issues/${id}" class="mention-issue" data-issue-id="${id}">${label}</a>`
  }
}

function createMentionMarkdown(): MarkdownIt {
  const md = new MarkdownIt({ html: false, linkify: true })
    .use(taskLists, { enabled: true })
    .use(fileCardPlugin)
    .use(mentionPlugin)

  // 关闭无 scheme 的模糊链接识别(http(s):// 完整 URL 不受影响)。
  // .md 是摩尔多瓦顶级域名,否则裸文件名 "xxx.md" 会被识别成外部域名,
  // 再被 fileCardPlugin 渲染成假的附件卡片(悬浮预览失效、点击跳转到
  // 不存在的外部站点)。注意不能用 linkify.tlds('md', false) 单独移除:
  // 该 API 会整体替换 TLD 列表,且两字符国家域名在 linkify-it 里是硬编码的。
  md.linkify.set({ fuzzyLink: false })

  // 行内图片补 loading=lazy/decoding=async:评论流里的截图滚到视口再加载
  const defaultImage = md.renderer.rules.image
    ?? ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
  md.renderer.rules.image = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    if (token) {
      token.attrSet('loading', 'lazy')
      token.attrSet('decoding', 'async')
    }
    return defaultImage(tokens, idx, options, env, self)
  }

  return md
}

// 实例无状态,模块级单例:评论区每条评论挂一个 MarkdownView,
// 避免每次组件 setup 都重建 MarkdownIt + linkify 实例
let sharedMd: MarkdownIt | null = null

export function useMentionMarkdown() {
  if (!sharedMd) sharedMd = createMentionMarkdown()
  return { md: sharedMd, mentionPlugin }
}
