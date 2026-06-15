# PR ↔ Issue Linking Design

- **Date:** 2026-06-15
- **Status:** Approved (design)
- **Branch:** `feat/markdown-link-hover-preview` (work stays on this branch — other agents are active; do **not** switch branches)

## Goal

Pull GitHub pull requests into DevTrack and link them to internal issues by parsing
`ISS-xxx` references out of the PR title and body, so a viewer can tell whether an
issue has been fixed. When a linked PR is merged, the issue surfaces a non-binding
"suggest resolved" hint with a one-click action to mark the issue resolved.

## Current State (as explored)

- `repos` app has `Repo`, `GitHubIssue`, `Commit`, `GitAuthorAlias`. **No PullRequest model.**
- `GitHubSyncService.sync_repo()` fetches `/repos/{owner}/{repo}/issues?state=all` and
  **explicitly skips PRs** (`if "pull_request" in item: continue`).
- Sync is pull-based polling. `celery-worker` and `celery-beat` run in
  `docker-compose.yml:32-52` (DatabaseScheduler). The periodic task
  `apps.repos.tasks.sync_all_repos` is seeded enabled, hourly
  (`apps/ai/migrations/0002_seed_celery_periodic_tasks.py`). Its body only calls
  `sync_repo`, so **PRs are never synced today** — this plan wires PR sync into that
  same task path.
- GitHub token is stored per-repo in `Repo.github_token` (plaintext, reused as-is).
- `Issue` uses the auto-increment `id`, displayed as `ISS-{id:03d}` (e.g. `ISS-042`).
  Status enum: 未计划 / 待分配 / 待确认 / 进行中 / 已解决 / 已发布 / 已关闭. Completed
  states: **已解决, 已发布, 已关闭**.
- Resolving is a plain `PATCH /api/issues/{id}/ {"status":"已解决"}` (perm
  `issues.change_issue`); the serializer `update()` sets `resolved_at` and freezes the
  KPI `settlement` snapshot (settlement requires an assignee, else it is skipped while
  status still changes). There is no dedicated resolve endpoint.
- Frontend (Nuxt 4 + Nuxt UI). Issue detail: `app/pages/app/issues/[id].vue`
  (sidebar cards, `autoSave()` for status). Repo detail:
  `app/pages/app/repos/[id]/index.vue` (`UTabs` with lazy-loaded tab data).
- The current branch already defines a `GithubPreview` type
  (`app/composables/useLinkPreview.ts`): `kind: 'pr' | 'issue'`,
  `state: 'open' | 'closed' | 'merged'`. New PR shapes must align with it.

## Design Decisions (locked)

1. **Link behavior:** link + display + suggest-on-merge. The system never changes issue
   status automatically.
2. **Match scope:** parse `ISS-xxx` from PR **title + body**.
3. **UI surface:** Issue detail page (linked PRs + suggested-resolved badge) **and** a
   Repo detail "Pull Requests" tab.
4. **Suggestion interaction:** badge **plus** a one-click "accept → mark resolved"
   button that reuses the normal status-change path.
5. **Data model:** dedicated `PullRequest` model; the PR↔Issue link is stored as a
   **JSONField on the PR** (no M2M table), mirroring the existing `Issue.related_issues`
   convention.
6. **Scheduling:** fold PR sync into the existing `sync_all_repos` task — reuse the
   existing hourly schedule, **no new periodic task and no new scheduling migration**.

## Data Model — `repos.PullRequest`

Mirrors `GitHubIssue`. Fields:

| Field | Type | Notes |
|---|---|---|
| `repo` | FK → Repo (CASCADE) | owning repo |
| `number` | PositiveIntegerField | GitHub PR number |
| `title` | CharField | parsed for `ISS-xxx` |
| `body` | TextField | parsed for `ISS-xxx` |
| `state` | CharField | `open` / `closed` / `merged` (derived: `merged_at` set ⇒ `merged`) |
| `merged_at` | DateTimeField (null) | merge time |
| `closed_at` | DateTimeField (null) | close time |
| `base_branch` | CharField | merge target (supports future "merged to main = resolved") |
| `head_branch` | CharField | source branch |
| `author_login` | CharField | GitHub author |
| `author_avatar` | CharField | avatar URL (aligns with `GithubPreview`) |
| `html_url` | CharField | link target |
| `github_created_at` / `github_updated_at` | DateTimeField | GitHub timestamps |
| `synced_at` | DateTimeField | last sync |
| `linked_issues` | **JSONField(default=list)** | parse result, e.g. `[{"id":42,"ref":"ISS-042","source":"title"}]` |

- `unique_together = ("repo", "number")`.
- **GIN index** on `linked_issues` (Postgres) to support
  `linked_issues__contains=[{"id": <issue_id>}]` reverse lookup.
- `Issue.github_issues` (existing M2M) is **untouched** — that is a separate feature.
  PR linkage lives only on the PR side; the issue detail reverse-queries on demand.
- Migration generated via `makemigrations` (never hand-write schema migrations).

## Parsing & "Fixed" Derivation

- Regex: `(?i)\bISS-0*(\d+)\b`. Scan **title** then **body**, dedupe by issue id.
  A hit in the title is recorded as `source:"title"`, otherwise `source:"body"`.
- For each parsed id, keep it only if `Issue.objects.filter(pk=id, is_deleted=False).exists()`.
  Invalid / deleted ids (e.g. a typo `ISS-999`) are dropped — no dangling links.
