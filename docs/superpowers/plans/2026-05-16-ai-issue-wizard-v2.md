# AI Issue Wizard v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the v1 3-stage AI Issue Wizard (`classify → extract → generate`, up to 60 s) with a single vision-capable LLM call (~6-8 s) that reads attached screenshots, dedupes against the existing `check_duplicates` service in parallel, and produces a draft issue customer-success staff can submit directly.

**Architecture:** One `wizard_oneshot` prompt + DashScope `qwen-vl-max-latest`. The `AiWizardService.stream_draft()` runs two threads via `ThreadPoolExecutor` — Thread A calls the vision LLM, Thread B calls the existing `apps.issues.services.check_duplicates`. SSE events stream as each thread finishes. Server-side, the `inferred_env` field returned by the LLM is appended to the user's raw description as a markdown blockquote. v1 prompts and code paths stay on disk behind `AI_WIZARD_LEGACY=False` for a 7-day rollback window.

**Tech Stack:** Django 5 + DRF, Python 3.14, OpenAI Python SDK (multimodal `content` array), `concurrent.futures.ThreadPoolExecutor`, Nuxt 4 / Vue 3 / TypeScript, SSE via `StreamingHttpResponse`.

**Spec:** [docs/superpowers/specs/2026-05-16-ai-issue-wizard-v2-design.md](../specs/2026-05-16-ai-issue-wizard-v2-design.md)

**Branch:** `feat/ai-issue-wizard` (already checked out).

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `backend/apps/ai/client.py` | edit | Add `complete_multimodal(images, …)` that builds the OpenAI multimodal `content` array. |
| `backend/apps/ai/seed_prompts/wizard_oneshot.json` | new | System + user prompt + `llm_model="qwen-vl-max-latest"` + `temperature=0.3`. |
| `backend/apps/ai/migrations/0007_add_wizard_oneshot_prompt.py` | new | Seed `wizard_oneshot`; flip v1 slugs to `is_active=False`. |
| `backend/apps/issues/services_ai_wizard.py` | rewrite | Add `oneshot_draft()`, `_load_image_attachments()`, `_assemble_description()`; rewrite `stream_draft()` to parallel-fan-out + reuse `check_duplicates`; keep v1 methods gated by `settings.AI_WIZARD_LEGACY`. |
| `backend/apps/issues/views.py` | edit | `IssueAiDraftView.post()` reads `attachment_ids`, passes them to `stream_draft()`. |
| `backend/apps/issues/serializers.py` | no change | `AiDraftInputSerializer` already accepts `attachment_ids` ([line 270](../../../backend/apps/issues/serializers.py#L270)). |
| `backend/config/settings.py` | edit | `AI_WIZARD_LEGACY = env.bool("AI_WIZARD_LEGACY", default=False)`. |
| `backend/tests/test_ai_wizard.py` | edit | Append v2 test cases. Leave v1 tests untouched (they will be removed by the day-7 cleanup PR). |
| `frontend/app/composables/useAiWizard.ts` | edit | `WizardDraft` adds `inferred_env`; new `duplicates` ref + handler; `INITIAL_STEPS` → 1 entry. |
| `frontend/app/components/AiIssueWizard.vue` | edit | Thread `duplicates` from `wizard` into `StepDraft`. |
| `frontend/app/components/AiIssueWizard/StepDescribe.vue` | edit | Update placeholder copy. |
| `frontend/app/components/AiIssueWizard/StepAnalyzing.vue` | edit | Show a single progress entry + "通常 6-8 秒" hint. |
| `frontend/app/components/AiIssueWizard/StepDraft.vue` | edit | Render a "可能重复" collapsible above the title field. |

---

## Task 1: Add `complete_multimodal` to `LLMClient`

**Files:**

- Modify: `backend/apps/ai/client.py`
- Test: `backend/tests/test_ai_models.py` (existing file; append)

- [ ] **Step 1: Read the existing test file to see its conventions**

Run: `head -30 backend/tests/test_ai_models.py`
Note the imports and patterns — this is where the new test goes.

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_ai_models.py`:

```python
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
def test_complete_multimodal_builds_openai_content_array():
    """LLMClient.complete_multimodal sends OpenAI-format multimodal messages."""
    from apps.ai.client import LLMClient
    from tests.factories import LLMConfigFactory

    config = LLMConfigFactory(is_default=True, is_active=True)
    client = LLMClient(config)

    captured = {}
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]

    def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_response

    with patch.object(client.client.chat.completions, "create", side_effect=fake_create):
        out = client.complete_multimodal(
            model="qwen-vl-max-latest",
            system_prompt="你是助手",
            user_prompt="看这张图",
            images=[("image/png", b"\x89PNG\r\n\x1a\nfake")],
            temperature=0.3,
            timeout=25,
        )

    assert out == '{"ok": true}'
    messages = captured["messages"]
    assert messages[0] == {"role": "system", "content": "你是助手"}
    user_content = messages[1]["content"]
    assert user_content[0] == {"type": "text", "text": "看这张图"}
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert captured["temperature"] == 0.3
    assert captured["timeout"] == 25


@pytest.mark.django_db
def test_complete_multimodal_with_no_images_falls_back_to_plain_text():
    """When images=[] the user content is a plain string, not a content array.
    This keeps the request compatible with text-only fallback paths."""
    from apps.ai.client import LLMClient
    from tests.factories import LLMConfigFactory

    config = LLMConfigFactory(is_default=True, is_active=True)
    client = LLMClient(config)

    captured = {}
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="text-only ok"))]

    def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_response

    with patch.object(client.client.chat.completions, "create", side_effect=fake_create):
        client.complete_multimodal(
            model="qwen-vl-max-latest",
            system_prompt="s",
            user_prompt="u",
            images=[],
            temperature=0.2,
        )

    # User content is a plain string when there are no images
    assert captured["messages"][1] == {"role": "user", "content": "u"}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_ai_models.py::test_complete_multimodal_builds_openai_content_array tests/test_ai_models.py::test_complete_multimodal_with_no_images_falls_back_to_plain_text -v`
Expected: FAIL with `AttributeError: 'LLMClient' object has no attribute 'complete_multimodal'`.

- [ ] **Step 4: Implement `complete_multimodal`**

Replace the entire contents of `backend/apps/ai/client.py` with:

```python
import base64
import openai
from .models import LLMConfig


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = openai.OpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )

    def complete(self, model: str, system_prompt: str, user_prompt: str, temperature: float, timeout: float | None = None) -> str:
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        if self.config.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def complete_multimodal(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        images: list[tuple[str, bytes]],
        temperature: float,
        timeout: float | None = None,
    ) -> str:
        """Multimodal chat completion.

        `images` is a list of (mime_type, raw_bytes) tuples. When the list is
        empty the user message is sent as a plain string so the same call path
        works for text-only fallback after a vision-model failure.
        """
        if images:
            content: list[dict] = [{"type": "text", "text": user_prompt}]
            for mime, raw in images:
                b64 = base64.b64encode(raw).decode("ascii")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
            user_message = {"role": "user", "content": content}
        else:
            user_message = {"role": "user", "content": user_prompt}

        kwargs = dict(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, user_message],
            temperature=temperature,
        )
        # NOTE: DashScope's compatible-mode rejects response_format=json_object
        # on VL models. We rely on prompt instructions for clean JSON instead.
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_models.py -v -k complete_multimodal`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/ai/client.py backend/tests/test_ai_models.py
git commit -m "feat(ai): add LLMClient.complete_multimodal for vision calls

Builds the OpenAI multimodal content array with base64-inlined images.
Falls back to plain-text content when no images are supplied so the
same code path serves text-only fallback after a vision failure."
```

---

## Task 2: Seed the `wizard_oneshot` prompt and deactivate v1 prompts

**Files:**

- Create: `backend/apps/ai/seed_prompts/wizard_oneshot.json`
- Create: `backend/apps/ai/migrations/0007_add_wizard_oneshot_prompt.py`
- Test: `backend/tests/test_ai_wizard.py` (append)

- [ ] **Step 1: Write the seed JSON**

Create `backend/apps/ai/seed_prompts/wizard_oneshot.json` with the exact content below. Note: the system_prompt is the verbatim §5.2 text from the spec; the user prompt template matches §5.3.

