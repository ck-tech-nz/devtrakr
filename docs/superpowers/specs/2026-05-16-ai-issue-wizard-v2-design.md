# AI Issue Wizard v2 — Design

**Status**: Draft for review
**Date**: 2026-05-16
**Owner**: CK
**Supersedes**: `apps/ai/seed_prompts/wizard_classify.json|wizard_extract.json|wizard_generate.json` (the 3-stage pipeline shipped with `0005_seed_wizard_prompts`)

---

## 1. Problem

DevTrack's AI Issue Wizard is meant to help non-engineering staff (customer-success, QA) file
issues that engineers can act on without back-and-forth. The shipped v1 wizard is rarely used
(6 of 196 issues, 3%) and the manual issues that dominate the dataset have predictable quality
gaps:

| Metric (on 196 issues) | Count |
| --- | ---: |
| Empty description | 21 (11%) |
| Description < 100 chars | 83 (42%) |
| Description starts with a screenshot, ≤ 1 line of text | 74 (38%) |
| Contains "复现步骤" / "步骤" | 3 (1.5%) |
| Contains "预期" / "期望" | 4 (2%) |
| Created via AI wizard (`source=ai_wizard`) | 6 (3%) |

Manual issues also exhibit recurring anti-patterns: vague titles ("前端排版异常"), multiple
unrelated bugs combined into one ticket, missing environment/role context, and duplicate
filings (e.g. ID-185/197/198 all describe the same UI bug).

### Why v1 underperforms

- 3 sequential LLM calls (`classify → extract → generate`), each with a 20 s timeout — worst-case
  60 s; users abandon before it finishes.
- No vision. ~38% of inputs are "screenshot + one line" and v1 drops the screenshot entirely.
- No deduplication. v1 never consults existing issues; it produces drafts of duplicates without
  flagging them.
- `follow_up_questions` are surfaced *after* the draft is generated, not used to actually
  improve the draft.

---

## 2. Goals & Non-Goals

### Goals

1. Single ≤ 30 s end-to-end call (target ≤ 10 s typical).
2. Read attached screenshots so the AI can extract page paths, error text, and visible state.
3. Surface likely-duplicate existing issues alongside the draft.
4. Force the "operation → observed → expected" shape into every draft, even when the user
   was terse — and clearly label inferred content with `(推断)`.
5. Extract environment / role / page from the description + screenshots; render it as a
   markdown blockquote in the draft `description`.

### Non-Goals

- Code-scanning the repository to enrich the draft (kept out: slow, and not the value-add we
  need for customer-success staff).
- Vector / embedding search for similar issues. Reuse the existing keyword + LLM
  `check_duplicates` flow.
- Live streaming of partial draft fields. Single `draft` SSE event remains the contract.
- On-prem inference. Local oMLX (Qwen3.6-35B-VL) was benchmarked and rejected: 165 s cold
  start, 9 s warm text-only, 12-18 s with images, and Mac uptime would become a service SPoF.
  See [`reference_omlx_local.md`](../../../.claude/projects/-Users-ck-Git-matrix-devtrack/memory/reference_omlx_local.md).

---

## 3. Architecture

```text
POST /api/issues/ai-draft/  (SSE)
  │
  ├── Validate input (description ≥ 5 chars, project required)
  │
  ├── Parallel (ThreadPoolExecutor, 2 workers):
  │     ┌─ Thread A: vision-capable LLM oneshot call
  │     │     model: configurable (e.g. deepseek-vl, qwen-vl-max)
  │     │     timeout: 25 s
  │     │     input: description + ≤3 base64 images + modules/labels
  │     │     output: structured JSON draft (see §4)
  │     │
  │     └─ Thread B: apps.issues.services.check_duplicates(
  │             project_id, title=description[:50], description
  │           )
  │           reuses existing duplicate-check LLM call, 15 s timeout
  │
  ├── Stream SSE events as each thread finishes (no ordering requirement)
  │
  └── On any error → SSE error event with typed code; client falls back
      to raw description.
```

**Why parallel + reuse `check_duplicates`**: the user explicitly asked to reuse manual-flow
logic. `check_duplicates` is well-tested and surfaces the same warning UX customer-success
already see in the manual create-issue modal. Putting it in parallel keeps end-to-end time
at `max(A, B)` ≈ 6-8 s typical.

---

## 4. Data Contract

### 4.1 Request

