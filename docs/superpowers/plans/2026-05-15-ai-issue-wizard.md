# AI Issue Creation Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AI-guided 3-step Issue creation wizard on `/app/home`, plus a default-project mechanism and a SiteSettings modules taxonomy.

**Architecture:** Backend exposes `POST /api/issues/ai-draft/` returning a Server-Sent-Events stream with 3 sequential LLM calls (`wizard_classify` → `wizard_extract` → `wizard_generate`). Frontend consumes the stream via `fetch + ReadableStream` in a `useAiWizard` composable, drives a 3-step wizard component, and submits the final draft through the existing `POST /api/issues/`. New `default_project` fields on `SiteSettings` and `User` cascade through `/api/auth/me/` to the wizard, the existing issue-create modal, and the profile page.

**Tech Stack:** Django 6 + DRF (SSE via `StreamingHttpResponse`), django-simple-history (existing), OpenAI SDK via existing `LLMClient` (existing). Nuxt 4 SPA, Vue 3 `<script setup>` composables. `pytest-django` + `factory-boy` for backend tests.

**Source design:** `docs/superpowers/specs/2026-05-15-ai-issue-wizard-design.md`
**Branch:** `feat/ai-issue-wizard`

---

## File Structure

### New backend files
- `backend/apps/projects/utils.py` — `get_effective_default_project(user)` helper
- `backend/apps/issues/services_ai_wizard.py` — `AiWizardService` with classify/extract/generate methods
- `backend/apps/ai/seed_prompts/wizard_classify.json` — prompt 1 seed
- `backend/apps/ai/seed_prompts/wizard_extract.json` — prompt 2 seed
- `backend/apps/ai/seed_prompts/wizard_generate.json` — prompt 3 seed
- `backend/apps/settings/migrations/0007_default_project_and_modules.py`
- `backend/apps/users/migrations/0003_user_default_project.py`
- `backend/apps/ai/migrations/0005_seed_wizard_prompts.py`
- `backend/tests/test_default_project.py`
- `backend/tests/test_ai_wizard.py`

### Modified backend files
- `backend/apps/settings/models.py` — add `default_project` FK, `modules` JSONField, `default_modules()` function
- `backend/apps/users/models.py` — add `default_project` FK on `User`
- `backend/apps/projects/utils.py` — new helper (above)
- `backend/apps/users/serializers.py` — `MeSerializer` exposes `default_project` (write) + nested read
- `backend/apps/settings/serializers.py` — `SiteSettingsSerializer` exposes `default_project` + `modules`
- `backend/apps/issues/serializers.py` — `IssueCreateUpdateSerializer` accepts `source`, `source_meta`
- `backend/apps/issues/views.py` — new `IssueAiDraftView`
- `backend/apps/issues/urls.py` — wire `/ai-draft/` URL

### New frontend files
- `frontend/app/composables/useAiWizard.ts` — SSE consumer composable
- `frontend/app/components/AiIssueWizard.vue` — top-level wizard container
- `frontend/app/components/AiIssueWizard/StepDescribe.vue` — Step 1
- `frontend/app/components/AiIssueWizard/StepAnalyzing.vue` — Step 2
- `frontend/app/components/AiIssueWizard/StepDraft.vue` — Step 3 (incl. success)
- `frontend/app/components/AiIssueWizard/AiBadge.vue` — small "AI 生成" / "AI 推断" pill

### Modified frontend files
- `frontend/app/pages/app/home.vue` — strip top quick-actions; mount wizard at top; restyle stat/todo/mention/activity sections
- `frontend/app/composables/useAuth.ts` — `AuthUser` adds `default_project`
- `frontend/app/pages/app/issues/index.vue` — default `newIssue.project` from `user.default_project`
- `frontend/app/pages/app/profile.vue` — default project select
- `frontend/app/components/AppHeader.vue` — surface "新建 Issue" button in top-right (Phase 1 keeps the current location if already present; this task only adds it if missing)

---

# Phase 1 — Default Project Mechanism

### Task 1: Add `default_project` FK to SiteSettings + `modules` JSONField

**Files:**
- Modify: `backend/apps/settings/models.py`
- Create: `backend/apps/settings/migrations/0007_default_project_and_modules.py`

- [ ] **Step 1: Add model fields + default_modules()**

Edit `backend/apps/settings/models.py` — add the `default_modules` function and two fields to `SiteSettings`:

```python
def default_modules():
    return ["通知中心", "审批流程", "用户管理", "项目管理", "表单", "其他"]


class SiteSettings(SingletonModel):
    labels = models.JSONField(default=default_labels, verbose_name="Issue 标签")
    priorities = models.JSONField(default=default_priorities, verbose_name="优先级选项")
    issue_statuses = models.JSONField(default=default_issue_statuses, verbose_name="Issue 状态选项")
    modules = models.JSONField(default=default_modules, verbose_name="功能模块")
    default_project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="默认项目",
    )

    class Meta:
        verbose_name = "系统设置"
        verbose_name_plural = "系统设置"

    def __str__(self):
        return "系统设置"
```

- [ ] **Step 2: Generate the migration**

Run: `cd backend && uv run python manage.py makemigrations settings`
Expected: file `0007_*.py` created with two `AddField` ops.

Rename the generated file to `0007_default_project_and_modules.py` for clarity.

- [ ] **Step 3: Augment the migration with data backfill for `default_project`**

Open the generated migration file and add a data migration that sets `default_project_id = 1` on the existing singleton row (idempotent, runs after the schema change):

```python
def seed_default_project(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    Project = apps.get_model("projects", "Project")
    project_one = Project.objects.filter(pk=1).first()
    if project_one is None:
        return
    SiteSettings.objects.filter(default_project__isnull=True).update(default_project=project_one)


def unseed_default_project(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    SiteSettings.objects.update(default_project=None)


class Migration(migrations.Migration):
    dependencies = [
        ("settings", "0006_update_issue_statuses"),
        ("projects", "0001_initial"),  # adjust if projects has a higher migration
    ]

    operations = [
        # ... auto-generated AddField operations stay above this ...
        migrations.RunPython(seed_default_project, reverse_code=unseed_default_project),
    ]
```

Verify `apps/projects/migrations/` for the latest migration name and use it in `dependencies`. Run:
`ls backend/apps/projects/migrations/`

- [ ] **Step 4: Apply the migration**

Run: `cd backend && uv run python manage.py migrate settings`
Expected: `Applying settings.0007_default_project_and_modules... OK`

- [ ] **Step 5: Verify in shell**

Run:
```bash
cd backend && uv run python manage.py shell -c "
from apps.settings.models import SiteSettings
s = SiteSettings.get_solo()
print('default_project:', s.default_project)
print('modules:', s.modules)
"
```
Expected: `default_project: <Project: ...>` (the project with id=1), `modules: ['通知中心', '审批流程', '用户管理', '项目管理', '表单', '其他']`

- [ ] **Step 6: Commit**

```bash
git add backend/apps/settings/models.py backend/apps/settings/migrations/0007_default_project_and_modules.py
git commit -m "feat(settings): add SiteSettings.default_project and modules taxonomy"
```

---

### Task 2: Add `default_project` FK to User

**Files:**
- Modify: `backend/apps/users/models.py`
- Create: `backend/apps/users/migrations/0003_user_default_project.py`

- [ ] **Step 1: Add the model field**

Edit `backend/apps/users/models.py`:

```python
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    name = models.CharField(max_length=50, verbose_name="姓名")
    github_id = models.CharField(max_length=100, blank=True, verbose_name="GitHub ID")
    avatar = models.CharField(max_length=50, blank=True, verbose_name="头像")
    settings = models.JSONField(default=dict, blank=True, verbose_name="用户设置")
    is_bot = models.BooleanField(default=False, verbose_name="是否为机器人")
    default_project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="默认项目",
    )

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def __str__(self):
        return self.name or self.username
```

- [ ] **Step 2: Generate the migration**

Run: `cd backend && uv run python manage.py makemigrations users`
Rename the file to `0003_user_default_project.py`.

- [ ] **Step 3: Apply the migration**

Run: `cd backend && uv run python manage.py migrate users`
Expected: `Applying users.0003_user_default_project... OK`

- [ ] **Step 4: Commit**

```bash
git add backend/apps/users/models.py backend/apps/users/migrations/0003_user_default_project.py
git commit -m "feat(users): add User.default_project FK"
```

---

### Task 3: `get_effective_default_project` helper

**Files:**
- Create: `backend/apps/projects/utils.py`
- Create: `backend/tests/test_default_project.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_default_project.py`:

```python
import pytest

from apps.projects.utils import get_effective_default_project
from tests.factories import ProjectFactory, UserFactory


@pytest.mark.django_db
def test_returns_user_default_when_set():
    project = ProjectFactory()
    user = UserFactory(default_project=project)

    assert get_effective_default_project(user) == project


@pytest.mark.django_db
def test_falls_back_to_site_default(settings_singleton):
    # settings_singleton fixture seeds SiteSettings; we override default_project here
    from apps.settings.models import SiteSettings
    site_project = ProjectFactory()
    SiteSettings.objects.update(default_project=site_project)

    user = UserFactory(default_project=None)

    assert get_effective_default_project(user) == site_project


@pytest.mark.django_db
def test_returns_none_when_neither_set():
    from apps.settings.models import SiteSettings
    SiteSettings.objects.update(default_project=None)

    user = UserFactory(default_project=None)

    assert get_effective_default_project(user) is None


@pytest.mark.django_db
def test_returns_none_for_anonymous_user():
    from django.contrib.auth.models import AnonymousUser
    from apps.settings.models import SiteSettings
    SiteSettings.objects.update(default_project=None)

    assert get_effective_default_project(AnonymousUser()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_default_project.py -v`