```json
{
  "name": "向导：单次多模态草稿",
  "slug": "wizard_oneshot",
  "system_prompt": "你是 R&D 团队的 issue 助手，服务对象是不懂代码的客服 / QA 同事。\n他们的描述通常很糙：标题宽泛、截图代替文字、混合多个问题、缺角色/环境信息。\n你的任务是把这些粗糙输入变成工程师能立刻处理的高质量 issue draft。\n\n【规则】\n1. 标题：动词+对象+触发条件，≤25 字。\n   示例：好=\"费用中心提交充值申请后，计费管理列表不显示该申请\"\n        差=\"充值有问题\" / \"前端排版异常\"\n2. 复现步骤：从描述+截图中提炼。每条 ≤20 字，1./2./3. 编号。\n   如果是从截图推断的步骤，末尾加 (推断)。用户没提的步骤不要编造。\n3. 预期行为：1 句话。用户没明说也要基于上下文推断，并标 (推断)。\n4. 优先级：\n   - P0 阻塞全员 / 影响计费 / 数据丢失\n   - P1 核心功能不可用\n   - P2 体验 / 局部功能异常\n   - P3 文案 / 优化建议\n5. 模块：必须从 modules 列表选一个；都不匹配选\"其他\"。\n6. follow_up_questions：列出 1-3 个最关键的缺失信息，每条 ≤25 字。\n   优先级：角色 > 环境(dev/test/prod) > 复现频率 > 浏览器 > 数据状态\n   如果用户描述里出现多个不相关子问题，第一条必须是\n   \"建议拆成 N 个独立 issue: A / B / C\"。\n7. inferred_env：从描述/截图中识别环境/角色/页面路径，写成\n   \"环境: xx | 角色: xx | 页面: xx\"。识别不出留空字符串。\n8. labels：从 labels 列表选最多 3 个。\n\n【输出严格 JSON，字段顺序固定】\n{\"title\":\"...\",\"priority\":\"P0|P1|P2|P3\",\"module\":\"...\",\"repro_steps\":\"...\",\"expected_behavior\":\"...\",\"labels\":[],\"follow_up_questions\":[],\"inferred_env\":\"\"}\n不要输出 markdown 代码块，不要输出任何 JSON 以外的文字。",
  "user_prompt_template": "用户描述:\n{description}\n\n可用模块:\n{modules_json}\n\n可用标签:\n{labels_json}",
  "llm_model": "qwen-vl-max-latest",
  "temperature": 0.3,
  "is_active": true
}
```

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_wizard_oneshot_is_seeded_and_v1_is_deactivated():
    """After migration 0007 the v2 prompt is active and v1 prompts are inactive."""
    oneshot = Prompt.objects.filter(slug="wizard_oneshot").first()
    assert oneshot is not None, "wizard_oneshot not seeded"
    assert oneshot.is_active
    assert oneshot.llm_model == "qwen-vl-max-latest"
    assert "复现步骤" in oneshot.system_prompt
    assert "{description}" in oneshot.user_prompt_template
    assert "{modules_json}" in oneshot.user_prompt_template
    assert "{labels_json}" in oneshot.user_prompt_template

    # v1 prompts must still exist (kept for 7-day rollback) but inactive
    for v1_slug in ("wizard_classify", "wizard_extract", "wizard_generate"):
        p = Prompt.objects.filter(slug=v1_slug).first()
        assert p is not None, f"v1 prompt {v1_slug} must be preserved for rollback"
        assert not p.is_active, f"v1 prompt {v1_slug} must be deactivated"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_wizard_oneshot_is_seeded_and_v1_is_deactivated -v`
Expected: FAIL with `AssertionError: wizard_oneshot not seeded`.

- [ ] **Step 4: Write the migration**

Create `backend/apps/ai/migrations/0007_add_wizard_oneshot_prompt.py`:

```python
import json
from pathlib import Path

from django.db import migrations


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
V1_SLUGS = ("wizard_classify", "wizard_extract", "wizard_generate")
V2_SLUG = "wizard_oneshot"


def seed_oneshot_and_deactivate_v1(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    data = json.loads((SEED_DIR / f"{V2_SLUG}.json").read_text(encoding="utf-8"))
    Prompt.objects.update_or_create(
        slug=V2_SLUG,
        defaults={
            "name": data["name"],
            "system_prompt": data["system_prompt"],
            "user_prompt_template": data["user_prompt_template"],
            "llm_model": data["llm_model"],
            "temperature": data["temperature"],
            "is_active": data["is_active"],
        },
    )
    # v1 rows preserved for 7-day rollback window; only flip is_active off.
    Prompt.objects.filter(slug__in=V1_SLUGS).update(is_active=False)


def reverse_oneshot_and_reactivate_v1(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug=V2_SLUG).delete()
    Prompt.objects.filter(slug__in=V1_SLUGS).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0006_update_wizard_generate_prompt"),
    ]

    operations = [
        migrations.RunPython(
            seed_oneshot_and_deactivate_v1,
            reverse_code=reverse_oneshot_and_reactivate_v1,
        ),
    ]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_wizard_oneshot_is_seeded_and_v1_is_deactivated -v`
Expected: PASS.

Also confirm the legacy tests still pass since they only assert the v1 rows *exist*, not that they are active:

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_wizard_prompts_are_seeded -v`

Expected: This will now FAIL because the legacy test asserts `is_active is True`. That is correct — we need to update it.

- [ ] **Step 6: Update the legacy seed-test to tolerate the deactivation**

Modify `backend/tests/test_ai_wizard.py:6-13` from:

```python
@pytest.mark.django_db
def test_wizard_prompts_are_seeded():
    for slug in ("wizard_classify", "wizard_extract", "wizard_generate"):
        p = Prompt.objects.filter(slug=slug).first()
        assert p is not None, f"Prompt '{slug}' not seeded"
        assert p.is_active, f"Prompt '{slug}' should be active"
        assert p.system_prompt.strip(), f"Prompt '{slug}' has empty system_prompt"
        assert p.user_prompt_template.strip(), f"Prompt '{slug}' has empty user_prompt_template"
```

To:

```python
@pytest.mark.django_db
def test_wizard_v1_prompts_still_exist_for_rollback():
    """v1 prompts are kept (deactivated) for the 7-day rollback window."""
    for slug in ("wizard_classify", "wizard_extract", "wizard_generate"):
        p = Prompt.objects.filter(slug=slug).first()
        assert p is not None, f"v1 Prompt '{slug}' must be preserved for rollback"
        assert not p.is_active, f"v1 Prompt '{slug}' must be deactivated by migration 0007"
        assert p.system_prompt.strip(), f"Prompt '{slug}' has empty system_prompt"
        assert p.user_prompt_template.strip(), f"Prompt '{slug}' has empty user_prompt_template"
```

- [ ] **Step 7: Run the full test file to verify**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v -k "wizard_v1_prompts or wizard_oneshot_is_seeded"`
Expected: Both pass.

Also run the migration check:

Run: `cd backend && uv run python manage.py migrate --plan | tail -10`
Expected: shows `ai.0007_add_wizard_oneshot_prompt` in the plan when running on a database that has not yet applied it.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/ai/seed_prompts/wizard_oneshot.json \
        backend/apps/ai/migrations/0007_add_wizard_oneshot_prompt.py \
        backend/tests/test_ai_wizard.py
git commit -m "feat(ai): seed wizard_oneshot prompt; deactivate v1 slugs

Migration 0007 inserts the consolidated single-call prompt and flips the
three v1 slugs to is_active=False. v1 rows are preserved so a Django admin
toggle can restore the legacy path during the 7-day rollback window."
```

---

## Task 3: Implement `AiWizardService.oneshot_draft`

**Files:**

- Modify: `backend/apps/issues/services_ai_wizard.py`
- Test: `backend/tests/test_ai_wizard.py` (append)

- [ ] **Step 1: Write the failing happy-path test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_oneshot_draft_happy_path(site_settings):
    """oneshot_draft returns a validated structured dict from a clean LLM JSON."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(
        modules=["费用中心", "其他"],
        labels={
            "Bug": {"foreground": "#fff", "background": "#d00", "description": ""},
            "前端": {"foreground": "#fff", "background": "#000", "description": ""},
        },
    )

    fake = (
        '{"title": "费用中心提交充值后不显示", '
        '"priority": "P1", "module": "费用中心", '
        '"repro_steps": "1. 登录\\n2. 提交充值\\n3. 查看列表 (推断)", '
        '"expected_behavior": "应显示充值申请 (推断)", '
        '"labels": ["Bug", "前端"], '
        '"follow_up_questions": ["复现频率？"], '
        '"inferred_env": "dev1 | 超管 | /finance"}'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=fake,
    ):
        svc = AiWizardService()
        result = svc.oneshot_draft(description="充值不显示", images=[])

    assert result["title"] == "费用中心提交充值后不显示"
    assert result["priority"] == "P1"
    assert result["module"] == "费用中心"
    assert "1. 登录" in result["repro_steps"]
    assert result["labels"] == ["Bug", "前端"]
    assert result["follow_up_questions"] == ["复现频率？"]
    assert result["inferred_env"] == "dev1 | 超管 | /finance"


@pytest.mark.django_db
def test_oneshot_draft_sanitises_bad_priority_and_module(site_settings):
    """LLM-returned junk values are sanitised; never leak to caller."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(
        modules=["费用中心", "其他"],
        labels={"Bug": {"foreground": "#fff", "background": "#d00", "description": ""}},
    )

    fake = (
        '{"title": "x", "priority": "HIGH", "module": "未知模块", '
        '"repro_steps": "", "expected_behavior": "", '
        '"labels": ["Bug", "bogus"], "follow_up_questions": [], "inferred_env": ""}'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=fake,
    ):
        svc = AiWizardService()
        result = svc.oneshot_draft("d", [])

    assert result["priority"] == "P2"            # HIGH → default P2
    assert result["module"] == "其他"             # unknown → 其他 (in modules list)
    assert result["labels"] == ["Bug"]           # bogus filtered out


