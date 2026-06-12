// @vitest-environment nuxt
import { describe, it, expect } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import KanbanCard from '../app/components/issue/KanbanCard.vue'

function item(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    title: '导入案件后跳转异常',
    priority: 'P1',
    assignee_name: '凯歌',
    ...over,
  }
}

async function mount(it: Record<string, unknown>) {
  return await mountSuspended(KanbanCard, { props: { item: it } })
}

describe('IssueKanbanCard 处理人头像', () => {
  it('有头像 id 时显示头像图片,不再显示首字 flag', async () => {
    const w = await mount(item({ assignee_avatar: 'rubber-duck' }))
    const img = w.find('img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBeTruthy()
    expect(w.text()).not.toContain('凯歌'.slice(0, 1) + '凯歌') // 首字 flag + 全名不再同时出现
    w.unmount()
  })

  it('无头像/未知头像 id 回退首字 flag', async () => {
    for (const avatar of [undefined, '', 'not-an-avatar']) {
      const w = await mount(item({ assignee_avatar: avatar }))
      expect(w.find('img').exists()).toBe(false)
      expect(w.text()).toContain('凯') // 首字 flag
      w.unmount()
    }
  })

  it('无处理人时回退「?」flag 与「-」', async () => {
    const w = await mount(item({ assignee_name: undefined }))
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).toContain('?')
    expect(w.text()).toContain('-')
    w.unmount()
  })
})