```http
POST /api/issues/ai-draft/
Authorization: Bearer <jwt>
Content-Type: application/json
Accept: text/event-stream

{
  "description": "string, ≥ 5 chars",
  "project": "uuid",
  "attachment_ids": ["uuid", ...]   // ≤ 3 used; rest ignored
}
```

### 4.2 SSE Events

| Event | Order | Payload |
| --- | --- | --- |
| `step` | first (always) | `{"step":1,"label":"理解描述与截图","status":"running"}` |
| `duplicates` | when Thread B finishes | `{"items":[{"id":int,"title":str,"status":str,"reason":str}]}` (empty array on failure) |
| `step` | when Thread A finishes | `{"step":1,"label":"理解描述与截图","status":"done"}` |
| `draft` | when Thread A finishes | see §4.3 |
| `done` | last | `{}` |
| `error` | replaces `draft` on failure | `{"code":str,"message":str}` |

### 4.3 `draft` payload

```json
{
  "title": "费用中心提交充值申请后，计费管理列表不显示该申请",
  "description": "<user's raw description>\n\n> 🤖 *AI 推断环境*: dev1 | 超级管理员 | /费用中心/充值",
  "repro_steps": "1. 使用超级管理员账户登录\n2. 进入费用中心-充值与套餐-充值页面\n3. 提交 100 万充值申请 (推断)",
  "expected_behavior": "充值申请应出现在计费管理列表中 (推断)",
  "priority": "P2",
  "module": "费用中心",
  "labels": ["Bug", "前端"],
  "follow_up_questions": [
    "其他角色登录是否复现？",
    "刷新页面后是否出现？"
  ],
  "inferred_env": "dev1 | 超级管理员 | /费用中心/充值"
}
```

**Description assembly** (server-side): `f"{user_description}\n\n> 🤖 *AI 推断环境*: {inferred_env}"`
when `inferred_env` is non-empty; otherwise the raw description is passed through. Markdown
renderer (existing in StepDraft) handles the blockquote highlight.

**`(推断)` suffix**: appended to `repro_steps` lines and `expected_behavior` strings that the
LLM inferred from context (vs. quoted from the user). Encourages the user to verify before
submission and signals to engineers which content is AI-derived.

### 4.4 Error codes

| Code | When | Frontend behavior |
| --- | --- | --- |
| `timeout` | Thread A exceeded 25 s | Show "AI 思考超时，已用原始描述填充。请直接编辑提交。" Pre-fill title from `description[:25]`. |
| `bad_json` | LLM returned non-JSON after 1 retry | Same fallback as `timeout` |
| `vision_failed` | Vision model errored, text fallback succeeded | Soft warning toast: "AI 未能读取截图，已基于文字生成"; draft still delivered |
| `llm_unconfigured` | No active LLMConfig or Prompt | 503 (no SSE stream) — admin must fix |

---

## 5. Prompt Design

### 5.1 New Prompt slug

`wizard_oneshot` — single Prompt row in `apps.ai.Prompt`. Existing v1 slugs
(`wizard_classify`, `wizard_extract`, `wizard_generate`) set to `is_active=False` via the
same migration; **rows preserved for 7 days** as a fast rollback path. After 7 days of
stability, a follow-up cleanup migration deletes them and removes the legacy code branch
(see §7).

### 5.2 System prompt (verbatim, Chinese; lives in `apps/ai/seed_prompts/wizard_oneshot.json`)

```text
你是 R&D 团队的 issue 助手，服务对象是不懂代码的客服 / QA 同事。
他们的描述通常很糙：标题宽泛、截图代替文字、混合多个问题、缺角色/环境信息。
你的任务是把这些粗糙输入变成工程师能立刻处理的高质量 issue draft。

【规则】
1. 标题：动词+对象+触发条件，≤25 字。
   示例：好="费用中心提交充值申请后，计费管理列表不显示该申请"
        差="充值有问题" / "前端排版异常"
2. 复现步骤：从描述+截图中提炼。每条 ≤20 字，1./2./3. 编号。
   如果是从截图推断的步骤，末尾加 (推断)。用户没提的步骤不要编造。
3. 预期行为：1 句话。用户没明说也要基于上下文推断，并标 (推断)。
4. 优先级：
   - P0 阻塞全员 / 影响计费 / 数据丢失
   - P1 核心功能不可用
   - P2 体验 / 局部功能异常
   - P3 文案 / 优化建议
5. 模块：必须从 modules 列表选一个；都不匹配选"其他"。
6. follow_up_questions：列出 1-3 个最关键的缺失信息，每条 ≤25 字。
   优先级：角色 > 环境(dev/test/prod) > 复现频率 > 浏览器 > 数据状态
   如果用户描述里出现多个不相关子问题，第一条必须是
   "建议拆成 N 个独立 issue: A / B / C"。
7. inferred_env：从描述/截图中识别环境/角色/页面路径，写成
   "环境: xx | 角色: xx | 页面: xx"。识别不出留空字符串。
8. labels：从 labels 列表选最多 3 个。

【输出严格 JSON，字段顺序固定】
{"title":"...","priority":"P0|P1|P2|P3","module":"...","repro_steps":"...","expected_behavior":"...","labels":[],"follow_up_questions":[],"inferred_env":""}
不要输出 markdown 代码块，不要输出任何 JSON 以外的文字。
```