@pytest.mark.django_db
def test_oneshot_draft_strips_json_markdown_fence(site_settings):
    """When the LLM wraps output in ```json fences (qwen-vl-plus/flash habit),
    parse_json_response strips them."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})

    fake = (
        '```json\n{"title": "T", "priority": "P2", "module": "其他", '
        '"repro_steps": "1. x", "expected_behavior": "y", '
        '"labels": [], "follow_up_questions": [], "inferred_env": ""}\n```'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=fake,
    ):
        svc = AiWizardService()
        result = svc.oneshot_draft("d", [])

    assert result["title"] == "T"


@pytest.mark.django_db
def test_oneshot_draft_retries_once_on_bad_json(site_settings):
    """First call returns garbage; second call returns valid JSON; succeeds."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})

    responses = iter([
        "not json at all",
        '{"title": "T", "priority": "P2", "module": "其他", '
        '"repro_steps": "", "expected_behavior": "", '
        '"labels": [], "follow_up_questions": [], "inferred_env": ""}',
    ])

    def fake_mm(self, **kwargs):
        return next(responses)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        new=fake_mm,
    ):
        svc = AiWizardService()
        result = svc.oneshot_draft("d", [])

    assert result["title"] == "T"


@pytest.mark.django_db
def test_oneshot_draft_raises_after_two_bad_json_attempts(site_settings):
    """Both attempts return non-JSON → raises AiWizardError(code=llm_bad_json)."""
    from apps.issues.services_ai_wizard import AiWizardService, AiWizardError
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value="still not json",
    ):
        svc = AiWizardService()
        with pytest.raises(AiWizardError) as exc:
            svc.oneshot_draft("d", [])
    assert exc.value.code == "llm_bad_json"