Expected: 4 errors with `ModuleNotFoundError: No module named 'apps.projects.utils'`

- [ ] **Step 3: Check that the `settings_singleton` fixture exists**

Run: `grep -n "settings_singleton\|site_settings" backend/tests/conftest.py`
If the fixture is named `site_settings` (per CLAUDE.md), update the test to use that name. Otherwise add a fixture in `tests/conftest.py`:

```python
@pytest.fixture
def settings_singleton(db):
    from apps.settings.models import SiteSettings
    return SiteSettings.get_solo()
```

Confirm which name applies before continuing.

- [ ] **Step 4: Write the helper**

Create `backend/apps/projects/utils.py`:

```python
from apps.settings.models import SiteSettings


def get_effective_default_project(user):
    """Return the project that should default-select for this user.

    Priority: user's own default_project → SiteSettings.default_project → None.
    Safe with AnonymousUser (returns None).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if user.default_project_id:
        return user.default_project
    return SiteSettings.get_solo().default_project
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_default_project.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/projects/utils.py backend/tests/test_default_project.py
git commit -m "feat(projects): add get_effective_default_project helper"
```

---

### Task 4: Expose `default_project` on `/api/auth/me/` and `/api/settings/`

**Files:**
- Modify: `backend/apps/users/serializers.py:15-28`
- Modify: `backend/apps/settings/serializers.py:6-9`
- Modify: `backend/tests/test_default_project.py` (append tests)

- [ ] **Step 1: Write failing tests for the API**

Append to `backend/tests/test_default_project.py`:

```python
@pytest.mark.django_db
def test_me_endpoint_returns_effective_default_project(api_client):
    """GET /api/auth/me/ returns user's effective default project."""
    from apps.settings.models import SiteSettings
    project = ProjectFactory(name="Default Site Project")
    SiteSettings.objects.update(default_project=project)

    user = UserFactory()
    api_client.force_authenticate(user)

    resp = api_client.get("/api/auth/me/")

    assert resp.status_code == 200
    assert resp.data["default_project"] == {"id": str(project.id), "name": "Default Site Project"}


@pytest.mark.django_db
def test_me_endpoint_user_default_overrides_site(api_client):
    from apps.settings.models import SiteSettings
    site_p = ProjectFactory()
    user_p = ProjectFactory(name="My Pick")
    SiteSettings.objects.update(default_project=site_p)

    user = UserFactory(default_project=user_p)
    api_client.force_authenticate(user)

    resp = api_client.get("/api/auth/me/")

    assert resp.data["default_project"]["name"] == "My Pick"


@pytest.mark.django_db
def test_me_patch_sets_user_default_project(api_client):
    p = ProjectFactory()
    user = UserFactory()
    api_client.force_authenticate(user)

    resp = api_client.patch("/api/auth/me/", {"default_project": str(p.id)}, format="json")

    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.default_project_id == p.id


@pytest.mark.django_db
def test_settings_endpoint_returns_modules_and_default_project(api_client):
    from apps.settings.models import SiteSettings
    SiteSettings.objects.update(default_project=None)
    user = UserFactory()
    api_client.force_authenticate(user)

    resp = api_client.get("/api/settings/")

    assert resp.status_code == 200
    assert isinstance(resp.data["modules"], list)
    assert "通知中心" in resp.data["modules"]
    assert "default_project" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_default_project.py -v -k "endpoint or me_patch"`
Expected: 4 failures (`default_project` not in response / not writable).

- [ ] **Step 3: Update `MeSerializer` to expose `default_project`**

Edit `backend/apps/users/serializers.py:15-28`. Replace the `MeSerializer` class with:

```python
class MeSerializer(serializers.ModelSerializer):
    groups = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    default_project = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "name", "email", "github_id", "avatar",
            "groups", "permissions", "settings", "is_superuser", "default_project",
        ]
        read_only_fields = ["id", "username", "groups", "permissions", "is_superuser"]

    def get_groups(self, obj):
        return list(obj.groups.values_list("name", flat=True))

    def get_permissions(self, obj):
        return list(obj.get_all_permissions())

    def get_default_project(self, obj):
        from apps.projects.utils import get_effective_default_project
        project = get_effective_default_project(obj)
        if project is None:
            return None
        return {"id": str(project.id), "name": project.name}

    def update(self, instance, validated_data):
        # Pull default_project from raw input (it's serializer-method-read but writable via raw)
        raw = self.context["request"].data
        if "default_project" in raw:
            from apps.projects.models import Project
            val = raw["default_project"]
            instance.default_project = Project.objects.filter(pk=val).first() if val else None
        return super().update(instance, validated_data)
```

- [ ] **Step 4: Add `default_project` and `modules` to `SiteSettingsSerializer`**

Edit `backend/apps/settings/serializers.py:6-9`:

```python
class SiteSettingsSerializer(serializers.ModelSerializer):
    default_project = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = ["labels", "priorities", "issue_statuses", "modules", "default_project"]

    def get_default_project(self, obj):
        if obj.default_project is None:
            return None
        return {"id": str(obj.default_project.id), "name": obj.default_project.name}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_default_project.py -v`
Expected: all 8 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/users/serializers.py backend/apps/settings/serializers.py backend/tests/test_default_project.py
git commit -m "feat(api): expose default_project on /api/auth/me/ and /api/settings/"
```

---

# Phase 2 — AI Wizard Prompts (seed)

### Task 5: Seed three wizard prompts

**Files:**
- Create: `backend/apps/ai/seed_prompts/wizard_classify.json`
- Create: `backend/apps/ai/seed_prompts/wizard_extract.json`
- Create: `backend/apps/ai/seed_prompts/wizard_generate.json`
- Create: `backend/apps/ai/migrations/0005_seed_wizard_prompts.py`
- Modify: `backend/tests/test_ai_wizard.py` (new file, partial)

- [ ] **Step 1: Write a failing test for the seeded prompts**

Create `backend/tests/test_ai_wizard.py`:

```python
import pytest

from apps.ai.models import Prompt


@pytest.mark.django_db
def test_wizard_prompts_are_seeded():
    for slug in ("wizard_classify", "wizard_extract", "wizard_generate"):
        p = Prompt.objects.filter(slug=slug).first()
        assert p is not None, f"Prompt '{slug}' not seeded"
        assert p.is_active, f"Prompt '{slug}' should be active"
        assert p.system_prompt.strip(), f"Prompt '{slug}' has empty system_prompt"
        assert p.user_prompt_template.strip(), f"Prompt '{slug}' has empty user_prompt_template"


@pytest.mark.django_db
def test_wizard_extract_template_has_required_placeholders():
    p = Prompt.objects.get(slug="wizard_extract")
    assert "{description}" in p.user_prompt_template
    assert "{classify_json}" in p.user_prompt_template
    assert "{modules_json}" in p.user_prompt_template


@pytest.mark.django_db
def test_wizard_generate_template_has_required_placeholders():
    p = Prompt.objects.get(slug="wizard_generate")
    assert "{description}" in p.user_prompt_template
    assert "{classify_json}" in p.user_prompt_template
    assert "{extract_json}" in p.user_prompt_template
    assert "{labels_json}" in p.user_prompt_template
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v`
Expected: 3 failures (`Prompt 'wizard_classify' not seeded`, etc.)

- [ ] **Step 3: Create the three seed JSON files**

Create `backend/apps/ai/seed_prompts/wizard_classify.json`:

```json
{
  "name": "向导：识别问题类型",
  "system_prompt": "你是 issue 分类助手。读取用户对一个 bug 或问题的自然语言描述，判断问题类型与影响范围。严格返回 JSON 对象，形如 {\"category\": \"<分类>\", \"scope\": \"<受影响范围>\"}。category 可选值：前端 UI / 后端 API / 数据库 / 性能 / 兼容性 / 业务流程 / 其他。scope 用一句话概括（不超过 30 字）。",
  "user_prompt_template": "用户描述:\n{description}",
  "llm_model": "deepseek-v4-flash",
  "temperature": 0.2,
  "is_active": true
}
```

Create `backend/apps/ai/seed_prompts/wizard_extract.json`:

```json
{
  "name": "向导：抽取关键字段",
  "system_prompt": "你是字段抽取助手。基于用户原始描述与上一步的分类结果，抽取适合 Issue 的 title / priority / module。title 控制在 30 字以内、清晰描述现象。priority 从 P0/P1/P2/P3 中选一项（紧急→P0，高→P1，中→P2，低→P3）。module 必须从给定的 modules 列表中选一项；如都不匹配返回 \"其他\"。严格返回 JSON 对象，形如 {\"title\": \"...\", \"priority\": \"P2\", \"module\": \"...\"}。",
  "user_prompt_template": "用户描述:\n{description}\n\n上一步分类结果:\n{classify_json}\n\n可用模块列表:\n{modules_json}",
  "llm_model": "deepseek-v4-flash",
  "temperature": 0.2,
  "is_active": true
}
```

Create `backend/apps/ai/seed_prompts/wizard_generate.json`:

```json
{
  "name": "向导：生成复现步骤",
  "system_prompt": "你是测试用例生成助手。基于用户描述与前两步的分类/抽取结果，生成结构化的复现步骤、预期行为，并推荐 0-3 个分类标签。严格返回 JSON 对象，形如 {\"repro_steps\": \"1. ...\\n2. ...\", \"expected_behavior\": \"...\", \"labels\": [\"前端\", \"Bug\"]}。复现步骤要分行编号、动作具体；预期行为一句话；labels 必须从给定的 labels 列表中选取（最多 3 个），都不匹配时返回空数组。",
  "user_prompt_template": "用户描述:\n{description}\n\n分类:\n{classify_json}\n\n抽取:\n{extract_json}\n\n可用标签:\n{labels_json}",
  "llm_model": "deepseek-v4-flash",
  "temperature": 0.5,
  "is_active": true
}
```

- [ ] **Step 4: Create the migration**

Create `backend/apps/ai/migrations/0005_seed_wizard_prompts.py`:

```python
import json
from pathlib import Path

