# AI Issue Creation Wizard — Workbench Redesign

**Date:** 2026-05-15
**Approach:** 3-step guided wizard with SSE-streamed LLM analysis (3-stage prompting)

## Overview

Replace the existing workbench quick-actions bar with a hero AI wizard that guides users — primarily testers — through a structured 3-step Issue creation flow:

1. **Describe** — user types or pastes a problem description (or clicks a scenario chip)
2. **Analyze** — three LLM calls stream progress over SSE: classify → extract → generate
3. **Confirm** — an editable Issue draft card appears; user reviews/edits, then submits

The conversation is **not persisted** — only the resulting Issue is saved. The wizard is shown for **all users** at the top of `/app/home`, with the existing manual "新建 Issue" button kept in the top-right.

Adjacent additions in scope:

- **Default project** mechanism: `SiteSettings.default_project` (system-wide) and `User.default_project` (per-user override), exposed on `/api/auth/me/`, used by the wizard, the existing `/app/issues` create modal, and `/app/profile`.
- **Module** taxonomy: new `SiteSettings.modules` config (admin-managed list) — the AI's "所属模块" pick is constrained to this list. Stored on Issue as `source_meta.module` (no new column).

## Visual & UX Design

### Page Layout (new `/app/home`)

```text
┌────────────────────────────────────────────────────────────┐
│  AI Wizard Hero (new, primary entry)                       │
├────────────────────────────────────────────────────────────┤
│  Stat cards row (existing, restyled with deltas)           │
│  本周已解决 30 ↑12%  待处理 14 ↑3  进行中 10 稳定  总 230 ↑5 │
├────────────────────────────────────────────────────────────┤
│  我的待办        │        提及我的       (existing, restyled)│
├────────────────────────────────────────────────────────────┤
│  最近动态        (existing, restyled)                       │
└────────────────────────────────────────────────────────────┘
```

The existing top quick-actions bar (`新建 Issue` button + search) is removed from the page body. The `新建 Issue` button moves to the right side of the top app header — manual creation path remains available.

### Wizard Hero Anatomy

```text
┌──────────────────────────────────────────────────────────────┐
│ ✦ 你好，凯歌 👋               • 模型已就绪          [模型 ▾]   │
│   AI 助手已就绪 · 描述问题，让 AI 帮你创建 Issue                 │
├──────────────────────────────────────────────────────────────┤
│ ① 描述 ─── ② AI 分析 ─── ③ 确认提交                            │
│                                                              │
│ 🖱按钮无响应  ⬜页面白屏  💾数据未保存  🔗跳转异常  🖼上传异常    │
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ [📁 项目: Post-Loan-Agent ▾]                              │ │
│ │ 描述你发现的问题：在哪个页面、做了什么操作、出现了什么现象？     │ │
│ │                                                          │ │
│ │ [+] [📷]  拖拽·Ctrl+V·Enter   [✦ GPT-4o ▾]  [🔍 AI 分析] │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

- **Project selector** sits inside the textarea wrapper, top-left. Default value = `auth.user.default_project` (falling back to `SiteSettings.default_project` resolved server-side). User can change before submitting.
- **Quick-suggestion chips** (Step 1 only) fill the textarea on click. The 5 starter chips:
  - `🖱 按钮无响应` → "点击提交按钮后页面没有任何反应，按钮无响应"
  - `⬜ 页面白屏` → "页面加载后出现白屏，控制台报错 Cannot read properties of undefined"
  - `💾 数据未保存` → "表单提交后数据没有保存，刷新后内容消失"
  - `🔗 跳转异常` → "通知中心点击待审批事项后跳转到错误页面"
  - `🖼 上传异常` → "上传图片后显示上传成功但图片列表中看不到"
- **Model dropdown** is decorative — backend always uses the active `LLMConfig`. The dropdown is rendered for future-proofing UX but disabled / read-only in Phase 1.
- **Attach buttons** open the existing attachment upload flow. Files upload synchronously to the existing `tools.Attachment` endpoint and their IDs are queued for the final Issue creation. Phase 1 does **not** pass images to the LLM.

### Step 2 — Analyzing State

The textarea container becomes semi-transparent (`opacity: 0.5`), the toolbar disables, and the chips row hides. A loading panel mounts below the textarea:

```text
  ⟳  AI 正在分析…
     ✓ 识别问题类型与影响范围
     ✓ 提取关键字段（标题、优先级、模块）
     ◌ 生成复现步骤与预期行为…
