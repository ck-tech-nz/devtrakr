import type { PageRouteConfig } from './usePagePerms'

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

export const useNavigation = () => {
  const { can, hasGroup, user } = useAuth()
  const { routes, loaded } = usePagePerms()
  const isAdmin = computed(() => user.value?.is_superuser || hasGroup('管理员'))

  // 用户级可见性：superuserOnly / adminOnly / permission
  function canShowForUser(item: { meta?: Record<string, any>; permission?: string }) {
    if (item.meta?.superuserOnly && !user.value?.is_superuser) return false
    if (item.meta?.adminOnly && !isAdmin.value) return false
    if (item.permission && !can(item.permission)) return false
    return true
  }

  const homeItem: NavItem = { label: '工作台', icon: 'i-heroicons-home', to: '/app/home' }

  // navItems: 所有可见叶子，仅按 show_in_nav / is_active 过滤
  // (breadcrumbs 消费这个 list，需要 resolve 跨角色的 label，所以不在这里做用户级 filter)
  const navItems = computed<NavItem[]>(() => {
    if (!loaded.value) return []
    return routes.value
      .filter(r => !r.is_group && r.show_in_nav && r.is_active)
      .map(r => ({
        label: r.label,
        icon: r.icon,
        to: r.path,
        permission: r.permission ?? undefined,
        meta: r.meta,
      }))
  })

  // filteredNavItems: navItems + 用户级 filter —— AppBottomTabBar / forbidden 在用
  const filteredNavItems = computed(() => {
    if (!user.value) return []
    return [homeItem, ...navItems.value.filter(canShowForUser)]
  })

  // 按 DB 里 parent 字段建两级树
  const groupedNavItems = computed<NavEntry[]>(() => {
    if (!loaded.value || !user.value) return [homeItem]

    const visibleLeavesByParent = new Map<string, NavItem[]>()

    // 用同样的可见性规则过滤叶子
    const canShowLeaf = (r: PageRouteConfig) =>
      !r.is_group && r.show_in_nav && r.is_active && canShowForUser({ meta: r.meta, permission: r.permission ?? undefined })

    const toNavItem = (r: PageRouteConfig): NavItem => ({
      label: r.label,
      icon: r.icon,
      to: r.path,
      permission: r.permission ?? undefined,
      meta: r.meta,
    })

    for (const r of routes.value) {
      if (!canShowLeaf(r)) continue
      if (r.parent) {
        const arr = visibleLeavesByParent.get(r.parent) ?? []
        arr.push(toNavItem(r))
        visibleLeavesByParent.set(r.parent, arr)
      }
      // 顶级叶子在主循环里 emit, 这里跳过
    }

    // 遍历 routes 顺序（已按 sort_order 来自后端）合成最终列表
    const result: NavEntry[] = [homeItem]
    const emittedGroups = new Set<string>()

    for (const r of routes.value) {
      if (r.is_group) {
        if (emittedGroups.has(r.path)) continue
        if (!r.show_in_nav || !r.is_active) continue
        const children = visibleLeavesByParent.get(r.path) ?? []
        if (children.length === 0) continue  // 空分组不显示
        result.push({ label: r.label, icon: r.icon, children })
        emittedGroups.add(r.path)
      } else if (!r.parent && canShowLeaf(r)) {
        result.push(toNavItem(r))
      }
    }

    return result
  })

  const route = useRoute()
  const currentPath = computed(() => route.path)

  // 不在 navItems 中的独立页面
  const standalonePages: Record<string, string> = {
    '/app/profile': '个人资料',
    '/app/notifications': '通知中心',
    '/app/kpi/me': '我的 KPI',
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