from django.db import migrations


SEED_DIR = Path(__file__).resolve().parent.parent / "seed_prompts"
SLUGS = ("wizard_classify", "wizard_extract", "wizard_generate")


def seed_wizard_prompts(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    for slug in SLUGS:
        data = json.loads((SEED_DIR / f"{slug}.json").read_text(encoding="utf-8"))
        Prompt.objects.update_or_create(
            slug=slug,
            defaults={
                "name": data["name"],
                "system_prompt": data["system_prompt"],
                "user_prompt_template": data["user_prompt_template"],
                "llm_model": data["llm_model"],
                "temperature": data["temperature"],
                "is_active": data["is_active"],
            },
        )


def unseed_wizard_prompts(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug__in=SLUGS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0004_fix_duplicate_check_model"),
    ]

    operations = [
        migrations.RunPython(seed_wizard_prompts, reverse_code=unseed_wizard_prompts),
    ]
```

- [ ] **Step 5: Apply the migration**

Run: `cd backend && uv run python manage.py migrate ai`
Expected: `Applying ai.0005_seed_wizard_prompts... OK`

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/ai/seed_prompts/wizard_*.json backend/apps/ai/migrations/0005_seed_wizard_prompts.py backend/tests/test_ai_wizard.py
git commit -m "feat(ai): seed three wizard prompts (classify/extract/generate)"
```

---

# Phase 3 — AI Wizard Service

### Task 6: `AiWizardService.classify` — single LLM call returning {category, scope}

**Files:**
- Create: `backend/apps/issues/services_ai_wizard.py`
- Modify: `backend/tests/test_ai_wizard.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
from unittest.mock import patch


@pytest.mark.django_db
def test_classify_returns_parsed_json():
    from apps.issues.services_ai_wizard import AiWizardService

    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    fake = '{"category": "前端 UI", "scope": "通知中心铃铛下拉"}'
    with patch("apps.issues.services_ai_wizard.LLMClient.complete", return_value=fake):
        svc = AiWizardService()
        result = svc.classify("点击铃铛没反应")

    assert result == {"category": "前端 UI", "scope": "通知中心铃铛下拉"}


@pytest.mark.django_db
def test_classify_raises_on_bad_json():
    from apps.issues.services_ai_wizard import AiWizardService, AiWizardError

    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", return_value="not json"):
        svc = AiWizardService()
        with pytest.raises(AiWizardError) as exc:
            svc.classify("点击铃铛没反应")
        assert exc.value.code == "llm_bad_json"
        assert exc.value.step == 1


@pytest.mark.django_db
def test_classify_raises_on_missing_prompt():
    from apps.issues.services_ai_wizard import AiWizardService, AiWizardError
    Prompt.objects.filter(slug="wizard_classify").delete()

    svc = AiWizardService()
    with pytest.raises(AiWizardError) as exc:
        svc.classify("点击铃铛没反应")
    assert exc.value.code == "missing_prompt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_classify_returns_parsed_json -v`
Expected: `ModuleNotFoundError: No module named 'apps.issues.services_ai_wizard'`

- [ ] **Step 3: Create the service file with classify**

Create `backend/apps/issues/services_ai_wizard.py`:

```python
"""AI wizard service — three-stage LLM pipeline that drafts an Issue from a
free-form bug description. Used by the SSE endpoint POST /api/issues/ai-draft/.
"""
import json
import logging
from dataclasses import dataclass

from apps.ai.client import LLMClient
from apps.ai.models import LLMConfig, Prompt


logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 20


@dataclass
class AiWizardError(Exception):
    step: int
    code: str
    message: str

    def __str__(self):
        return f"[step {self.step}] {self.code}: {self.message}"


class AiWizardService:
    """Three-stage LLM pipeline for the issue creation wizard.

    Each stage:
      1. classify(description) → {category, scope}
      2. extract(description, classify, modules) → {title, priority, module}
      3. generate(description, classify, extract, labels) → {repro_steps, expected_behavior, labels}

    On any LLM failure or malformed JSON, raises AiWizardError carrying the
    failed step number and a typed error code for the SSE layer to relay.
    """

    def _run_prompt(self, step: int, slug: str, **format_kwargs) -> dict:
        prompt = Prompt.objects.filter(slug=slug, is_active=True).first()
        if prompt is None:
            raise AiWizardError(step=step, code="missing_prompt", message=f"未配置 Prompt: {slug}")

        config = prompt.llm_config or LLMConfig.objects.filter(is_default=True, is_active=True).first()
        if config is None:
            raise AiWizardError(step=step, code="missing_llm_config", message="未配置可用的 LLM")

        try:
            user_prompt = prompt.user_prompt_template.format(**format_kwargs)
        except KeyError as e:
            raise AiWizardError(step=step, code="prompt_format_error", message=f"模板缺失变量 {e}")

        try:
            raw = LLMClient(config).complete(
                model=prompt.llm_model,
                system_prompt=prompt.system_prompt,
                user_prompt=user_prompt,
                temperature=prompt.temperature,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except Exception as e:
            logger.warning("wizard step=%s LLM call failed: %s", step, e, exc_info=True)
            raise AiWizardError(step=step, code="llm_call_failed", message="AI 调用失败，请重试")

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("wizard step=%s bad JSON: %r", step, raw)
            raise AiWizardError(step=step, code="llm_bad_json", message="AI 返回格式异常，请重试")

    def classify(self, description: str) -> dict:
        return self._run_prompt(step=1, slug="wizard_classify", description=description)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_classify_returns_parsed_json tests/test_ai_wizard.py::test_classify_raises_on_bad_json tests/test_ai_wizard.py::test_classify_raises_on_missing_prompt -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services_ai_wizard.py backend/tests/test_ai_wizard.py
git commit -m "feat(issues): add AiWizardService.classify with typed errors"
```

---

### Task 7: `AiWizardService.extract` — uses classify + modules to extract title/priority/module

**Files:**
- Modify: `backend/apps/issues/services_ai_wizard.py`
- Modify: `backend/tests/test_ai_wizard.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_extract_returns_parsed_json():
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    fake = '{"title": "通知中心铃铛下拉无响应", "priority": "P2", "module": "通知中心"}'
    with patch("apps.issues.services_ai_wizard.LLMClient.complete", return_value=fake):
        svc = AiWizardService()
        result = svc.extract(
            description="点击铃铛没反应",
            classify={"category": "前端 UI", "scope": "通知中心"},
            modules=["通知中心", "审批流程"],
        )

    assert result["title"] == "通知中心铃铛下拉无响应"
    assert result["priority"] == "P2"
    assert result["module"] == "通知中心"


@pytest.mark.django_db
def test_extract_passes_modules_into_template():
    """Modules list must reach the LLM via the user_prompt_template."""
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    captured = {}
    def fake_complete(self, model, system_prompt, user_prompt, temperature, timeout=None):
        captured["user_prompt"] = user_prompt
        return '{"title": "x", "priority": "P2", "module": "通知中心"}'

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        svc = AiWizardService()
        svc.extract(description="d", classify={"category": "c"}, modules=["通知中心", "审批流程"])

    assert "通知中心" in captured["user_prompt"]
    assert "审批流程" in captured["user_prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_extract_returns_parsed_json tests/test_ai_wizard.py::test_extract_passes_modules_into_template -v`
Expected: 2 failures (`AttributeError: 'AiWizardService' object has no attribute 'extract'`).

- [ ] **Step 3: Implement `extract`**

Add at the end of `AiWizardService` in `backend/apps/issues/services_ai_wizard.py`:

```python
    def extract(self, description: str, classify: dict, modules: list) -> dict:
        return self._run_prompt(
            step=2,
            slug="wizard_extract",
            description=description,
            classify_json=json.dumps(classify, ensure_ascii=False),
            modules_json=json.dumps(modules, ensure_ascii=False),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_extract_returns_parsed_json tests/test_ai_wizard.py::test_extract_passes_modules_into_template -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services_ai_wizard.py backend/tests/test_ai_wizard.py
git commit -m "feat(issues): add AiWizardService.extract stage"
```

---

### Task 8: `AiWizardService.generate` — produces repro_steps, expected_behavior, labels

**Files:**
- Modify: `backend/apps/issues/services_ai_wizard.py`
- Modify: `backend/tests/test_ai_wizard.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_generate_returns_parsed_json():
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    fake = (
        '{"repro_steps": "1. 点击铃铛\\n2. 看不到列表",'
        ' "expected_behavior": "应展开通知列表",'
        ' "labels": ["前端", "Bug"]}'
    )
    with patch("apps.issues.services_ai_wizard.LLMClient.complete", return_value=fake):
        svc = AiWizardService()
        result = svc.generate(
            description="点击铃铛没反应",
            classify={"category": "前端 UI"},
            extract={"title": "x", "priority": "P2", "module": "通知中心"},
            labels=["前端", "Bug", "后端"],
        )

    assert "1. 点击铃铛" in result["repro_steps"]
    assert result["expected_behavior"] == "应展开通知列表"
    assert result["labels"] == ["前端", "Bug"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_generate_returns_parsed_json -v`
Expected: `AttributeError: 'AiWizardService' object has no attribute 'generate'`.

- [ ] **Step 3: Implement `generate`**

Add at the end of `AiWizardService` in `backend/apps/issues/services_ai_wizard.py`:

```python
    def generate(self, description: str, classify: dict, extract: dict, labels: list) -> dict:
        return self._run_prompt(
            step=3,
            slug="wizard_generate",
            description=description,
            classify_json=json.dumps(classify, ensure_ascii=False),
            extract_json=json.dumps(extract, ensure_ascii=False),
            labels_json=json.dumps(labels, ensure_ascii=False),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_generate_returns_parsed_json -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services_ai_wizard.py backend/tests/test_ai_wizard.py
git commit -m "feat(issues): add AiWizardService.generate stage"
```

---

### Task 9: `AiWizardService.stream_draft` — generator yielding SSE events

**Files:**
- Modify: `backend/apps/issues/services_ai_wizard.py`
- Modify: `backend/tests/test_ai_wizard.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_stream_draft_emits_three_steps_then_draft_and_done():
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["通知中心"], labels={"前端": {"foreground": "#fff", "background": "#000", "description": ""}, "Bug": {"foreground": "#fff", "background": "#d00", "description": ""}})

    responses = iter([
        '{"category": "前端 UI", "scope": "通知中心"}',
        '{"title": "T", "priority": "P2", "module": "通知中心"}',
        '{"repro_steps": "1. 步骤", "expected_behavior": "应正常", "labels": ["前端"]}',
    ])

    def fake_complete(self, **kwargs):
        return next(responses)

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        svc = AiWizardService()
        events = list(svc.stream_draft(description="点击铃铛没反应"))

    names = [e[0] for e in events]
    assert names == ["step", "step", "step", "draft", "done"]

    # Step events carry step numbers 1,2,3
    assert events[0][1]["step"] == 1
    assert events[1][1]["step"] == 2
    assert events[2][1]["step"] == 3

    # Draft event merges everything
    draft = events[3][1]
    assert draft["title"] == "T"
    assert draft["priority"] == "P2"
    assert draft["module"] == "通知中心"
    assert "1. 步骤" in draft["repro_steps"]
    assert draft["expected_behavior"] == "应正常"
    assert draft["labels"] == ["前端"]


@pytest.mark.django_db
def test_stream_draft_yields_error_when_step_fails():
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    def fake_complete(self, **kwargs):
        return "not json"

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        svc = AiWizardService()
        events = list(svc.stream_draft(description="x"))

    assert events[-1][0] == "error"
    err = events[-1][1]
    assert err["step"] == 1
    assert err["code"] == "llm_bad_json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_stream_draft_emits_three_steps_then_draft_and_done tests/test_ai_wizard.py::test_stream_draft_yields_error_when_step_fails -v`
Expected: 2 failures.

- [ ] **Step 3: Implement `stream_draft`**

Add at the end of `AiWizardService` in `backend/apps/issues/services_ai_wizard.py`:

```python
    def stream_draft(self, description: str):
        """Generator yielding (event_name, data_dict) tuples for the SSE layer.

        Events:
          ("step", {"step": N, "label": ..., "status": "done", "result": {...}})
          ("draft", merged_draft)
          ("done", {})
          ("error", {"step": N, "code": ..., "message": ...})  on failure
        """
        from apps.settings.models import SiteSettings

        site = SiteSettings.get_solo()
        modules = list(site.modules or [])
        labels_dict = site.labels or {}
        labels_list = list(labels_dict.keys()) if isinstance(labels_dict, dict) else list(labels_dict)

        try:
            classify = self.classify(description)
            yield ("step", {
                "step": 1,
                "label": "识别问题类型与影响范围",
                "status": "done",
                "result": classify,
            })

            extract = self.extract(description, classify, modules)
            yield ("step", {
                "step": 2,
                "label": "提取关键字段",
                "status": "done",
                "result": extract,
            })

            generate = self.generate(description, classify, extract, labels_list)
            yield ("step", {
                "step": 3,
                "label": "生成复现步骤与预期行为",
                "status": "done",
                "result": generate,
            })

            yield ("draft", self._merge(description, classify, extract, generate))
            yield ("done", {})

        except AiWizardError as e:
            yield ("error", {"step": e.step, "code": e.code, "message": e.message})

    def _merge(self, description: str, classify: dict, extract: dict, generate: dict) -> dict:
        return {
            "title": extract.get("title", ""),
            "description": description,  # client decides whether to use AI-rephrased or raw input
            "repro_steps": generate.get("repro_steps", ""),
            "expected_behavior": generate.get("expected_behavior", ""),
            "priority": extract.get("priority", "P2"),
            "module": extract.get("module", ""),
            "labels": generate.get("labels", []),
            "environment": None,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v`
Expected: all wizard tests pass (12+).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services_ai_wizard.py backend/tests/test_ai_wizard.py
git commit -m "feat(issues): AiWizardService.stream_draft orchestrates 3 stages over SSE"
```

---

# Phase 4 — SSE Endpoint

### Task 10: `POST /api/issues/ai-draft/` SSE view

**Files:**
- Modify: `backend/apps/issues/views.py` (append new view + serializer)
- Modify: `backend/apps/issues/urls.py` (wire URL)
- Modify: `backend/apps/issues/serializers.py` (add input serializer)
- Modify: `backend/tests/test_ai_wizard.py` (append view tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_ai_draft_endpoint_requires_authentication(api_client):
    resp = api_client.post("/api/issues/ai-draft/", {"description": "x", "project": 1}, format="json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_ai_draft_endpoint_validates_description(api_client):
    user = UserFactory()
    api_client.force_authenticate(user)

    resp = api_client.post("/api/issues/ai-draft/", {"project": 1}, format="json")
    assert resp.status_code == 400
    assert "description" in resp.data


@pytest.mark.django_db
def test_ai_draft_endpoint_streams_sse_events(api_client):
    """Smoke test: SSE response with correct content type and 3 step events + draft + done."""
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["通知中心"])
    project = ProjectFactory()
    user = UserFactory()
    api_client.force_authenticate(user)

    responses = iter([
        '{"category": "前端", "scope": "通知中心"}',
        '{"title": "T", "priority": "P2", "module": "通知中心"}',
        '{"repro_steps": "1. x", "expected_behavior": "y", "labels": []}',
    ])
    def fake_complete(self, **kwargs):
        return next(responses)

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        resp = api_client.post(
            "/api/issues/ai-draft/",
            {"description": "点击铃铛没反应", "project": str(project.id)},
            format="json",
        )

    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/event-stream")
    assert resp.get("X-Accel-Buffering") == "no"

    body = b"".join(resp.streaming_content).decode()
    assert body.count("event: step") == 3
    assert "event: draft" in body
    assert "event: done" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v -k "endpoint"`
Expected: 3 failures (404 — URL not registered).

- [ ] **Step 3: Add input serializer**

Append to `backend/apps/issues/serializers.py`:

```python
class AiDraftInputSerializer(serializers.Serializer):
    description = serializers.CharField(min_length=5, max_length=4000)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
```

If `Project` isn't already imported in this file, add `from apps.projects.models import Project` at the top.

- [ ] **Step 4: Add the view**

Append to `backend/apps/issues/views.py`:

```python
import json as _json
from django.http import StreamingHttpResponse


class IssueAiDraftView(APIView):
    """POST /api/issues/ai-draft/ — SSE stream that drafts an Issue from
    a free-form bug description via the 3-stage AI wizard pipeline.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .serializers import AiDraftInputSerializer
        from .services_ai_wizard import AiWizardService

        serializer = AiDraftInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def event_stream():
            svc = AiWizardService()
            for event_name, payload in svc.stream_draft(description=data["description"]):
                yield f"event: {event_name}\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"

        resp = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        resp["X-Accel-Buffering"] = "no"
        resp["Cache-Control"] = "no-cache"
        return resp
```

- [ ] **Step 5: Wire the URL**

Edit `backend/apps/issues/urls.py`. Add `IssueAiDraftView` to the imports and add to `urlpatterns`:

```python
from .views import (
    IssueListCreateView, IssueDetailView, BatchUpdateView,
    IssueGitHubCreateView, IssueGitHubLinkView, IssueCloseWithGitHubView,
    IssueAIAnalyzeView, IssueAIStatusView, IssueAnalysesView,
    IssueAttachmentsView, IssueCheckDuplicateView, IssueHistoryView,
    IssueAiDraftView,
)

urlpatterns = [
    # ... existing ...
    path("ai-draft/", IssueAiDraftView.as_view(), name="issue-ai-draft"),
]
```

Place the new line before any `<int:pk>/...` patterns so the literal path doesn't get captured as a pk.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py -v`
Expected: all wizard tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/issues/views.py backend/apps/issues/urls.py backend/apps/issues/serializers.py backend/tests/test_ai_wizard.py
git commit -m "feat(issues): POST /api/issues/ai-draft/ SSE endpoint"
```

---

### Task 11: Allow `source` and `source_meta` on Issue create

**Files:**
- Modify: `backend/apps/issues/serializers.py:114-121`
- Modify: `backend/tests/test_ai_wizard.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_ai_wizard.py`:

```python
@pytest.mark.django_db
def test_issue_create_accepts_source_and_source_meta(api_client):
    """The wizard sets source='ai_wizard' and source_meta={module, environment, ...} on the new Issue."""
    from tests.factories import ProjectFactory
    user = UserFactory()
    project = ProjectFactory()
    api_client.force_authenticate(user)

    resp = api_client.post(
        "/api/issues/",
        {
            "project": str(project.id),
            "title": "通过向导创建",
            "description": "AI-rephrased desc\n\n## 复现步骤\n1. x",
            "priority": "P2",
            "labels": [],
            "source": "ai_wizard",
            "source_meta": {"module": "通知中心", "environment": "Chrome / Windows"},
        },
        format="json",
    )

    assert resp.status_code == 201, resp.data
    from apps.issues.models import Issue
    issue = Issue.objects.get(pk=resp.data["id"])
    assert issue.source == "ai_wizard"
    assert issue.source_meta == {"module": "通知中心", "environment": "Chrome / Windows"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_issue_create_accepts_source_and_source_meta -v`
Expected: failure — `source` either not accepted or persisted as null.

- [ ] **Step 3: Add `source` and `source_meta` to writable fields**

Edit `backend/apps/issues/serializers.py:114-121`. In the `IssueCreateUpdateSerializer.Meta.fields` list, append `"source"` and `"source_meta"`:

```python
class Meta:
    model = Issue
    fields = [
        "id", "project", "repo", "title", "description", "priority", "status",
        "labels", "assignee", "helpers", "reporter", "remark", "estimated_completion",
        "estimated_hours", "actual_hours", "cause", "solution", "attachment_ids",
        "source", "source_meta",
    ]
    read_only_fields = ["id"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_ai_wizard.py::test_issue_create_accepts_source_and_source_meta -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/serializers.py backend/tests/test_ai_wizard.py
git commit -m "feat(issues): allow source and source_meta on Issue create"
```

---

# Phase 5 — Frontend Composable

### Task 12: `useAiWizard` SSE consumer composable

**Files:**
- Create: `frontend/app/composables/useAiWizard.ts`

- [ ] **Step 1: Write the composable**

Create `frontend/app/composables/useAiWizard.ts`:

```typescript
type WizardState = 'idle' | 'analyzing' | 'drafting' | 'error'

type StepStatus = 'pending' | 'done' | 'error'

type StepProgress = {
  step: 1 | 2 | 3
  label: string
  status: StepStatus
}

export type WizardDraft = {
  title: string
  description: string
  repro_steps: string
  expected_behavior: string
  priority: 'P0' | 'P1' | 'P2' | 'P3'
  module: string
  labels: string[]
  environment: string | null
}

const INITIAL_STEPS: StepProgress[] = [
  { step: 1, label: '识别问题类型与影响范围', status: 'pending' },
  { step: 2, label: '提取关键字段', status: 'pending' },
  { step: 3, label: '生成复现步骤与预期行为', status: 'pending' },
]

export function useAiWizard() {
  const state = ref<WizardState>('idle')
  const steps = ref<StepProgress[]>(structuredClone(INITIAL_STEPS))
  const draft = ref<WizardDraft | null>(null)
  const errorMessage = ref<string>('')

  let abortController: AbortController | null = null

  function reset() {
    state.value = 'idle'
    steps.value = structuredClone(INITIAL_STEPS)
    draft.value = null
    errorMessage.value = ''
    abortController?.abort()
    abortController = null
  }

  async function start(params: { description: string; project: string; attachment_ids?: string[] }) {
    reset()
    state.value = 'analyzing'
    abortController = new AbortController()

    const token = useCookie('access_token').value
    let resp: Response
    try {
      resp = await fetch('/api/issues/ai-draft/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          description: params.description,
          project: params.project,
          attachment_ids: params.attachment_ids || [],
        }),
        signal: abortController.signal,
      })
    } catch (e: any) {
      state.value = 'error'
      errorMessage.value = e?.message || '网络错误，请重试'
      return
    }

    if (!resp.ok || !resp.body) {
      state.value = 'error'
      errorMessage.value = `请求失败 (${resp.status})`
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // Split SSE frames: blank line separates events
        let idx
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          handleFrame(frame)
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        state.value = 'error'
        errorMessage.value = e?.message || '流读取失败'
      }
    }
  }

  function handleFrame(frame: string) {
    // Parse "event: <name>\ndata: <json>"
    const lines = frame.split('\n')
    let event = 'message'
    let data = ''
    for (const ln of lines) {
      if (ln.startsWith('event:')) event = ln.slice(6).trim()
      else if (ln.startsWith('data:')) data = ln.slice(5).trim()
    }
    if (!data) return
    let payload: any
    try { payload = JSON.parse(data) } catch { return }

    if (event === 'step') {
      const s = steps.value.find(x => x.step === payload.step)
      if (s) s.status = 'done'
    } else if (event === 'draft') {
      draft.value = payload as WizardDraft
      state.value = 'drafting'
    } else if (event === 'error') {
      const s = steps.value.find(x => x.step === payload.step)
      if (s) s.status = 'error'
      state.value = 'error'
      errorMessage.value = payload.message || 'AI 分析失败'
    }
    // 'done' is a no-op signal — the stream is finished
  }

  function abort() {
    abortController?.abort()
    abortController = null
  }

  return { state, steps, draft, errorMessage, start, reset, abort }
}
```

- [ ] **Step 2: Type check the frontend**

Run: `cd frontend && npx nuxi typecheck 2>&1 | grep "useAiWizard\|AiIssueWizard" | head -10`
Expected: no errors in `useAiWizard.ts` (other pre-existing errors elsewhere are OK).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/composables/useAiWizard.ts
git commit -m "feat(frontend): add useAiWizard SSE composable"
```

