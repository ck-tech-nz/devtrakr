export interface PageRouteConfig {
  id: number
  path: string
  label: string
  icon: string
  permission: string | null
  parent: string | null
  is_group: boolean
  show_in_nav: boolean
  sort_order: number
  is_active: boolean
  meta: Record<string, any>
}

export function usePagePerms() {
  const routes = useState<PageRouteConfig[]>('page_routes', () => [])
  const loaded = useState<boolean>('page_routes_loaded', () => false)
  const error = useState<string | null>('page_routes_error', () => null)
  const { api } = useApi()

  async function fetchRoutes() {
    try {
      const response = await api<any>('/api/page-perms/routes/')
      // Handle both paginated and non-paginated responses
      routes.value = Array.isArray(response) ? response : response.results
      loaded.value = true
      error.value = null
    } catch (e: any) {
      error.value = '无法加载页面配置，请刷新重试'
      console.error('Failed to fetch page routes:', e)
    }
  }

  const routePermissions = computed(() => {
    const map: Record<string, string> = {}
    for (const route of routes.value) {
      if (route.permission) {
        map[route.path] = route.permission
      }
    }
    return map
  })

  return { routes, loaded, error, fetchRoutes, routePermissions }
}