- `linked_issues` is **recomputed and overwritten on every sync**, so editing a PR title
  self-corrects on the next sync.
- **Suggest-resolved rule:** for a given issue, if **any** linked PR has `state == "merged"`
  **and** the issue is not already in a completed state (已解决/已发布/已关闭), the issue
  detail shows the "suggest resolved" hint. `open` PRs show an in-progress indicator;
  `closed` (not merged) PRs are displayed but produce no suggestion.

## Sync Pipeline

- New `GitHubSyncService.sync_pull_requests(repo)`:
  - `GET /repos/{owner}/{repo}/pulls?state=all&per_page=100`, paginated like the issue
    sync. The list endpoint already returns `merged_at`, so **no per-PR extra request**.
  - `update_or_create` by `(repo, number)`; recompute `linked_issues` each run.
  - Uses `repo.github_token` (same auth as issue sync).
- Wire-in (decision 6): `apps/repos/tasks.py::sync_all_repos` calls
  `sync_pull_requests(repo)` alongside `sync_repo(repo)` in the same loop. The manual
  per-repo sync `RepoSyncView` (`POST /api/repos/{id}/sync/`) likewise syncs both, so one
  "Sync" button pulls issues + PRs. No scheduling migration needed; the hourly periodic
  task already exists.

## API

- `GET /api/repos/{id}/pull-requests/?state=` — list a repo's PRs. `linked_issues` is
  serialized into `{id, title, status}` entries for frontend navigation.
- `GET /api/issues/{id}/pull-requests/` — reverse lookup of PRs linked to an issue via
  `PullRequest.objects.filter(linked_issues__contains=[{"id": issue_id}])`. Response
  includes a computed `suggest_resolved: bool`.
- **Accept action:** no new endpoint. Reuse `PATCH /api/issues/{id}/ {"status":"已解决"}`
  (perm `issues.change_issue`; no-assignee case changes status but skips settlement,
  matching existing behavior).
- Permissions follow existing conventions (`FullDjangoModelPermissions`,
  `repos.view_*` on GET).

## Frontend

### Issue detail (`app/pages/app/issues/[id].vue`)
- New sidebar "Linked PRs" card near the existing GitHub-association card
  (`:494-524`). Loaded in the secondary `onMounted` fetch via
  `GET /api/issues/{id}/pull-requests/`.
- Each PR row: `#number` + title, `state` badge (open→warning, merged→purple,
  closed→gray, reusing existing `UBadge` conventions), click opens `html_url`.
- When `suggest_resolved === true`: a hint bar "关联 PR 已合并 · 建议标记为已解决" with a
  `UButton` "采纳建议" that calls the existing `autoSave({status:'已解决'})` path (same as
  clicking the status chip). After acceptance the hint disappears and the status chip
  refreshes. The button is hidden/disabled without `issues.change_issue`.

### Repo detail (`app/pages/app/repos/[id]/index.vue`)
- Add `{ label: 'Pull Requests', slot: 'pull-requests', value: 'pull-requests' }` to
  `tabItems` (`:481-485`); lazy-load on `watch(activeTab)` via
  `GET /api/repos/{id}/pull-requests/`.
- `UTable` columns: `#number`, title, `state` badge, linked issues (rendered as
  clickable chips → `/app/issues/{id}`), updated time. Optional `state` filter.
- Reuse the page's existing "Sync" button (now also syncs PRs).

### Types
- Align new PR list/detail types with the existing `GithubPreview`
  (`useLinkPreview.ts`) so there is a single PR shape across the app.

## Edge Cases

- PR title/body edited → `linked_issues` recomputed next sync.
- One issue referenced by multiple PRs → all displayed; suggestion triggers if any is merged.
- PR closed without merge → displayed, no suggestion.
- Reference to a non-existent / soft-deleted issue → dropped.
- Pagination 100/page, same as the issue sync.

## Testing (pytest + factory-boy, `backend/tests/`)

- Parser: title-only, body-only, both, multiple ids, zero-padding (`ISS-042`→42),
  case-insensitivity, invalid/deleted id dropped.
- `sync_pull_requests`: `update_or_create` upsert, state derivation
  (open/closed/merged from `merged_at`), `linked_issues` recompute/overwrite on title
  change (mock the GitHub HTTP layer).
- `suggest_resolved`: true only when a merged PR links a non-completed issue; false for
  open/closed-unmerged or already-completed issues.
- API: repo PR list, issue→PR reverse lookup, permission enforcement.
- `sync_all_repos` calls both issue and PR sync.

## Implementation Constraints

- **Stay on `feat/markdown-link-hover-preview`; do not switch/create branches** (other
  agents are working in parallel).
- Backend uses `uv`; migrations via `makemigrations`; never edit existing migrations.
- Frontend UI text and code comments in Chinese (zh-hans).
- Do not silence warnings; surface anything that cannot be safely resolved.

## Out of Scope (YAGNI)

- Auto-changing issue status (explicitly rejected; suggestion only).
- GitHub webhooks / real-time push (keep hourly polling).
- Multi-provider (GitLab/Bitbucket) PR support.
- Branch-name parsing for `ISS-xxx` (title + body only).
- Separate PR sync schedule/frequency (folded into `sync_all_repos`).
- "Merged to which branch = which status" refinement (`base_branch` is stored to enable
  it later, but no logic now).
