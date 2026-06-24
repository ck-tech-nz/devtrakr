// 问题列表筛选 → 查询参数的纯逻辑,从 issues/index.vue 抽出以便单测。
// 优先级:行内徽标(filterHandler/filterPriorityTag,点击单元格设置)覆盖
// 筛选栏下拉(filterAssignee/filterPriority)。

export interface IssueReporterFilter {
  // 'reporter'              — 按 reporter 自由文本精确匹配(点击非空提出人单元格)
  // 'created_by'            — 按创建人 id 精确匹配(保留)
  // 'reporter_display_user' — 按「列里显示的提出人」匹配:reporter 文本==该用户显示名,
  //                            或 reporter 为空且 created_by==该用户(提出人下拉 / 只看我提出的)
  type: 'reporter' | 'created_by' | 'reporter_display_user'
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
  // DRF OrderingFilter 的 ordering 值(如 'title' / '-created_at');空串表示用后端默认排序
  ordering?: string
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
  if (s.ordering) params.set('ordering', s.ordering)
  return params
}
