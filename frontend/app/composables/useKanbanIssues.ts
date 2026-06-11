// 看板按列独立分页取数(学 GitHub Projects):每列首屏取 20 条,
// 滚动到底部 loadMore 续取;列头计数用后端返回的真实 count。
// 列查询参数由调用方以闭包注入(buildColumnParams),返回 null 表示该列
// 不取数、置为空列(如用户在状态下拉里筛了别的状态)。

export const KANBAN_COLUMN_PAGE_SIZE = 20

export interface KanbanColumnState {
  items: any[]
  count: number
  page: number
  loading: boolean
  hasMore: boolean
}

interface PagedResponse {
  results: any[]
  count: number
  next: string | null
}

function emptyColumn(): KanbanColumnState {
  return { items: [], count: 0, page: 0, loading: false, hasMore: false }
}

export function useKanbanIssues(
  buildColumnParams: (status: string, page: number) => URLSearchParams | null,
) {
  const { api } = useApi()
  const columns = ref<Record<string, KanbanColumnState>>({})
  // 重置序号:筛选条件连续变化时丢弃旧 reset 的迟到响应
  let resetSeq = 0

  async function fetchColumnPage(status: string, pageNum: number): Promise<PagedResponse | null> {
    const params = buildColumnParams(status, pageNum)
    if (!params) return null
    return await api<PagedResponse>(`/api/issues/?${params.toString()}`)
  }

  async function reset(statuses: string[]) {
    const seq = ++resetSeq
    const next: Record<string, KanbanColumnState> = {}
    for (const s of statuses) next[s] = { ...emptyColumn(), loading: true }
    columns.value = next

    await Promise.all(statuses.map(async (status) => {
      try {
        const data = await fetchColumnPage(status, 1)
        if (seq !== resetSeq) return // 已有更新的 reset,丢弃迟到响应
        const col = columns.value[status]
        if (!col) return
        if (!data) {
          Object.assign(col, emptyColumn())
          return
        }
        col.items = data.results || []
        col.count = data.count ?? col.items.length
        col.page = 1
        col.hasMore = !!data.next
        col.loading = false
      } catch (e) {
        if (seq !== resetSeq) return
        console.error(`Failed to load kanban column ${status}:`, e)
        const col = columns.value[status]
        if (col) col.loading = false
      }
    }))
  }

  async function loadMore(status: string) {
    const seq = resetSeq
    const col = columns.value[status]
    if (!col || col.loading || !col.hasMore) return
    col.loading = true
    try {
      const data = await fetchColumnPage(status, col.page + 1)
      if (seq !== resetSeq) return
      if (!data) {
        col.hasMore = false
        return
      }
      // 翻页期间数据可能漂移(他人改了状态),按 id 去重后追加
      const seen = new Set(col.items.map((i: any) => i.id))
      col.items.push(...(data.results || []).filter((i: any) => !seen.has(i.id)))
      col.count = data.count ?? col.count
      col.page += 1
      col.hasMore = !!data.next
    } catch (e: any) {
      if (seq !== resetSeq) return
      console.error(`Failed to load more for ${status}:`, e)
      // 列在翻页期间收缩(他人拖走/改状态)时,越界页码会被 DRF 以 404 拒绝:
      // 置 hasMore=false 止损,避免每次触底都重发注定失败的请求;其余错误保留重试机会
      if (e?.statusCode === 404 || e?.status === 404 || e?.response?.status === 404) {
        col.hasMore = false
      }
    } finally {
      if (seq === resetSeq) col.loading = false
    }
  }

  // 拖拽乐观迁移:从源列摘出、插到目标列顶部,计数同步增减;返回回滚函数
  function moveCard(itemId: string | number, from: string, to: string): () => void {
    const fromCol = columns.value[from]
    const toCol = columns.value[to]
    if (!fromCol || !toCol) return () => {}
    const idx = fromCol.items.findIndex((i: any) => i.id === itemId)
    if (idx === -1) return () => {}
    const [item] = fromCol.items.splice(idx, 1)
    fromCol.count = Math.max(0, fromCol.count - 1)
    toCol.items.unshift(item)
    toCol.count += 1
    return () => {
      const backIdx = toCol.items.findIndex((i: any) => i.id === itemId)
      if (backIdx !== -1) toCol.items.splice(backIdx, 1)
      toCol.count = Math.max(0, toCol.count - 1)
      fromCol.items.splice(Math.min(idx, fromCol.items.length), 0, item)
      fromCol.count += 1
    }
  }

  return { columns, reset, loadMore, moveCard }
}