@pytest.mark.django_db
def test_oneshot_draft_falls_back_to_text_when_vision_fails(site_settings):
    """If complete_multimodal raises for the image call, retry text-only and
    prepend a follow_up_question warning."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})

    call_log = []

    def fake_mm(self, **kwargs):
        call_log.append(kwargs.get("images"))
        if kwargs.get("images"):
            raise RuntimeError("vision model unavailable")
        return (
            '{"title": "T", "priority": "P2", "module": "其他", '
            '"repro_steps": "", "expected_behavior": "", '
            '"labels": [], "follow_up_questions": [], "inferred_env": ""}'
        )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        new=fake_mm,
    ):
        svc = AiWizardService()
        result = svc.oneshot_draft("d", images=[("image/png", b"x")])

    # First call had images; second was text-only fallback
    assert call_log[0] == [("image/png", b"x")]
    assert call_log[1] == []
    # The warning is prepended to follow_up_questions
    assert result["follow_up_questions"][0].startswith("AI 未能读取截图")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v -k oneshot_draft`
Expected: All 6 FAIL with `AttributeError: 'AiWizardService' object has no attribute 'oneshot_draft'` (or related).

- [ ] **Step 3: Implement `oneshot_draft` in the service**

Modify `backend/apps/issues/services_ai_wizard.py`. Keep all existing v1 code (it stays behind the legacy flag for now; Task 6 wires the flag). At the top of the file add the new schema constants near `SCHEMA_GENERATE`:

```python
SCHEMA_ONESHOT = [
    ("title", str, False),
    ("priority", str, False),
    ("module", str, False),
    ("repro_steps", str, True),
    ("expected_behavior", str, True),
    ("labels", list, True),
    ("follow_up_questions", list, True),
    ("inferred_env", str, True),
]

ONESHOT_TIMEOUT_SECONDS = 25
ONESHOT_RETRY_COUNT = 1   # one retry on bad JSON (total 2 attempts)
```

Then add the following methods to `AiWizardService` (after the existing `generate` method, before `stream_draft`). The implementation reuses the existing `_run_prompt` helper where possible, but adds a direct multimodal path:

```python
def oneshot_draft(self, description: str, images: list[tuple[str, bytes]]) -> dict:
    """Single multimodal LLM call that produces a complete draft.

    Returns the same merged shape as the legacy 3-stage pipeline plus
    inferred_env. On vision failure, retries text-only and prepends a
    follow_up_question warning. On bad JSON, retries once.
    """
    from apps.ai.client import LLMClient
    from apps.ai.models import LLMConfig, Prompt
    from apps.ai.services import parse_json_response
    from apps.settings.models import SiteSettings

    prompt = Prompt.objects.filter(slug="wizard_oneshot", is_active=True).first()
    if prompt is None:
        raise AiWizardError(step=1, code="missing_prompt", message="未配置 Prompt: wizard_oneshot")

    config = prompt.llm_config or LLMConfig.objects.filter(is_default=True, is_active=True).first()
    if config is None:
        raise AiWizardError(step=1, code="missing_llm_config", message="未配置可用的 LLM")

    site = SiteSettings.get_solo()
    modules = list(site.modules or [])
    labels_dict = site.labels or {}
    labels_list = list(labels_dict.keys()) if isinstance(labels_dict, dict) else list(labels_dict)

    try:
        user_prompt = prompt.user_prompt_template.format(
            description=description,
            modules_json=json.dumps(modules, ensure_ascii=False),
            labels_json=json.dumps(labels_list, ensure_ascii=False),
        )
    except KeyError as e:
        raise AiWizardError(step=1, code="prompt_format_error", message=f"模板缺失变量 {e}")

    client = LLMClient(config)
    vision_warning = None
    attempts_left = ONESHOT_RETRY_COUNT + 1
    current_images = list(images)
    last_raw = None

    while attempts_left > 0:
        attempts_left -= 1
        try:
            raw = client.complete_multimodal(
                model=prompt.llm_model,
                system_prompt=prompt.system_prompt,
                user_prompt=user_prompt,
                images=current_images,
                temperature=prompt.temperature,
                timeout=ONESHOT_TIMEOUT_SECONDS,
            )
        except Exception as e:
            if current_images:
                # Vision-down: drop images, retry once as text-only
                logger.warning("wizard_oneshot vision call failed, falling back to text-only: %s", e)
                vision_warning = "AI 未能读取截图，已基于文字生成"
                current_images = []
                continue
            logger.warning("wizard_oneshot LLM call failed: %s", e, exc_info=True)
            raise AiWizardError(step=1, code="llm_call_failed", message="AI 调用失败，请重试")

        last_raw = raw
        try:
            parsed = parse_json_response(raw)
            break
        except (json.JSONDecodeError, ValueError):
            if attempts_left == 0:
                logger.warning("wizard_oneshot bad JSON after retries: %r", raw)
                raise AiWizardError(step=1, code="llm_bad_json", message="AI 返回格式异常，请重试")
            # else loop and retry

    parsed = _validate_shape(1, "wizard_oneshot", parsed, SCHEMA_ONESHOT)
    self._sanitize_oneshot(parsed, modules, labels_list)
    if vision_warning:
        parsed["follow_up_questions"] = [vision_warning] + list(parsed.get("follow_up_questions") or [])
        parsed["follow_up_questions"] = parsed["follow_up_questions"][:3]
    return parsed

@staticmethod
def _sanitize_oneshot(data: dict, modules: list, labels_list: list) -> None:
    """In-place validation per spec §5.4."""
    # title
    title = (data.get("title") or "").strip()[:200]
    if not title:
        raise AiWizardError(step=1, code="llm_bad_shape", message="title 为空")
    data["title"] = title

    # priority
    if data.get("priority") not in ALLOWED_PRIORITIES:
        data["priority"] = "P2"

    # module
    mod = (data.get("module") or "").strip()
    if modules and mod not in modules:
        mod = "其他" if "其他" in modules else modules[0]
    data["module"] = mod

    # repro_steps / expected_behavior / inferred_env truncation
    data["repro_steps"] = (data.get("repro_steps") or "")[:2000]
    data["expected_behavior"] = (data.get("expected_behavior") or "")[:500]
    data["inferred_env"] = (data.get("inferred_env") or "")[:200]

    # labels: filter to known + cap 3
    raw_labels = data.get("labels") or []
    if not isinstance(raw_labels, list):
        raw_labels = []
    valid = set(labels_list)
    data["labels"] = [l for l in raw_labels if isinstance(l, str) and l in valid][:3]

    # follow_up_questions: cap items + each ≤ 100 chars
    raw_q = data.get("follow_up_questions") or []
    if not isinstance(raw_q, list):
        raw_q = []
    data["follow_up_questions"] = [str(q)[:100] for q in raw_q if q][:3]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v -k oneshot_draft`
Expected: All 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services_ai_wizard.py backend/tests/test_ai_wizard.py
git commit -m "feat(wizard): add AiWizardService.oneshot_draft

Single multimodal LLM call replacing the v1 3-stage pipeline. Vision
failure falls back to text-only with a user-visible follow_up_question
warning. Bad JSON is retried once before raising AiWizardError."
```

---

## Task 4: Add `_load_image_attachments` helper

**Files:**

- Modify: `backend/apps/issues/services_ai_wizard.py`
- Test: `backend/tests/test_ai_wizard.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_load_image_attachments_filters_to_images_and_caps_at_three(tmp_path):
    """Only image MIME types are loaded; max 3 per call; >2MB are skipped."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.tools.models import Attachment
    from tests.factories import UserFactory
    from unittest.mock import patch

    user = UserFactory()
    # Mix of image and non-image; one image is >2MB
    attachments = [
        Attachment.objects.create(
            uploaded_by=user, file_name="ok1.png", file_key="k1",
            file_url="/u/1", file_size=1000, mime_type="image/png",
        ),
        Attachment.objects.create(
            uploaded_by=user, file_name="doc.pdf", file_key="k2",
            file_url="/u/2", file_size=2000, mime_type="application/pdf",
        ),
        Attachment.objects.create(
            uploaded_by=user, file_name="ok2.jpg", file_key="k3",
            file_url="/u/3", file_size=1500, mime_type="image/jpeg",
        ),
        Attachment.objects.create(
            uploaded_by=user, file_name="ok3.png", file_key="k4",
            file_url="/u/4", file_size=500, mime_type="image/png",
        ),
        Attachment.objects.create(
            uploaded_by=user, file_name="huge.png", file_key="k5",
            file_url="/u/5", file_size=5 * 1024 * 1024, mime_type="image/png",
        ),
        Attachment.objects.create(
            uploaded_by=user, file_name="ok4.png", file_key="k6",
            file_url="/u/6", file_size=600, mime_type="image/png",
        ),
    ]
    ids = [str(a.id) for a in attachments]

    def fake_read(file_key):
        return b"\x89PNGfake-" + file_key.encode()

    with patch("apps.issues.services_ai_wizard._read_attachment_bytes", side_effect=fake_read):
        svc = AiWizardService()
        images = svc._load_image_attachments(ids)

    # Only ok1/ok2/ok3 — the first 3 image-MIME attachments under 2MB
    assert len(images) == 3
    mimes = [m for m, _ in images]
    assert all(m.startswith("image/") for m in mimes)
    assert b"k1" in images[0][1] or b"k1" in images[1][1] or b"k1" in images[2][1]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_load_image_attachments_filters_to_images_and_caps_at_three -v`
Expected: FAIL with `AttributeError: '_load_image_attachments'`.

- [ ] **Step 3: Find how the project already reads stored attachment bytes**

Run: `grep -rn "file_key\|minio\|boto3" backend/apps/tools/ --include="*.py" | head -20`

You should find a storage helper. If there is a function like `download_object(file_key)` or similar, the new helper `_read_attachment_bytes` should delegate to it. If there is no helper yet, read it directly via `minio` client using the env vars in `backend/config/settings.py` (MinIO endpoint/access/secret). The point: the new helper must NOT make an HTTP request to `file_url` — go through the storage layer.

If there is no shared helper at all, add this minimal version to `backend/apps/issues/services_ai_wizard.py` near the top (after imports):

```python
def _read_attachment_bytes(file_key: str) -> bytes:
    """Read an attachment's raw bytes from MinIO by its file_key.

    Uses the same MinIO connection details (settings.MINIO_*) as the upload
    path so we don't depend on file_url being publicly fetchable.
    """
    from django.conf import settings
    from minio import Minio  # already a dependency via apps.tools

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_SSL,
    )
    resp = client.get_object(settings.MINIO_BUCKET, file_key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()
```

If a helper already exists (likely in `apps/tools/storage.py` or similar), import and call it instead — keep this module thin.

- [ ] **Step 4: Implement `_load_image_attachments`**

Add the method on `AiWizardService` (after `_sanitize_oneshot` from Task 3):

```python
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB

def _load_image_attachments(self, attachment_ids: list) -> list[tuple[str, bytes]]:
    """Resolve attachment_ids → up to MAX_IMAGES (mime, bytes) pairs.

    - Filters to image MIME types only
    - Skips files larger than MAX_IMAGE_BYTES
    - Silently skips read failures (logs warning) so one bad attachment
      doesn't abort the whole wizard call
    """
    if not attachment_ids:
        return []

    from apps.tools.models import Attachment

    rows = list(
        Attachment.objects
        .filter(id__in=attachment_ids, mime_type__startswith="image/")
        .order_by("created_at")
    )

    out: list[tuple[str, bytes]] = []
    for att in rows:
        if att.file_size > MAX_IMAGE_BYTES:
            logger.info("wizard skipping oversize image %s (%d bytes)", att.file_name, att.file_size)
            continue
        try:
            raw = _read_attachment_bytes(att.file_key)
        except Exception as e:
            logger.warning("wizard could not read attachment %s: %s", att.file_key, e)
            continue
        out.append((att.mime_type, raw))
        if len(out) >= MAX_IMAGES:
            break
    return out
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_load_image_attachments_filters_to_images_and_caps_at_three -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/issues/services_ai_wizard.py backend/tests/test_ai_wizard.py
git commit -m "feat(wizard): load attachment images for oneshot vision call

Reads up to 3 image attachments via MinIO by file_key. Filters by image
MIME type, skips files over 2MB, and never lets a single read failure
abort the wizard call."
```

---

## Task 5: Rewrite `stream_draft` for parallel oneshot + dedup

**Files:**

- Modify: `backend/apps/issues/services_ai_wizard.py`
- Test: `backend/tests/test_ai_wizard.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_stream_draft_v2_emits_step_duplicates_draft_done(site_settings):
    """The v2 stream emits exactly: step(running), duplicates, step(done), draft, done.

    Order of the duplicates event vs the step(done)/draft pair is not
    asserted — they are emitted as each thread finishes.
    """
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory
    from unittest.mock import patch
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})
    project = ProjectFactory()

    valid_json = (
        '{"title": "T", "priority": "P2", "module": "其他", '
        '"repro_steps": "", "expected_behavior": "", '
        '"labels": [], "follow_up_questions": [], "inferred_env": ""}'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=valid_json,
    ), patch(
        "apps.issues.services_ai_wizard.check_duplicates",
        return_value=[{"id": 7, "title": "old", "status": "待处理", "reason": "same"}],
    ):
        svc = AiWizardService()
        events = list(svc.stream_draft(
            description="some bug here please help",
            project_id=project.id,
            attachment_ids=[],
        ))

    names = [e[0] for e in events]
    # First event is always step running
    assert names[0] == "step"
    assert events[0][1]["status"] == "running"
    # Last event is always done
    assert names[-1] == "done"
    # Set of events between contains step-done, draft, duplicates
    middle_names = set(names[1:-1])
    assert "step" in middle_names    # the "done" status step
    assert "draft" in middle_names
    assert "duplicates" in middle_names
    # The draft payload has the inferred_env stitched into description
    draft_event = next(e for e in events if e[0] == "draft")
    assert draft_event[1]["title"] == "T"
    # Duplicates payload shape
    dup_event = next(e for e in events if e[0] == "duplicates")
    assert dup_event[1]["items"] == [{"id": 7, "title": "old", "status": "待处理", "reason": "same"}]


@pytest.mark.django_db
def test_stream_draft_v2_assembles_description_with_inferred_env(site_settings):
    """When the LLM returns a non-empty inferred_env the draft's description
    field has the env blockquote appended."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory
    from unittest.mock import patch
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})
    project = ProjectFactory()

    valid_json = (
        '{"title": "T", "priority": "P2", "module": "其他", '
        '"repro_steps": "", "expected_behavior": "", '
        '"labels": [], "follow_up_questions": [], '
        '"inferred_env": "dev1 | 超管 | /a/b"}'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=valid_json,
    ), patch(
        "apps.issues.services_ai_wizard.check_duplicates",
        return_value=[],
    ):
        svc = AiWizardService()
        events = list(svc.stream_draft(
            description="raw user input",
            project_id=project.id,
            attachment_ids=[],
        ))

    draft = next(e for e in events if e[0] == "draft")[1]
    assert draft["description"].startswith("raw user input")
    assert "AI 推断环境" in draft["description"]
    assert "dev1 | 超管 | /a/b" in draft["description"]


@pytest.mark.django_db
def test_stream_draft_v2_emits_error_when_oneshot_fails(site_settings):
    """oneshot_draft raising AiWizardError → SSE error event; duplicates still emitted."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory
    from unittest.mock import patch
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})
    project = ProjectFactory()

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value="not json",
    ), patch(
        "apps.issues.services_ai_wizard.check_duplicates",
        return_value=[],
    ):
        svc = AiWizardService()
        events = list(svc.stream_draft(
            description="some bug here",
            project_id=project.id,
            attachment_ids=[],
        ))

    names = [e[0] for e in events]
    assert "error" in names
    err = next(e for e in events if e[0] == "error")[1]
    assert err["code"] == "llm_bad_json"


