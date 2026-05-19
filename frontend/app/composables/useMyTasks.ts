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
      const uid = user.value.id
      const fetches: Promise<any>[] = [
        api<any>(`/api/issues/?assignee=${uid}&status=待分配&page_size=20`),
        api<any>(`/api/issues/?assignee=${uid}&status=进行中&page_size=20`),
        api<any>(`/api/issues/?helpers=${uid}&status=待分配&page_size=20`),
        api<any>(`/api/issues/?helpers=${uid}&status=进行中&page_size=20`),
      ]
      if (isTester.value) {
        fetches.push(api<any>(`/api/issues/?status=已发布&page_size=20`))
      }
      const results = await Promise.all(fetches)
      const seen = new Set<number>()
      const merged: MyTask[] = []
      let total = 0
      for (const res of results) {
        const items = res.results || res || []
        const prevSize = seen.size
        for (const item of items) {
          if (!seen.has(item.id)) { seen.add(item.id); merged.push(item) }
        }
        const batchNew = seen.size - prevSize
        const batchDup = items.length - batchNew
        total += (res.count ?? items.length) - batchDup
      }
      totalCount.value = total
      tasks.value = merged.slice(0, 20)
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
