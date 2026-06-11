import { describe, it, expect } from 'vitest'
import { buildIssueQueryParams, fetchAllIssuePages, type IssueFilterState, type PagedIssues } from '../app/utils/issueQuery'

function base(over: Partial<IssueFilterState> = {}): IssueFilterState {
  return {
    page: 1,
    pageSize: 20,
    showCompleted: false,
    filterStatus: '',
    filterAssignee: '',
    filterHandlerId: null,
    filterPriority: '',
    filterPriorityTagValue: null,
    filterReporter: null,
    search: '',
    ...over,
  }
}

describe('buildIssueQueryParams', () => {
  it('always sets page and page_size', () => {
    const p = buildIssueQueryParams(base({ page: 3, pageSize: 50 }))
    expect(p.get('page')).toBe('3')
    expect(p.get('page_size')).toBe('50')
  })

  it('excludes completed statuses by default (no showCompleted, no status)', () => {
    const p = buildIssueQueryParams(base())
    expect(p.get('exclude_statuses')).toBe('已关闭,未计划')
  })

  it('drops the exclude_statuses default when showCompleted is on', () => {
    const p = buildIssueQueryParams(base({ showCompleted: true }))
    expect(p.has('exclude_statuses')).toBe(false)
  })

  it('drops the exclude_statuses default when an explicit status is chosen', () => {
    const p = buildIssueQueryParams(base({ filterStatus: '处理中' }))
    expect(p.has('exclude_statuses')).toBe(false)
    expect(p.get('status')).toBe('处理中')
  })

  it('inline handler badge takes precedence over the assignee dropdown', () => {
    const p = buildIssueQueryParams(base({ filterHandlerId: '7', filterAssignee: '99' }))
    expect(p.get('assignee')).toBe('7')
  })

  it('falls back to the assignee dropdown when no handler badge', () => {
    const p = buildIssueQueryParams(base({ filterAssignee: '99' }))
    expect(p.get('assignee')).toBe('99')
  })

  it('inline priority badge takes precedence over the priority slider', () => {
    const p = buildIssueQueryParams(base({ filterPriorityTagValue: 'P0', filterPriority: 'P3' }))
    expect(p.get('priority')).toBe('P0')
  })

  it('falls back to the priority slider when no priority badge', () => {
    const p = buildIssueQueryParams(base({ filterPriority: 'P2' }))
    expect(p.get('priority')).toBe('P2')
  })

  it('maps reporter filter to its own param key (reporter vs created_by)', () => {
    const asReporter = buildIssueQueryParams(base({ filterReporter: { type: 'reporter', value: 'alice' } }))
    expect(asReporter.get('reporter')).toBe('alice')
    expect(asReporter.has('created_by')).toBe(false)

    const asCreatedBy = buildIssueQueryParams(base({ filterReporter: { type: 'created_by', value: '42' } }))
    expect(asCreatedBy.get('created_by')).toBe('42')
    expect(asCreatedBy.has('reporter')).toBe(false)
  })

  it('trims search and omits it when blank', () => {
    expect(buildIssueQueryParams(base({ search: '  bug  ' })).get('search')).toBe('bug')
    expect(buildIssueQueryParams(base({ search: '   ' })).has('search')).toBe(false)
  })

  it('omits optional params entirely when nothing is filtered', () => {
    const p = buildIssueQueryParams(base())
    expect(p.has('assignee')).toBe(false)
    expect(p.has('priority')).toBe(false)
    expect(p.has('status')).toBe(false)
    expect(p.has('search')).toBe(false)
  })
})

describe('fetchAllIssuePages', () => {
  // 伪造分页接口:按调用次数依次返回预设的每一页,并记录每次收到的查询参数
  function pagedFetcher(pages: PagedIssues[]) {
    const calls: URLSearchParams[] = []
    const fetchPage = async (params: URLSearchParams): Promise<PagedIssues> => {
      calls.push(new URLSearchParams(params))
      return pages[calls.length - 1]!
    }
    return { calls, fetchPage }
  }

  it('follows next across pages and concatenates results in order', async () => {
    const { calls, fetchPage } = pagedFetcher([
      { results: [{ id: 1 }, { id: 2 }], count: 5, next: 'p2' },
      { results: [{ id: 3 }, { id: 4 }], count: 5, next: 'p3' },
      { results: [{ id: 5 }], count: 5, next: null },
    ])
    const data = await fetchAllIssuePages(fetchPage, new URLSearchParams('status=进行中'), 2)
    expect(data.results.map(r => r.id)).toEqual([1, 2, 3, 4, 5])
    expect(data.count).toBe(5)
    expect(calls.map(c => c.get('page'))).toEqual(['1', '2', '3'])
    expect(calls.every(c => c.get('page_size') === '2')).toBe(true)
    expect(calls.every(c => c.get('status') === '进行中')).toBe(true)
  })

  it('stops after a single request when next is null', async () => {
    const { calls, fetchPage } = pagedFetcher([
      { results: [{ id: 1 }], count: 1, next: null },
    ])
    const data = await fetchAllIssuePages(fetchPage, new URLSearchParams(), 100)
    expect(data.results.map(r => r.id)).toEqual([1])
    expect(data.count).toBe(1)
    expect(calls.length).toBe(1)
  })

  it('does not mutate the base params', async () => {
    const baseParams = new URLSearchParams('page=9&page_size=15')
    const { fetchPage } = pagedFetcher([
      { results: [], count: 0, next: null },
    ])
    await fetchAllIssuePages(fetchPage, baseParams, 100)
    expect(baseParams.get('page')).toBe('9')
    expect(baseParams.get('page_size')).toBe('15')
  })
})
