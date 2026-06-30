// 列表筛选条件(负责人/状态/优先级/标签/处理人/提出人),按账号记忆
export type IssuesFilters = {
  assignee?: string
  status?: string
  priority?: string
  priorityTag?: { value: string; label: string } | null
  handler?: { id: string; label: string } | null
  reporter?: { type: 'reporter' | 'created_by' | 'reporter_display_user'; value: string; label: string } | null
}

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
  // ↓ 以下原先存浏览器 localStorage(跨账号共享),改为按账号存服务端:换用户登录回到各自默认
  // 列表(表格)视图被隐藏的列 key 数组
  issues_table_hidden: string[]
  // 列表筛选条件
  issues_filters: IssuesFilters
  // 列表「查看全部(含已完成)」开关
  issues_show_completed: boolean
  // 列表标题列宽(像素),null = 默认自适应
  issues_title_col_width: number | null
  // 问题详情页右侧各卡片的展开/收起(按卡片 key)
  issue_detail_panels: Record<string, boolean>
  // 工作台「我的待办」是否折叠
  pending_tasks_collapsed: boolean
  // AI 工单向导发送方式:enter=回车直发 / modifier=⌘/Ctrl+Enter 发送
  ai_wizard_send_mode: 'enter' | 'modifier'
  // 系统公告(站点告警)已忽略的签名
  system_alert_dismissed: string
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
  // 列表默认隐藏 GitHub Issues 列,其余列显示(沿用迁移前的默认)
  issues_table_hidden: ['github_issues'],
  issues_filters: {},
  issues_show_completed: false,
  issues_title_col_width: null,
  issue_detail_panels: {},
  pending_tasks_collapsed: false,
  ai_wizard_send_mode: 'modifier',
  system_alert_dismissed: '',
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