---

# Phase 6 — Frontend Components

### Task 13: `AiBadge` small pill component

**Files:**
- Create: `frontend/app/components/AiIssueWizard/AiBadge.vue`

- [ ] **Step 1: Create the component**

Create `frontend/app/components/AiIssueWizard/AiBadge.vue`:

```vue
<template>
  <span class="ai-badge" :class="kindClass">{{ label }}</span>
</template>

<script setup lang="ts">
const props = defineProps<{ kind: 'generated' | 'inferred' }>()

const label = computed(() => (props.kind === 'generated' ? 'AI 生成' : 'AI 推断'))
const kindClass = computed(() => `ai-badge--${props.kind}`)
</script>

<style scoped>
.ai-badge {
  display: inline-flex;
  align-items: center;
  margin-left: 0.5rem;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.6875rem;
  font-weight: 500;
  line-height: 1;
}
.ai-badge--generated {
  color: #2563eb;
  background-color: #dbeafe;
}
.ai-badge--inferred {
  color: #7c3aed;
  background-color: #ede9fe;
}
:root.dark .ai-badge--generated {
  color: #93c5fd;
  background-color: rgba(37, 99, 235, 0.15);
}
:root.dark .ai-badge--inferred {
  color: #c4b5fd;
  background-color: rgba(124, 58, 237, 0.15);
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/components/AiIssueWizard/AiBadge.vue
git commit -m "feat(frontend): add AiBadge component for 'AI 生成'/'AI 推断' pills"
```

