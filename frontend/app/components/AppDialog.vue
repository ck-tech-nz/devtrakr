<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="state.open" class="dialog-overlay" @click.self="onOverlayClick" @keydown.esc="onEsc">
        <div class="dialog-panel" role="dialog" aria-modal="true" :aria-labelledby="state.title ? 'dialog-title' : undefined">
          <div class="dialog-body">
            <div v-if="state.icon" class="dialog-icon" :class="iconClass">
              <UIcon :name="state.icon" class="w-6 h-6" />
            </div>
            <div class="dialog-text">
              <h3 v-if="state.title" id="dialog-title" class="dialog-title">{{ state.title }}</h3>
              <div
                v-if="state.htmlBody"
                class="dialog-markdown markdown-body"
                v-html="state.htmlBody"
              />
              <p v-else-if="state.message" class="dialog-message">{{ state.message }}</p>
            </div>
          </div>
          <div class="dialog-footer">
            <UButton v-if="state.mode === 'confirm'" variant="outline" color="neutral" @click="cancel">
              {{ state.cancelText }}
            </UButton>
            <UButton ref="confirmBtnRef" :color="state.color" @click="ok">{{ state.confirmText }}</UButton>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
const { state, _respond } = useDialog()

const iconClass = computed(() => `dialog-icon--${state.value.color}`)
const confirmBtnRef = ref<any>(null)

function ok() { _respond(true) }
function cancel() { _respond(false) }
function onOverlayClick() {
  if (state.value.persistent) return
  // Mirror native confirm: clicking outside is treated as cancel for confirm,
  // and as confirm for alert (since alert has only one action).
  if (state.value.mode === 'alert') ok()
  else cancel()
}
function onEsc() {
  if (state.value.persistent) return
  if (state.value.mode === 'alert') ok()
  else cancel()
}

// Global Esc listener (overlay only catches when focused)
function handleKey(e: KeyboardEvent) {
  if (!state.value.open) return
  if (e.key === 'Escape') {
    e.stopPropagation()
    onEsc()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKey, { capture: true })
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKey, { capture: true })
})

