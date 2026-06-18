// 从文本和光标位置检测 @ 或 # 触发词。
// 从 MarkdownEditor.vue 内联逻辑提取为可复用 composable，
// 供 ChatThread 聊天回复框和未来其他轻量编辑器使用。
// 注意：MarkdownEditor.vue 目前保留自己的内联实现（与 textarea ref / props 深度耦合），
// 不做回溯重构，以避免回归风险。

export interface MentionTrigger {
  type: 'user' | 'issue'
  query: string
  start: number
}

/**
 * 检测文本中是否有未完成的 @ 或 # 触发词。
 * @param text  完整文本内容
 * @param cursor 当前光标位置（selectionStart）
 */
export function detectMentionTrigger(text: string, cursor: number): MentionTrigger | null {
  const before = text.slice(0, cursor)

  const atMatch = before.match(/@([^\s@]*)$/)
  if (atMatch) {
    return { type: 'user', query: atMatch[1] ?? '', start: cursor - atMatch[0].length }
  }

  const hashMatch = before.match(/#([^\s#]*)$/)
  if (hashMatch) {
    return { type: 'issue', query: hashMatch[1] ?? '', start: cursor - hashMatch[0].length }
  }

  return null
}