@pytest.mark.django_db
def test_stream_draft_v2_silently_swallows_check_duplicates_failure(site_settings):
    """A failure inside check_duplicates must NOT abort the draft path."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory
    from unittest.mock import patch
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})
    project = ProjectFactory()

    valid_json = (
        '{"title": "T", "priority": "P2", "module": "其他", '
        '"repro_steps": "", "expected_behavior": "", '
        '"labels": [], "follow_up_questions": [], "inferred_env": ""}'
    )

    def boom(*a, **k):
        raise RuntimeError("dedup service down")

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=valid_json,
    ), patch(
        "apps.issues.services_ai_wizard.check_duplicates",
        side_effect=boom,
    ):
        svc = AiWizardService()
        events = list(svc.stream_draft(
            description="ok",
            project_id=project.id,
            attachment_ids=[],
        ))

    names = [e[0] for e in events]
    assert "draft" in names
    assert "done" in names
    dup_event = next(e for e in events if e[0] == "duplicates")
    assert dup_event[1]["items"] == []


@pytest.mark.django_db
def test_stream_draft_v2_appends_image_markdown_to_description(site_settings):
    """Image attachments are auto-embedded as ![name](file_url) in the draft
    description so the issue body previews inline (fixes Bug 1: wizard
    submitted issues had related attachments but no inline image preview)."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from apps.tools.models import Attachment
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    from unittest.mock import patch
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})
    project = ProjectFactory()
    user = UserFactory()
    att = Attachment.objects.create(
        uploaded_by=user, file_name="shot.png", file_key="k1",
        file_url="/uploads/2026/05/shot.png", file_size=1000, mime_type="image/png",
    )
    # Non-image attachment must NOT be embedded
    Attachment.objects.create(
        uploaded_by=user, file_name="notes.pdf", file_key="k2",
        file_url="/uploads/2026/05/notes.pdf", file_size=2000, mime_type="application/pdf",
    )

    valid_json = (
        '{"title": "T", "priority": "P2", "module": "其他", '
        '"repro_steps": "", "expected_behavior": "", '
        '"labels": [], "follow_up_questions": [], "inferred_env": "dev | qa | /x"}'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=valid_json,
    ), patch(
        "apps.issues.services_ai_wizard.check_duplicates",
        return_value=[],
    ):
        svc = AiWizardService()
        events = list(svc.stream_draft(
            description="user typed text",
            project_id=project.id,
            attachment_ids=[str(att.id)],
        ))

    draft = next(e for e in events if e[0] == "draft")[1]
    # Order: raw → inferred_env blockquote → image markdown
    assert draft["description"].startswith("user typed text")
    assert "AI 推断环境" in draft["description"]
    assert "![shot.png](/uploads/2026/05/shot.png)" in draft["description"]
    # PDF must NOT appear as markdown image
    assert "notes.pdf" not in draft["description"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v -k "stream_draft_v2"`
Expected: All 4 FAIL — the existing `stream_draft` has a different signature and event sequence.

- [ ] **Step 3: Rewrite `stream_draft` in `AiWizardService`**

In `backend/apps/issues/services_ai_wizard.py`, rename the existing `stream_draft` method to `_stream_draft_legacy` (kept for Task 6's legacy flag), then add at the top of the file an import:

```python
import queue
from concurrent.futures import ThreadPoolExecutor
from apps.issues.services import check_duplicates
```

And add the new `stream_draft` method on `AiWizardService` (place it directly above `_stream_draft_legacy`):

```python
def stream_draft(self, description: str, project_id, attachment_ids: list | None = None):
    """v2 generator yielding (event_name, payload) for the SSE layer.

    Runs the multimodal oneshot LLM call and `check_duplicates` in parallel
    via two-thread executor. Events are emitted in arrival order:
      ("step", {step:1, status:"running"})
      then, as each thread finishes:
        ("duplicates", {"items":[...]})    when check_duplicates returns
        ("step", {step:1, status:"done"}) + ("draft", {...}) when oneshot returns
        ("error", {...}) instead of step+draft on oneshot failure
      ("done", {})
    """
    images = self._load_image_attachments(attachment_ids or [])

    q: queue.Queue = queue.Queue()
    STEP_LABEL = "理解描述与截图"

    def run_oneshot():
        try:
            draft = self.oneshot_draft(description, images)
            # Look up image attachment metadata (name + url) so the assembled
            # description can embed them as inline markdown previews.
            image_meta = self._load_image_metadata(attachment_ids or [])
            draft["description"] = self._assemble_description(
                description, draft.get("inferred_env", ""), image_meta,
            )
            q.put(("draft", draft, None))
        except AiWizardError as e:
            q.put(("draft", None, e))
        except Exception as e:
            logger.exception("wizard oneshot unexpected failure")
            q.put(("draft", None, AiWizardError(
                step=1, code="llm_call_failed", message="AI 调用失败，请重试")))

    def run_dupcheck():
        try:
            items = check_duplicates(project_id, description[:50], description) or []
        except Exception:
            logger.warning("wizard check_duplicates failed; returning empty", exc_info=True)
            items = []
        q.put(("duplicates", items, None))

    with ThreadPoolExecutor(max_workers=2) as ex:
        ex.submit(run_oneshot)
        ex.submit(run_dupcheck)

        yield ("step", {"step": 1, "label": STEP_LABEL, "status": "running"})

        results_pending = 2
        while results_pending > 0:
            kind, payload, error = q.get()
            results_pending -= 1
            if kind == "duplicates":
                yield ("duplicates", {"items": payload})
            elif kind == "draft":
                if error:
                    yield ("step", {"step": 1, "label": STEP_LABEL, "status": "error"})
                    yield ("error", {"code": error.code, "message": error.message})
                else:
                    yield ("step", {"step": 1, "label": STEP_LABEL, "status": "done"})
                    yield ("draft", payload)
    yield ("done", {})

@staticmethod
def _assemble_description(user_description: str, inferred_env: str, image_meta: list | None = None) -> str:
    """Server-side description assembly per spec §4.3.

    Order: raw user description → inferred_env blockquote → image markdown.
    Each block separated by a blank line. Image attachments are embedded as
    ![name](file_url) so the issue body previews inline (fixes Bug 1).
    """
    raw = (user_description or "").rstrip()
    env = (inferred_env or "").strip()
    parts: list[str] = []
    if raw:
        parts.append(raw)
    if env:
        parts.append(f"> 🤖 *AI 推断环境*: {env}")
    for att in image_meta or []:
        name = att.get("file_name") or "image"
        url = att.get("file_url") or ""
        if url:
            parts.append(f"![{name}]({url})")
    return "\n\n".join(parts)

def _load_image_metadata(self, attachment_ids: list) -> list[dict]:
    """Return image attachment metadata (file_name, file_url) for inline markdown.

    Separate from _load_image_attachments (Task 4) which reads raw bytes
    for the vision LLM call — this one only needs the URL for the markdown
    that goes into the draft description.
    """
    if not attachment_ids:
        return []
    from apps.tools.models import Attachment
    return list(
        Attachment.objects
        .filter(id__in=attachment_ids, mime_type__startswith="image/")
        .order_by("created_at")
        .values("file_name", "file_url")
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v -k "stream_draft_v2"`
Expected: All 4 PASS.

Also run the v1 stream_draft test to confirm it still works (since we just renamed it):

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_stream_draft_emits_three_steps_then_draft_and_done -v`

Expected: FAIL — the legacy test calls `stream_draft(description=...)` but the new signature requires `project_id` and changes the event sequence. **Don't fix it yet** — Task 6 wires the legacy flag, after which we'll update this test to call `_stream_draft_legacy` directly.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services_ai_wizard.py backend/tests/test_ai_wizard.py
git commit -m "feat(wizard): rewrite stream_draft for parallel oneshot + dedup

Two-thread ThreadPoolExecutor runs the multimodal LLM call and the
existing check_duplicates service concurrently. Events stream as each
thread completes; inferred_env is appended to the draft description as
a markdown blockquote server-side. v1 stream_draft is preserved as
_stream_draft_legacy for Task 6."
```

---

## Task 6: Wire the `AI_WIZARD_LEGACY` rollback flag

**Files:**

- Modify: `backend/config/settings.py`
- Modify: `backend/apps/issues/services_ai_wizard.py`
- Test: `backend/tests/test_ai_wizard.py`

- [ ] **Step 1: Find the existing env-var pattern**

Run: `grep -n "env.bool\|env(" backend/config/settings.py | head -10`
Note which env library (`environ.Env`, `os.environ.get`, etc.) the project uses. Use the same.

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_stream_draft_routes_to_v1_when_legacy_flag_set(site_settings, settings):
    """AI_WIZARD_LEGACY=True routes to the preserved 3-stage pipeline."""
    settings.AI_WIZARD_LEGACY = True
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory
    from unittest.mock import patch
    LLMConfigFactory(is_default=True, is_active=True)
    # Re-activate v1 prompts since the rollback path queries them
    from apps.ai.models import Prompt
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})
    project = ProjectFactory()

    responses = iter([
        '{"category": "x", "scope": "y"}',
        '{"title": "T", "priority": "P2", "module": "其他"}',
        '{"repro_steps": "1.", "expected_behavior": "y", "labels": []}',
    ])
    def fake_complete(self, **kwargs):
        return next(responses)

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        svc = AiWizardService()
        events = list(svc.stream_draft(
            description="x",
            project_id=project.id,
            attachment_ids=[],
        ))

    # v1 pipeline emits 3 step events
    step_events = [e for e in events if e[0] == "step"]
    assert len(step_events) >= 3
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_stream_draft_routes_to_v1_when_legacy_flag_set -v`
Expected: FAIL — currently `stream_draft` always runs the v2 path.

- [ ] **Step 4: Add the setting**

In `backend/config/settings.py`, add near other AI-related settings (search for `AI_API_KEY` first to find the right location):

```python
# AI Issue Wizard rollback flag — set True to fall back to the 3-stage
# legacy pipeline (wizard_classify / wizard_extract / wizard_generate).
# Defaults to False; v1 prompt rows are preserved for 7 days after deploy.
AI_WIZARD_LEGACY = env.bool("AI_WIZARD_LEGACY", default=False)
```

If the project uses `os.environ.get` instead of `django-environ`'s `env`, adapt:

```python
import os
AI_WIZARD_LEGACY = os.environ.get("AI_WIZARD_LEGACY", "").lower() in ("1", "true", "yes")
```

- [ ] **Step 5: Update `stream_draft` to dispatch on the flag**

In `backend/apps/issues/services_ai_wizard.py`, rename the v2 method you wrote in Task 5 to `_stream_draft_v2` and replace `stream_draft` with a dispatcher:

```python
def stream_draft(self, description: str, project_id=None, attachment_ids=None):
    from django.conf import settings
    if getattr(settings, "AI_WIZARD_LEGACY", False):
        # Legacy path keeps the original signature (description only)
        yield from self._stream_draft_legacy(description)
    else:
        yield from self._stream_draft_v2(
            description=description,
            project_id=project_id,
            attachment_ids=attachment_ids or [],
        )
```

- [ ] **Step 6: Update the legacy v1 stream_draft test to call legacy directly**

The legacy test at `backend/tests/test_ai_wizard.py:152-196` is calling `stream_draft(description=...)` and expecting the 3-step events. Either rewrite it to call `_stream_draft_legacy` directly, or rewrite it to set `settings.AI_WIZARD_LEGACY = True`. Use the second form — it exercises the dispatcher too. Modify the test:

```python
@pytest.mark.django_db
def test_stream_draft_emits_three_steps_then_draft_and_done(site_settings, settings):
    settings.AI_WIZARD_LEGACY = True   # ← new line; rest unchanged
    from apps.issues.services_ai_wizard import AiWizardService
    ...   # keep the rest of the function body identical to the existing test
```

- [ ] **Step 7: Run the v2, legacy-dispatch, and original v1 tests together**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v`
Expected: All tests pass (both v1 legacy tests and new v2 tests).

- [ ] **Step 8: Add the flag to `.env.example`**

In `backend/.env.example`, after the `DASHSCOPE_API_KEY` line you added earlier:

```bash
# Set to "True" to roll back the AI Issue Wizard to the 3-stage v1 pipeline.
# Used as an emergency switch during the 7-day v2 observation window.
AI_WIZARD_LEGACY=False
```

- [ ] **Step 9: Commit**

```bash
git add backend/config/settings.py backend/apps/issues/services_ai_wizard.py \
        backend/tests/test_ai_wizard.py backend/.env.example
git commit -m "feat(wizard): add AI_WIZARD_LEGACY flag for 7-day rollback

When set, stream_draft routes to the preserved 3-stage v1 pipeline
(wizard_classify/extract/generate). v1 prompts in DB are still inactive
by default; flipping is_active and setting AI_WIZARD_LEGACY=True via env
restores the legacy path with no code redeploy."
```

---

## Task 7: Wire the view to pass `project_id` and `attachment_ids`

**Files:**

- Modify: `backend/apps/issues/views.py`
- Test: `backend/tests/test_ai_wizard.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_ai_draft_endpoint_passes_project_and_attachments_to_service(api_client, site_settings):
    """The view must forward project_id and attachment_ids to stream_draft."""
    from django.contrib.auth.models import Permission
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    from unittest.mock import patch
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})
    project = ProjectFactory()
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename="add_issue"))
    api_client.force_authenticate(user)

    captured = {}

    def fake_stream(self, description, project_id=None, attachment_ids=None):
        captured["description"] = description
        captured["project_id"] = project_id
        captured["attachment_ids"] = attachment_ids
        yield ("step", {"step": 1, "label": "x", "status": "running"})
        yield ("draft", {
            "title": "T", "description": description,
            "repro_steps": "", "expected_behavior": "",
            "priority": "P2", "module": "其他",
            "labels": [], "follow_up_questions": [],
            "inferred_env": "",
        })
        yield ("done", {})

    with patch(
        "apps.issues.services_ai_wizard.AiWizardService.stream_draft",
        new=fake_stream,
    ):
        resp = api_client.post(
            "/api/issues/ai-draft/",
            {
                "description": "ok long enough description",
                "project": str(project.id),
                "attachment_ids": [],
            },
            format="json",
        )
        body = b"".join(resp.streaming_content).decode()

    assert resp.status_code == 200
    assert captured["project_id"] == project.id
    assert captured["attachment_ids"] == []
    assert "event: draft" in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_ai_draft_endpoint_passes_project_and_attachments_to_service -v`
Expected: FAIL — the current view calls `stream_draft(description=...)` without `project_id` or `attachment_ids`.

- [ ] **Step 3: Update `IssueAiDraftView.post`**

In `backend/apps/issues/views.py`, replace the body of `event_stream()` inside `IssueAiDraftView.post`:

```python
def event_stream():
    svc = AiWizardService()
    try:
        for event_name, payload in svc.stream_draft(
            description=data["description"],
            project_id=data["project"].id,
            attachment_ids=[str(x) for x in data.get("attachment_ids") or []],
        ):
            if event_name == "_heartbeat":
                yield ": heartbeat\n\n"
            else:
                yield f"event: {event_name}\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
        import logging
        logging.getLogger(__name__).info("SSE client disconnected; stopping draft stream")
        return