```

The three lines update reactively from SSE `step` events. Each line shows a spinner while pending, ✓ when its `step` event arrives. Failure on any step shows ✗ and surfaces the error inline; the user can click "重试" or "重新描述" to go back to Step 1 with their text preserved.

### Step 3 — Draft Card

Replaces the textarea region. Layout (single column on mobile, 3-col grid on the priority/module/assignee row):

```text
✓ Issue 草稿已生成 · 请确认并编辑后提交        AI 自动填写 6 个字段

  Issue 标题 [AI 生成]
  [ editable input ]

  问题描述
  [ editable textarea — AI-rephrased version of user input ]

  复现步骤 [AI 生成]
  [ editable textarea, multiline ]

  优先级 [AI 推断]      所属模块 [AI 推断]     指派给
  [ P0-P3 select   ]   [ module select   ]   [ user select ]

  预期行为 [AI 生成]                          环境
  [ editable input, span-2 columns        ]   [ env select ]

  ✦ 所有字段均可编辑 · 提交后将自动创建 Issue 并通知相关成员
                              [ 重新描述 ]  [ ✓ 提交 Issue ]
```

The `[AI 生成]` / `[AI 推断]` badges are small blue pill-shaped tags appended to the field label, signaling provenance. `AI 生成` is content the model wrote (text fields); `AI 推断` is a categorical pick from a constrained list (dropdowns).

**Project** does NOT get an AI badge — it's user-chosen on Step 1. The project selector is shown in this draft card as an editable select pre-filled with the Step 1 choice, so the user can still change project at final review.

### Step 3 — Success State

Replaces the body of the draft card (header stays):

```text
✓
Issue 已成功提交！
ISS-236
已自动分配给 凯歌 · 优先级 P2

[ + 继续提交新 Issue ]
```

The success card shows the new ISS-ID (formatted from the response's numeric id), the assignee name, and priority. Clicking "继续提交新 Issue" resets the wizard state machine back to Step 1 with all fields cleared.

Simultaneously, the "我的待办" list below refreshes (re-fetches) so the new Issue appears if it's assigned to the current user. A toast also confirms creation (uses the existing `useDialog` or toast pattern).

### State Machine

```text
idle → describing → analyzing → drafting → submitting → success
                       ↓             ↓
                     error         error
                       ↓             ↓
                    describing   drafting (keeps draft)
```

Transitions:
- `describing → analyzing` — user clicks "AI 分析" (or presses Enter in textarea)
- `analyzing → drafting` — SSE `draft` event received
- `analyzing → describing(error)` — SSE `error` event; textarea content preserved
- `drafting → submitting` — user clicks "提交 Issue"
- `submitting → success` — `POST /api/issues/` returns 201
- `submitting → drafting(error)` — Issue creation fails; inline error shown
- `success → describing` — user clicks "继续提交新 Issue"; all state cleared
- `drafting → describing` — user clicks "重新描述"; draft discarded, textarea content restored

## Backend Design

### New Endpoint — `POST /api/issues/ai-draft/`

SSE streaming. Returns `Content-Type: text/event-stream`.

**Request body:**
```json
{
  "description": "string, required",
  "project": "<project-id>, required",
  "attachment_ids": ["uuid1", "uuid2"]
}
```

**Permission:** `IsAuthenticated`. No special role gate — all logged-in users can use the wizard.

**Response stream — events in order:**

```text
event: step
data: {"step": 1, "label": "识别问题类型与影响范围", "status": "done",
       "result": {"category": "前端 UI", "scope": "通知中心模块"}}

event: step
data: {"step": 2, "label": "提取关键字段", "status": "done",
       "result": {"title": "...", "priority": "P2", "module": "通知中心"}}

event: step
data: {"step": 3, "label": "生成复现步骤与预期行为", "status": "done",
       "result": {"repro_steps": "1. ...\n2. ...", "expected_behavior": "..."}}

event: draft
data: {
  "title": "...",
  "description": "AI 改写后的描述",
  "repro_steps": "...",
  "expected_behavior": "...",
  "priority": "P2",
  "module": "通知中心",
  "labels": ["前端", "Bug"],
  "environment": null
}

event: done
data: {}
```

Failure on any step:
```text
event: error
data: {"step": 2, "code": "llm_timeout", "message": "AI 分析超时，请重试"}
```

After `error`, the stream terminates. No partial Issue is created. The user retries from Step 1.

### Three-Stage Prompting

Each step is a separate LLM call against the existing `LLMClient.complete()`, with three new `Prompt` rows seeded via data migration (mirroring `issue_duplicate_check`):

| Prompt key | System role | Inputs | Output JSON |
|------------|-------------|--------|-------------|
| `wizard_classify` | "你是 issue 分类助手" | user_description | `{category, scope}` |
| `wizard_extract`  | "你是字段抽取助手" | user_description + classify result + available modules | `{title, priority, module}` |
| `wizard_generate` | "你是测试用例生成助手" | user_description + classify + extract results | `{repro_steps, expected_behavior, labels}` |

`labels` (categorical tags like 前端/Bug/性能) is produced by the third stage as part of generation, constrained to `SiteSettings.labels.keys()`.

Each prompt uses OpenAI JSON mode (`response_format={"type": "json_object"}`) for reliable parsing. Temperature: 0.2 (classification/extraction) → 0.5 (generation).

Approximate timing (sequential): step 1 ~1s, step 2 ~1s, step 3 ~2s. Total ~4s. Acceptable for a one-shot interactive flow.

### Service Layer

New file `apps/issues/services_ai_wizard.py`:

```python
class AiWizardService:
    def stream_draft(self, user, description, project_id, attachment_ids):
        """Generator yielding SSE event tuples (event_name, data_dict).
        Raises a typed exception on any LLM failure; views.py catches
        and emits the error event."""
        classify = self._run_classify(description)
        yield ("step", {"step": 1, ...})

        extract = self._run_extract(description, classify, modules)
        yield ("step", {"step": 2, ...})

        gen = self._run_generate(description, classify, extract)
        yield ("step", {"step": 3, ...})

        draft = self._merge(classify, extract, gen)
        yield ("draft", draft)
        yield ("done", {})
