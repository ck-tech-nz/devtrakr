interface AuthUser {
  id: string
  username: string
  name: string
  email: string
  avatar: string
  groups: string[]
  permissions: string[]
  settings: Record<string, any>
  is_superuser: boolean
  default_project: { id: string; name: string } | null
  impersonated_by: number | null
  impersonated_by_username: string | null
}

export function useAuth() {
  const user = useState<AuthUser | null>('auth_user', () => null)
  const { api, clearTokens, setTokens } = useApi()
  const { load: loadSettings } = useUserSettings()

  async function fetchMe() {
    try {
      user.value = await api<AuthUser>('/api/auth/me/')
      loadSettings(user.value?.settings)
    } catch {
      user.value = null
    }
  }

  function can(permission: string): boolean {
    return user.value?.permissions.includes(permission) ?? false
  }

  function hasGroup(groupName: string): boolean {
    return user.value?.groups.includes(groupName) ?? false
  }

  function logout() {
    clearTokens()
    user.value = null
    navigateTo('/login')
  }

  // 模拟登录：暂存管理员原 token，换入目标用户 token
  async function impersonate(userId: number | string) {
    // 已处于模拟态则拒绝（防止覆盖暂存的管理员 token）
    if (localStorage.getItem('admin_access_token')) return
    const res = await api<{ access: string; refresh: string }>('/api/auth/impersonate/', {
      method: 'POST',
      body: { user_id: userId },
    })
    // 二次校验：并发/双击下若已被其它调用暂存，则不再覆盖
    if (!localStorage.getItem('admin_access_token')) {
      localStorage.setItem('admin_access_token', localStorage.getItem('access_token') || '')
      localStorage.setItem('admin_refresh_token', localStorage.getItem('refresh_token') || '')
    }
    setTokens(res.access, res.refresh)
    await fetchMe()
    navigateTo('/app/home')
  }

  // 返回管理员：恢复暂存的原 token
  async function stopImpersonation() {
    const adminAccess = localStorage.getItem('admin_access_token')
    const adminRefresh = localStorage.getItem('admin_refresh_token')
    if (!adminAccess || !adminRefresh) {
      // 兜底：暂存丢失则直接登出
      logout()
      return
    }
    setTokens(adminAccess, adminRefresh)
    localStorage.removeItem('admin_access_token')
    localStorage.removeItem('admin_refresh_token')
    await fetchMe()
    navigateTo('/app/users')
  }

  return { user, fetchMe, can, hasGroup, logout, impersonate, stopImpersonation }
}