// Autofocus the confirm button when the dialog opens
watch(() => state.value.open, async (open) => {
  if (!open) return
  await nextTick()
  confirmBtnRef.value?.$el?.focus?.()
})
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background-color: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(2px);
  /* Reka UI's modal sets body { pointer-events: none } when open.
     AppDialog is teleported to body, so it must opt back in. */
  pointer-events: auto;
}
:root.dark .dialog-overlay {
  background-color: rgba(0, 0, 0, 0.65);
}
.dialog-panel {
  width: 100%;
  max-width: 520px;
  max-height: min(80vh, 720px);
  display: flex;
  flex-direction: column;
  background-color: #ffffff;
  border-radius: 0.875rem;
  box-shadow: 0 20px 50px -10px rgba(15, 23, 42, 0.35), 0 8px 16px -8px rgba(15, 23, 42, 0.2);
  padding: 1.5rem 1.75rem 1.25rem;
  outline: none;
}
:root.dark .dialog-panel {
  background-color: #1f2937;
  box-shadow: 0 20px 50px -10px rgba(0, 0, 0, 0.6), 0 8px 16px -8px rgba(0, 0, 0, 0.4);
}
.dialog-body {
  display: flex;
  gap: 1rem;
  align-items: stretch;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.dialog-icon {
  flex-shrink: 0;
  align-self: flex-start;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 9999px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog-icon--primary { background-color: #ede9fe; color: #7c3aed; }
.dialog-icon--error { background-color: #fee2e2; color: #dc2626; }
.dialog-icon--warning { background-color: #fef3c7; color: #d97706; }
.dialog-icon--success { background-color: #d1fae5; color: #059669; }
.dialog-icon--info { background-color: #dbeafe; color: #2563eb; }
.dialog-icon--neutral { background-color: #f3f4f6; color: #4b5563; }
:root.dark .dialog-icon--primary { background-color: rgba(124, 58, 237, 0.18); color: #a78bfa; }
:root.dark .dialog-icon--error { background-color: rgba(220, 38, 38, 0.18); color: #f87171; }
:root.dark .dialog-icon--warning { background-color: rgba(217, 119, 6, 0.18); color: #fbbf24; }
:root.dark .dialog-icon--success { background-color: rgba(5, 150, 105, 0.18); color: #34d399; }
:root.dark .dialog-icon--info { background-color: rgba(37, 99, 235, 0.18); color: #60a5fa; }
:root.dark .dialog-icon--neutral { background-color: rgba(75, 85, 99, 0.25); color: #d1d5db; }
.dialog-text {
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding-top: 0.125rem;
  overflow-y: auto;
}
.dialog-title {
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
  margin-bottom: 0.375rem;
}
:root.dark .dialog-title {
  color: #f3f4f6;
}
.dialog-message {
  font-size: 0.875rem;
  line-height: 1.5;
  color: #4b5563;
  white-space: pre-line;
}
:root.dark .dialog-message {
  color: #9ca3af;
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.625rem;
  margin-top: 1.25rem;
}

.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 0.15s ease;
}
.dialog-enter-active .dialog-panel,
.dialog-leave-active .dialog-panel {
  transition: transform 0.15s ease, opacity 0.15s ease;
}
.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}
.dialog-enter-from .dialog-panel,
.dialog-leave-to .dialog-panel {
  opacity: 0;
  transform: translateY(8px) scale(0.97);
}
</style>

<style>
/* Unscoped: `v-html` content does not receive Vue's scope attribute,
   so .dialog-markdown rules must live outside <style scoped>. */
.dialog-markdown {
  font-size: 0.875rem;
  line-height: 1.6;
  color: #1f2937;
}
:root.dark .dialog-markdown {
  color: #e5e7eb;
}
.dialog-markdown h1 {
  font-size: 1.15rem;
  font-weight: 700;
  margin: 0.5em 0 0.4em;
}
.dialog-markdown h2 {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0.6em 0 0.4em;
}
.dialog-markdown h3 {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0.6em 0 0.3em;
}
.dialog-markdown p {
  margin: 0.4em 0;
}
.dialog-markdown ul,
.dialog-markdown ol {
  margin: 0.4em 0;
  padding-left: 1.5em;
}
.dialog-markdown ul {
  list-style-type: disc;
}
.dialog-markdown ol {
  list-style-type: decimal;
}
.dialog-markdown li {
  margin: 0.2em 0;
}
.dialog-markdown strong {
  font-weight: 600;
}
.dialog-markdown em {
  font-style: italic;
}
.dialog-markdown code {
  background-color: rgba(15, 23, 42, 0.06);
  padding: 0.15em 0.35em;
  border-radius: 3px;
  font-size: 0.85em;
}
:root.dark .dialog-markdown code {
  background-color: rgba(255, 255, 255, 0.08);
}
.dialog-markdown pre {
  background-color: #f3f4f6;
  padding: 0.75rem 0.875rem;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5em 0;
}
:root.dark .dialog-markdown pre {
  background-color: #1f2937;
}
.dialog-markdown pre code {
  background: none;
  padding: 0;
}
.dialog-markdown a {
  color: #6366f1;
  text-decoration: none;
}
.dialog-markdown a:hover {
  text-decoration: underline;
}
:root.dark .dialog-markdown a {
  color: #818cf8;
}
.dialog-markdown blockquote {
  border-left: 3px solid #d1d5db;
  padding-left: 0.875rem;
  color: #6b7280;
  margin: 0.5em 0;
}
:root.dark .dialog-markdown blockquote {
  border-left-color: #4b5563;
  color: #9ca3af;
}
.dialog-markdown img {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  margin: 0.5em 0;
  display: block;
}
.dialog-markdown hr {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 0.75em 0;
}
:root.dark .dialog-markdown hr {
  border-top-color: #374151;
}
</style>
