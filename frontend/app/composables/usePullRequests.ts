// PR 行类型,与 useLinkPreview 的 GithubPreview 字段保持一致
export interface LinkedIssueRef {
  id: number
  title: string
  status: string
  ref: string
  source: 'title' | 'body'
}

export interface PullRequestRow {
  id: number
  repo: number
  repo_full_name: string
  number: number
  title: string
  state: 'open' | 'closed' | 'merged'
  merged_at: string | null
  closed_at: string | null
  base_branch: string
  head_branch: string
  author_login: string
  author_avatar: string
  html_url: string
  github_created_at: string
  github_updated_at: string
  linked_issues: LinkedIssueRef[]
}

// PR 状态徽标颜色(open→警告,merged→紫色用 secondary,closed→中性)
export function prStateColor(state: string): 'warning' | 'secondary' | 'neutral' {
  if (state === 'open') return 'warning'
  if (state === 'merged') return 'secondary'
  return 'neutral'
}
