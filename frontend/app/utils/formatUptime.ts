export function formatUptime(
  lastUpAt: string | null,
  outageStartedAt: string | null,
  lastStatus: string,
): string {
  if (lastStatus === 'unknown') return '等待首次检查'

  const anchor = lastStatus === 'down' ? outageStartedAt : lastUpAt
  if (!anchor) return '等待首次检查'

  const now = Date.now()
  const then = new Date(anchor).getTime()
  const diffMs = Math.max(0, now - then)
  const minutes = Math.floor(diffMs / 60000)

  const prefix = lastStatus === 'down' ? '已宕机' : '已稳定运行'

  if (minutes < 60) return `${prefix} ${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${prefix} ${hours} 小时`
  const days = Math.floor(hours / 24)
  return `${prefix} ${days} 天`
}
