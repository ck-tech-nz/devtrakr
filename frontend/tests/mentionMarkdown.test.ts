import { describe, it, expect } from 'vitest'
import { useMentionMarkdown } from '../app/composables/useMentionMarkdown'

const { md } = useMentionMarkdown()

describe('useMentionMarkdown 渲染', () => {
  // 回归:.md 是摩尔多瓦顶级域名,linkify 的 fuzzyLink 会把裸文件名
  // "xxx.md" 识别成外部域名,再被 fileCardPlugin 渲染成附件卡片,
  // 用户误以为是已上传的附件(悬浮预览也不会生效)。
  it('裸 .md 文件名不应被识别为链接', () => {
    const html = md.render('外呼系统-队列排队容错重试机制说明.md')
    expect(html).not.toContain('<a')
    expect(html).toContain('外呼系统-队列排队容错重试机制说明.md')
  })

  it('英文裸文件名 README.md 不应被识别为链接', () => {
    const html = md.render('README.md')
    expect(html).not.toContain('<a')
  })

  it('显式上传链接渲染为 .md 文件卡片', () => {
    const html = md.render('[报告.md](/uploads/2026/06/10/abc.md)')
    expect(html).toContain('md-file-card md-file-text')
    expect(html).toContain('download="报告.md"')
    expect(html).toContain('href="/uploads/2026/06/10/abc.md"')
    expect(html).toContain('<span class="md-file-ext">MD</span>')
  })

  it('显式上传链接渲染为 pdf 文件卡片', () => {
    const html = md.render('[规格书.pdf](/uploads/2026/06/10/def.pdf)')
    expect(html).toContain('md-file-card md-file-pdf')
  })

  it('带 scheme 的完整 URL 仍自动转为链接', () => {
    const html = md.render('见 https://example.com/docs 说明')
    expect(html).toContain('<a href="https://example.com/docs"')
  })

  it('用户提及正常渲染', () => {
    const html = md.render('@[张三](user:5)')
    expect(html).toContain('<span class="mention-user">@张三</span>')
  })

  it('问题提及正常渲染', () => {
    const html = md.render('#[#问题-042](issue:42)')
    expect(html).toContain('href="/app/issues/42"')
  })

  it('escapes html in mention display names (XSS)', () => {
    const html = md.render('@[<img src=x onerror=alert(1)>](user:1)')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
  })

  it('issue mention ignores display name — renders from id, not user-supplied label', () => {
    // mention_issue renderer 用 id 重建标签,忽略 token.content,无 XSS 风险
    const html = md.render('#[<script>alert(1)</script>](issue:99)')
    expect(html).not.toContain('<script>')
    expect(html).toContain('#问题-099')
  })

  it('问题提及带 data-issue-id 供悬浮预览取数', () => {
    const html = md.render('#[#问题-042](issue:42)')
    expect(html).toContain('data-issue-id="42"')
    expect(html).toContain('class="mention-issue"')
  })

  it('外部 URL 链接带 external-link class 与安全 rel/target', () => {
    const html = md.render('见 https://example.com/docs 说明')
    expect(html).toContain('class="external-link"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('站内根相对链接不应标记为 external-link', () => {
    const html = md.render('[详情](/app/issues/3)')
    expect(html).not.toContain('external-link')
  })
})

describe('图片尺寸标记 |w=', () => {
  it('alt 末尾的 |w=300 设置宽度并从 alt 中剥离', () => {
    const html = md.render('![架构图|w=300](/uploads/x.png)')
    expect(html).toContain('width="300"')
    expect(html).toContain('alt="架构图"')
    expect(html).not.toContain('|w=300')
  })

  it('只有标记没有说明文字时宽度生效且 alt 为空', () => {
    const html = md.render('![|w=200](/uploads/x.png)')
    expect(html).toContain('width="200"')
    expect(html).toContain('alt=""')
  })

  it('不写标记的图片宽度不受影响(回归)', () => {
    const html = md.render('![普通截图](/uploads/x.png)')
    expect(html).not.toContain('width=')
    expect(html).toContain('alt="普通截图"')
  })

  it('非数字宽度不解析,标记原样保留为 alt', () => {
    const html = md.render('![图|w=abc](/uploads/x.png)')
    expect(html).not.toContain('width=')
    expect(html).toContain('|w=abc')
  })

  it('容忍标记前后的空格', () => {
    const html = md.render('![图 | w=300 ](/uploads/x.png)')
    expect(html).toContain('width="300"')
    expect(html).toContain('alt="图"')
  })
})

describe('图片对齐标记 |left/center/right', () => {
  it('|center 加居中 class 并从 alt 剥离', () => {
    const html = md.render('![图|center](/uploads/x.png)')
    expect(html).toContain('md-img-center')
    expect(html).toContain('alt="图"')
    expect(html).not.toContain('|center')
  })

  it('|right 加靠右 class', () => {
    const html = md.render('![图|right](/uploads/x.png)')
    expect(html).toContain('md-img-right')
  })

  it('|left 加靠左 class', () => {
    const html = md.render('![图|left](/uploads/x.png)')
    expect(html).toContain('md-img-left')
  })

  it('宽度与对齐可组合', () => {
    const html = md.render('![图|w=300|center](/uploads/x.png)')
    expect(html).toContain('width="300"')
    expect(html).toContain('md-img-center')
    expect(html).toContain('alt="图"')
  })

  it('标记顺序无关', () => {
    const html = md.render('![图|center|w=300](/uploads/x.png)')
    expect(html).toContain('width="300"')
    expect(html).toContain('md-img-center')
  })

  it('无标记的图片不加对齐 class(回归)', () => {
    const html = md.render('![普通图](/uploads/x.png)')
    expect(html).not.toContain('md-img-')
    expect(html).toContain('alt="普通图"')
  })

  it('未知关键字不解析,原样保留为 alt', () => {
    const html = md.render('![图|middle](/uploads/x.png)')
    expect(html).not.toContain('md-img-')
    expect(html).toContain('|middle')
  })
})