---

### Task 14: `StepDescribe.vue` — Step 1 view

**Files:**
- Create: `frontend/app/components/AiIssueWizard/StepDescribe.vue`

- [ ] **Step 1: Create the component**

Create `frontend/app/components/AiIssueWizard/StepDescribe.vue`:

```vue
<template>
  <div class="step-describe">
    <div class="chips">
      <button v-for="chip in chips" :key="chip.label" class="chip" type="button" @click="fillChip(chip.value)">
        {{ chip.label }}
      </button>
    </div>

    <div class="input-wrap">
      <div class="input-header">
        <USelect
          v-model="projectId"
          :items="projectOptions"
          value-key="value"
          size="sm"
          placeholder="选择项目"
          class="project-select"
          :ui="{ base: 'min-w-44' }"
        />
      </div>

      <UTextarea
        v-model="description"
        :rows="3"
        placeholder="描述你发现的问题：在哪个页面、做了什么操作、出现了什么现象？也可以粘贴截图 (Ctrl+V) 或拖拽文件…"
        autoresize
      />

      <div class="toolbar">
        <UButton size="xs" variant="ghost" color="neutral" icon="i-heroicons-plus" />
        <UButton size="xs" variant="ghost" color="neutral" icon="i-heroicons-photo" />
        <span class="toolbar-hint">拖拽 · Ctrl+V 粘贴 · Enter 分析</span>
        <div class="toolbar-spacer" />
        <USelect
          v-model="modelLabel"
          :items="modelOptions"
          size="xs"
          class="model-select"
          disabled
        />
        <UButton
          size="sm"
          icon="i-heroicons-magnifying-glass"
          :disabled="!canAnalyze"
          @click="onAnalyze"
        >
          AI 分析
        </UButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
type Project = { id: string; name: string }

const props = defineProps<{
  projects: Project[]
  defaultProjectId: string | null
}>()

const emit = defineEmits<{
  analyze: [payload: { description: string; project: string }]
}>()

const description = ref('')
const projectId = ref<string>(props.defaultProjectId ?? '')
const modelLabel = ref('✦ GPT-4o')

const projectOptions = computed(() =>
  props.projects.map(p => ({ label: p.name, value: String(p.id) })),
)

const modelOptions = ['✦ GPT-4o', '◆ Claude 3.5', '◉ Gemini 2.0']

const chips = [
  { label: '🖱 按钮无响应', value: '点击提交按钮后页面没有任何反应，按钮无响应' },
  { label: '⬜ 页面白屏', value: '页面加载后出现白屏，控制台报错 Cannot read properties of undefined' },
  { label: '💾 数据未保存', value: '表单提交后数据没有保存，刷新后内容消失' },
  { label: '🔗 跳转异常', value: '通知中心点击待审批事项后跳转到错误页面' },
  { label: '🖼 上传异常', value: '上传图片后显示上传成功但图片列表中看不到' },
]

const canAnalyze = computed(() => description.value.trim().length >= 5 && !!projectId.value)

function fillChip(text: string) {
  description.value = text
}

function onAnalyze() {
  if (!canAnalyze.value) return
  emit('analyze', { description: description.value.trim(), project: projectId.value })
}

watch(() => props.defaultProjectId, (v) => {
  if (v && !projectId.value) projectId.value = v
})
</script>

<style scoped>
.step-describe { display: flex; flex-direction: column; gap: 1rem; }
.chips { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.chip {
  padding: 0.375rem 0.875rem;
  border-radius: 9999px;
  background-color: #f3f4f6;
  font-size: 0.8125rem;
  color: #374151;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background-color 0.15s;
}
.chip:hover { background-color: #e5e7eb; }
:root.dark .chip { background-color: #1f2937; color: #d1d5db; }
:root.dark .chip:hover { background-color: #374151; }

.input-wrap {
  display: flex; flex-direction: column; gap: 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.875rem;
  padding: 0.875rem;
  background-color: #ffffff;
}
:root.dark .input-wrap { border-color: #374151; background-color: #111827; }

.input-header { display: flex; gap: 0.5rem; }
.project-select :deep(button) { font-size: 0.8125rem; }

.toolbar { display: flex; align-items: center; gap: 0.5rem; }
.toolbar-hint { font-size: 0.75rem; color: #9ca3af; }
.toolbar-spacer { flex: 1; }
.model-select :deep(button) { min-width: 8rem; font-size: 0.75rem; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/components/AiIssueWizard/StepDescribe.vue
git commit -m "feat(frontend): add Step 1 (describe) view for AI wizard"
```

