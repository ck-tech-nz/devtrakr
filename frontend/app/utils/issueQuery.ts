// 问题列表筛选 → 查询参数的纯逻辑,从 issues/index.vue 抽出以便单测。
// 优先级:行内徽标(filterHandler/filterPriorityTag,点击单元格设置)覆盖
// 筛选栏下拉(filterAssignee/filterPriority)。

export interface IssueReporterFilter {
  type: 'reporter' | 'created_by'
  value: string
}

export interface IssueFilterState {
  page: number
  pageSize: number
  showCompleted: boolean
  filterStatus: string
  filterAssignee: string
  filterHandlerId: string | null
  filterPriority: string
  filterPriorityTagValue: string | null
  filterReporter: IssueReporterFilter | null
  search: string
}

export interface PagedIssues {
  results: any[]
  count: number
  next: string | null
}

// 看板按状态分桶需要全量数据:循环拉取所有分页直到 next 为空,
// 否则排序靠后的问题(如创建较早的进行中问题)会被第 1 页截断、永远不显示。
// pageSize 需 ≤ 后端 max_page_size(200)。
export const KANBAN_PAGE_SIZE = 100

export async function fetchAllIssuePages(
  fetchPage: (params: URLSearchParams) => Promise<PagedIssues>,
  baseParams: URLSearchParams,
  pageSize: number = KANBAN_PAGE_SIZE,
): Promise<{ results: any[]; count: number }> {
  const results: any[] = []
  let count = 0
  for (let pageNum = 1; ; pageNum++) {
    const params = new URLSearchParams(baseParams)
    params.set('page', String(pageNum))
    params.set('page_size', String(pageSize))
    const data = await fetchPage(params)
    results.push(...(data.results || []))
    count = data.count ?? results.length
    if (!data.next) break
  }
  return { results, count }
}

export function buildIssueQueryParams(s: IssueFilterState): URLSearchParams {
  const params = new URLSearchParams()
  params.set('page', String(s.page))
  params.set('page_size', String(s.pageSize))
  // 未勾选「显示已完成」且没有显式选状态时,默认排除已关闭/未计划
  if (!s.showCompleted && !s.filterStatus) {
    params.set('exclude_statuses', '已关闭,未计划')
  }
  // 行内处理人徽标优先于筛选栏负责人下拉
  const assigneeId = s.filterHandlerId || s.filterAssignee
  if (assigneeId) params.set('assignee', assigneeId)
  // 行内优先级徽标优先于筛选栏优先级滑块
  const priorityVal = s.filterPriorityTagValue || s.filterPriority
  if (priorityVal) params.set('priority', priorityVal)
  if (s.filterStatus) params.set('status', s.filterStatus)
  if (s.filterReporter) params.set(s.filterReporter.type, s.filterReporter.value)
  const search = s.search.trim()
  if (search) params.set('search', search)
  return params
}