```

The view wraps this generator in a `StreamingHttpResponse(content_type="text/event-stream")`, formatting each yield as `event: <name>\ndata: <json>\n\n`. Standard Django; no extra dependencies.

**Important:** Disable response buffering by setting `X-Accel-Buffering: no` header so nginx/whitenoise doesn't hold the stream.

### Issue Field Mapping

Frontend sends `POST /api/issues/` with this body when the user clicks "提交 Issue":

```json
{
  "project": "<project-id>",
  "title": "通知中心待审批跳转异常",
  "description": "AI 改写的问题描述\n\n## 复现步骤\n1. ...\n\n## 预期行为\n应跳转到对应详情页",
  "priority": "P2",
  "labels": ["前端", "Bug"],
  "assignee": "<user-id-or-omit>",
  "reporter": "<current user name>",
  "source": "ai_wizard",
  "source_meta": {
    "module": "通知中心",
    "environment": "Chrome / Windows",
    "original_input": "用户原始输入"
  },
  "attachment_ids": ["uuid1", "uuid2"]
}
```

| Wizard field | Issue field | Notes |
|---|---|---|
| `project` | `project` (FK) | from Step 1 selector |
| `title` | `title` | direct |
| `description` (AI-rephrased) | `description` first paragraph | followed by `## 复现步骤` and `## 预期行为` H2 sections |
| `repro_steps` | embedded in `description` | under `## 复现步骤` |
| `expected_behavior` | embedded in `description` | under `## 预期行为` |
| `priority` | `priority` | P0-P3 |
| `module` | `source_meta.module` | new key |
| `environment` | `source_meta.environment` | new key |
| `assignee` | `assignee` | user-picked, optional |
| `labels` | `labels` | AI-recommended categorical tags |
| `source` | fixed `"ai_wizard"` | for analytics/filtering |
| `attachment_ids` | M2M via existing flow | unchanged |

The Issue detail page renders `description` through the existing markdown renderer — `## 复现步骤` and `## 预期行为` headings appear naturally. The right-column "外部来源" panel (already exists, conditional on `source`) displays `source_meta.module` and `source_meta.environment` as labeled fields.

## Default Project Mechanism

### Data Model Changes

**`SiteSettings` (new field):**
```python
default_project = models.ForeignKey(
    "projects.Project", on_delete=models.SET_NULL,
    null=True, blank=True, verbose_name="默认项目"
)
```
A data migration seeds `default_project_id = 1`.

**`User` (new field, `apps/users/models.py`):**
```python
default_project = models.ForeignKey(
    "projects.Project", on_delete=models.SET_NULL,
    null=True, blank=True, related_name="+", verbose_name="默认项目"
)
```
No bulk backfill — existing users stay null and fall back to `SiteSettings.default_project`.

### Resolution Helper

New `apps/projects/utils.py::get_effective_default_project(user)`:
```python
def get_effective_default_project(user):
    if user and user.default_project_id:
        return user.default_project
    return SiteSettings.get_solo().default_project
```

### API Surface

- **`GET /api/auth/me/`** — response gains:
  ```json
  "default_project": {"id": "1", "name": "Post-Loan-Agent"}
  ```
  Resolved via the helper above. `null` if neither user nor site has one.

- **`PATCH /api/users/me/`** — already exists; adds `default_project` to writable fields. Users update only their own preference.

- **`PATCH /api/settings/`** — already covers SiteSettings; the `default_project` field becomes available via admin and via this endpoint.

### UI Integration

| Surface | Change |
|---|---|
| AI wizard project selector | New control in textarea wrapper; initial value = `user.default_project.id` |
| `/app/issues` new-issue modal (`pages/app/issues/index.vue`) | On modal open, set `newIssue.project = user.default_project.id` if currently empty |
| `/app/profile` | New "默认项目" select control; saves via `PATCH /api/users/me/` |
| `/api/auth/me/` response | Add `default_project` |