---

### Task 15: `StepAnalyzing.vue` — Step 2 loading view

**Files:**
- Create: `frontend/app/components/AiIssueWizard/StepAnalyzing.vue`

- [ ] **Step 1: Create the component**

Create `frontend/app/components/AiIssueWizard/StepAnalyzing.vue`:

```vue
<template>
  <div class="step-analyzing">
    <div class="spinner-row">
      <UIcon name="i-heroicons-cpu-chip" class="w-5 h-5 text-crystal-500 animate-spin" />
      <span class="title">AI 正在分析…</span>
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

<style scoped>
.step-analyzing { display: flex; flex-direction: column; gap: 1rem; padding: 1rem 0; }
.spinner-row { display: flex; align-items: center; gap: 0.5rem; }
.title { font-size: 0.875rem; font-weight: 500; color: #374151; }
:root.dark .title { color: #e5e7eb; }

.step-list { display: flex; flex-direction: column; gap: 0.5rem; padding-left: 1.5rem; }
.step-line { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8125rem; color: #6b7280; }
.step-line--done { color: #059669; }
.step-line--error { color: #dc2626; }
.dot {
  width: 0.5rem; height: 0.5rem; border-radius: 9999px;
  background-color: #d1d5db; animation: pulse 1s infinite alternate;
}
@keyframes pulse { from { opacity: 0.4; } to { opacity: 1; } }

.error-msg { font-size: 0.8125rem; color: #dc2626; }
.actions { display: flex; gap: 0.5rem; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/components/AiIssueWizard/StepAnalyzing.vue
git commit -m "feat(frontend): add Step 2 (analyzing) view with progress + retry"
```

---

### Task 16: `StepDraft.vue` — Step 3 draft form + success state

**Files:**
- Create: `frontend/app/components/AiIssueWizard/StepDraft.vue`

- [ ] **Step 1: Create the component**

Create `frontend/app/components/AiIssueWizard/StepDraft.vue`:

```vue
<template>
  <div class="step-draft">
    <!-- Success state -->
    <div v-if="successIssueId" class="success">
      <div class="success-icon">
        <UIcon name="i-heroicons-check" class="w-8 h-8 text-emerald-500" />
      </div>
      <div class="success-title">Issue 已成功提交！</div>
      <div class="success-iss">ISS-{{ String(successIssueId).padStart(3, '0') }}</div>
      <div class="success-sub">
        <template v-if="form.assignee">已自动分配给 <strong>{{ assigneeName }}</strong> · </template>
        优先级 <strong>{{ form.priority }}</strong>
      </div>
      <UButton size="sm" icon="i-heroicons-plus" @click="emit('reset')">继续提交新 Issue</UButton>
    </div>

    <!-- Draft state -->
    <div v-else class="draft">
      <div class="draft-header">
        <UIcon name="i-heroicons-check" class="w-4 h-4 text-emerald-500" />
        <span class="draft-title">Issue 草稿已生成 · 请确认并编辑后提交</span>
        <span class="draft-sub">AI 自动填写 <span class="count">6</span> 个字段</span>
      </div>

      <div class="field">
        <label class="field-label">Issue 标题 <AiBadge kind="generated" /></label>
        <UInput v-model="form.title" />
      </div>

      <div class="field">
        <label class="field-label">问题描述</label>
        <UTextarea v-model="form.description" :rows="3" autoresize />
      </div>

      <div class="field">
        <label class="field-label">复现步骤 <AiBadge kind="generated" /></label>
        <UTextarea v-model="form.repro_steps" :rows="4" autoresize />
      </div>

      <div class="row-3">
        <div class="field">
          <label class="field-label">优先级 <AiBadge kind="inferred" /></label>
          <USelect v-model="form.priority" :items="priorityOptions" value-key="value" />
        </div>
        <div class="field">
          <label class="field-label">所属模块 <AiBadge kind="inferred" /></label>
          <USelect v-model="form.module" :items="moduleOptions" />
        </div>
        <div class="field">
          <label class="field-label">指派给</label>
          <USelect v-model="form.assignee" :items="assigneeOptions" value-key="value" placeholder="（不指派）" />
        </div>
      </div>

      <div class="row-3">
        <div class="field span-2">
          <label class="field-label">预期行为 <AiBadge kind="generated" /></label>
          <UInput v-model="form.expected_behavior" />
        </div>
        <div class="field">
          <label class="field-label">环境</label>
          <USelect v-model="form.environment" :items="envOptions" placeholder="（可选）" />
        </div>
      </div>

      <div class="field">
        <label class="field-label">项目</label>
        <USelect v-model="form.project" :items="projectOptions" value-key="value" />
      </div>

      <p v-if="submitError" class="submit-error">{{ submitError }}</p>

      <div class="footer">
        <span class="footer-hint">✦ 所有字段均可编辑 · 提交后将自动创建 Issue 并通知相关成员</span>
        <UButton variant="ghost" color="neutral" size="sm" @click="emit('back')">重新描述</UButton>
        <UButton
          size="sm"
          icon="i-heroicons-check"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="onSubmit"
        >提交 Issue</UButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AiBadge from './AiBadge.vue'
import type { WizardDraft } from '~/composables/useAiWizard'

type UserChoice = { id: string; name: string }
type Project = { id: string; name: string }

const props = defineProps<{
  draft: WizardDraft
  projects: Project[]
  initialProjectId: string
  modules: string[]
  users: UserChoice[]
  submitting: boolean
  submitError: string
  successIssueId: number | null
}>()

const emit = defineEmits<{
  submit: [payload: any]
  back: []
  reset: []
}>()

const form = ref({
  title: props.draft.title,
  description: props.draft.description,
  repro_steps: props.draft.repro_steps,
  expected_behavior: props.draft.expected_behavior,
  priority: props.draft.priority,
  module: props.draft.module,
  environment: props.draft.environment ?? '',
  labels: props.draft.labels,
  assignee: '',
  project: props.initialProjectId,
})

const priorityOptions = [
  { label: '🔴 P0 — 紧急', value: 'P0' },
  { label: '🟠 P1 — 高', value: 'P1' },
  { label: '🟡 P2 — 中', value: 'P2' },
  { label: '⚪ P3 — 低', value: 'P3' },
]

const envOptions = ['Chrome / Windows', 'Safari / macOS', 'Safari / iOS', 'Chrome / Android', '其他']

const projectOptions = computed(() => props.projects.map(p => ({ label: p.name, value: String(p.id) })))
const moduleOptions = computed(() => props.modules)
const assigneeOptions = computed(() => props.users.map(u => ({ label: u.name, value: String(u.id) })))

const assigneeName = computed(() => {
  const u = props.users.find(x => String(x.id) === String(form.value.assignee))
  return u?.name || ''
})

const canSubmit = computed(() => form.value.title.trim().length >= 3 && !!form.value.project && !props.submitting)

function onSubmit() {
  // Build the Issue create payload — embeds repro_steps + expected_behavior in description Markdown
  const desc = [
    form.value.description.trim(),
    form.value.repro_steps.trim() ? `\n\n## 复现步骤\n${form.value.repro_steps.trim()}` : '',
    form.value.expected_behavior.trim() ? `\n\n## 预期行为\n${form.value.expected_behavior.trim()}` : '',
  ].join('')

  const body: any = {
    project: form.value.project,
    title: form.value.title.trim(),
    description: desc,
    priority: form.value.priority,
    labels: form.value.labels,
    source: 'ai_wizard',
    source_meta: {
      module: form.value.module || null,
      environment: form.value.environment || null,
      original_input: props.draft.description,
    },
  }
  if (form.value.assignee) body.assignee = form.value.assignee

  emit('submit', body)
}
</script>