### 5.3 User prompt template

```text
用户描述:
{description}

可用模块:
{modules_json}

可用标签:
{labels_json}
```

The image(s) are attached via the multimodal `content` array, not the template.

### 5.4 Field validation (post-LLM, in `services_ai_wizard.py`)

| Field | Rule |
| --- | --- |
| `title` | truncate to 200 chars; reject empty |
| `priority` | must be in `{P0,P1,P2,P3}`; default `P2` |
| `module` | must be in `SiteSettings.modules` or `"其他"` if `"其他"` is in the list, else first module |
| `repro_steps` | truncate to 2000 chars |
| `expected_behavior` | truncate to 500 chars |
| `labels` | filter to `SiteSettings.labels.keys()`; cap at 3 |
| `follow_up_questions` | each ≤ 100 chars; cap at 3 |
| `inferred_env` | truncate to 200 chars |

---

## 6. File-Level Changes

| Path | Action | Notes |
| --- | --- | --- |
| `backend/apps/ai/migrations/0007_add_wizard_oneshot_prompt.py` | new | seeds `wizard_oneshot`; sets v1 slugs `is_active=False` |
| `backend/apps/ai/seed_prompts/wizard_oneshot.json` | new | system+user prompt; seed `llm_model="qwen-vl-max-latest"` (see §10.3) |
| `backend/apps/ai/client.py` | edit | add `complete_multimodal(messages_with_images, ...)` that builds OpenAI-format `content` arrays; reuse for any future VL calls |
| `backend/apps/issues/services_ai_wizard.py` | rewrite | `AiWizardService.oneshot_draft(description, attachments)`; `stream_draft()` orchestrates parallel oneshot + `check_duplicates`; legacy `classify/extract/generate` methods kept behind `if settings.AI_WIZARD_LEGACY` |
| `backend/apps/issues/services.py` | no change | reuse `check_duplicates` as-is |
| `backend/apps/issues/views.py` `IssueAiDraftView` | edit | adapt to new SSE event set; assemble `description` with `inferred_env`; resolve `attachment_ids` to file paths |
| `backend/config/settings.py` | edit | `AI_WIZARD_LEGACY = env.bool("AI_WIZARD_LEGACY", default=False)` |
| `backend/tests/test_ai_wizard.py` | edit | new test cases (see §8) |
| `frontend/app/composables/useAiWizard.ts` | edit | `WizardDraft` type adds `inferred_env`; new `duplicates` ref; `handleFrame` handles `duplicates` event; `INITIAL_STEPS` collapses to 1 entry |
| `frontend/app/components/AiIssueWizard/StepDescribe.vue` | edit | placeholder copy: "描述问题：哪个页面/角色，做了什么，看到什么。可以贴截图——AI 会读取截图内容。" |
| `frontend/app/components/AiIssueWizard/StepAnalyzing.vue` | edit | single progress entry; show "通常 6-8 秒" estimate |
| `frontend/app/components/AiIssueWizard/StepDraft.vue` | edit | render `description` markdown so the AI-env blockquote highlights; show "可能重复" collapsible if `duplicates.length > 0`, with one-click "查看" / "我仍要创建" buttons |
| `frontend/app/components/AiIssueWizard.vue` | edit | thread `duplicates` state into StepDraft |

---

## 7. Rollback / Cleanup

**Within 7 days of merge**:

- New wizard is the active path (`AI_WIZARD_LEGACY=False`).
- v1 prompt rows still exist (`is_active=False`).
- Rollback procedure if metrics regress: set env `AI_WIZARD_LEGACY=True`, toggle the three
  v1 prompt rows back to `is_active=True` via Django admin. No code redeploy needed.

**Day 7+**:

- Cleanup migration `0008_remove_wizard_legacy.py` deletes the v1 prompt rows.
- Code PR removes the `AI_WIZARD_LEGACY` branch, the legacy methods on `AiWizardService`,
  and the `_validate_shape` helper functions that only serve v1.