```

Confirm `AiDraftInputSerializer` already returns `project` as a `Project` instance (it does — it uses `PrimaryKeyRelatedField`). If `attachment_ids` isn't already in the serializer, it is at [line 273](../../../backend/apps/issues/serializers.py#L273) — no change needed there.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_ai_draft_endpoint_passes_project_and_attachments_to_service -v`
Expected: PASS.

Also run the full test file to catch regressions:

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/views.py backend/tests/test_ai_wizard.py
git commit -m "feat(wizard): pass project + attachments to v2 stream_draft

The SSE view now forwards the validated project id and attachment ids
to AiWizardService.stream_draft, enabling the parallel dedup call and
vision input."
```

---

## Task 8: Update the frontend composable for v2 events

**Files:**

- Modify: `frontend/app/composables/useAiWizard.ts`

No frontend tests (none exist for the wizard composables today; spec §8.2). Manual verification at the end of this task.

- [ ] **Step 1: Replace the file contents**

Open `frontend/app/composables/useAiWizard.ts` and apply these changes:

a) Update the `WizardDraft` type — add `inferred_env`, remove `environment` (it was used by v1 only):

```ts
export type WizardDraft = {
  title: string
  description: string
  repro_steps: string
  expected_behavior: string
  priority: 'P0' | 'P1' | 'P2' | 'P3'
  module: string
  labels: string[]
  follow_up_questions: string[]
  inferred_env: string
}