## Module Taxonomy

### Data Model

**`SiteSettings` (new field):**
```python
modules = models.JSONField(
    default=default_modules,
    verbose_name="功能模块",
)
```
where:
```python
def default_modules():
    return ["通知中心", "审批流程", "用户管理", "项目管理", "表单", "其他"]
```

### API & Usage

- **`GET /api/settings/`** already exposes the singleton; `modules` is added.
- **`PATCH /api/settings/`** allows admins to edit the modules list.
- The wizard backend fetches `SiteSettings.modules` at the start of each draft stream and passes them to `wizard_extract` as the constrained pick-list for `module`.
- The wizard draft card's "所属模块" dropdown also fetches from `/api/settings/` so admin edits show up everywhere.

### Storage on Issue

Module **does not** create a new column on the Issue model. It lives in `Issue.source_meta["module"]`. The Issue detail page's existing "外部来源" panel (it already iterates `source_meta`) shows it.

If a future need arises for cross-issue module filtering/grouping, we can promote it to a real column or use a JSON path index. Out of scope for Phase 1.

## Frontend Components

### New

- `app/components/AiIssueWizard.vue` — top-level wizard container, owns the state machine and SSE connection
- `app/components/AiIssueWizard/StepDescribe.vue` — Step 1 view
- `app/components/AiIssueWizard/StepAnalyzing.vue` — Step 2 view
- `app/components/AiIssueWizard/StepDraft.vue` — Step 3 view (draft form + success state)
- `app/composables/useAiWizard.ts` — SSE consumer; exposes reactive `state`, `progress`, `draft`, plus `start()`, `submit()`, `reset()`. Uses native `EventSource` or `fetch + ReadableStream` (because `EventSource` doesn't support POST bodies — must use fetch+stream).

### Modified

- `app/pages/app/home.vue` — strip top quick-actions bar; mount `<AiIssueWizard />` at top; keep stats / todos / mentions / recent activity sections below
- `app/components/AppHeader.vue` — relocate "新建 Issue" button to the top-right (or keep there if already)
- `app/pages/app/issues/index.vue` — default new-issue modal's `newIssue.project` from `user.default_project`
- `app/pages/app/profile.vue` — add default project select control

## Restyle Scope (existing sections)

The stat cards, todos, mentions, and recent activity sections keep their data and queries — only **styles** change to match the new visual language shown in the screenshot:

- **Stat cards** become horizontal cards with a small icon top-right and a delta line under the big number (e.g., `↑ 12% 较上周`). The delta requires a small backend addition — see "Open Items" below.
- **My todos** keeps the same data; row styling is tightened (smaller priority dots, smaller font, more compact rows).
- **Mentions** unchanged in data; styling tightened.
- **Recent activity** unchanged in data; styling tightened.
- **提升计划** panel is kept conditionally — moves below the stats row, visible only if `planData` exists. Lower visual weight than the wizard.

## Out of Scope (Phase 2)

- LLM vision (passing screenshots as image content to the model)
- Multi-LLM provider switching (the model dropdown stays decorative)
- Cross-issue analytics on `source_meta.module` (filtering/grouping by module)
- Persisting wizard sessions (currently not persisted)
- Stats deltas backend changes — if too much work for this iteration, ship without deltas (stats cards keep current data shape, no `↑ 12%`)

## Open Items

1. **Stats deltas backend** — does `/api/dashboard/stats/` get extended to return week-over-week deltas (`resolved_this_week_delta`, `pending_delta`, etc.)? Decision deferred to the implementation plan; lightweight enough to include.
2. **Project change on draft card** — confirmed editable in the Step 3 card so user can fix mistakes pre-submit.
3. **"提升计划" section placement** — keep on home for now, just visually de-emphasized. Removal would be a separate UX decision.

## Migration Plan

1. New migration on `apps.settings`: add `default_project` and `modules` JSONField to `SiteSettings`. Data migration seeds `default_project_id = 1` and `modules` to the default list.
2. New migration on `apps.users`: add `default_project` FK to `User`. No backfill.
3. New migration on `apps.ai`: seed 3 new Prompt rows (`wizard_classify`, `wizard_extract`, `wizard_generate`) via JSON files in `apps/ai/seed_prompts/`.

No changes to the `Issue` table.

## Testing

- **Backend** — unit tests for each prompt's JSON parsing, SSE event ordering, error event on LLM failure. Use `pytest-django` and the existing factories.
- **Frontend** — manual smoke test of the 3-step flow + abort/retry. SSE consumption is testable with a mock `fetch` returning a `ReadableStream`.
- **Issue creation integration** — confirm `description` markdown renders correctly on the existing Issue detail page; confirm `source_meta.module` and `source_meta.environment` appear in "外部来源".