---

## 8. Testing

### 8.1 Backend unit tests (`backend/tests/test_ai_wizard.py`)

- Happy path: `oneshot_draft` with mocked `LLMClient.complete_multimodal` returning a
  valid JSON — asserts shape and validation.
- Vision-down fallback: `complete_multimodal` raises; service falls back to text-only call
  and prepends a `follow_up_question` warning.
- Timeout: thread A exceeds 25 s → service yields `error` event with `code=timeout`.
- Bad JSON + retry: first call returns non-JSON, retry returns valid JSON → success.
- Bad JSON without recovery: both attempts return non-JSON → `code=bad_json`.
- Parallel ordering: thread B finishes before A → `duplicates` event arrives before `draft`.
- Field validation: out-of-range `priority`, unknown `module`, extra `labels` → all sanitized.
- Empty `attachment_ids`: text-only path; no vision call.

### 8.2 Frontend tests

Skipped — no test infrastructure exists for the wizard composables today; covered by manual QA.

### 8.3 Manual QA replay

Re-run the wizard against six historical issues that exemplify the failure modes the v2 is
designed to fix. For each, capture: time to draft, draft quality (better/same/worse vs the
original), and whether duplicate detection fired.

| ID | Why it's in the set |
| --- | --- |
| 189 | Pure screenshot, no body text — tests vision |
| 195 | Three-in-one compound issue — tests "建议拆成 N 个独立 issue" |
| 197 | Exact duplicate of 198 — tests duplicate detection |
| 184 | Long-form, no screenshot — tests text-only path |
| 192 | Has `agent_platform`-injected env footer — tests env extraction doesn't double-count |
| 176 | Almost only a title ("产品上线规范") — tests sparse-input behavior |

### 8.4 Success metrics (observation window: 7 days post-merge)

- `wizard_oneshot` LLM success rate (`Analysis.status=DONE`) ≥ 95%.
- Share of new issues with `source=ai_wizard` ≥ 15% (vs current 3%).
- p50 wizard latency ≤ 8 s; p95 ≤ 20 s.

---

## 9. Open Questions

- **Image size limits**: enforced at 2 MB per image, 3 images max. Larger images are skipped
  with a warning in `follow_up_questions`. Tune based on what the chosen VL model accepts.

---

## 10. Provider Selection (Validated 2026-05-16)

### 10.1 DeepSeek rejected for vision

The default DeepSeek key (`https://api.deepseek.com/v1`) exposes only `deepseek-v4-flash`
and `deepseek-v4-pro`, both text-only. Any `image_url` content element is rejected with
`unknown variant "image_url", expected "text"`. DeepSeek-VL2 is open-weight on Hugging Face
but not on the public API.

### 10.2 DashScope accepted — measured latency

Tested with a 400×300 PNG screenshot containing Chinese UI text + role + env info, prompt
matching §5.2/5.3:

| Model | Latency (warm) | Quality | JSON format |
| --- | ---: | --- | --- |
| `qwen-vl-max-latest` | 3.8 – 5.3 s | Read "dev1" / 超管 / module correctly | Clean JSON |
| `qwen-vl-plus-latest` | 2.0 s | Misread env as "生产环境" | Wrapped in ` ```json` fence |
| `qwen3-vl-flash` | 2.4 s | Same accuracy as `max`, 50% faster | Wrapped in ` ```json` fence |

All three are well under the 10 s ideal. The existing `parse_json_response` in
[`apps/ai/services.py:23`](../../../backend/apps/ai/services.py) already strips ` ```json `
markdown fences, so the `plus` and `flash` outputs are usable without code changes.

### 10.3 Default model recommendation

- `wizard_oneshot.json` seeds with `llm_model="qwen-vl-max-latest"` (best accuracy on
  small Chinese text, ~5 s).
- `qwen3-vl-flash` is documented in the prompt's admin notes as a faster alternative —
  admin can switch via Django admin without code change if cost or latency dominates.

### 10.4 Admin setup steps

CK to add one `LLMConfig` row via Django admin:

- name: `DashScope`
- base_url: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- api_key: value of `DASHSCOPE_API_KEY` from `backend/.env` (validated working 2026-05-16)
- is_active: `True`, is_default: `False`

Implementation may proceed in parallel — code path is provider-agnostic (configured by
`Prompt.llm_model` + `LLMConfig`); tests mock `LLMClient.complete_multimodal`.
