// 相对时间格式化(中文),Mentions / Activity 共用。
export function timeAgo(isoDate: string): string {
  const then = new Date(isoDate)
  if (Number.isNaN(then.getTime())) return '' // 防御无效/缺失时间戳,避免 "NaN 天前"
  const diffMs = Date.now() - then.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} 小时前`
  const diffDay = Math.floor(diffHour / 24)
  return `${diffDay} 天前`
}

// 看板卡片用:今天显示时分,昨天/前天显示文字,更早显示具体日期(跨年带年份)。
export function formatCardTime(isoDate: string): string {
  const d = new Date(isoDate)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const startOfDay = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / 86400000)
  if (diffDays <= 0) return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (diffDays === 1) return '昨天'
  if (diffDays === 2) return '前天'
  const md = `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return d.getFullYear() === now.getFullYear() ? md : `${d.getFullYear()}-${md}`
}
