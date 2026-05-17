export interface NavItem {
  label: string
  icon: string
  to?: string
  permission?: string
  meta?: Record<string, any>
}

export interface NavGroup {
  label: string
  icon: string
  children: NavItem[]
}

export type NavEntry = NavItem | NavGroup

export function isNavGroup(entry: NavEntry): entry is NavGroup {
  return 'children' in entry
}

// Groups are defined by which paths they collect, in display order.
// The group appears at the position of its first matching child in the route list.
const GROUP_DEFS: { label: string; icon: string; paths: string[] }[] = [
  { label: '项目管理', icon: 'i-heroicons-folder', paths: ['/app/projects', '/app/repos'] },
  { label: '团队效能', icon: 'i-heroicons-chart-bar', paths: ['/app/ai/team-analysis', '/app/ai/plans'] },
  { label: '用户管理', icon: 'i-heroicons-users', paths: ['/app/users', '/app/kpi', '/app/permissions'] },
  { label: '系统管理', icon: 'i-heroicons-cog-6-tooth', paths: ['/app/settings/kpi-scoring', '/app/settings/backups', '/app/api-docs', '/app/about'] },
]

export const useNavigation = () => {
  const { can, hasGroup, user } = useAuth()
  const { routes, loaded } = usePagePerms()
  const isAdmin = computed(() => user.value?.is_superuser || hasGroup('管理员'))

  const navItems = computed<NavItem[]>(() => {
    if (!loaded.value) return []
    return routes.value
      .filter(r => r.show_in_nav && r.is_active)
      .map(r => ({
        label: r.label,
        icon: r.icon,
        to: r.path,
        permission: r.permission ?? undefined,
        meta: r.meta,
      }))
  })

  const homeItem: NavItem = { label: '工作台', icon: 'i-heroicons-home', to: '/app/home' }

  const filteredNavItems = computed(() => {
    if (!user.value) return []
    const items = navItems.value.filter(item => {
      if (item.meta?.superuserOnly && !user.value?.is_superuser) return false
      if (item.meta?.adminOnly && !isAdmin.value) return false
      if (item.permission && !can(item.permission)) return false
      return true
    })
    return [homeItem, ...items]
  })

  // Grouped nav: items belonging to a GROUP_DEF are collapsed under a parent entry.
  // Order follows the original route list (group inserted at position of first matching child).
  const groupedNavItems = computed<NavEntry[]>(() => {
    const items = filteredNavItems.value
    const pathToGroupDef = new Map<string, typeof GROUP_DEFS[0]>()
    for (const def of GROUP_DEFS) {
      for (const path of def.paths) pathToGroupDef.set(path, def)
    }

    const result: NavEntry[] = []
    const emittedGroupLabels = new Set<string>()

    for (const item of items) {
      if (!item.to) { result.push(item); continue }
      const def = pathToGroupDef.get(item.to)
      if (!def) { result.push(item); continue }
      if (emittedGroupLabels.has(def.label)) continue
      emittedGroupLabels.add(def.label)
      const children = def.paths
        .map(p => items.find(i => i.to === p))
        .filter(Boolean) as NavItem[]
      result.push({ label: def.label, icon: def.icon, children })
    }

    return result
  })

  const route = useRoute()
  const currentPath = computed(() => route.path)

  // 不在 navItems 中的独立页面
  const standalonePages: Record<string, string> = {
    '/app/profile': '个人资料',
    '/app/notifications': '通知中心',
  }

  const breadcrumbs = computed(() => {
    const path = route.path
    const crumbs: { label: string; to?: string }[] = [{ label: '首页', to: '/app/home' }]

    // 独立页面直接返回页面标题，不显示"首页"面包屑
    const standaloneName = standalonePages[path]
    if (standaloneName) {
      return [{ label: standaloneName }]
    }

    for (const item of navItems.value) {
      if (item.to === path) {
        crumbs.push({ label: item.label })
        return crumbs
      }
    }

    for (const item of navItems.value) {
      if (item.to && path.startsWith(item.to + '/')) {
        crumbs.push({ label: item.label, to: item.to })
        crumbs.push({ label: '详情' })
        return crumbs
      }
    }

    return crumbs
  })

  return { navItems, filteredNavItems, groupedNavItems, currentPath, breadcrumbs }
}
