<template>
  <div class="space-y-6 max-w-2xl">
    <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">个人资料</h1>

    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-6 space-y-6">
      <!-- Avatar & basic info -->
      <div class="flex items-center gap-4 pb-4 border-b border-gray-100 dark:border-gray-800">
        <img v-if="form.avatar" :src="resolveAvatarUrl(form.avatar)" class="w-16 h-16 rounded-full" />
        <div>
          <div class="text-lg font-semibold text-gray-900 dark:text-gray-100">{{ user?.username }}</div>
          <div class="text-sm text-gray-500 dark:text-gray-400">{{ user?.groups?.join(', ') || '无用户组' }}</div>
        </div>
      </div>

      <!-- Avatar picker -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">修改头像</label>
        <AvatarPicker v-model="form.avatar" />
      </div>

      <!-- Editable fields -->
      <div class="grid grid-cols-2 gap-4">
        <UFormField label="昵称">
          <div class="flex gap-2">
            <UInput v-model="form.name" size="lg" class="flex-1" />
            <UButton
              variant="outline"
              color="neutral"
              size="lg"
              :loading="generatingName"
              icon="i-heroicons-sparkles"
              title="AI 生成昵称"
              @click="generateNickname"
            />
          </div>
        </UFormField>
        <UFormField label="邮箱" hint="用于接收通知">
          <UInput v-model="form.email" type="email" size="lg" class="w-full" />
        </UFormField>
      </div>

      <!-- Change password -->
      <div class="pt-4 border-t border-gray-100 dark:border-gray-800">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">修改密码</h3>
        <div class="space-y-3">
          <UFormField label="当前密码" :error="pwError">
            <UInput v-model="pw.current" type="password" placeholder="请输入当前密码" size="lg" class="w-full" :color="pwError ? 'error' : undefined" />
          </UFormField>
          <div class="grid grid-cols-2 gap-4">
            <UFormField label="新密码">
              <UInput v-model="pw.new_password" type="password" placeholder="请输入新密码" size="lg" class="w-full" />
            </UFormField>
            <UFormField label="确认新密码">
              <UInput v-model="pw.confirm" type="password" placeholder="请确认新密码" size="lg" class="w-full" />
            </UFormField>
          </div>
        </div>
      </div>

      <!-- Personal settings -->
      <div class="pt-4 border-t border-gray-100 dark:border-gray-800">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">个人设置</h3>
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-700 dark:text-gray-300">默认项目</div>
              <div class="text-xs text-gray-400">新建问题/AI 向导会默认选中该项目</div>
            </div>
            <USelect
              v-model="defaultProjectId"
              :items="projectOptions"
              value-key="value"
              placeholder="（使用站点默认）"
              size="sm"
              class="w-48"
              @update:model-value="saveDefaultProject"
            />
          </div>
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-700 dark:text-gray-300">侧栏自动收起</div>
              <div class="text-xs text-gray-400">窗口较小时自动折叠导航栏</div>
            </div>
            <USwitch v-model="settingsForm.sidebar_auto_collapse" />
          </div>
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-700 dark:text-gray-300">问题列表默认视图</div>
              <div class="text-xs text-gray-400">打开问题跟踪页时的默认展示方式</div>
            </div>
            <USelect v-model="settingsForm.issues_view_mode" :items="viewModeOptions" size="sm" class="w-24" />
          </div>
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-700 dark:text-gray-300">项目默认视图</div>
              <div class="text-xs text-gray-400">打开项目管理页时的默认展示方式</div>
            </div>
            <USelect v-model="settingsForm.project_view_mode" :items="viewModeOptions" size="sm" class="w-24" />
          </div>
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-gray-700 dark:text-gray-300">主题</div>
              <div class="text-xs text-gray-400">界面颜色模式</div>
            </div>
            <USelect v-model="settingsForm.theme" :items="themeOptions" size="sm" class="w-24" />
          </div>
        </div>
      </div>

      <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      <p v-if="success" class="text-sm text-green-600">{{ success }}</p>
      <div class="flex justify-end pt-4 border-t border-gray-100 dark:border-gray-800">
        <UButton :loading="saving" @click="handleSave">保存修改</UButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const { user, fetchMe } = useAuth()
