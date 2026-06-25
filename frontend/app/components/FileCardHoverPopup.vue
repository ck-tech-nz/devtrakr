<template>
  <Teleport to="body">
    <div
      v-if="hover.visible"
      class="fc-hover-preview"
      :style="{ top: hover.top + 'px', left: hover.left + 'px' }"
      @mouseenter="emit('enter')"
      @mouseleave="emit('leave')"
    >
      <div class="fc-hover-header">
        <span class="fc-hover-title" :title="hover.filename">{{ hover.filename }}</span>
        <a
          class="fc-hover-download"
          :href="hover.url"
          :download="hover.filename"
          target="_blank"
          rel="noopener noreferrer"
        >下载</a>
      </div>
      <div v-if="hover.loading" class="fc-hover-msg">加载中...</div>
      <div v-else-if="hover.tooLarge" class="fc-hover-msg">文件较大,请点击"下载"后查看</div>
      <!-- HTML: 沙箱 iframe,无 allow-same-origin → 脚本运行在 null 源,无法触达父页面/cookie -->
      <iframe
        v-else-if="hover.kind === 'html'"
        class="fc-hover-iframe"
        :srcdoc="hover.rawHtml"
        sandbox="allow-scripts"
        referrerpolicy="no-referrer"
      />
      <!-- Markdown: 渲染后的 HTML;样式自包含于本组件,不依赖宿主页 -->
      <div v-else class="fc-hover-md" v-html="hover.content" />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { FileHoverState } from '~/composables/useFileCardHoverPreview'

defineProps<{ hover: FileHoverState }>()
const emit = defineEmits<{ enter: []; leave: [] }>()
</script>

<style>
.fc-hover-preview {
  position: absolute;
  width: min(720px, calc(100vw - 32px));
  max-height: min(640px, 70vh);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12), 0 4px 10px rgba(0, 0, 0, 0.06);
  z-index: 9999;
  font-size: 14px;
  line-height: 1.6;
  color: #1f2937;
}
.fc-hover-preview .fc-hover-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 8px 8px 0 0;
}
.fc-hover-preview .fc-hover-title {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  font-size: 13px;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fc-hover-preview .fc-hover-download {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 4px;
  background: #6366f1;
  color: #ffffff;
  text-decoration: none;
  transition: background 0.15s;
}
.fc-hover-preview .fc-hover-download:hover { background: #4f46e5; text-decoration: none; }
.fc-hover-preview .fc-hover-msg { color: #9ca3af; font-size: 13px; padding: 16px 20px; }
.fc-hover-preview .fc-hover-iframe {
  flex: 1;
  width: 100%;
  min-height: 320px;
  border: 0;
  background: #ffffff;
}
.fc-hover-preview .fc-hover-md {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
  word-wrap: break-word;
}
/* 自包含的 markdown 内容样式(核心元素),不依赖宿主页是否加载了 .markdown-body/.markdown-view */
.fc-hover-md > :first-child { margin-top: 0; }
.fc-hover-md > :last-child { margin-bottom: 0; }
.fc-hover-md h1 { font-size: 1.4em; font-weight: 700; margin: 0.67em 0; }
.fc-hover-md h2 { font-size: 1.2em; font-weight: 600; margin: 0.75em 0; }
.fc-hover-md h3 { font-size: 1.05em; font-weight: 600; margin: 0.9em 0 0.4em; }
.fc-hover-md p { margin: 0.5em 0; }
.fc-hover-md ul { margin: 0.4em 0; padding-left: 1.5em; list-style-type: disc; }
.fc-hover-md ol { margin: 0.4em 0; padding-left: 1.5em; list-style-type: decimal; }
.fc-hover-md li { margin: 0.2em 0; }
.fc-hover-md strong { font-weight: 600; }
.fc-hover-md em { font-style: italic; }
.fc-hover-md code { background: #f3f4f6; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.875em; }
.fc-hover-md pre { background: #f3f4f6; padding: 0.85em; border-radius: 6px; overflow-x: auto; margin: 0.5em 0; }
.fc-hover-md pre code { background: none; padding: 0; }
.fc-hover-md blockquote { border-left: 3px solid #d1d5db; padding-left: 0.85em; color: #6b7280; margin: 0.5em 0; }
.fc-hover-md a { color: #2563eb; text-decoration: none; }
.fc-hover-md a:hover { text-decoration: underline; }
.fc-hover-md hr { border: none; border-top: 1px solid #e5e7eb; margin: 1em 0; }
.fc-hover-md table { border-collapse: collapse; margin: 0.5em 0; }
.fc-hover-md th, .fc-hover-md td { border: 1px solid #d1d5db; padding: 0.4em 0.6em; }
.fc-hover-md img { max-width: 100%; height: auto; border-radius: 6px; margin: 0.5em 0; }

:root.dark .fc-hover-preview {
  background: #1f2937;
  border-color: #374151;
  color: #e5e7eb;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 4px 10px rgba(0, 0, 0, 0.3);
}
:root.dark .fc-hover-preview .fc-hover-header { background: #111827; border-bottom-color: #374151; }
:root.dark .fc-hover-preview .fc-hover-title { color: #e5e7eb; }
:root.dark .fc-hover-preview .fc-hover-msg { color: #6b7280; }
:root.dark .fc-hover-preview .fc-hover-iframe { background: #ffffff; } /* 文档多为浅底,保持白底更可读 */
:root.dark .fc-hover-md code,
:root.dark .fc-hover-md pre { background: #111827; }
:root.dark .fc-hover-md blockquote { border-left-color: #4b5563; color: #9ca3af; }
:root.dark .fc-hover-md a { color: #60a5fa; }
:root.dark .fc-hover-md th, :root.dark .fc-hover-md td { border-color: #4b5563; }
</style>
