export type RoadmapStatus = '计划中' | '进行中' | '已完成'
export type RoadmapType = '功能' | '优化' | '修复' | '里程碑'

export interface RoadmapItem {
  id: string
  date: string
  title: string
  description: string
  status: RoadmapStatus
  type: RoadmapType
}

export interface RoadmapData {
  items: RoadmapItem[]
}
