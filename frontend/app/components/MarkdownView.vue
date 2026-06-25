<template>
  <div ref="rootEl" class="markdown-view" v-html="html" />
</template>

<script setup lang="ts">
const props = defineProps<{ text?: string }>()

const { md } = useMentionMarkdown()

// html 必须在 useInlineLinkPreviews 之前声明:后者的 immediate watch 会在 setup
// 阶段同步读取 htmlGetter(),若 html 尚未初始化会触发 TDZ
// (ReferenceError: Cannot access 'html' before initialization)。
const html = computed(() => {
  if (!props.text) return ''
  return md.render(props.text)
    .replace(/<input class="task-list-item-checkbox" checked=""type="checkbox">/g, '<span class="md-checkbox md-checked"></span>')
    .replace(/<input class="task-list-item-checkbox"type="checkbox">/g, '<span class="md-checkbox"></span>')
})

const rootEl = ref<HTMLElement | null>(null)
useInlineLinkPreviews(rootEl, () => html.value)
</script>

<style>
/* 只读 Markdown 渲染（与 MarkdownEditor 预览风格一致；自带样式，随本组件按需加载） */
.markdown-view { font-size: 0.875rem; line-height: 1.6; color: #374151; }
:root.dark .markdown-view { color: #d1d5db; }
.markdown-view > :first-child { margin-top: 0; }
.markdown-view > :last-child { margin-bottom: 0; }
.markdown-view h1 { font-size: 1.4em; font-weight: 700; margin: 0.67em 0; }
.markdown-view h2 { font-size: 1.2em; font-weight: 600; margin: 0.75em 0; }
.markdown-view h3 { font-size: 1.05em; font-weight: 600; margin: 0.9em 0 0.4em; }
.markdown-view h4 { font-size: 1em; font-weight: 600; margin: 0.8em 0 0.3em; }
.markdown-view p { margin: 0.5em 0; }
.markdown-view ul { margin: 0.4em 0; padding-left: 1.5em; list-style-type: disc; }
.markdown-view ol { margin: 0.4em 0; padding-left: 1.5em; list-style-type: decimal; }
.markdown-view li { margin: 0.2em 0; }
.markdown-view strong { font-weight: 600; color: #111827; }
:root.dark .markdown-view strong { color: #f3f4f6; }
.markdown-view em { font-style: italic; }
.markdown-view code { background: #f3f4f6; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.875em; }
:root.dark .markdown-view code { background: #1f2937; }
.markdown-view pre { background: #f3f4f6; padding: 0.85em; border-radius: 6px; overflow-x: auto; margin: 0.5em 0; }
:root.dark .markdown-view pre { background: #1f2937; }
.markdown-view pre code { background: none; padding: 0; }
.markdown-view blockquote { border-left: 3px solid #d1d5db; padding-left: 0.85em; color: #6b7280; margin: 0.5em 0; }
:root.dark .markdown-view blockquote { border-left-color: #4b5563; color: #9ca3af; }
.markdown-view a { color: #2563eb; text-decoration: none; }
.markdown-view a:hover { text-decoration: underline; }
:root.dark .markdown-view a { color: #60a5fa; }
.markdown-view hr { border: none; border-top: 1px solid #e5e7eb; margin: 1em 0; }
:root.dark .markdown-view hr { border-top-color: #374151; }
.markdown-view table { border-collapse: collapse; margin: 0.5em 0; }
.markdown-view th, .markdown-view td { border: 1px solid #d1d5db; padding: 0.4em 0.6em; }
:root.dark .markdown-view th, :root.dark .markdown-view td { border-color: #4b5563; }
.markdown-view img { max-width: 100%; height: auto; border-radius: 6px; margin: 0.5em 0; box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.12); }
/* 图片对齐:|left/center/right 标记(块级 + auto 外边距,配合 |w= 才有可见效果) */
.markdown-view img.md-img-left { display: block; margin-right: auto; }
.markdown-view img.md-img-center { display: block; margin-left: auto; margin-right: auto; }
.markdown-view img.md-img-right { display: block; margin-left: auto; }
:root.dark .markdown-view img { box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1), 0 2px 8px rgba(0, 0, 0, 0.45); }

/* 以下 mention/file-card/task-list 样式与 MarkdownEditor.vue 的 .markdown-body 段保持同步 */

/* Mention styles */
.markdown-view .mention-user {
  background: #dbeafe;
  color: #1d4ed8;
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.9em;
  font-weight: 500;
}
.markdown-view .mention-issue {
  background: #dcfce7;
  color: #15803d;
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.9em;
  font-weight: 500;
  text-decoration: none;
}
.markdown-view .mention-issue:hover {
  text-decoration: underline;
}
:root.dark .markdown-view .mention-user {
  background: #1e3a5f;
  color: #93c5fd;
}
:root.dark .markdown-view .mention-issue {
  background: #14532d;
  color: #86efac;
}

/* File card (non-image attachments in markdown preview) */
.markdown-view .md-file-card {
  display: inline-flex;
  align-items: center;
  gap: 0.5em;
  padding: 0.4em 0.75em;
  margin: 0.25em 0.25em 0.25em 0;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  color: #1f2937;
  text-decoration: none;
  font-size: 0.875em;
  line-height: 1.2;
  transition: background 0.15s, border-color 0.15s;
  max-width: 100%;
}
.markdown-view .md-file-card:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
  text-decoration: none;
}
.markdown-view .md-file-card .md-file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.markdown-view .md-file-card .md-file-ext {
  font-size: 0.7em;
  font-weight: 600;
  letter-spacing: 0.05em;
  padding: 0.15em 0.4em;
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.06);
  color: #4b5563;
}
.markdown-view .md-file-card .md-file-icon {
  display: inline-block;
  width: 1.1em;
  height: 1.1em;
  flex-shrink: 0;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
}
.markdown-view .md-file-pdf .md-file-icon::before { content: '📄'; }
.markdown-view .md-file-word .md-file-icon::before { content: '📝'; }
.markdown-view .md-file-excel .md-file-icon::before { content: '📊'; }
.markdown-view .md-file-ppt .md-file-icon::before { content: '📽'; }
.markdown-view .md-file-text .md-file-icon::before { content: '📄'; }
.markdown-view .md-file-archive .md-file-icon::before { content: '📦'; }
.markdown-view .md-file-html .md-file-icon::before { content: '🌐'; }

.markdown-view .md-file-pdf .md-file-ext { background: #fee2e2; color: #b91c1c; }
.markdown-view .md-file-word .md-file-ext { background: #dbeafe; color: #1d4ed8; }
.markdown-view .md-file-excel .md-file-ext { background: #dcfce7; color: #15803d; }
.markdown-view .md-file-ppt .md-file-ext { background: #ffedd5; color: #c2410c; }
.markdown-view .md-file-text .md-file-ext { background: #f3f4f6; color: #4b5563; }
.markdown-view .md-file-archive .md-file-ext { background: #e5e7eb; color: #374151; }
.markdown-view .md-file-html .md-file-ext { background: #ede9fe; color: #6d28d9; }

:root.dark .markdown-view .md-file-card {
  background: #1f2937;
  border-color: #374151;
  color: #e5e7eb;
}
:root.dark .markdown-view .md-file-card:hover {
  background: #374151;
  border-color: #4b5563;
}
:root.dark .markdown-view .md-file-card .md-file-ext {
  background: rgba(255, 255, 255, 0.08);
  color: #d1d5db;
}
:root.dark .markdown-view .md-file-pdf .md-file-ext { background: #7f1d1d; color: #fecaca; }
:root.dark .markdown-view .md-file-word .md-file-ext { background: #1e3a5f; color: #bfdbfe; }
:root.dark .markdown-view .md-file-excel .md-file-ext { background: #14532d; color: #bbf7d0; }
:root.dark .markdown-view .md-file-ppt .md-file-ext { background: #7c2d12; color: #fed7aa; }
:root.dark .markdown-view .md-file-text .md-file-ext { background: #374151; color: #e5e7eb; }
:root.dark .markdown-view .md-file-archive .md-file-ext { background: #4b5563; color: #f3f4f6; }
:root.dark .markdown-view .md-file-html .md-file-ext { background: #3b2f5e; color: #d6c7ff; }

/* Task list (todo) styles */
.markdown-view ul.contains-task-list { padding-left: 1.5em; list-style: none; margin: 0.5em 0; }
.markdown-view .task-list-item { list-style: none; }
.markdown-view .md-checkbox {
  display: inline-block;
  width: 0.95em; height: 0.95em;
  border: 1.5px solid #9ca3af;
  border-radius: 3px;
  margin-right: 0.4em;
  vertical-align: middle;
  position: relative;
  top: -0.05em;
}
.markdown-view .md-checkbox.md-checked {
  background: #6366f1;
  border-color: #6366f1;
}
.markdown-view .md-checkbox.md-checked::after {
  content: '';
  position: absolute;
  left: 2.5px; top: 0.5px;
  width: 4px; height: 8px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}
</style>
