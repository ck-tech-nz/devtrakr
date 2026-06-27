interface MyTask {
  id: number
  title: string
  status: string
  priority: string
  project_name?: string
}

export function useMyTasks() {
  const { api } = useApi()
  const { user, hasGroup } = useAuth()

  const tasks = useState<MyTask[]>('my-tasks', () => [])
  const totalCount = useState<number>('my-tasks-count', () => 0)
  const loading = useState<boolean>('my-tasks-loading', () => false)

  const isTester = computed(() => hasGroup('测试'))

  async function load() {
    if (!user.value || loading.value) return
    loading.value = true
    try {
      // 后端聚合:一次查询返回去重后的精确总数与前 20 条
      // (负责/协助 + 测试组「已发布」口径均在服务端,取代旧的 5~6 个分状态请求)
      const res = await api<{ count: number; results: MyTask[] }>('/api/issues/my-tasks/')
      totalCount.value = res.count ?? 0
      tasks.value = res.results || []
    } catch (e) {
      console.error('Failed to load my tasks:', e)
    } finally {
      loading.value = false
    }
  }

  async function closeIssue(task: MyTask) {
    await api(`/api/issues/${task.id}/close-with-github/`, { method: 'POST' })
    await load()
  }

  return { tasks, totalCount, loading, isTester, load, closeIssue }
}
