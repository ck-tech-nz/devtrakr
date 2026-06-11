export const ISSUE_STATUS = {
  UNPLANNED: '未计划',
  UNASSIGNED: '待分配',
  PENDING_CONFIRMATION: '待确认',
  IN_PROGRESS: '进行中',
  RESOLVED: '已解决',
  PUBLISHED: '已发布',
  CLOSED: '已关闭',
} as const

export type IssueStatusValue = typeof ISSUE_STATUS[keyof typeof ISSUE_STATUS]

export const ISSUE_STATUS_OPTIONS: { label: string; value: IssueStatusValue }[] = [
  { label: '未计划', value: ISSUE_STATUS.UNPLANNED },
  { label: '待分配', value: ISSUE_STATUS.UNASSIGNED },
  { label: '待确认', value: ISSUE_STATUS.PENDING_CONFIRMATION },
  { label: '进行中', value: ISSUE_STATUS.IN_PROGRESS },
  { label: '已解决', value: ISSUE_STATUS.RESOLVED },
  { label: '已发布', value: ISSUE_STATUS.PUBLISHED },
  { label: '已关闭', value: ISSUE_STATUS.CLOSED },
]

export const KANBAN_DEFAULT_COLUMNS: IssueStatusValue[] = [
  ISSUE_STATUS.UNASSIGNED,
  ISSUE_STATUS.PENDING_CONFIRMATION,
  ISSUE_STATUS.IN_PROGRESS,
  ISSUE_STATUS.RESOLVED,
  ISSUE_STATUS.PUBLISHED,
]

export const KANBAN_COMPLETED_LEFT: IssueStatusValue[] = [ISSUE_STATUS.UNPLANNED]
export const KANBAN_COMPLETED_RIGHT: IssueStatusValue[] = [ISSUE_STATUS.CLOSED]

type BadgeColor = 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'error' | 'neutral'

export function statusColor(status: string): BadgeColor {
  switch (status) {
    case ISSUE_STATUS.UNPLANNED: return 'secondary'
    case ISSUE_STATUS.UNASSIGNED: return 'warning'
    case ISSUE_STATUS.PENDING_CONFIRMATION: return 'warning'
    case ISSUE_STATUS.IN_PROGRESS: return 'info'
    case ISSUE_STATUS.RESOLVED: return 'success'
    case ISSUE_STATUS.PUBLISHED: return 'primary'
    default: return 'neutral'
  }
}

// 状态主色已迁移到站点设置(composables/useStatus.ts statusMainColor),此处不再保留硬编码色值
