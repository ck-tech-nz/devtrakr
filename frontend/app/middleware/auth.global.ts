export default defineNuxtRouteMiddleware(async (to) => {
  if (to.path === '/' || to.path === '/login' || to.path === '/register') return
  if (to.path === '/app/forbidden') return

  const { getToken } = useApi()
  if (!getToken()) {
    return navigateTo('/login')
  }

  const { user, fetchMe, can } = useAuth()
  const { loaded, fetchRoutes, routePermissions, routes, error } = usePagePerms()

  if (!user.value) {
    await fetchMe()
  }

  if (!user.value) {
    return navigateTo('/login')
  }

  if (!loaded.value) {
    await fetchRoutes()
  }

  if (error.value && to.path.startsWith('/app/')) {
    return navigateTo('/app/forbidden')
  }

  // Permission code check — use longest matching prefix so more specific
  // routes (e.g. /app/kpi/me) win over broader ones (/app/kpi)
  const perms = routePermissions.value
  const entries = Object.entries(perms)
    .filter(([prefix]) => to.path === prefix || to.path.startsWith(prefix + '/'))
    .sort((a, b) => b[0].length - a[0].length)
  if (entries.length > 0) {
    const [, perm] = entries[0]!
    if (!can(perm)) {
      return navigateTo('/app/forbidden')
    }
  }

  // meta.adminOnly check
  const isAdmin = user.value.is_superuser || user.value.groups.includes('管理员')
  for (const route of routes.value) {
    if (to.path === route.path || to.path.startsWith(route.path + '/')) {
      if (route.meta?.adminOnly && !isAdmin) {
        return navigateTo('/app/forbidden')
      }
      break
    }
  }
})
