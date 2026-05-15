# Issue duplicate check on create (AI-driven)

## Problem

The "新建问题" modal lets users create issues freely. Teams report frequent duplicates: a user files something that already exists as an open issue, often phrased slightly differently. Today there is no signal until someone notices later.

## Goal

When a user finishes typing the title (or description) in the create-issue modal, compare the new issue against currently-open issues in the same project using an LLM, and show a non-blocking inline warning under the title field listing any similar issues.

## Non-goals

- Blocking the create flow. The warning is advisory; the 创建 button remains active.
- Cross-project duplicate detection. The user explicitly chose project-scoped only.
- Detecting duplicates of already-closed issues. 已关闭 and 已发布 are excluded.
- Fuzzy / Levenshtein client-side similarity. We delegate the judgment to the LLM.
- Bulk de-duplication of existing data. This is a creation-time guardrail only.

## Definitions

**Open issue** — an issue whose `status` is not in `{"已关闭", "已发布"}`. (Decided with the user; 已解决 is treated as open because issues are often re-opened or duplicates filed before resolution propagates.)

**Candidate set** — open issues in the selected project, returning fields `id, title, description, status`. Descriptions are truncated to ~300 characters to bound token usage. Hard cap at 100 candidates (newest first by `-id`); above this we send the most recent 100.

**Check key** — the tuple `(project_id, normalized_title, normalized_description)` used to dedupe repeated calls when the user re-blurs the same content. `normalized_*` is `trim().toLowerCase()`.

## User flow

1. User opens the new-issue modal and picks a project.
2. User types a title and tabs/clicks away → title `@blur` fires.
3. If `project` is set and trimmed title length ≥ 3 and check-key has changed since the last call:
   a. Frontend shows a small inline status under the title field: "正在检查相似问题…"
   b. Frontend POSTs `{project, title, description}` to `/api/issues/check-duplicate/`.
   c. Backend returns `{candidates: [{id, title, status, reason}]}`. May be empty.
4. On result:
   - Empty list → no UI shown, status indicator disappears.
   - Non-empty → render yellow warning box "发现 N 条相似的未关闭问题，请确认是否重复：" followed by clickable rows: `#{id} {title}` with a small status badge and the AI-supplied `reason` underneath. Each row opens `/app/issues/{id}` in a new tab (so the modal state is preserved).
5. If the user edits the title or description after results are shown, the warning clears immediately (stale).
6. When the description `@blur` fires under the same conditions, the same check runs (title + current description).
7. Submitting the form does not depend on the check at all; if the backend is slow or down, creation proceeds normally.

## Architecture

### Backend

**New endpoint:** `POST /api/issues/check-duplicate/`

Mounted on the existing `IssueViewSet` as `@action(detail=False, methods=["post"], url_path="check-duplicate")`. Reuses existing auth/permission stack.

**Request body** (validated by a small serializer):
```json
{
  "project": 12,
  "title": "登录页报 500",
  "description": "点击登录后报错…"
}
```

**Validation / guards** (return `{candidates: []}` without invoking the LLM if any fail):
- `project` is missing or not an integer the user can see.
- `title.strip()` length < 3.
- No candidate issues exist for that project.
- No active `Prompt(slug="issue_duplicate_check")` exists.
- No active `LLMConfig` (default or attached to the prompt) is configured.

**Candidate query:**
```python
Issue.objects.filter(project_id=project_id) \
    .exclude(status__in=["已关闭", "已发布"]) \
    .order_by("-id") \
    .values("id", "title", "description", "status")[:100]
```
Descriptions are truncated to 300 chars in Python before serialization.

**LLM call:** Reuses `apps.ai.client.LLMClient.complete(...)` (OpenAI-compatible). The `Prompt` row provides `system_prompt`, `user_prompt_template`, `llm_model`, `temperature`, and optional `llm_config`. The user-prompt template is filled with three placeholders:
- `{candidates_json}` — JSON array of `{id, title, description, status}` for candidates.
- `{new_title}` — the new issue's title.
- `{new_description}` — the new issue's description (may be empty).

`supports_json_mode=True` on the LLMConfig means we request `response_format={"type": "json_object"}`. Expected model output:
```json
{ "duplicates": [ { "id": 42, "reason": "同样描述登录页 500" } ] }
```

Parsing rules:
- If JSON fails to parse, return `{candidates: []}` (silent fail).
- Filter `duplicates[].id` to ids that exist in the candidate set (defense against hallucinated ids).
- Cap returned matches at 5 (drop the rest after the model has chosen).

