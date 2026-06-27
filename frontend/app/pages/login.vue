<template>
  <div class="w-full max-w-sm">
    <div class="text-center mb-8">
      <img src="~/assets/images/logo-icon.svg" alt="DevTrakr" class="w-14 h-14 mx-auto mb-4" />
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">DevTrakr</h1>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">项目管理平台</p>
    </div>

    <form class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl shadow-gray-200/50 dark:shadow-none border border-gray-100 dark:border-gray-800 p-8" @submit.prevent="handleLogin">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-6">登录</h2>
      <div v-if="registered" class="mb-4 p-3 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-900 rounded-lg text-sm text-green-700 dark:text-green-400">
        注册成功，请等待管理员审批后登录
      </div>
      <div class="space-y-4">
        <UFormField label="用户名">
          <UInput v-model="username" placeholder="请输入用户名" icon="i-heroicons-user" size="lg" class="w-full" />
        </UFormField>
        <UFormField label="密码">
          <UInput
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            placeholder="请输入密码"
            icon="i-heroicons-lock-closed"
            size="lg"
            class="w-full"
          >
            <template #trailing>
              <UButton
                color="neutral"
                variant="link"
                size="sm"
                :icon="showPassword ? 'i-heroicons-eye-slash' : 'i-heroicons-eye'"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                :padded="false"
                tabindex="-1"
                @click="showPassword = !showPassword"
              />
            </template>
          </UInput>
        </UFormField>
        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
        <UButton block size="lg" color="primary" :loading="loading" type="submit">登录</UButton>
      </div>
    </form>

    <p class="text-center text-sm text-gray-500 mt-4">
      还没有账号？
      <NuxtLink to="/register" class="text-crystal-500 hover:text-crystal-700 font-medium">去注册</NuxtLink>
    </p>
    <p class="text-center text-xs text-gray-400 mt-6">&copy; 2026 DevTrakr 项目管理平台</p>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth' })

const route = useRoute()
const registered = computed(() => route.query.registered === '1')

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')
const loading = ref(false)

const { setTokens } = useApi()
const { fetchMe } = useAuth()

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    const data = await $fetch<{ access: string; refresh: string }>('/api/auth/login/', {
      method: 'POST',
      body: { username: username.value, password: password.value },
    })
    setTokens(data.access, data.refresh)
    await fetchMe()
    await navigateTo('/app/home')
  } catch (e: any) {
    // 后端重启/尚未就绪时返回 502/503/504(或完全不可达),不应误报为凭证错误
    error.value = isServiceUnavailable(e) ? SERVICE_BUSY_MESSAGE : '用户名或密码错误'
  } finally {
    loading.value = false
  }
}
</script>
