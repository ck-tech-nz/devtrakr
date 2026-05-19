export function useIssueActions() {
  const { api } = useApi()

  async function claim(issueId: number) {
    return api(`/api/issues/${issueId}/claim/`, { method: 'POST' })
  }

  async function confirm(issueId: number) {
    return api(`/api/issues/${issueId}/confirm/`, { method: 'POST' })
  }

  async function transfer(issueId: number, toUserId: number, reason: string) {
    return api(`/api/issues/${issueId}/transfer/`, {
      method: 'POST',
      body: { to_user: toUserId, reason },
    })
  }

  async function assignTo(issueId: number, toUserId: number) {
    return api(`/api/issues/${issueId}/assign/`, {
      method: 'POST',
      body: { to_user: toUserId },
    })
  }

  return { claim, confirm, transfer, assignTo }
}
