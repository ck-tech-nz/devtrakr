interface UserSettings {
  sidebar_auto_collapse: boolean
  issues_view_mode: 'kanban' | 'table'
  project_view_mode: 'kanban' | 'table'
  theme: 'light' | 'dark' | 'auto'
  // 工作台区块布局:有序的 {id, visible} 数组(空数组 = 用默认布局)
  dashboard_layout: { id: string; visible: boolean }[]
  // 看板中被隐藏的状态列(状态值数组),按账号记忆;问题页与项目页各自独立
  issues_kanban_hidden: string[]
  project_kanban_hidden: string[]
}

const defaults: UserSettings = {
  sidebar_auto_collapse: false,
  issues_view_mode: 'table',
  project_view_mode: 'kanban',
  theme: 'light',
  dashboard_layout: [],
  // 问题页看板默认隐藏「未计划/已关闭」(沿用原「查看全部」关闭时的列集);项目页默认全显示
  issues_kanban_hidden: ['未计划', '已关闭'],
  project_kanban_hidden: [],
}

export function useUserSettings() {
  const settings = useState<UserSettings>('user_settings', () => ({ ...defaults }))
  const { api } = useApi()

  function load(raw: Record<string, any> | null | undefined) {
    settings.value = { ...defaults, ...(raw || {}) }
  }

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function save() {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(async () => {
      try {
        await api('/api/auth/me/', {
          method: 'PATCH',
          body: { settings: settings.value },
        })
      } catch (e) {
        console.error('Failed to save user settings:', e)
      }
    }, 500)
  }

  function update<K extends keyof UserSettings>(key: K, value: UserSettings[K]) {
    settings.value = { ...settings.value, [key]: value }
    save()
  }

  return { settings, load, update }
}
