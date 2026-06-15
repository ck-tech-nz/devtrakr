// @vitest-environment nuxt
import { describe, it, expect } from 'vitest'
import { matchPreviewAnchor } from '../app/composables/useLinkPreview'

function anchor(html: string): HTMLAnchorElement {
  const d = document.createElement('div')
  d.innerHTML = html
  return d.querySelector('a')!
}

describe('matchPreviewAnchor', () => {
  it('matches an issue mention by data-issue-id', () => {
    const a = anchor('<a class="mention-issue" data-issue-id="42" href="/app/issues/42">#问题-042</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'issue', issueId: '42' })
  })

  it('matches an external link to a different host', () => {
    const a = anchor('<a class="external-link" href="https://example.com/docs">x</a>')
    expect(matchPreviewAnchor(a)).toEqual({ type: 'external', url: 'https://example.com/docs' })
  })

  it('does not match a same-host external-link', () => {
    const a = anchor(`<a class="external-link" href="${location.origin}/x">x</a>`)
    expect(matchPreviewAnchor(a)).toBeNull()
  })

  it('returns null for a plain anchor', () => {
    const a = anchor('<a href="/app/issues/3">x</a>')
    expect(matchPreviewAnchor(a)).toBeNull()
  })

  it('returns null for null input', () => {
    expect(matchPreviewAnchor(null)).toBeNull()
  })
})
