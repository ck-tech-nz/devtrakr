interface AuthUser {
  id: string
  name: string
  email: string
  avatar: string
  groups: string[]
  permissions: string[]
  settings: Record<string, any>
  is_superuser: boolean
  default_project: { id: string; name: string } | null
}

export function useAuth() {
  const user = useState<AuthUser | null>('auth_user', () => null)
  const { api, clearTokens } = useApi()
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

  return { user, fetchMe, can, hasGroup, logout }
}
