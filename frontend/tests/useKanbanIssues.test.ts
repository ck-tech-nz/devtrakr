// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { useKanbanIssues, KANBAN_COLUMN_PAGE_SIZE } from '../app/composables/useKanbanIssues'

// useApi 是 composable 内部的自动导入,替换成可控 mock(同 useBulletins 测试模式)
const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

function page(ids: number[], count: number, hasNext: boolean) {
  return {
    results: ids.map(id => ({ id, status: 's' })),
    count,
    next: hasNext ? 'next-url' : null,
  }
}

// 默认列参数构造:status + page,模拟 index.vue 注入的闭包
function defaultBuild(status: string, pageNum: number): URLSearchParams | null {
  const p = new URLSearchParams()
  p.set('status', status)
  p.set('page', String(pageNum))
  p.set('page_size', String(KANBAN_COLUMN_PAGE_SIZE))
  return p
}

beforeEach(() => {
  apiMock.mockReset()
})

describe('useKanbanIssues', () => {
  it('reset fetches page 1 for each status in parallel and fills column state', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url.includes('status=%E8%BF%9B%E8%A1%8C%E4%B8%AD')) return Promise.resolve(page([1, 2], 30, true))
      return Promise.resolve(page([3], 1, false))
    })
    const k = useKanbanIssues(defaultBuild)
    await k.reset(['进行中', '已解决'])
    await flushPromises()

    const inProgress = k.columns.value['进行中']!
    expect(inProgress.items.map((i: any) => i.id)).toEqual([1, 2])
    expect(inProgress.count).toBe(30)
    expect(inProgress.hasMore).toBe(true)
    expect(inProgress.loading).toBe(false)

    const resolved = k.columns.value['已解决']!
    expect(resolved.items.map((i: any) => i.id)).toEqual([3])
    expect(resolved.count).toBe(1)
    expect(resolved.hasMore).toBe(false)
  })

  it('loadMore appends the next page and dedupes by id', async () => {
    apiMock.mockResolvedValueOnce(page([1, 2], 4, true))
    const k = useKanbanIssues(defaultBuild)
    await k.reset(['进行中'])

    // 第 2 页带一条与第 1 页重复的数据(数据漂移),应去重
    apiMock.mockResolvedValueOnce(page([2, 3, 4], 4, false))
    await k.loadMore('进行中')

    const col = k.columns.value['进行中']!
    expect(col.items.map((i: any) => i.id)).toEqual([1, 2, 3, 4])
    expect(col.hasMore).toBe(false)
    // 第 2 次请求 page=2
    const lastUrl = apiMock.mock.calls.at(-1)![0] as string
    expect(lastUrl).toContain('page=2')
  })

  it('loadMore is a no-op when hasMore is false or column is loading', async () => {
    apiMock.mockResolvedValueOnce(page([1], 1, false))
    const k = useKanbanIssues(defaultBuild)
    await k.reset(['进行中'])
    apiMock.mockClear()

    await k.loadMore('进行中') // hasMore=false
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('a null params builder marks the column empty without fetching', async () => {
    const k = useKanbanIssues(() => null)
    await k.reset(['进行中'])
    expect(apiMock).not.toHaveBeenCalled()
    const col = k.columns.value['进行中']!
    expect(col.items).toEqual([])
    expect(col.count).toBe(0)
    expect(col.hasMore).toBe(false)
    expect(col.loading).toBe(false)
  })

  it('moveCard moves an item across columns, adjusts counts, and rollback restores', async () => {
    apiMock.mockImplementation((url: string) => {
      if (url.includes('page=1') && url.includes('%E8%BF%9B%E8%A1%8C%E4%B8%AD')) return Promise.resolve(page([1, 2], 2, false))
      return Promise.resolve(page([], 0, false))
    })
    const k = useKanbanIssues(defaultBuild)
    await k.reset(['进行中', '已解决'])

    const rollback = k.moveCard(1, '进行中', '已解决')
    expect(k.columns.value['进行中']!.items.map((i: any) => i.id)).toEqual([2])
    expect(k.columns.value['进行中']!.count).toBe(1)
    expect(k.columns.value['已解决']!.items.map((i: any) => i.id)).toEqual([1])
    expect(k.columns.value['已解决']!.count).toBe(1)

    rollback()
    expect(k.columns.value['进行中']!.items.map((i: any) => i.id)).toEqual([1, 2])
    expect(k.columns.value['进行中']!.count).toBe(2)
    expect(k.columns.value['已解决']!.items).toEqual([])
    expect(k.columns.value['已解决']!.count).toBe(0)
  })

  it('a newer reset discards responses from an older in-flight reset', async () => {
    let resolveOld: (v: any) => void
    apiMock.mockImplementationOnce(() => new Promise((r) => { resolveOld = r }))
    const k = useKanbanIssues(defaultBuild)
    const oldReset = k.reset(['进行中'])

    apiMock.mockResolvedValueOnce(page([9], 1, false))
    await k.reset(['进行中'])

    resolveOld!(page([1], 1, false)) // 旧响应迟到,应被丢弃
    await oldReset
    await flushPromises()
    expect(k.columns.value['进行中']!.items.map((i: any) => i.id)).toEqual([9])
  })

  it('reset failure leaves the column empty and not stuck in loading', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    apiMock.mockRejectedValue(new Error('network down'))
    const k = useKanbanIssues(defaultBuild)
    await k.reset(['进行中'])
    await flushPromises()

    const col = k.columns.value['进行中']!
    expect(col.loading).toBe(false)
    expect(col.items).toEqual([])
    expect(errSpy).toHaveBeenCalled()
    errSpy.mockRestore()
  })

  it('loadMore failure keeps existing items and hasMore so the user can retry', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    apiMock.mockResolvedValueOnce(page([1, 2], 4, true))
    const k = useKanbanIssues(defaultBuild)
    await k.reset(['进行中'])

    apiMock.mockRejectedValueOnce(new Error('network down'))
    await k.loadMore('进行中')

    const col = k.columns.value['进行中']!
    expect(col.items.map((i: any) => i.id)).toEqual([1, 2]) // 已有数据不丢
    expect(col.page).toBe(1) // 页码不前进,重试仍取第 2 页
    expect(col.hasMore).toBe(true)
    expect(col.loading).toBe(false)
    errSpy.mockRestore()
  })
})
