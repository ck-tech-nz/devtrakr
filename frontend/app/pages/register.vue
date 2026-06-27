<template>
  <div class="w-full max-w-sm">
    <div class="text-center mb-8">
      <img src="~/assets/images/logo-icon.svg" alt="DevTrakr" class="w-14 h-14 mx-auto mb-4" />
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">DevTrakr</h1>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">项目管理平台</p>
    </div>

    <form class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl shadow-gray-200/50 dark:shadow-none border border-gray-100 dark:border-gray-800 p-8" @submit.prevent="handleRegister">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-6">注册</h2>
      <div class="space-y-4">
        <UFormField label="用户名" required :error="fieldErrors.username">
          <UInput v-model="form.username" placeholder="请输入用户名" icon="i-heroicons-user" size="lg" class="w-full" />
        </UFormField>
        <UFormField label="密码" required :error="fieldErrors.password">
          <UInput v-model="form.password" type="password" placeholder="请输入密码" icon="i-heroicons-lock-closed" size="lg" class="w-full" />
        </UFormField>
        <UFormField label="确认密码" required :error="fieldErrors.password_confirm">
          <UInput v-model="form.password_confirm" type="password" placeholder="请再次输入密码" icon="i-heroicons-lock-closed" size="lg" class="w-full" />
        </UFormField>
        <UFormField label="昵称" :error="fieldErrors.name">
          <div class="flex gap-2">
            <UInput v-model="form.name" placeholder="请输入昵称" icon="i-heroicons-user-circle" size="lg" class="flex-1" />
            <UButton
              type="button"
              variant="outline"
              color="neutral"
              size="lg"
              :loading="generatingName"
              icon="i-heroicons-sparkles"
              :title="'AI 生成昵称'"
              @click="generateNickname"
            />
          </div>
        </UFormField>
        <UFormField label="邮箱" hint="用于接收通知" :error="fieldErrors.email">
          <UInput v-model="form.email" type="email" placeholder="请输入邮箱" icon="i-heroicons-envelope" size="lg" class="w-full" />
        </UFormField>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">选择头像</label>
          <AvatarPicker v-model="form.avatar" />
        </div>
        <p v-if="fieldErrors._global" class="text-sm text-red-500">{{ fieldErrors._global }}</p>
        <UButton block size="lg" color="primary" :loading="loading" type="submit">注册</UButton>
      </div>
    </form>

    <p class="text-center text-sm text-gray-500 mt-4">
      已有账号？
      <NuxtLink to="/login" class="text-crystal-500 hover:text-crystal-700 font-medium">返回登录</NuxtLink>
    </p>
    <p class="text-center text-xs text-gray-400 mt-6">&copy; 2026 DevTrakr 项目管理平台</p>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth' })

const { randomAvatarId } = useAvatars()

const form = ref({
  username: '',
  password: '',
  password_confirm: '',
  name: '',
  email: '',
  avatar: randomAvatarId(),
})

const fieldErrors = ref<Record<string, string>>({})
const loading = ref(false)
const generatingName = ref(false)
const generatedNames = ref<string[]>([])

async function generateNickname() {
  if (!form.value.username.trim()) {
    fieldErrors.value = { ...fieldErrors.value, name: '请先输入用户名，再生成昵称' }
    return
  }
  fieldErrors.value = { ...fieldErrors.value, name: '' }
  generatingName.value = true
  try {
    const data = await $fetch<{ nickname: string }>('/api/auth/generate-nickname/', {
      method: 'POST',
      body: { username: form.value.username, exclude: generatedNames.value },
    })
    form.value.name = data.nickname
    if (data.nickname) generatedNames.value.push(data.nickname)
  } catch {
    // silently ignore — user can type manually
  } finally {
    generatingName.value = false
  }
}

async function handleRegister() {
  fieldErrors.value = {}
  if (form.value.password !== form.value.password_confirm) {
    fieldErrors.value = { password_confirm: '两次密码输入不一致' }
    return
  }
  loading.value = true
  try {
    await $fetch('/api/auth/register/', {
      method: 'POST',
      body: form.value,
    })
    await navigateTo('/login?registered=1')
  } catch (e: any) {
    // 后端重启/尚未就绪时返回 502/503/504(或完全不可达),提示服务繁忙而非注册失败
    if (isServiceUnavailable(e)) {
      fieldErrors.value = { _global: SERVICE_BUSY_MESSAGE }
      return
    }
    const data = e?.data || e?.response?._data
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      const errors: Record<string, string> = {}
      for (const [k, v] of Object.entries(data)) {
        const msg = Array.isArray(v) ? v.join('；') : String(v)
        // Map known fields; everything else goes to _global
        if (['username', 'password', 'password_confirm', 'name', 'email'].includes(k)) {
          errors[k] = msg
        } else {
          errors._global = (errors._global ? errors._global + '；' : '') + msg
        }
      }
      fieldErrors.value = errors
    } else {
      fieldErrors.value = { _global: '注册失败，请重试' }
    }
  } finally {
    loading.value = false
  }
}
</script>
