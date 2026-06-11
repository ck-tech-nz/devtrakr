// @vitest-environment nuxt
import { describe, it, expect } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import KanbanBoard from '../app/components/shared/KanbanBoard.vue'
import type { KanbanColumn } from '../app/components/shared/KanbanBoard.vue'

function col(over: Partial<KanbanColumn> = {}): KanbanColumn {
  return {
    key: '进行中',
    label: '进行中',
    items: [{ id: 1 }, { id: 2 }],
    ...over,
  }
}

async function mount(columns: KanbanColumn[], scrollable = true) {
  return await mountSuspended(KanbanBoard, {
    props: { columns, scrollable, draggable: false },
  })
}

describe('SharedKanbanBoard', () => {
  it('不传 count 时列头计数回退 items.length(回归:项目详情页旧用法)', async () => {
    const w = await mount([col()], false)
    expect(w.text()).toContain('2')
    expect(w.text()).toContain('进行中')
    w.unmount()
  })

  it('分页模式列头计数用后端真实 count,而非已加载条数', async () => {
    const w = await mount([col({ count: 37, hasMore: true })])
    expect(w.text()).toContain('37')
    w.unmount()
  })

  it('hasMore 时显示「加载更多」兜底按钮,点击携列 key 触发 loadMore;loading 时显示加载中', async () => {
    const w = await mount([col({ count: 37, hasMore: true })])
    const btn = w.findAll('button').find(b => b.text() === '加载更多')
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('loadMore')).toEqual([['进行中']])

    await w.setProps({ columns: [col({ count: 37, hasMore: true, loading: true })] })
    expect(w.text()).toContain('加载中...')
    expect(w.findAll('button').find(b => b.text() === '加载更多')).toBeUndefined()
    w.unmount()
  })

  it('列内滚动到距底 120px 内触发 loadMore;没到底/没有更多则不触发', async () => {
    const w = await mount([col({ count: 37, hasMore: true })])
    const list = w.find('.space-y-2')
    const el = list.element as HTMLElement
    // happy-dom 没有真实布局,手工伪造滚动几何
    Object.defineProperty(el, 'clientHeight', { value: 500, configurable: true })
    Object.defineProperty(el, 'scrollHeight', { value: 900, configurable: true })

    Object.defineProperty(el, 'scrollTop', { value: 0, configurable: true })
    await list.trigger('scroll')
    expect(w.emitted('loadMore')).toBeUndefined() // 离底 400px,不触发

    Object.defineProperty(el, 'scrollTop', { value: 300, configurable: true })
    await list.trigger('scroll')
    expect(w.emitted('loadMore')).toEqual([['进行中']]) // 离底 100px,触发

    // hasMore=false 后再滚不触发
    await w.setProps({ columns: [col({ count: 2, hasMore: false })] })
    await w.find('.space-y-2').trigger('scroll')
    expect(w.emitted('loadMore')).toHaveLength(1)
    w.unmount()
  })
})
