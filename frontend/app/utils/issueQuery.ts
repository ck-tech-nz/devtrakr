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

// 纯筛选条件部分(不含分页/状态默认排除),看板按列取数时复用
export type IssueFilterOnly = Omit<IssueFilterState, 'page' | 'pageSize' | 'showCompleted'>

export function buildIssueFilterParams(s: IssueFilterOnly): URLSearchParams {
  const params = new URLSearchParams()
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

export function buildIssueQueryParams(s: IssueFilterState): URLSearchParams {
  const params = buildIssueFilterParams(s)
  params.set('page', String(s.page))
  params.set('page_size', String(s.pageSize))
  // 未勾选「显示已完成」且没有显式选状态时,默认排除已关闭/未计划
  if (!s.showCompleted && !s.filterStatus) {
    params.set('exclude_statuses', '已关闭,未计划')
  }
  return params
}
