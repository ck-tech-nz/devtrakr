export function useApi() {
  const getToken = () => localStorage.getItem('access_token')
  const getRefreshToken = () => localStorage.getItem('refresh_token')

  const setTokens = (access: string, refresh: string) => {
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  const clearTokens = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('admin_access_token')
    localStorage.removeItem('admin_refresh_token')
  }

  async function refreshAccessToken(): Promise<string | null> {
    const refresh = getRefreshToken()
    if (!refresh) return null
    try {
      const data = await $fetch<{ access: string }>('/api/auth/refresh/', {
        method: 'POST',
        body: { refresh },
      })
      localStorage.setItem('access_token', data.access)
      return data.access
    } catch {
      // 模拟态下刷新失败（模拟会话短期过期）：恢复管理员会话，而非直接登出
      const adminAccess = localStorage.getItem('admin_access_token')
      const adminRefresh = localStorage.getItem('admin_refresh_token')
      if (adminAccess && adminRefresh) {
        localStorage.setItem('access_token', adminAccess)
        localStorage.setItem('refresh_token', adminRefresh)
        localStorage.removeItem('admin_access_token')
        localStorage.removeItem('admin_refresh_token')
        navigateTo('/app/users')
        return null
      }
      clearTokens()
      navigateTo('/login')
      return null
    }
  }

  async function api<T>(url: string, options: any = {}): Promise<T> {
    const token = getToken()
    const headers: Record<string, string> = {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }

    try {
      return await $fetch<T>(url, { ...options, headers })
    } catch (error: any) {
      if (error?.response?.status === 401 && token) {
        const newToken = await refreshAccessToken()
        if (newToken) {
          return $fetch<T>(url, {
            ...options,
            headers: { ...(options.headers || {}), Authorization: `Bearer ${newToken}` },
          })
        }
      }
      throw error
    }
  }

  return { api, setTokens, clearTokens, getToken }
}
