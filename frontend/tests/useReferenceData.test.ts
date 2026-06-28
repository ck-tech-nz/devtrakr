// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { useReferenceData } from '../app/composables/useReferenceData'

// useReferenceData 内部自动导入 useApi;替换成可控 mock。
const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
mockNuxtImport('useApi', () => () => ({ api: apiMock }))

function mockEndpoints() {
  apiMock.mockImplementation((url: string) => {
    if (url === '/api/settings/') return Promise.resolve({ labels: { bug: '#f00' }, priorities: [], issue_statuses: [] })
    if (url === '/api/users/choices/') return Promise.resolve([
      { id: 1, name: 'A', groups: ['开发者'] },
      { id: 2, name: 'B', groups: [] },
    ])
    if (url === '/api/projects/') return Promise.resolve({ results: [{ id: 1, name: 'P' }] })
    if (url === '/api/repos/') return Promise.resolve([{ id: 1, name: 'R' }])
    return Promise.resolve(null)
  })
}

function urlCount(url: string): number {
  return apiMock.mock.calls.filter(c => c[0] === url).length
}

beforeEach(() => {
  apiMock.mockReset()
  // 模块级单例:跨用例清空缓存,保证隔离(reset 是面向登出等场景的真实 API)
  useReferenceData().reset()
  mockEndpoints()
})

describe('useReferenceData', () => {
  it('fetches each reference endpoint exactly once across repeated ensureAll calls', async () => {
    const a = useReferenceData()
    await a.ensureAll()
    await a.ensureAll()
    // 模拟第二个页面挂载,拿到的是同一份缓存
    const b = useReferenceData()
    await b.ensureAll()
    await flushPromises()
    expect(urlCount('/api/settings/')).toBe(1)
    expect(urlCount('/api/users/choices/')).toBe(1)
    expect(urlCount('/api/projects/')).toBe(1)
    expect(urlCount('/api/repos/')).toBe(1)
  })

  it('shares loaded data between consumers and normalizes paginated/array shapes', async () => {
    const r = useReferenceData()
    await r.ensureAll()
    await flushPromises()
    expect(r.siteSettings.value?.labels).toEqual({ bug: '#f00' })
    expect(r.projects.value).toEqual([{ id: 1, name: 'P' }]) // 从 {results} 解包
    expect(r.repos.value).toEqual([{ id: 1, name: 'R' }]) // 已是数组
    expect(r.developers.value.map((u: any) => u.id)).toEqual([1]) // 仅「开发者」组
  })

  it('dedups concurrent ensureAll into a single request per endpoint', async () => {
    const r = useReferenceData()
    await Promise.all([r.ensureAll(), r.ensureAll()])
    await flushPromises()
    expect(urlCount('/api/projects/')).toBe(1)
  })

  it('refetches after refresh()', async () => {
    const r = useReferenceData()
    await r.ensureAll()
    await r.refresh()
    await flushPromises()
    expect(urlCount('/api/settings/')).toBe(2)
  })

  it('does not cache a failed fetch and keeps previous data', async () => {
    const r = useReferenceData()
    await r.ensureAll()
    await flushPromises()
    expect(r.projects.value).toEqual([{ id: 1, name: 'P' }])

    // 让 projects 拉取失败,其余成功
    apiMock.mockImplementation((url: string) => {
      if (url === '/api/projects/') return Promise.reject(new Error('boom'))
      if (url === '/api/settings/') return Promise.resolve({ labels: {} })
      if (url === '/api/users/choices/') return Promise.resolve([])
      if (url === '/api/repos/') return Promise.resolve([])
      return Promise.resolve(null)
    })
    await r.refresh()
    await flushPromises()
    // 失败时保留上次数据
    expect(r.projects.value).toEqual([{ id: 1, name: 'P' }])

    // 未标记已加载 → 下次 ensure 会重试
    const before = urlCount('/api/projects/')
    await r.ensureProjects()
    await flushPromises()
    expect(urlCount('/api/projects/')).toBe(before + 1)
  })
})