const { resolveAvatarUrl } = useAvatars()
const { settings } = useUserSettings()

const saving = ref(false)
const error = ref('')
const pwError = ref('')
const success = ref('')
const generatingName = ref(false)
const generatedNames = ref<string[]>([])

async function generateNickname() {
  generatingName.value = true
  try {
    const data = await api<{ nickname: string }>('/api/auth/generate-nickname/', {
      method: 'POST',
      body: { username: user.value?.username, exclude: generatedNames.value },
    })
    form.value.name = data.nickname
    if (data.nickname) generatedNames.value.push(data.nickname)
  } catch {
    // silently ignore
  } finally {
    generatingName.value = false
  }
}

const form = ref({ name: '', email: '', avatar: '' })
const pw = ref({ current: '', new_password: '', confirm: '' })
const settingsForm = ref({ sidebar_auto_collapse: false, issues_view_mode: 'table' as string, project_view_mode: 'kanban' as string, theme: 'light' as string })

const viewModeOptions = [{ label: '列表', value: 'table' }, { label: '看板', value: 'kanban' }]
const themeOptions = [{ label: '浅色', value: 'light' }, { label: '深色', value: 'dark' }, { label: '跟随系统', value: 'auto' }]

const projects = ref<{ id: string; name: string }[]>([])
const defaultProjectId = ref<string>('')

const projectOptions = computed(() => [
  { label: '（使用站点默认）', value: '' },
  ...projects.value.map(p => ({ label: p.name, value: String(p.id) })),
])

onMounted(async () => {
  const data = await api<any>('/api/projects/').catch(() => ({ results: [] }))
  projects.value = (data.results || data || []).map((p: any) => ({ id: String(p.id), name: p.name }))
  defaultProjectId.value = String(user.value?.default_project?.id || '')
})

async function saveDefaultProject(v: string) {
  try {
    await api('/api/auth/me/', {
      method: 'PATCH',
      body: { default_project: v || null },
      format: 'json',
    })
    await fetchMe()
  } catch (e) {
    console.error('Failed to save default project:', e)
  }
}

watch(user, (u) => {
  if (u) {
    form.value = { name: u.name || '', email: u.email || '', avatar: u.avatar || '' }
  }
}, { immediate: true })

watch(settings, (s) => {
  settingsForm.value = { ...s }
}, { immediate: true })

async function handleSave() {
  saving.value = true
  error.value = ''
  pwError.value = ''
  success.value = ''
  try {
    if (pw.value.new_password || pw.value.confirm) {
      if (!pw.value.current) {
        pwError.value = '请输入当前密码'
        saving.value = false
        return
      }
      if (pw.value.new_password !== pw.value.confirm) {
        pwError.value = '两次新密码输入不一致'
        saving.value = false
        return
      }
    }

    await api('/api/auth/me/', {
      method: 'PATCH',
      body: { name: form.value.name, email: form.value.email, avatar: form.value.avatar, settings: settingsForm.value },
    })

    if (pw.value.new_password || pw.value.confirm) {
      await api('/api/auth/me/change-password/', {
        method: 'POST',
        body: {
          current_password: pw.value.current,
          new_password: pw.value.new_password,
          new_password_confirm: pw.value.confirm,
        },
      })
      pw.value = { current: '', new_password: '', confirm: '' }
    }

    await fetchMe()
    success.value = '保存成功'
  } catch (e: any) {
    const data = e?.data || e?.response?._data
    if (data && typeof data === 'object') {
      const msgs = Object.entries(data)
        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
        .join('; ')
      error.value = msgs || '保存失败'
    } else {
      error.value = '保存失败'
    }
  } finally {
    saving.value = false
  }
}
</script>
