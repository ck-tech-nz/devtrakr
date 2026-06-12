<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-4">
    <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">评论 ({{ comments.length }})</h3>

    <div v-if="loading" class="text-xs text-gray-400 dark:text-gray-500">加载中...</div>
    <div v-else-if="loadError" class="text-xs text-rose-500 flex items-center gap-2">
      <span>评论加载失败</span>
      <UButton size="xs" variant="link" @click="loadComments">重试</UButton>
    </div>
    <p v-else-if="!comments.length" class="text-xs text-gray-400 dark:text-gray-500">暂无评论</p>

    <div v-else class="space-y-3">
      <div
        v-for="c in comments"
        :key="c.id"
        data-testid="comment-item"
        class="border border-gray-100 dark:border-gray-800 rounded-lg"
      >
        <div class="flex items-center justify-between px-3 py-1.5 bg-gray-50 dark:bg-gray-800/60 rounded-t-lg">
          <div class="flex items-center gap-2 min-w-0">
            <img v-if="c.author_avatar" :src="resolveAvatarUrl(c.author_avatar)" alt="" class="w-5 h-5 rounded-full shrink-0" />
            <span class="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">{{ c.author_name || '已注销用户' }}</span>
            <time class="text-[11px] text-gray-400 dark:text-gray-500 shrink-0" :datetime="c.created_at" :title="c.created_at">{{ timeAgo(c.created_at) }}</time>
            <span v-if="c.is_edited" class="text-[11px] text-gray-400 dark:text-gray-500 shrink-0">已编辑</span>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <UButton
              v-if="canEdit(c)"
              data-testid="edit-comment"
              aria-label="编辑评论"
              size="xs" variant="ghost" color="neutral" icon="i-heroicons-pencil-square"
              @click="startEdit(c)"
            />
            <UButton
              v-if="canDelete(c)"
              data-testid="delete-comment"
              aria-label="删除评论"
              size="xs" variant="ghost" color="error" icon="i-heroicons-trash"
              @click="pendingDelete = c"
            />
          </div>
        </div>
        <div class="p-3">
          <template v-if="editingId === c.id">
            <MarkdownEditor v-model="editDraft" min-height="120px" />
            <div class="flex justify-end gap-2 mt-2">
              <UButton size="xs" variant="ghost" color="neutral" @click="cancelEdit">取消</UButton>
              <UButton size="xs" :loading="savingEdit" :disabled="!editDraft.trim()" @click="saveEdit(c)">保存</UButton>
            </div>
          </template>
          <MarkdownView v-else :text="c.content" />
        </div>
      </div>
    </div>

    <!-- 新评论输入框 -->
    <div data-testid="new-comment" class="space-y-2">
      <MarkdownEditor v-model="draft" placeholder="发表评论... 支持 Markdown 和 @提及" min-height="120px" />
      <div class="flex justify-end">
        <UButton data-testid="submit-comment" size="sm" :loading="submitting" :disabled="!draft.trim()" @click="submit">评论</UButton>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <UModal :open="!!pendingDelete" @update:open="(v: boolean) => { if (!v) pendingDelete = null }">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>删除评论</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="pendingDelete = null" />
          </div>
          <div class="modal-body">
            <p class="text-sm text-gray-700 dark:text-gray-300">确认删除这条评论？此操作不可恢复。</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="pendingDelete = null">取消</UButton>
            <UButton color="error" :loading="deleting" @click="confirmDelete">删除</UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
import { timeAgo } from '~/utils/timeAgo'

interface IssueCommentItem {
  id: number
  author: number | null
  author_name: string | null
  author_avatar: string
  content: string
  created_at: string
  updated_at: string
  is_edited: boolean
}

const props = defineProps<{ issueId: number }>()

const { api } = useApi()
const { user, hasGroup } = useAuth()
const { resolveAvatarUrl } = useAvatars()
const toast = useToast()

const comments = ref<IssueCommentItem[]>([])
const loading = ref(true)
const loadError = ref(false)

const draft = ref('')
const submitting = ref(false)

const editingId = ref<number | null>(null)
const editDraft = ref('')
const savingEdit = ref(false)

const pendingDelete = ref<IssueCommentItem | null>(null)
const deleting = ref(false)

const isAdmin = computed(() => hasGroup('管理员') || !!user.value?.is_superuser)

function isAuthor(c: IssueCommentItem): boolean {
  return !!user.value && Number(user.value.id) === c.author
}
function canEdit(c: IssueCommentItem): boolean {
  return isAuthor(c)
}
function canDelete(c: IssueCommentItem): boolean {
  return isAuthor(c) || isAdmin.value
}

// DRF 错误结构统一提取:字段级错误(content)优先级低于全局 detail
function errMsg(e: any, fallback: string): string {
  return e?.data?.detail || e?.data?.content?.[0] || fallback
}

async function loadComments() {
  loading.value = true
  loadError.value = false
  try {
    comments.value = await api<IssueCommentItem[]>(`/api/issues/${props.issueId}/comments/`)
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!draft.value.trim() || submitting.value) return
  submitting.value = true
  try {
    const created = await api<IssueCommentItem>(`/api/issues/${props.issueId}/comments/`, {
      method: 'POST', body: { content: draft.value },
    })
    comments.value.push(created)
    draft.value = ''
  } catch (e: any) {
    toast.add({ title: errMsg(e, '评论发表失败'), color: 'error' })
  } finally {
    submitting.value = false
  }
}

function startEdit(c: IssueCommentItem) {
  editingId.value = c.id
  editDraft.value = c.content
}
function cancelEdit() {
  editingId.value = null
  editDraft.value = ''
}
async function saveEdit(c: IssueCommentItem) {
  if (!editDraft.value.trim() || savingEdit.value) return
  savingEdit.value = true
  try {
    const updated = await api<IssueCommentItem>(`/api/issues/${props.issueId}/comments/${c.id}/`, {
      method: 'PATCH', body: { content: editDraft.value },
    })
    const idx = comments.value.findIndex(x => x.id === c.id)
    if (idx !== -1) comments.value[idx] = updated
    cancelEdit()
  } catch (e: any) {
    toast.add({ title: errMsg(e, '评论保存失败'), color: 'error' })
  } finally {
    savingEdit.value = false
  }
}

async function confirmDelete() {
  const target = pendingDelete.value
  if (!target || deleting.value) return
  deleting.value = true
  try {
    await api(`/api/issues/${props.issueId}/comments/${target.id}/`, { method: 'DELETE' })
    comments.value = comments.value.filter(x => x.id !== target.id)
    pendingDelete.value = null
  } catch (e: any) {
    toast.add({ title: errMsg(e, '评论删除失败'), color: 'error' })
  } finally {
    deleting.value = false
  }
}

onMounted(loadComments)
</script>

<style scoped>
/* 弹窗局部样式 — 与 app/pages/app/issues/[id].vue 等页面的 modal 样式保持一致 */
.modal-form { padding: 1.5rem 2rem; }
.modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; }
.modal-header h3 { font-size: 1.125rem; font-weight: 600; color: #111827; }
:root.dark .modal-header h3 { color: #f3f4f6; }
.modal-body { display: flex; flex-direction: column; gap: 1rem; }
.modal-footer { display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #f3f4f6; }
:root.dark .modal-footer { border-top-color: #374151; }
</style>