**Response shape:**
```json
{
  "candidates": [
    { "id": 42, "title": "登录后出现 500 错误", "status": "进行中", "reason": "同样描述登录页 500" }
  ]
}
```

**Logging / observability:** log the duplicate check as a regular Python log at INFO with `project_id`, `candidate_count`, `match_count`, and timing. Do not persist an `Analysis` row — this is a transient check, not a saved analysis, and the existing `Analysis` model is shaped around saving artifacts to an issue.

**Error handling:**
- Any exception in the LLM call → log at WARNING, return `{candidates: []}`. The user is not made aware of the failure; the modal continues to work.
- Timeouts: bound LLM latency to ~15s (passed to the `openai` client `timeout` parameter — exact wiring is an implementation detail). Do not add custom retries; a single failure returns empty.

### Backend: seeding the prompt

Add a data migration `backend/apps/issues/migrations/00XX_seed_duplicate_check_prompt.py` (or place under `apps/ai/migrations/` since the model lives there — chosen location: `apps/ai/migrations/` to stay close to the model).

The migration uses `apps.get_model("ai", "Prompt")` and calls `Prompt.objects.get_or_create(slug="issue_duplicate_check", defaults={...})` where defaults are loaded from a version-controlled JSON file checked in at `backend/apps/ai/seed_prompts/issue_duplicate_check.json`. The JSON file contains:
- `name`, `system_prompt`, `user_prompt_template`, `llm_model`, `temperature`, `is_active`.
- Does *not* set `llm_config` — falls back to the default `LLMConfig`.