<style scoped>
.step-draft { display: flex; flex-direction: column; gap: 1rem; }
.draft-header {
  display: flex; align-items: center; gap: 0.5rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #f3f4f6;
}
:root.dark .draft-header { border-bottom-color: #374151; }
.draft-title { font-size: 0.875rem; font-weight: 600; color: #111827; }
:root.dark .draft-title { color: #f3f4f6; }
.draft-sub { font-size: 0.75rem; color: #9ca3af; margin-left: auto; }
.count { color: #7c3aed; font-weight: 600; }

.field { display: flex; flex-direction: column; gap: 0.375rem; }
.field-label { font-size: 0.8125rem; font-weight: 500; color: #374151; display: flex; align-items: center; }
:root.dark .field-label { color: #d1d5db; }
.row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }
.span-2 { grid-column: span 2; }
@media (max-width: 768px) { .row-3 { grid-template-columns: 1fr; } .span-2 { grid-column: auto; } }

.submit-error { font-size: 0.8125rem; color: #dc2626; }

.footer {
  display: flex; align-items: center; gap: 0.5rem;
  padding-top: 0.75rem; border-top: 1px solid #f3f4f6;
}
:root.dark .footer { border-top-color: #374151; }
.footer-hint { font-size: 0.75rem; color: #9ca3af; flex: 1; }

.success { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; padding: 2rem 0; }
.success-icon {
  width: 4rem; height: 4rem; border-radius: 9999px;
  display: flex; align-items: center; justify-content: center;
  background-color: #d1fae5;
}
:root.dark .success-icon { background-color: rgba(5, 150, 105, 0.18); }
.success-title { font-size: 1.125rem; font-weight: 600; color: #111827; }
:root.dark .success-title { color: #f3f4f6; }
.success-iss { font-size: 1.5rem; font-weight: 700; color: #7c3aed; font-family: ui-monospace, monospace; }
.success-sub { font-size: 0.8125rem; color: #6b7280; margin-bottom: 0.5rem; }
:root.dark .success-sub { color: #9ca3af; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/components/AiIssueWizard/StepDraft.vue
git commit -m "feat(frontend): add Step 3 (draft + success) view for AI wizard"
```

---

### Task 17: `AiIssueWizard.vue` top-level container

**Files:**
- Create: `frontend/app/components/AiIssueWizard.vue`

- [ ] **Step 1: Create the component**

Create `frontend/app/components/AiIssueWizard.vue`:

```vue
<template>
  <div class="ai-wizard">
    <!-- Header -->
    <div class="wizard-header">
      <div class="hello">
        <UIcon name="i-heroicons-sparkles" class="w-6 h-6 text-crystal-500" />
        <div>
          <h2 class="hello-title">你好，{{ userName }} <span class="wave">👋</span></h2>
          <p class="hello-sub">AI 助手已就绪 · 描述问题，让 AI 帮你创建 Issue</p>
        </div>
      </div>
      <div class="status">
        <span class="status-dot" />
        <span class="status-text">模型已就绪</span>
      </div>
    </div>

    <!-- Stepper -->
    <div class="stepper">
      <div class="step-pill" :class="{ active: currentStep >= 1, done: currentStep > 1 }">
        <span class="step-num">1</span>
        <span>描述问题</span>
      </div>
      <span class="step-connector" :class="{ done: currentStep > 1 }" />
      <div class="step-pill" :class="{ active: currentStep >= 2, done: currentStep > 2 }">
        <span class="step-num">2</span>
        <span>AI 分析</span>
      </div>
      <span class="step-connector" :class="{ done: currentStep > 2 }" />
      <div class="step-pill" :class="{ active: currentStep >= 3 }">
        <span class="step-num">3</span>
        <span>确认提交</span>
      </div>
    </div>

    <!-- Step body -->
    <StepDescribe
      v-if="currentStep === 1"
      :projects="projects"
      :default-project-id="defaultProjectId"
      @analyze="onAnalyze"
    />
    <StepAnalyzing
      v-else-if="currentStep === 2"
      :steps="wizard.steps.value"
      :error-message="wizard.errorMessage.value"
      @retry="onRetry"
      @back="onBackToDescribe"
    />
    <StepDraft
      v-else-if="currentStep === 3 && wizard.draft.value"
      :draft="wizard.draft.value"
      :projects="projects"
      :initial-project-id="lastAnalyzedProject"
      :modules="modules"
      :users="users"
      :submitting="submitting"
      :submit-error="submitError"
      :success-issue-id="successIssueId"
      @submit="onSubmit"
      @back="onBackToDescribe"
      @reset="onReset"
    />
  </div>
</template>

<script setup lang="ts">
import StepDescribe from './AiIssueWizard/StepDescribe.vue'
import StepAnalyzing from './AiIssueWizard/StepAnalyzing.vue'
import StepDraft from './AiIssueWizard/StepDraft.vue'

const emit = defineEmits<{ created: [issueId: number] }>()

const { api } = useApi()
const { user } = useAuth()

const userName = computed(() => user.value?.name || user.value?.email || '')
const defaultProjectId = computed(() => user.value?.default_project?.id || null)

const projects = ref<{ id: string; name: string }[]>([])
const modules = ref<string[]>([])
const users = ref<{ id: string; name: string }[]>([])
const lastAnalyzedProject = ref<string>('')

const wizard = useAiWizard()
const submitting = ref(false)
const submitError = ref('')
const successIssueId = ref<number | null>(null)

const currentStep = computed(() => {
  if (successIssueId.value) return 3
  if (wizard.state.value === 'idle') return 1
  if (wizard.state.value === 'analyzing' || wizard.state.value === 'error') return 2
  if (wizard.state.value === 'drafting') return 3
  return 1
})

onMounted(async () => {
  const [projectData, settingsData, usersData] = await Promise.all([
    api<any>('/api/projects/').catch(() => ({ results: [] })),
    api<any>('/api/settings/').catch(() => ({ modules: [] })),
    api<any[]>('/api/users/choices/').catch(() => []),
  ])
  projects.value = (projectData.results || projectData || []).map((p: any) => ({ id: String(p.id), name: p.name }))
  modules.value = settingsData.modules || []
  users.value = (usersData || []).map((u: any) => ({ id: String(u.id), name: u.name || u.username }))
})

function onAnalyze(payload: { description: string; project: string }) {
  lastAnalyzedProject.value = payload.project
  wizard.start(payload)
}

function onRetry() {
  // Re-run the analysis with the same description from the previous attempt
  // The composable holds no description state, so the user-facing flow goes back to step 1
  onBackToDescribe()
}

function onBackToDescribe() {
  wizard.reset()
  successIssueId.value = null
  submitError.value = ''
}

function onReset() {
  onBackToDescribe()
}

async function onSubmit(body: any) {
  submitting.value = true
  submitError.value = ''
  try {
    const created = await api<any>('/api/issues/', { method: 'POST', body, format: 'json' })
    successIssueId.value = Number(created.id)
    emit('created', created.id)
  } catch (e: any) {
    const data = e?.data || e?.response?._data
    submitError.value = (data && typeof data === 'object') ? JSON.stringify(data) : (e?.message || '创建失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.ai-wizard {
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 1rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
:root.dark .ai-wizard { background-color: #111827; border-color: #1f2937; }

.wizard-header { display: flex; justify-content: space-between; align-items: flex-start; }
.hello { display: flex; align-items: center; gap: 0.75rem; }
.hello-title { font-size: 1.125rem; font-weight: 600; color: #111827; }
.hello-sub { font-size: 0.8125rem; color: #6b7280; margin-top: 0.125rem; }
:root.dark .hello-title { color: #f3f4f6; }
:root.dark .hello-sub { color: #9ca3af; }
.wave { display: inline-block; animation: wave 1.5s ease-in-out infinite; transform-origin: 70% 70%; }
@keyframes wave { 0%,60%,100% { transform: rotate(0); } 20% { transform: rotate(14deg); } 40% { transform: rotate(-8deg); } }

.status { display: flex; align-items: center; gap: 0.375rem; }
.status-dot {
  width: 0.5rem; height: 0.5rem; border-radius: 9999px;
  background-color: #10b981; animation: pulse 1.5s infinite;
}
.status-text { font-size: 0.75rem; color: #6b7280; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

.stepper { display: flex; align-items: center; gap: 0.5rem; }
.step-pill {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.375rem 0.75rem; border-radius: 9999px;
  font-size: 0.8125rem; color: #9ca3af;
  background-color: #f3f4f6;
}
.step-pill.active { color: #7c3aed; background-color: #ede9fe; }
.step-pill.done { color: #059669; background-color: #d1fae5; }
:root.dark .step-pill { background-color: #1f2937; color: #6b7280; }
:root.dark .step-pill.active { background-color: rgba(124, 58, 237, 0.15); color: #c4b5fd; }
:root.dark .step-pill.done { background-color: rgba(5, 150, 105, 0.18); color: #34d399; }
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 1.25rem; height: 1.25rem;
  border-radius: 9999px;
  background-color: currentColor;
  color: #ffffff;
  font-size: 0.625rem; font-weight: 700;
}
.step-pill.active .step-num,
.step-pill.done .step-num { background-color: currentColor; color: #ffffff; }
.step-connector {
  height: 1px; flex: 1; max-width: 3rem;
  background-color: #e5e7eb;
}
.step-connector.done { background-color: #10b981; }
:root.dark .step-connector { background-color: #374151; }
</style>
```

- [ ] **Step 2: Manually smoke test**

Run: `cd frontend && npm run dev` and visit `http://localhost:3000/app/home`.
Expected error: home.vue not yet using the wizard — the component just doesn't appear yet. The component itself should compile without errors. Check `npx nuxi typecheck 2>&1 | grep AiIssueWizard` for errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/AiIssueWizard.vue
git commit -m "feat(frontend): add AiIssueWizard top-level component"
```

---

# Phase 7 — Home page integration

### Task 18: Mount `<AiIssueWizard />` on `home.vue` and strip quick-actions bar

**Files:**
- Modify: `frontend/app/pages/app/home.vue:1-20` (remove quick-actions bar), insert wizard above the loading block

- [ ] **Step 1: Replace the quick-actions bar with the wizard**

Edit `frontend/app/pages/app/home.vue`. Replace lines 3-20 (the `<!-- Quick Actions Bar -->` block) with:

```vue
    <!-- AI Issue Wizard -->
    <AiIssueWizard @created="onIssueCreated" />
```

Add `onIssueCreated` to the `<script setup>` block (right after `const isTester = computed(...)`):

```typescript
async function onIssueCreated(_issueId: number) {
  // Re-fetch My Todos so the new issue appears if assigned to current user
  if (isTester.value) {
    myIssues.value = await fetchTesterTodos()
  } else {
    myIssues.value = await fetchDefaultTodos()
  }
}
```

Also remove the `searchQuery` ref and `handleSearch()` function (no longer used now that the search box is gone). If the search box still appears anywhere else in the project, leave them alone.

- [ ] **Step 2: Run typecheck**

Run: `cd frontend && npx nuxi typecheck 2>&1 | grep "home.vue\|AiIssueWizard" | head -10`
Expected: no new errors related to the change. Pre-existing project errors are OK.

- [ ] **Step 3: Smoke test in browser**

Run `npm run dev` if not already running. Visit `http://localhost:3000/app/home`. Verify:
- Wizard appears at top
- "你好, {name} 👋" header shows your name
- Stepper shows 3 steps with step 1 highlighted
- 5 chips render correctly
- Clicking a chip fills the textarea
- "AI 分析" button enables once textarea has 5+ chars and a project is selected
- Clicking it transitions to Step 2 (loading animation)
- All 3 steps eventually turn green ✓
- Step 3 shows the draft card with `AI 生成` / `AI 推断` badges
- Clicking "提交 Issue" creates the issue and shows success card with the new ISS-ID

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pages/app/home.vue
git commit -m "feat(home): mount AI wizard hero, drop quick-actions bar"
```

---

### Task 19: Use `default_project` in the manual new-issue modal

**Files:**
- Modify: `frontend/app/pages/app/issues/index.vue` (the `showCreateModal = true` handler / `newIssue` ref initialization)

- [ ] **Step 1: Locate the project initialization**

Run: `grep -n "newIssue.value = \|project: ''" frontend/app/pages/app/issues/index.vue | head`

Look at where `newIssue` is initialized and where the modal opens. The current initialization sets `project: ''`. We need to default it to the user's effective default project on modal-open.

- [ ] **Step 2: Add `useAuth` import and update modal open path**

Confirm `useAuth` is already imported (Nuxt auto-import covers it). In the existing button:

```vue
<UButton icon="i-heroicons-plus" size="sm" @click="showCreateModal = true">
```

Change to:

```vue
<UButton icon="i-heroicons-plus" size="sm" @click="openCreateModal">
```

In the `<script setup>` section, add:

```typescript
const { user } = useAuth()

function openCreateModal() {
  if (!newIssue.value.project && user.value?.default_project) {
    newIssue.value.project = String(user.value.default_project.id)
  }
  showCreateModal.value = true
}
```

Also update `resetCreateForm` so that after submission/dismissal, the next open re-uses the default:

```typescript
function resetCreateForm() {
  newIssue.value = {
    project: String(user.value?.default_project?.id || ''),
    title: '',
    description: '',
    priority: 'P2',
    status: '待处理',
    labels: [],
    assignee: defaultAssignee.value,
    repo: null,
    reporter: user.value?.name || '',
  }
  attachmentIds.value = []
  projectRepos.value = []
}
```

- [ ] **Step 3: Manually verify**

Refresh `/app/issues`. Click "新建问题". The project select should be pre-filled with your default project (or the site default if you haven't set yours).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pages/app/issues/index.vue
git commit -m "feat(issues): default new-issue modal's project to user.default_project"
```

---

### Task 20: Default project on `/app/profile`

**Files:**
- Modify: `frontend/app/pages/app/profile.vue`
- Modify: `frontend/app/composables/useAuth.ts` (type augmentation)

- [ ] **Step 1: Type `default_project` on `AuthUser`**

Edit `frontend/app/composables/useAuth.ts`. Update the `AuthUser` interface:

```typescript
interface AuthUser {
  id: string
  name: string
  email: string
  avatar: string
  groups: string[]
  permissions: string[]
  settings: Record<string, any>
  is_superuser: boolean
  default_project: { id: string; name: string } | null
}
```

- [ ] **Step 2: Add the select control to profile.vue**

Read `frontend/app/pages/app/profile.vue` to find the form layout. Add a new form-row near the other personal settings (e.g., next to avatar / name). Add:

```vue
<div class="form-row">
  <label>默认项目</label>
  <USelect
    v-model="defaultProjectId"
    :items="projectOptions"
    value-key="value"
    placeholder="（使用站点默认）"
    @update:model-value="saveDefaultProject"
  />
  <p class="hint">新建问题/AI 向导会默认选中该项目</p>
</div>
```

Add to the `<script setup>` block:

```typescript
const projects = ref<{ id: string; name: string }[]>([])
const defaultProjectId = ref<string>('')

const projectOptions = computed(() => [
  { label: '（使用站点默认）', value: '' },
  ...projects.value.map(p => ({ label: p.name, value: String(p.id) })),
])

onMounted(async () => {
  const data = await api<any>('/api/projects/').catch(() => ({ results: [] }))
  projects.value = (data.results || data || []).map((p: any) => ({ id: String(p.id), name: p.name }))
  defaultProjectId.value = String(user.value?.default_project?.id || '')
})

async function saveDefaultProject(v: string) {
  try {
    await api('/api/auth/me/', {
      method: 'PATCH',
      body: { default_project: v || null },
      format: 'json',
    })
    // Re-fetch /me so the rest of the app sees the new value
    const { fetchMe } = useAuth()
    await fetchMe()
  } catch (e) {
    console.error('Failed to save default project:', e)
  }
}
```

- [ ] **Step 3: Manually verify**

Refresh `/app/profile`. Change the select to a different project. Refresh `/app/home`. Wizard's project selector should default to the new pick. Refresh `/app/issues` and open the new-issue modal — same project pre-selected.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pages/app/profile.vue frontend/app/composables/useAuth.ts
git commit -m "feat(profile): add default project setting; type AuthUser.default_project"
```

---

# Phase 8 — End-to-end verification

### Task 21: Smoke test the full flow

- [ ] **Step 1: Run backend tests**

Run: `cd backend && uv run pytest tests/test_default_project.py tests/test_ai_wizard.py -v`
Expected: all tests pass.

- [ ] **Step 2: Run a manual end-to-end smoke**

1. Start backend: `cd backend && uv run python manage.py runserver`
2. Start frontend: `cd frontend && npm run dev`
3. Visit `http://localhost:3000/app/home`
4. Click "🖱 按钮无响应" chip → textarea fills
5. Click "AI 分析" → step 2 shows loading; three lines turn green ✓ in order
6. Step 3 draft card appears with all 6 AI-filled fields, each labeled `AI 生成` or `AI 推断`
7. Edit the title slightly
8. Click "提交 Issue"
9. Success card shows `ISS-XXX` and "已自动分配给 ... · 优先级 P2"
10. Navigate to `/app/issues` → the new Issue is in the list
11. Click the new Issue → detail page shows `## 复现步骤` and `## 预期行为` Markdown sections rendered
12. Verify "外部来源" panel on the right shows `module` and `environment`
13. Click "继续提交新 Issue" → wizard resets to step 1

- [ ] **Step 3: Test the error path**

Temporarily break the LLM (e.g., set an invalid API key in the active `LLMConfig` via admin). Submit a description. Step 2 should show ✗ on whichever step failed, with the error message and "重试" / "重新描述" buttons.

Restore the LLM key when done.

- [ ] **Step 4: Commit the working test branch state**

If any inline fixes were needed, commit them:

```bash
git status
git add -A
git commit -m "fix: address smoke-test findings"
```

If nothing needs fixing, skip this step.

- [ ] **Step 5: Final summary**

Verify the entire branch:

```bash
git log main..HEAD --oneline
```

Expected: ~20 commits, each focused on one task.

---

## Self-Review Notes

**Spec coverage:**
- ✅ 3-step wizard UX → Tasks 13-17
- ✅ SSE with 3 progress events + draft + done + error → Tasks 9-10
- ✅ 3-stage prompting (classify/extract/generate) → Tasks 5-9
- ✅ Default project mechanism (SiteSettings + User + helper + API + 3 UI surfaces) → Tasks 1-4, 19-20
- ✅ Modules taxonomy (SiteSettings.modules + admin + AI constraint + draft dropdown) → Tasks 1, 4, 9, 17
- ✅ Issue field mapping (description as markdown, source/source_meta) → Tasks 11, 16
- ✅ Home page rewrite (strip quick-actions, mount wizard) → Task 18

**Out of scope explicitly NOT included** (per spec):
- LLM vision / image input
- Multi-LLM provider switching (model dropdown stays decorative)
- Stats deltas backend changes
- Restyle of existing stat cards / todos / mentions / activity sections (no new component work needed; the existing styles are kept until a follow-up design pass)
- Moving "新建 Issue" button to AppHeader (the page-level button on `/app/issues` stays; the AppHeader change is a Phase 2 polish)

**Module list flow checked:**
- Backend reads `SiteSettings.modules` and passes to `wizard_extract` (Task 9, `stream_draft`).
- Frontend fetches `/api/settings/` to populate the draft card dropdown (Task 17, `onMounted`).
- Admin edits to `SiteSettings.modules` reach both surfaces because both pull at request time.

**Type consistency checked:**
- `WizardDraft` shape in `useAiWizard.ts` matches `_merge()` output in `services_ai_wizard.py`.
- `StepProgress` in composable and `StepAnalyzing.vue` use identical fields.
- API responses: `default_project: {id, name}` consistent between `MeSerializer` and `SiteSettingsSerializer`.
