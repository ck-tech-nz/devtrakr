// 站点参照数据(站点设置 / 用户选项 / 项目 / 仓库)在一个会话内基本不变,
// 却被问题列表、问题详情等页面在每次 onMounted 各自重新拉取。这里集中缓存:
// 首次拉取、整会话复用,并发去重。对标 useBulletins 的模块级单例写法。
//
// 用法:页面 onMounted 里 `await useReferenceData().ensureAll()`,随后从
// 返回的 siteSettings / users / developers / projects / repos 读取。
// 数据变更后(如编辑站点标签)调用 refresh() 或直接改 siteSettings.value。

type LoadKey = 'settings' | 'users' | 'projects' | 'repos'

const siteSettings = ref<any>(null)
const users = ref<any[]>([])
const projects = ref<any[]>([])
const repos = ref<any[]>([])

// loaded:某项是否已成功加载(成功才置 true,失败不缓存以便重试)
const loaded: Record<LoadKey, boolean> = { settings: false, users: false, projects: false, repos: false }
// inflight:并发去重——同一项在途时复用同一个 Promise
const inflight: Record<LoadKey, Promise<void> | null> = { settings: null, users: null, projects: null, repos: null }

let apiFn: (<T>(url: string, options?: any) => Promise<T>) | null = null

// 派生:负责人候选限「开发者」组成员(与各页面原有口径一致)
const developers = computed(() => users.value.filter((u: any) => u.groups?.includes('开发者')))

function ensure(key: LoadKey, loader: () => Promise<void>): Promise<void> {
  if (loaded[key]) return Promise.resolve()
  if (inflight[key]) return inflight[key]!
  inflight[key] = (async () => {
    try {
      await loader()
      loaded[key] = true
    } catch {
      // 拉取失败:保留上次数据,不标记已加载,下次进入页面会重试
    } finally {
      inflight[key] = null
    }
  })()
  return inflight[key]!
}

function ensureSettings(): Promise<void> {
  return ensure('settings', async () => {
    siteSettings.value = await apiFn!<any>('/api/settings/')
  })
}
function ensureUsers(): Promise<void> {
  return ensure('users', async () => {
    const data = await apiFn!<any[]>('/api/users/choices/')
    users.value = Array.isArray(data) ? data : []
  })
}
function ensureProjects(): Promise<void> {
  return ensure('projects', async () => {
    const data = await apiFn!<any>('/api/projects/')
    projects.value = data?.results || data || []
  })
}
function ensureRepos(): Promise<void> {
  return ensure('repos', async () => {
    const data = await apiFn!<any>('/api/repos/')
    repos.value = data?.results || data || []
  })
}

function ensureAll(): Promise<void[]> {
  return Promise.all([ensureSettings(), ensureUsers(), ensureProjects(), ensureRepos()])
}

// 强制重新拉取(数据可能已变更,如新建项目 / 改站点设置后)。
function refresh(): Promise<void[]> {
  ;(Object.keys(loaded) as LoadKey[]).forEach((k) => { loaded[k] = false })
  return ensureAll()
}

// 清空缓存(如登出),并保留 apiFn。
function reset(): void {
  ;(Object.keys(loaded) as LoadKey[]).forEach((k) => { loaded[k] = false; inflight[k] = null })
  siteSettings.value = null
  users.value = []
  projects.value = []
  repos.value = []
}

export function useReferenceData() {
  if (!apiFn) {
    const { api } = useApi()
    apiFn = api
  }
  return {
    siteSettings,
    users,
    developers,
    projects,
    repos,
    ensureSettings,
    ensureUsers,
    ensureProjects,
    ensureRepos,
    ensureAll,
    refresh,
    reset,
  }
}