`get_or_create` semantics: on first deploy the row is created from the JSON; on subsequent deploys the existing row is left alone so admin edits in Django admin are preserved. To re-seed after an admin override, an operator deletes the row manually and re-runs migrations (or runs the migration's RunPython forwards function via `manage.py shell`).

The reverse migration deletes the row by slug if it exists.

The JSON is loaded by the migration using `pathlib.Path(__file__).parent.parent / "seed_prompts" / "issue_duplicate_check.json"` so it is bundled with the source tree.

### Backend: prompt content (seed)

System prompt (Chinese, since the product UI is Chinese):
```
你是问题去重助手。给定一组候选问题（包含 id/title/description/status）和一条新问题（title + description），判断候选中哪些与新问题指向同一个 bug 或需求。
只在确实可能重复时返回；语义不同就不要列出。
严格返回 JSON 对象，形如 {"duplicates": [{"id": <int>, "reason": "<不超过 30 字的中文说明>"}]}，最多列出 5 条，按相似度从高到低排序。
没有重复时返回 {"duplicates": []}。
```

User-prompt template:
```
候选问题（JSON）:
{candidates_json}

新问题:
标题: {new_title}
描述: {new_description}
```

Defaults: `llm_model="gpt-4o-mini"`, `temperature=0.2`, `is_active=True`. (The chosen model name only matters as a default; admin can change it.)

### Frontend

Single file: `frontend/app/pages/app/issues/index.vue`.

**State (added inside `<script setup>`):**
```ts
const dupChecking = ref(false)
const dupCandidates = ref<Array<{ id: number; title: string; status: string; reason: string }>>([])
const dupCheckedKey = ref('')
```

**Helpers:**
```ts
function dupCheckKey(): string {
  const p = newIssue.value.project || ''
  const t = newIssue.value.title.trim().toLowerCase()
  const d = (newIssue.value.description || '').trim().toLowerCase()
  return `${p}|${t}|${d}`
}

async function runDuplicateCheck() {
  const projectId = newIssue.value.project
  const title = newIssue.value.title.trim()
  if (!projectId || title.length < 3) {
    dupCandidates.value = []
    return
  }
  const key = dupCheckKey()
  if (key === dupCheckedKey.value) return
  dupCheckedKey.value = key
  dupChecking.value = true
  try {
    const res = await api<{ candidates: Array<{ id: number; title: string; status: string; reason: string }> }>(
      '/api/issues/check-duplicate/',
      { method: 'POST', body: { project: projectId, title, description: newIssue.value.description || '' }, format: 'json' },
    )
    // Only apply if title/desc haven't changed since we kicked this off
    if (dupCheckKey() === key) dupCandidates.value = res.candidates || []
  } catch {
    dupCandidates.value = []
  } finally {
    dupChecking.value = false
  }
}
```

**Invalidation:** add a `watch` on `newIssue.value.title` and `newIssue.value.description` that clears `dupCandidates.value = []` and resets `dupCheckedKey.value = ''` as soon as either changes (so stale results disappear immediately and the next blur will re-check).

**Triggers:** bind `@blur="runDuplicateCheck"` on the title `UInput`. The `MarkdownEditor` component is used for description — we need to confirm it emits a `@blur` event or expose one; if it does not, add a `@blur` to the underlying textarea inside `MarkdownEditor`. (Verification step in implementation: read `MarkdownEditor.vue` to confirm.)

**Reset:** clear `dupCandidates`, `dupCheckedKey`, `dupChecking` inside `resetCreateForm()`.

**UI under the title field** (inserted between the title `UInput` and the description `form-row`):
```vue
<div v-if="dupChecking || dupCandidates.length" class="dup-check">
  <p v-if="dupChecking" class="text-xs text-gray-500">正在检查相似问题…</p>
  <div v-else class="dup-warning">
    <p class="text-sm text-amber-700 dark:text-amber-300">
      发现 {{ dupCandidates.length }} 条相似的未关闭问题，请确认是否重复：
    </p>
    <ul class="mt-1.5 space-y-1">
      <li v-for="c in dupCandidates" :key="c.id" class="text-sm">
        <NuxtLink :to="`/app/issues/${c.id}`" target="_blank" class="text-crystal-600 hover:underline">
          #{{ c.id }} {{ c.title }}
        </NuxtLink>
        <UBadge :color="statusColor(c.status)" variant="subtle" size="xs" class="ml-1.5">{{ c.status }}</UBadge>
        <p class="text-xs text-gray-500 dark:text-gray-400">{{ c.reason }}</p>
      </li>
    </ul>
  </div>
</div>
```

Styling: a yellow/amber `bg-amber-50` block with `border border-amber-200` rounded, padded ~`p-2.5`. Dark-mode equivalents per existing project conventions.

## Edge cases & decisions

| Case | Behavior |
|---|---|
| Project not chosen | Check does not run; nothing shown. |
| Title trimmed length < 3 | Skip; clear stale results. |
| User blurs title without changing it | Skipped via `dupCheckedKey`. |
| Title changes after results shown | Results cleared by the `watch`; new blur will re-check. |
| LLM returns invalid JSON | Treated as empty result. No error UI. |
| LLM hallucinates an id not in candidates | Filtered out by backend. |
| LLM returns >5 matches | Backend truncates to top 5. |
| User cancels modal mid-check | Stale response arrives — discarded because `key` mismatch in the guard at the end of `runDuplicateCheck`. |
| Description very long | Sent in full to the backend; backend truncates only candidates' descriptions, not the new issue's. Reasonable because there is exactly one "new" payload per call. |
| No `Prompt` row / no `LLMConfig` | Backend returns empty; feature silently inactive until admin configures. |

## Testing

Backend (`pytest`, in `backend/tests/test_issues_duplicate_check.py`):
- Returns empty when project absent.
- Returns empty when title too short.
- Returns empty when no candidate issues exist in project.
- Excludes 已关闭 and 已发布 issues from candidates.
- Returns empty when no `Prompt(slug="issue_duplicate_check")` row.
- With a mocked `LLMClient.complete` returning a known JSON payload, returns the enriched candidate list.
- Filters out hallucinated ids the LLM did not see.
- Truncates results to 5.
- LLM raises → endpoint returns `{candidates: []}` and logs at WARNING.

The migration is exercised by the standard pytest-django migration run; no extra test required beyond a smoke test that the row is present after `migrate`.

Frontend: manual verification only (no existing component test infrastructure for this page). Verification steps:
- Open modal, type title without picking a project → no check fires.
- Pick project, type < 3 chars, blur → no check fires.
- Pick project, type ≥ 3 chars matching an open issue's title, blur → warning appears.
- Edit title → warning disappears immediately; blur again → re-checks.
- Blur description → re-runs with title + description.
- Submit while results visible → issue is created, modal closes (no interference).

## Files touched

- `backend/apps/issues/views.py` — new `check_duplicate` action on `IssueViewSet`.
- `backend/apps/issues/serializers.py` — small `DuplicateCheckInputSerializer`.
- `backend/apps/ai/seed_prompts/issue_duplicate_check.json` — version-controlled prompt seed.
- `backend/apps/ai/migrations/00XX_seed_duplicate_check_prompt.py` — data migration with reverse.
- `backend/tests/test_issues_duplicate_check.py` — backend tests.
- `frontend/app/pages/app/issues/index.vue` — state, blur handlers, watch, inline warning UI.
- `frontend/app/components/MarkdownEditor.vue` — *only if* it does not already expose a blur event; verified during implementation.