export type DuplicateItem = {
  id: number
  title: string
  status: string
  reason: string
}
```

b) Collapse `INITIAL_STEPS` to a single entry:

```ts
const INITIAL_STEPS: StepProgress[] = [
  { step: 1, label: 'AI 正在理解描述与截图', status: 'pending' },
]
```

(Keep the `step` field typed as `1 | 2 | 3` for now — the type union still permits the v2 single step. A later cleanup can narrow it to `1`.)

c) Inside `useAiWizard()`, add a `duplicates` ref and reset it. Locate the existing refs:

```ts
const draft = ref<WizardDraft | null>(null)
const errorMessage = ref<string>('')
```

and add immediately below:

```ts
const duplicates = ref<DuplicateItem[]>([])
```

In `reset()`, set `duplicates.value = []` next to the other resets.

d) Extend `handleFrame()` to handle the new `duplicates` event. Locate the existing chain in `handleFrame`:

```ts
if (event === 'step') {
  ...
} else if (event === 'draft') {
  ...
} else if (event === 'error') {
  ...
}
```

Add a branch between `draft` and `error`:

```ts
} else if (event === 'duplicates') {
  duplicates.value = (payload.items || []) as DuplicateItem[]
```

e) Export `duplicates` from the return statement:

```ts
return { state, steps, draft, duplicates, errorMessage, start, reset, abort }
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx nuxi typecheck 2>&1 | tail -30`
Expected: No type errors related to `useAiWizard.ts` (there may be pre-existing errors in other files — ignore those, just make sure your edits don't introduce new ones).

If you see errors like "Property 'environment' does not exist on type 'WizardDraft'", they come from `StepDraft.vue` — those are fixed in Task 10.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/composables/useAiWizard.ts
git commit -m "feat(wizard): expose duplicates + inferred_env in v2 composable

WizardDraft drops the v1 environment field and adds inferred_env.
A new duplicates ref tracks the duplicates SSE event payload.
INITIAL_STEPS collapses to one entry matching the v2 single step."
```

---

## Task 9: Frontend — StepAnalyzing single-step copy

**Files:**

- Modify: `frontend/app/components/AiIssueWizard/StepAnalyzing.vue`

- [ ] **Step 1: Adjust the type and add the latency hint**

In `StepAnalyzing.vue`, change the `StepProgress` type to allow a `1` literal at minimum, and add a tiny hint line under the spinner row. Replace lines 1-32 with:

```vue
<template>
  <div class="step-analyzing">
    <div class="spinner-row">
      <UIcon name="i-heroicons-cpu-chip" class="w-5 h-5 text-crystal-500 animate-spin" />
      <span class="title">AI 正在分析…</span>
      <span class="latency-hint">通常 6-8 秒</span>
    </div>

    <div class="step-list">
      <div v-for="s in steps" :key="s.step" class="step-line" :class="`step-line--${s.status}`">
        <UIcon v-if="s.status === 'done'" name="i-heroicons-check-circle" class="w-4 h-4 text-emerald-500" />
        <UIcon v-else-if="s.status === 'error'" name="i-heroicons-x-circle" class="w-4 h-4 text-rose-500" />
        <span v-else class="dot" />
        <span class="label">{{ s.label }}{{ s.status === 'pending' ? '…' : '' }}</span>
      </div>
    </div>

    <p v-if="errorMessage" class="error-msg">{{ errorMessage }}</p>

    <div v-if="errorMessage" class="actions">
      <UButton variant="outline" color="neutral" size="sm" @click="emit('retry')">重试</UButton>
      <UButton variant="ghost" color="neutral" size="sm" @click="emit('back')">重新描述</UButton>
    </div>
  </div>
</template>

<script setup lang="ts">
type StepStatus = 'pending' | 'done' | 'error'
type StepProgress = { step: 1 | 2 | 3; label: string; status: StepStatus }

defineProps<{ steps: StepProgress[]; errorMessage: string }>()
const emit = defineEmits<{ retry: []; back: [] }>()
</script>
```

Append the new style at the end of the `<style scoped>` block:

```css
.latency-hint {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-left: auto;
}
:root.dark .latency-hint { color: #6b7280; }
```

- [ ] **Step 2: Visually verify**

Run: `cd frontend && npm run dev` (in another terminal). Open `http://localhost:3004` and navigate to the AI wizard (the create-issue button on the dashboard launches it). Type a quick description like "测试一下" and hit submit — the StepAnalyzing screen should show a single "AI 正在理解描述与截图…" line and "通常 6-8 秒" on the right.

Stop the dev server (Ctrl+C) when done.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/AiIssueWizard/StepAnalyzing.vue
git commit -m "feat(wizard): single-line analyzing UI with 6-8s hint

Replaces the v1 3-stage progress list with one entry matching the v2
single-call pipeline. Adds a small latency hint to set user expectations."
```

---

## Task 10: Frontend — StepDescribe placeholder copy

**Files:**

- Modify: `frontend/app/components/AiIssueWizard/StepDescribe.vue`

- [ ] **Step 1: Update the placeholder**

In `StepDescribe.vue`, locate the `UTextarea` ([line 25](../../../frontend/app/components/AiIssueWizard/StepDescribe.vue#L25)):

```vue
<UTextarea
  v-model="description"
  :rows="3"
  placeholder="描述你发现的问题：在哪个页面、做了什么操作、出现了什么现象？"
  ...
/>
```

Replace the `placeholder` attribute value:

```vue
placeholder="描述问题：哪个页面/角色，做了什么，看到什么。可以贴截图——AI 会读取截图内容。"
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/components/AiIssueWizard/StepDescribe.vue
git commit -m "feat(wizard): placeholder advertises screenshot OCR"
```

---

## Task 11: Frontend — StepDraft renders duplicates panel and inferred env

**Files:**

- Modify: `frontend/app/components/AiIssueWizard/StepDraft.vue`

- [ ] **Step 1: Update props to receive duplicates and drop the v1 environment field**

In `StepDraft.vue`, locate the `defineProps` block ([lines 137-148](../../../frontend/app/components/AiIssueWizard/StepDraft.vue#L137)):

```ts
const props = defineProps<{
  draft: WizardDraft
  projects: Project[]
  initialProjectId: string
  modules: string[]
  users: UserChoice[]
  validLabels: string[]
  attachmentIds: string[]
  submitting: boolean
  submitError: string
  successIssueId: number | null
}>()
```

Add `duplicates: DuplicateItem[]` to the props type:

```ts
import type { WizardDraft, DuplicateItem } from '~/composables/useAiWizard'
...
const props = defineProps<{
  draft: WizardDraft
  projects: Project[]
  initialProjectId: string
  modules: string[]
  users: UserChoice[]
  validLabels: string[]
  attachmentIds: string[]
  duplicates: DuplicateItem[]
  submitting: boolean
  submitError: string
  successIssueId: number | null
}>()
```

- [ ] **Step 2: Remove the v1 `environment` field from the form**

In the `form` ref ([lines 158-169](../../../frontend/app/components/AiIssueWizard/StepDraft.vue#L158)):

```ts
const form = ref({
  title: props.draft.title,
  description: props.draft.description,
  repro_steps: props.draft.repro_steps,
  expected_behavior: props.draft.expected_behavior,
  priority: props.draft.priority,
  module: props.draft.module,
  environment: props.draft.environment ?? '',
  labels: props.draft.labels,
  assignee: String(authUser.value?.id ?? ''),
  project: props.initialProjectId,
})
```

Remove the `environment` line:

```ts
const form = ref({
  title: props.draft.title,
  description: props.draft.description,
  repro_steps: props.draft.repro_steps,
  expected_behavior: props.draft.expected_behavior,
  priority: props.draft.priority,
  module: props.draft.module,
  labels: props.draft.labels,
  assignee: String(authUser.value?.id ?? ''),
  project: props.initialProjectId,
})
```

Also remove the `USelect` for environment in the template (the `pills-row` block has 4 pills; remove the 4th):

```vue
<USelect
  v-model="form.environment"
  :items="envOptions"
  size="xs"
  icon="i-heroicons-computer-desktop"
  placeholder="（环境）"
  class="pill-select"
/>
```

And remove the `envOptions` constant declaration.

- [ ] **Step 3: Update `onSubmit` to drop the `environment` field from the payload**

In `onSubmit()` ([line 191](../../../frontend/app/components/AiIssueWizard/StepDraft.vue#L191)), the `source_meta` block currently includes `environment`. Replace it to include `inferred_env` (which the AI returns) instead:

```ts
source_meta: {
  module: form.value.module || null,
  inferred_env: props.draft.inferred_env || null,
  original_input: props.draft.description,
},
```

- [ ] **Step 4: Add the duplicates collapsible above the title**

In the `<template>`, between `<div class="draft-header">…</div>` and `<!-- Title -->`, add the duplicates panel:

```vue
<div v-if="duplicates.length" class="dup-panel">
  <details>
    <summary>
      <UIcon name="i-heroicons-exclamation-triangle" class="w-4 h-4" />
      <span>发现 {{ duplicates.length }} 条可能重复的 Issue</span>
      <span class="dup-hint">— 点开查看</span>
    </summary>
    <ul class="dup-list">
      <li v-for="d in duplicates" :key="d.id">
        <NuxtLink :to="`/app/issues/${d.id}`" target="_blank" class="dup-link">
          ISS-{{ String(d.id).padStart(3, '0') }} · {{ d.title }}
          <span class="dup-status">[{{ d.status }}]</span>
        </NuxtLink>
        <div v-if="d.reason" class="dup-reason">{{ d.reason }}</div>
      </li>
    </ul>
  </details>
</div>
```

Append matching styles at the end of `<style scoped>`:

```css
.dup-panel {
  background-color: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 0.5rem;
  padding: 0.5rem 0.875rem;
  font-size: 0.8125rem;
}
:root.dark .dup-panel { background-color: rgba(251, 191, 36, 0.08); border-color: rgba(251, 191, 36, 0.3); }
.dup-panel summary {
  display: flex; align-items: center; gap: 0.375rem;
  cursor: pointer; color: #92400e; font-weight: 500;
}
:root.dark .dup-panel summary { color: #fcd34d; }
.dup-hint { color: #9ca3af; font-weight: 400; margin-left: auto; }
.dup-list { list-style: none; padding: 0.5rem 0 0 0; margin: 0; display: flex; flex-direction: column; gap: 0.375rem; }
.dup-list li { padding: 0.25rem 0; border-top: 1px dashed rgba(146, 64, 14, 0.2); }
.dup-link { color: #1f2937; text-decoration: none; }
.dup-link:hover { text-decoration: underline; }
:root.dark .dup-link { color: #e5e7eb; }
.dup-status { color: #9ca3af; font-size: 0.75rem; margin-left: 0.25rem; }
.dup-reason { color: #78350f; font-size: 0.75rem; margin-top: 0.125rem; }
:root.dark .dup-reason { color: #fcd34d; }
```

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx nuxi typecheck 2>&1 | tail -30`
Expected: No new type errors in `StepDraft.vue`.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/AiIssueWizard/StepDraft.vue
git commit -m "feat(wizard): show possible-duplicates panel; drop v1 env field

A new collapsible \"发现 N 条可能重复\" panel renders above the draft form
when the duplicates SSE event delivered entries. The hardcoded v1
environment dropdown is removed; inferred_env from the AI is now passed
through to source_meta instead."
```

---

## Task 12: Frontend — wire duplicates state into `AiIssueWizard.vue`

**Files:**

- Modify: `frontend/app/components/AiIssueWizard.vue`

- [ ] **Step 1: Pass `duplicates` through to `StepDraft`**

In `AiIssueWizard.vue`, locate the `<StepDraft …>` block ([line 18](../../../frontend/app/components/AiIssueWizard.vue#L18)) and add the `duplicates` prop:

```vue
<StepDraft
  v-else-if="currentStep === 3 && wizard.draft.value"
  :draft="wizard.draft.value"
  :duplicates="wizard.duplicates.value"
  :projects="projects"
  :initial-project-id="lastAnalyzedProject"
  :modules="modules"
  :users="users"
  :valid-labels="validLabels"
  :attachment-ids="lastAttachmentIds"
  :submitting="submitting"
  :submit-error="submitError"
  :success-issue-id="successIssueId"
  @submit="onSubmit"
  @back="onBackToDescribe"
  @reset="onReset"
/>
```

- [ ] **Step 2: Verify in dev**

Run: `cd frontend && npm run dev` (in another terminal) and `cd backend && uv run python manage.py runserver` (in another). Open `http://localhost:3004`, log in, click the AI wizard create-issue button, paste a description known to have similar existing issues (e.g. an issue about "充值申请"), and confirm the duplicates panel renders before/with the draft.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/AiIssueWizard.vue
git commit -m "feat(wizard): thread duplicates state into StepDraft"
```

---

## Task 13: Provision DashScope config and end-to-end smoke test

**Files:** None (config + manual QA only).

- [ ] **Step 1: Configure LLMConfig via Django admin**

Start the backend: `cd backend && uv run python manage.py runserver`. Open `http://localhost:8000/admin/ai/llmconfig/add/` and create the row per spec §10.4:

- name: `DashScope`
- api_key: copy from `backend/.env` `DASHSCOPE_API_KEY`
- base_url: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- supports_json_mode: **uncheck** (DashScope VL models reject `response_format=json_object`)
- is_default: **uncheck**
- is_active: **check**

- [ ] **Step 2: Point the `wizard_oneshot` prompt at the new config**

Open `http://localhost:8000/admin/ai/prompt/?q=wizard_oneshot`, edit the row, set:

- llm_config: `DashScope` (the row you just created)
- Confirm llm_model is `qwen-vl-max-latest`

Save.

- [ ] **Step 3: Apply migrations on the local dev DB**

Run: `cd backend && uv run python manage.py migrate ai`
Expected: `0007_add_wizard_oneshot_prompt` applies; `wizard_oneshot` row appears.

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && uv run pytest -x`
Expected: All tests pass.

- [ ] **Step 5: Manual QA replay (spec §8.3)**

For each of the six historical issues below, open the AI wizard, paste the original description, attach the screenshot (if any), and submit. Capture in a one-line note: time to draft (seconds), draft quality (better/same/worse than the original), and whether the duplicates panel fired.

| ID | Original description excerpt | Original screenshot |
| --- | --- | --- |
| 189 | "导入'测试方案2'文件，文件案件信息很久（五分钟）才显示在案件列表" | yes |
| 195 | The "(1)/(2)/(3)" multi-bug ticket about AI voice testing | no |
| 197 | "外呼任务页面排版异常超出边界" | yes |
| 184 | The "10点后不能外呼" long-form text bug | no |
| 192 | The "法院文书送达记录" feature request with agent_platform env footer | yes |
| 176 | "产品上线规范" — almost empty body | no |

Record findings in a quick Markdown gist or pin them in the PR description.

- [ ] **Step 6: Commit any final tweaks discovered during QA**

If the manual QA surfaces a prompt or copy issue, fix and commit. Otherwise no commit needed here.

---

## Task 14: Open the PR

- [ ] **Step 1: Push the branch**

Run: `git push -u origin feat/ai-issue-wizard`

- [ ] **Step 2: Open a PR**

Run:

```bash
gh pr create --title "feat(wizard): AI Issue Wizard v2 — single multimodal call + parallel dedup" --body "$(cat <<'EOF'
## Summary

- Replaces the 3-stage classify/extract/generate pipeline with a single multimodal LLM call against DashScope `qwen-vl-max-latest`.
- Runs the existing `check_duplicates` in parallel via `ThreadPoolExecutor`; surfaces possible duplicates in the wizard UI before submit.
- Adds `inferred_env` extraction, rendered as a markdown blockquote inside the issue description.
- Preserves v1 prompts (deactivated) and code paths behind `AI_WIZARD_LEGACY` env flag for a 7-day rollback window.

Spec: `docs/superpowers/specs/2026-05-16-ai-issue-wizard-v2-design.md`
Plan: `docs/superpowers/plans/2026-05-16-ai-issue-wizard-v2.md`

## Test plan

- [ ] `uv run pytest backend/tests/test_ai_wizard.py backend/tests/test_ai_models.py`
- [ ] Six-sample manual QA replay (IDs 189/195/197/184/192/176) — see plan Task 13
- [ ] Verify wizard latency p50 ≤ 8s, p95 ≤ 20s on dev
- [ ] Verify duplicate panel renders for known duplicate descriptions
- [ ] Verify vision fallback toast appears when DashScope is unreachable
- [ ] Verify `AI_WIZARD_LEGACY=True` restores the 3-stage path

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage** (skimmed §1-10 against tasks):

- §1 Problem & §2 Goals — addressed by oneshot architecture (Tasks 3, 5) and vision support (Task 4)
- §3 Architecture — implemented in Tasks 3-7 (oneshot, dedup parallelism, view wiring)
- §4 Data contract — request format unchanged; SSE events implemented in Task 5; `description` assembly in Task 5; `draft` shape with `inferred_env` in Task 3; error codes covered in Task 3
- §5 Prompt design — Task 2 seeds the JSON; field validation in Task 3 `_sanitize_oneshot`
- §6 File-level changes — every file in the spec table has a task
- §7 Rollback — Task 6 wires `AI_WIZARD_LEGACY` and the v1 row preservation is in Task 2
- §8 Testing — backend tests inline with each task; manual QA replay in Task 13
- §9 Image limits — enforced in Task 4 `_load_image_attachments`
- §10 Provider selection — Task 13 configures DashScope via admin

**Placeholders/TBDs**: None. Every code step shows the exact code.

**Type consistency:**

- `complete_multimodal(images: list[tuple[str, bytes]])` — same signature across Task 1 (definition), Task 3 (caller), Task 5 (tests)
- `stream_draft(description, project_id, attachment_ids)` — same in Tasks 5, 6, 7 (view caller)
- `WizardDraft` includes `inferred_env: string` — Task 8 (composable), Task 11 (StepDraft consumer)
- `DuplicateItem` — defined Task 8, consumed Task 11

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-ai-issue-wizard-v2.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
