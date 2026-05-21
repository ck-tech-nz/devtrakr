import json

import pytest

from apps.ai.models import Prompt


@pytest.mark.django_db
def test_wizard_v1_prompts_active_for_rollback():
    """v1 prompts must stay ACTIVE so the AI_WIZARD_LEGACY rollback flag works.

    Migration 0007 originally deactivated v1 prompts but the legacy code path
    queries Prompt by slug + is_active=True — flipping the env flag in prod
    would have raised missing_prompt on every request. The migration was
    corrected to leave v1 active; the dispatcher in AiWizardService picks
    v2 by default.
    """
    for slug in ("wizard_classify", "wizard_extract", "wizard_generate"):
        p = Prompt.objects.filter(slug=slug).first()
        assert p is not None, f"v1 Prompt '{slug}' must be preserved for rollback"
        assert p.is_active, f"v1 Prompt '{slug}' must remain active for rollback to work"
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


@pytest.mark.django_db
def test_wizard_generate_prompt_was_updated_to_conservative_version():
    p = Prompt.objects.get(slug="wizard_generate")
    assert p.temperature <= 0.3, "Conservative version should have low temperature"
    assert "客服" in p.system_prompt or "忠实" in p.system_prompt, "Should mention faithful collection style"
    assert "follow_up_questions" in p.system_prompt


from unittest.mock import patch


@pytest.mark.django_db
def test_classify_returns_parsed_json():
    from apps.issues.services_ai_wizard import AiWizardService

    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    # Re-activate v1 prompts (deactivated by migration 0007, kept for rollback)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

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
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

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


@pytest.mark.django_db
def test_extract_returns_parsed_json():
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

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
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

    captured = {}
    def fake_complete(self, model, system_prompt, user_prompt, temperature, timeout=None):
        captured["user_prompt"] = user_prompt
        return '{"title": "x", "priority": "P2", "module": "通知中心"}'

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        svc = AiWizardService()
        svc.extract(description="d", classify={"category": "c"}, modules=["通知中心", "审批流程"])

    assert "通知中心" in captured["user_prompt"]
    assert "审批流程" in captured["user_prompt"]


@pytest.mark.django_db
def test_generate_returns_parsed_json():
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

    fake = (
        '{"repro_steps": "1. 点击铃铛\\n2. 看不到列表",'
        ' "expected_behavior": "应展开通知列表",'
        ' "labels": ["前端", "Bug"],'
        ' "follow_up_questions": []}'
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


@pytest.mark.django_db
def test_stream_draft_emits_three_steps_then_draft_and_done(site_settings, settings):
    settings.AI_WIZARD_LEGACY = True
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)
    SiteSettings.objects.update(
        modules=["通知中心"],
        labels={
            "前端": {"foreground": "#fff", "background": "#000", "description": ""},
            "Bug": {"foreground": "#fff", "background": "#d00", "description": ""},
        },
    )

    responses = iter([
        '{"category": "前端 UI", "scope": "通知中心"}',
        '{"title": "T", "priority": "P2", "module": "通知中心"}',
        '{"repro_steps": "1. 步骤", "expected_behavior": "应正常", "labels": ["前端"], "follow_up_questions": ["浏览器版本？", "复现频率？"]}',
    ])

    def fake_complete(self, **kwargs):
        return next(responses)

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        svc = AiWizardService()
        events = list(svc.stream_draft(description="点击铃铛没反应"))

    # 过滤掉 _heartbeat 内部信号事件,只校验对外可见的事件序列
    visible = [e for e in events if e[0] != "_heartbeat"]
    names = [e[0] for e in visible]
    assert names == ["step", "step", "step", "draft", "done"]

    # Step events carry step numbers 1,2,3
    assert visible[0][1]["step"] == 1
    assert visible[1][1]["step"] == 2
    assert visible[2][1]["step"] == 3

    # Draft event merges everything
    draft = visible[3][1]
    assert draft["title"] == "T"
    assert draft["priority"] == "P2"
    assert draft["module"] == "通知中心"
    assert "1. 步骤" in draft["repro_steps"]
    assert draft["expected_behavior"] == "应正常"
    assert draft["labels"] == ["前端"]
    assert draft["follow_up_questions"] == ["浏览器版本？", "复现频率？"]


@pytest.mark.django_db
def test_stream_draft_yields_error_when_step_fails(site_settings, settings):
    settings.AI_WIZARD_LEGACY = True
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

    def fake_complete(self, **kwargs):
        return "not json"

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        svc = AiWizardService()
        events = list(svc.stream_draft(description="x"))

    assert events[-1][0] == "error"
    err = events[-1][1]
    assert err["step"] == 1
    assert err["code"] == "llm_bad_json"


@pytest.mark.django_db
def test_ai_draft_endpoint_requires_authentication(api_client):
    resp = api_client.post("/api/issues/ai-draft/", {"description": "x", "project": 1}, format="json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_ai_draft_endpoint_validates_description(api_client):
    from django.contrib.auth.models import Permission
    from tests.factories import UserFactory
    user = UserFactory()
    perm = Permission.objects.get(codename="add_issue")
    user.user_permissions.add(perm)
    api_client.force_authenticate(user)

    resp = api_client.post("/api/issues/ai-draft/", {"project": 1}, format="json")
    assert resp.status_code == 400
    assert "description" in resp.data


@pytest.mark.django_db
def test_ai_draft_endpoint_requires_add_issue_permission(api_client):
    """User without issues.add_issue cannot trigger an AI draft."""
    from tests.factories import UserFactory
    user = UserFactory()  # no permissions
    api_client.force_authenticate(user)
    resp = api_client.post(
        "/api/issues/ai-draft/",
        {"description": "x" * 10, "project": 1},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_ai_draft_endpoint_streams_sse_events(api_client, site_settings, settings):
    """Smoke test: SSE response with correct content type and 3 step events + draft + done."""
    settings.AI_WIZARD_LEGACY = True
    from django.contrib.auth.models import Permission
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    LLMConfigFactory(is_default=True, is_active=True)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)
    SiteSettings.objects.update(modules=["通知中心"])
    project = ProjectFactory()
    user = UserFactory()
    perm = Permission.objects.get(codename="add_issue")
    user.user_permissions.add(perm)
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
        body = b"".join(resp.streaming_content).decode()

    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/event-stream")
    assert resp.get("X-Accel-Buffering") == "no"
    assert body.count("event: step") == 3
    assert "event: draft" in body
    assert "event: done" in body


@pytest.mark.django_db
def test_ai_draft_endpoint_accepts_text_event_stream(api_client, site_settings):
    """Client sending Accept: text/event-stream must not get 406."""
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    from django.contrib.auth.models import Permission
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["通知中心"])
    project = ProjectFactory()
    user = UserFactory()
    perm = Permission.objects.get(codename="add_issue")
    user.user_permissions.add(perm)
    api_client.force_authenticate(user)
    api_client.credentials(HTTP_ACCEPT="text/event-stream")

    responses = iter([
        '{"category": "x", "scope": "y"}',
        '{"title": "T", "priority": "P2", "module": "通知中心"}',
        '{"repro_steps": "1.", "expected_behavior": "y", "labels": []}',
    ])
    def fake_complete(self, **kwargs):
        return next(responses)

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        resp = api_client.post(
            "/api/issues/ai-draft/",
            {"description": "test description", "project": str(project.id)},
            format="json",
        )
        # Must not be 406
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.content!r}"
        assert resp["Content-Type"].startswith("text/event-stream")


@pytest.mark.django_db
def test_issue_create_accepts_source_and_source_meta(api_client):
    """The wizard sets source='ai_wizard' and source_meta={module, environment, ...} on the new Issue."""
    from tests.factories import ProjectFactory, UserFactory
    user = UserFactory(is_superuser=True, is_staff=True)
    project = ProjectFactory()
    api_client.force_authenticate(user)

    resp = api_client.post(
        "/api/issues/",
        {
            "project": str(project.id),
            "title": "通过向导创建",
            "description": "AI-rephrased desc\n\n## 复现步骤\n1. x",
            "priority": "P2",
            "status": "待分配",
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


@pytest.mark.django_db
def test_ai_draft_endpoint_throttles_excessive_requests(api_client, site_settings):
    """User exceeding 10 reqs/min gets 429."""
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    from django.contrib.auth.models import Permission
    from django.core.cache import cache
    cache.clear()  # 清理 throttle 计数器,避免与其它测试相互影响
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["x"])
    project = ProjectFactory()
    user = UserFactory()
    perm = Permission.objects.get(codename="add_issue")
    user.user_permissions.add(perm)
    api_client.force_authenticate(user)

    def fake_complete(self, **kwargs):
        return '{"category": "x", "scope": "y"}'

    with patch("apps.issues.services_ai_wizard.LLMClient.complete", new=fake_complete):
        for i in range(10):
            resp = api_client.post(
                "/api/issues/ai-draft/",
                {"description": "test description", "project": str(project.id)},
                format="json",
            )
            assert resp.status_code == 200, f"req {i+1} unexpectedly failed: {resp.status_code}"
        # 第 11 次请求必须命中限流
        resp = api_client.post(
            "/api/issues/ai-draft/",
            {"description": "test description", "project": str(project.id)},
            format="json",
        )
        assert resp.status_code == 429, f"expected 429 throttled, got {resp.status_code}"

    cache.clear()


@pytest.mark.django_db
def test_issue_create_rejects_unknown_source(api_client):
    """Source not in allow-list is 400."""
    from tests.factories import ProjectFactory, UserFactory
    from django.core.cache import cache
    cache.clear()
    user = UserFactory(is_superuser=True, is_staff=True)
    project = ProjectFactory()
    api_client.force_authenticate(user)

    resp = api_client.post(
        "/api/issues/",
        {
            "project": str(project.id),
            "title": "fake provenance",
            "description": "x",
            "priority": "P2",
            "status": "待分配",
            "labels": [],
            "source": "fake_source",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "source" in resp.data
    cache.clear()


@pytest.mark.django_db
def test_issue_create_rejects_oversized_source_meta(api_client):
    """source_meta over 4KB is 400."""
    from tests.factories import ProjectFactory, UserFactory
    from django.core.cache import cache
    cache.clear()
    user = UserFactory(is_superuser=True, is_staff=True)
    project = ProjectFactory()
    api_client.force_authenticate(user)

    huge = {"data": "x" * 5000}
    resp = api_client.post(
        "/api/issues/",
        {
            "project": str(project.id),
            "title": "x",
            "description": "x",
            "priority": "P2",
            "status": "待分配",
            "labels": [],
            "source": "ai_wizard",
            "source_meta": huge,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "source_meta" in resp.data
    cache.clear()


@pytest.mark.django_db
def test_classify_raises_on_missing_field():
    """LLM response missing required fields raises llm_bad_shape."""
    from apps.issues.services_ai_wizard import AiWizardService, AiWizardError
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

    fake = '{"category": "x"}'  # 缺少 scope
    with patch("apps.issues.services_ai_wizard.LLMClient.complete", return_value=fake):
        svc = AiWizardService()
        with pytest.raises(AiWizardError) as exc:
            svc.classify("test")
        assert exc.value.code == "llm_bad_shape"


@pytest.mark.django_db
def test_extract_bounds_invalid_priority_to_p2():
    """LLM returning 'HIGH' as priority is normalized to P2."""
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

    fake = '{"title": "x", "priority": "HIGH", "module": "x"}'
    with patch("apps.issues.services_ai_wizard.LLMClient.complete", return_value=fake):
        svc = AiWizardService()
        result = svc.extract("d", {"category": "c"}, ["x"])
    assert result["priority"] == "P2"


@pytest.mark.django_db
def test_generate_filters_unknown_labels():
    """LLM returning labels outside the allowed list are filtered out."""
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    Prompt.objects.filter(slug__in=("wizard_classify", "wizard_extract", "wizard_generate")).update(is_active=True)

    fake = '{"repro_steps": "x", "expected_behavior": "y", "labels": ["前端", "bogus", "Bug"], "follow_up_questions": []}'
    with patch("apps.issues.services_ai_wizard.LLMClient.complete", return_value=fake):
        svc = AiWizardService()
        result = svc.generate("d", {}, {}, ["前端", "Bug", "性能"])
    assert result["labels"] == ["前端", "Bug"]


@pytest.mark.django_db
def test_wizard_oneshot_seeded_and_v1_remains_active():
    """After migration 0007 the v2 prompt is seeded; v1 prompts stay ACTIVE so
    AI_WIZARD_LEGACY rollback actually works (the legacy code path queries
    Prompt by slug + is_active=True). The dispatcher in AiWizardService
    chooses v2 by default; activation alone does not switch behavior."""
    oneshot = Prompt.objects.filter(slug="wizard_oneshot").first()
    assert oneshot is not None, "wizard_oneshot not seeded"
    assert oneshot.is_active
    assert oneshot.llm_model == "qwen-vl-max-latest"
    assert "复现步骤" in oneshot.system_prompt
    assert "{description}" in oneshot.user_prompt_template
    assert "{modules_json}" in oneshot.user_prompt_template
    assert "{labels_json}" in oneshot.user_prompt_template

    # v1 prompts must remain active so AI_WIZARD_LEGACY=True works in prod
    for v1_slug in ("wizard_classify", "wizard_extract", "wizard_generate"):
        p = Prompt.objects.filter(slug=v1_slug).first()
        assert p is not None, f"v1 prompt {v1_slug} must be preserved for rollback"
        assert p.is_active, f"v1 prompt {v1_slug} must remain active for rollback to work"


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
        images = svc._load_image_attachments(ids, owner=user)

    # Only ok1/ok2/ok3 — the first 3 image-MIME attachments under 2MB (ordered by created_at)
    assert len(images) == 3
    mimes = [m for m, _ in images]
    assert all(m.startswith("image/") for m in mimes)
    # The first 3 returned should correspond to k1, k3, k4 (skipping k2 PDF, in created_at order)
    # bytes payload encodes the file_key for traceability
    keys_seen = [b for _, b in images]
    assert any(b"k1" in b for b in keys_seen)
    assert any(b"k3" in b for b in keys_seen)
    assert any(b"k4" in b for b in keys_seen)


@pytest.mark.django_db
def test_load_image_attachments_rejects_other_users_attachments():
    """IDOR regression: _load_image_attachments must scope by uploaded_by.

    Without owner scoping a user could pass another user's attachment UUID
    and have its bytes shipped to the vision LLM (OCR exfiltration).
    """
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.tools.models import Attachment
    from tests.factories import UserFactory
    from unittest.mock import patch

    alice = UserFactory()
    bob = UserFactory()
    alice_att = Attachment.objects.create(
        uploaded_by=alice, file_name="alice.png", file_key="kA",
        file_url="/u/A", file_size=500, mime_type="image/png",
    )
    bob_att = Attachment.objects.create(
        uploaded_by=bob, file_name="bob.png", file_key="kB",
        file_url="/u/B", file_size=500, mime_type="image/png",
    )

    def fake_read(file_key):
        return b"bytes-" + file_key.encode()

    with patch("apps.issues.services_ai_wizard._read_attachment_bytes", side_effect=fake_read):
        svc = AiWizardService()
        images = svc._load_image_attachments(
            [str(alice_att.id), str(bob_att.id)], owner=alice,
        )

    assert len(images) == 1, "only Alice's attachment should be loaded for Alice"
    assert images[0][1] == b"bytes-kA"


@pytest.mark.django_db
def test_load_image_metadata_rejects_other_users_attachments():
    """IDOR regression: _load_image_metadata must scope by uploaded_by.

    Without owner scoping the wizard would embed another user's image URL
    into the new Issue.description as ![name](url) markdown.
    """
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.tools.models import Attachment
    from tests.factories import UserFactory

    alice = UserFactory()
    bob = UserFactory()
    alice_att = Attachment.objects.create(
        uploaded_by=alice, file_name="alice.png", file_key="kA",
        file_url="/u/A", file_size=500, mime_type="image/png",
    )
    bob_att = Attachment.objects.create(
        uploaded_by=bob, file_name="bob.png", file_key="kB",
        file_url="/u/B", file_size=500, mime_type="image/png",
    )

    svc = AiWizardService()
    meta = svc._load_image_metadata(
        [str(alice_att.id), str(bob_att.id)], owner=alice,
    )

    assert len(meta) == 1
    assert meta[0]["file_name"] == "alice.png"
    assert meta[0]["file_url"] == "/u/A"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_stream_draft_v2_emits_step_then_draft_then_done(site_settings):
    """The simplified v2 stream emits exactly: step(running), step(done), draft, done.

    No duplicates / no assignee_suggestion events — those side-effects moved off
    the critical path (auto-assign runs in Celery; dup check was removed).
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
    ):
        svc = AiWizardService()
        events = list(svc.stream_draft(
            description="some bug here please help",
            project_id=project.id,
            attachment_ids=[],
        ))

    names = [e[0] for e in events]
    assert names == ["step", "step", "draft", "done"]
    assert events[0][1]["status"] == "running"
    assert events[1][1]["status"] == "done"
    assert events[2][1]["title"] == "T"
    # The wizard no longer emits issue-content-unrelated events
    assert "duplicates" not in names
    assert "assignee_suggestion" not in names


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_stream_draft_v2_emits_error_when_oneshot_fails(site_settings):
    """oneshot_draft raising AiWizardError → SSE error event then done."""
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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
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
    ):
        svc = AiWizardService()
        events = list(svc.stream_draft(
            description="user typed text",
            project_id=project.id,
            attachment_ids=[str(att.id)],
            user=user,
        ))

    draft = next(e for e in events if e[0] == "draft")[1]
    # Order: raw → inferred_env blockquote → image markdown
    assert draft["description"].startswith("user typed text")
    assert "AI 推断环境" in draft["description"]
    assert "![shot.png](/uploads/2026/05/shot.png)" in draft["description"]
    # PDF must NOT appear as markdown image
    assert "notes.pdf" not in draft["description"]


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_stream_draft_routes_to_v1_when_legacy_flag_set(site_settings, settings):
    """AI_WIZARD_LEGACY=True routes to the preserved 3-stage pipeline."""
    settings.AI_WIZARD_LEGACY = True
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory
    from unittest.mock import patch
    LLMConfigFactory(is_default=True, is_active=True)
    # Migration 0007 now leaves v1 prompts active, so no manual re-activation needed.
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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
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

    def fake_stream(self, description, project_id=None, attachment_ids=None, user=None):
        captured["description"] = description
        captured["project_id"] = project_id
        captured["attachment_ids"] = attachment_ids
        captured["user"] = user
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


# ============================================================================
# Multi-turn revise (wizard_revise prompt + /ai-draft/revise/ endpoint)
# ============================================================================

VALID_CURRENT_DRAFT = {
    "title": "通知中心乱码",
    "priority": "P2",
    "module": "通知中心",
    "repro_steps": "1. 进入首页\n2. 查看通知",
    "expected_behavior": "应显示正常内容",
    "labels": ["Bug"],
    "follow_up_questions": [],
    "inferred_env": "环境: prod | 角色: 普通用户 | 页面: 首页",
}


@pytest.mark.django_db
def test_oneshot_revise_returns_updated_draft(site_settings):
    """Happy path: LLM 返回完整更新后的草稿, sanitize 不破坏字段。"""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(
        modules=["通知中心", "其他"],
        labels={
            "Bug": {"foreground": "#fff", "background": "#d00", "description": ""},
            "前端": {"foreground": "#fff", "background": "#000", "description": ""},
        },
    )

    fake = (
        '{"title": "通知中心乱码", "priority": "P1", "module": "通知中心", '
        '"repro_steps": "1. 进入首页\\n2. 查看通知\\n3. 切换深色模式 (新增)", '
        '"expected_behavior": "应显示正常内容", '
        '"labels": ["Bug", "前端"], '
        '"follow_up_questions": [], '
        '"inferred_env": "环境: prod | 角色: 普通用户 | 页面: 首页"}'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=fake,
    ):
        svc = AiWizardService()
        result = svc.oneshot_revise(
            current_draft=VALID_CURRENT_DRAFT,
            instruction="复现步骤增加第三条:切换深色模式后乱码;优先级提到 P1",
            images=[],
        )

    assert result["priority"] == "P1"  # changed
    assert result["title"] == "通知中心乱码"  # unchanged
    assert "切换深色模式" in result["repro_steps"]  # appended
    assert set(result["labels"]) >= {"Bug"}


@pytest.mark.django_db
def test_oneshot_revise_raises_on_missing_prompt(site_settings):
    from apps.issues.services_ai_wizard import AiWizardService, AiWizardError
    Prompt.objects.filter(slug="wizard_revise").update(is_active=False)
    svc = AiWizardService()
    with pytest.raises(AiWizardError) as exc:
        svc.oneshot_revise(current_draft=VALID_CURRENT_DRAFT, instruction="x", images=[])
    assert exc.value.code == "missing_prompt"


@pytest.mark.django_db
def test_oneshot_revise_retries_on_bad_json(site_settings):
    """First JSON is malformed → retried once; second succeeds."""
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    responses = iter([
        "not json at all",
        '{"title":"通知中心乱码","priority":"P2","module":"通知中心","repro_steps":"1. x","expected_behavior":"y","labels":[],"follow_up_questions":[],"inferred_env":""}',
    ])

    def fake(self, **kwargs):
        return next(responses)

    with patch("apps.issues.services_ai_wizard.LLMClient.complete_multimodal", new=fake):
        svc = AiWizardService()
        result = svc.oneshot_revise(VALID_CURRENT_DRAFT, "改", images=[])
    assert result["module"] == "通知中心"


@pytest.mark.django_db
def test_stream_revise_emits_step_running_done_then_draft_and_done(site_settings):
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    fake = (
        '{"title": "通知中心乱码", "priority": "P0", "module": "通知中心", '
        '"repro_steps": "1. x", "expected_behavior": "y", "labels": [], '
        '"follow_up_questions": [], "inferred_env": ""}'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=fake,
    ):
        svc = AiWizardService()
        events = list(svc.stream_revise(
            current_draft=VALID_CURRENT_DRAFT,
            instruction="改 P0",
        ))

    names = [e[0] for e in events]
    assert names == ["step", "step", "draft", "done"]
    assert events[0][1]["status"] == "running"
    assert events[1][1]["status"] == "done"
    assert events[2][1]["priority"] == "P0"


@pytest.mark.django_db
def test_stream_revise_yields_error_event_on_llm_failure(site_settings):
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    def boom(self, **kwargs):
        raise RuntimeError("upstream timeout")

    with patch("apps.issues.services_ai_wizard.LLMClient.complete_multimodal", new=boom):
        svc = AiWizardService()
        events = list(svc.stream_revise(VALID_CURRENT_DRAFT, "改", attachment_ids=[]))

    names = [e[0] for e in events]
    assert "error" in names
    err = [e for e in events if e[0] == "error"][0][1]
    assert err["code"] == "llm_call_failed"


@pytest.mark.django_db
def test_revise_endpoint_requires_authentication(api_client):
    resp = api_client.post(
        "/api/issues/ai-draft/revise/",
        {"current_draft": VALID_CURRENT_DRAFT, "instruction": "改", "project": 1},
        format="json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_revise_endpoint_requires_add_issue_permission(api_client):
    from tests.factories import UserFactory
    user = UserFactory()
    api_client.force_authenticate(user)
    resp = api_client.post(
        "/api/issues/ai-draft/revise/",
        {"current_draft": VALID_CURRENT_DRAFT, "instruction": "改", "project": 1},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_revise_endpoint_validates_instruction(api_client):
    from django.contrib.auth.models import Permission
    from tests.factories import UserFactory
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename="add_issue"))
    api_client.force_authenticate(user)
    resp = api_client.post(
        "/api/issues/ai-draft/revise/",
        {"current_draft": VALID_CURRENT_DRAFT, "instruction": "", "project": 1},
        format="json",
    )
    assert resp.status_code == 400
    assert "instruction" in resp.data


@pytest.mark.django_db
def test_revise_endpoint_streams_sse_events(api_client, site_settings):
    from django.contrib.auth.models import Permission
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    LLMConfigFactory(is_default=True, is_active=True)
    project = ProjectFactory()
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename="add_issue"))
    api_client.force_authenticate(user)

    fake = (
        '{"title": "通知中心乱码", "priority": "P0", "module": "通知中心", '
        '"repro_steps": "1. x", "expected_behavior": "y", "labels": [], '
        '"follow_up_questions": [], "inferred_env": ""}'
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=fake,
    ):
        resp = api_client.post(
            "/api/issues/ai-draft/revise/",
            {
                "current_draft": VALID_CURRENT_DRAFT,
                "instruction": "改 P0",
                "project": str(project.id),
            },
            format="json",
        )
        body = b"".join(resp.streaming_content).decode()

    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/event-stream")
    assert "event: step" in body
    assert "event: draft" in body
    assert "event: done" in body
    assert '"priority": "P0"' in body


# ----- LLM-driven action classifier (submit vs update) -----

@pytest.mark.django_db
def test_oneshot_revise_returns_submit_action_when_llm_classifies_confirm(site_settings):
    """LLM 输出 {action: submit} 时, oneshot_revise 短路返回 — 不走 draft 校验."""
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value='{"action": "submit"}',
    ):
        svc = AiWizardService()
        result = svc.oneshot_revise(VALID_CURRENT_DRAFT, "OK 了", images=[])

    assert result["action"] == "submit"


@pytest.mark.django_db
def test_oneshot_revise_tags_update_action_for_backward_compat(site_settings):
    """LLM 输出标准 draft 字段时, oneshot_revise 也会贴 action=update 标记,
    方便 stream_revise 统一分支."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(
        modules=["通知中心", "其他"],
        labels={"Bug": {"foreground": "#fff", "background": "#d00", "description": ""}},
    )

    fake = (
        '{"action": "update", "title": "通知中心乱码", "priority": "P0", "module": "通知中心", '
        '"repro_steps": "1. x", "expected_behavior": "y", "labels": ["Bug"], '
        '"follow_up_questions": [], "inferred_env": ""}'
    )
    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=fake,
    ):
        svc = AiWizardService()
        result = svc.oneshot_revise(VALID_CURRENT_DRAFT, "改 P0", images=[])

    assert result["action"] == "update"
    assert result["priority"] == "P0"


@pytest.mark.django_db
def test_oneshot_revise_handles_missing_action_field_as_update(site_settings):
    """老 prompt 没要求输出 action 字段时, 缺失应视为 update (backward compat)."""
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(
        modules=["通知中心"],
        labels={"Bug": {"foreground": "#fff", "background": "#d00", "description": ""}},
    )

    fake = (
        '{"title": "通知中心乱码", "priority": "P0", "module": "通知中心", '
        '"repro_steps": "1. x", "expected_behavior": "y", "labels": [], '
        '"follow_up_questions": [], "inferred_env": ""}'
    )
    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value=fake,
    ):
        svc = AiWizardService()
        result = svc.oneshot_revise(VALID_CURRENT_DRAFT, "改 P0", images=[])

    assert result["action"] == "update"
    assert result["priority"] == "P0"


@pytest.mark.django_db
def test_stream_revise_emits_submit_event_when_llm_classifies_confirm(site_settings):
    """submit 路径下 SSE 序列是 step(running) → step(done) → submit → done, 不发 draft."""
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value='{"action": "submit"}',
    ):
        svc = AiWizardService()
        events = list(svc.stream_revise(
            current_draft=VALID_CURRENT_DRAFT,
            instruction="OK 了",
        ))

    names = [e[0] for e in events]
    assert names == ["step", "step", "submit", "done"]
    # 没有 draft 事件
    assert "draft" not in names


@pytest.mark.django_db
def test_revise_endpoint_streams_submit_event_through_sse(api_client, site_settings):
    """端到端: 客户端拿到 SSE 流应包含 event: submit, 不含 event: draft."""
    from django.contrib.auth.models import Permission
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    LLMConfigFactory(is_default=True, is_active=True)
    project = ProjectFactory()
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename="add_issue"))
    api_client.force_authenticate(user)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.complete_multimodal",
        return_value='{"action": "submit"}',
    ):
        resp = api_client.post(
            "/api/issues/ai-draft/revise/",
            {
                "current_draft": VALID_CURRENT_DRAFT,
                "instruction": "OK 了",
                "project": str(project.id),
            },
            format="json",
        )
        body = b"".join(resp.streaming_content).decode()

    assert resp.status_code == 200
    assert "event: submit" in body
    assert "event: draft" not in body
    assert "event: done" in body


# ============================================================================
# wizard_chat: conversational multi-turn issue creation
# ============================================================================

@pytest.mark.django_db
def test_chat_returns_draft_action_on_first_user_message(site_settings):
    from apps.issues.services_ai_wizard import AiChatService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(
        modules=["通知中心", "其他"],
        labels={"Bug": {"foreground": "#fff", "background": "#d00", "description": ""}},
    )

    fake = (
        '{"action":"draft","title":"通知中心乱码","priority":"P2","module":"通知中心",'
        '"repro_steps":"1. 打开首页","expected_behavior":"应显示正常",'
        '"labels":["Bug"],"follow_up_questions":[],"inferred_env":""}'
    )

    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake):
        svc = AiChatService()
        result = svc.chat(
            messages=[{"role": "user", "content": "通知中心乱码"}],
            attachment_ids=[],
            user=None,
        )

    assert result["action"] == "draft"
    assert result["title"] == "通知中心乱码"
    assert result["priority"] == "P2"


@pytest.mark.django_db
def test_chat_returns_ask_action_when_info_incomplete(site_settings):
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.chat",
        return_value='{"action":"ask","question":"你这边是 dev 还是 prod 环境?"}',
    ):
        svc = AiChatService()
        result = svc.chat(
            messages=[{"role": "user", "content": "有 bug"}],
            attachment_ids=[],
            user=None,
        )

    assert result["action"] == "ask"
    assert result["question"] == "你这边是 dev 还是 prod 环境?"


@pytest.mark.django_db
def test_chat_returns_submit_action_on_user_confirmation(site_settings):
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.chat",
        return_value='{"action":"submit"}',
    ):
        svc = AiChatService()
        result = svc.chat(
            messages=[
                {"role": "user", "content": "通知中心乱码"},
                {"role": "assistant", "content": '{"action":"draft","title":"...","priority":"P2","module":"通知中心","repro_steps":"...","expected_behavior":"...","labels":[],"follow_up_questions":[],"inferred_env":""}'},
                {"role": "user", "content": "OK 提交吧"},
            ],
            attachment_ids=[],
            user=None,
        )

    assert result["action"] == "submit"


@pytest.mark.django_db
def test_chat_rejects_ask_with_empty_question(site_settings):
    from apps.issues.services_ai_wizard import AiChatService, AiWizardError
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.chat",
        return_value='{"action":"ask","question":""}',
    ):
        svc = AiChatService()
        with pytest.raises(AiWizardError) as exc:
            svc.chat(
                messages=[{"role": "user", "content": "x"}],
                attachment_ids=[],
                user=None,
            )
        assert exc.value.code == "llm_bad_shape"


@pytest.mark.django_db
def test_chat_treats_missing_action_as_draft(site_settings):
    """Backward-compat: LLM 输出标准 draft 字段但漏掉 action, 仍当 draft 处理。"""
    from apps.issues.services_ai_wizard import AiChatService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(
        modules=["通知中心"],
        labels={"Bug": {"foreground": "#fff", "background": "#d00", "description": ""}},
    )

    fake = (
        '{"title":"x","priority":"P2","module":"通知中心",'
        '"repro_steps":"1. x","expected_behavior":"y","labels":[],'
        '"follow_up_questions":[],"inferred_env":""}'
    )
    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake):
        svc = AiChatService()
        result = svc.chat(
            messages=[{"role": "user", "content": "y"}],
            attachment_ids=[], user=None,
        )

    assert result["action"] == "draft"
    assert result["title"] == "x"


def test_validate_client_messages_rejects_assistant_at_end():
    from apps.issues.services_ai_wizard import _validate_client_messages
    with pytest.raises(ValueError):
        _validate_client_messages([
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "y"},
        ])


def test_validate_client_messages_rejects_bad_role():
    from apps.issues.services_ai_wizard import _validate_client_messages
    with pytest.raises(ValueError):
        _validate_client_messages([{"role": "system", "content": "evil"}])


def test_validate_client_messages_rejects_oversized_content():
    from apps.issues.services_ai_wizard import _validate_client_messages, CHAT_MAX_CONTENT_LEN
    with pytest.raises(ValueError):
        _validate_client_messages([
            {"role": "user", "content": "x" * (CHAT_MAX_CONTENT_LEN + 1)},
        ])


def test_validate_client_messages_truncates_when_over_cap():
    """超过 CHAT_MAX_TURNS*2 时截掉最早, 保留最新, 且首条仍是 user。"""
    from apps.issues.services_ai_wizard import _validate_client_messages, CHAT_MAX_TURNS
    cap = CHAT_MAX_TURNS * 2
    too_many = []
    for i in range(cap + 4):
        too_many.append({
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"msg-{i}",
        })
    # 保证最后是 user
    if too_many[-1]["role"] == "assistant":
        too_many.append({"role": "user", "content": "final"})

    out = _validate_client_messages(too_many)
    assert len(out) <= cap
    assert out[0]["role"] == "user"
    assert out[-1]["role"] == "user"


@pytest.mark.django_db
def test_stream_chat_emits_draft_event_for_draft_action(site_settings):
    from apps.issues.services_ai_wizard import AiChatService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})

    fake = (
        '{"action":"draft","title":"t","priority":"P2","module":"其他",'
        '"repro_steps":"","expected_behavior":"","labels":[],'
        '"follow_up_questions":[],"inferred_env":""}'
    )
    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake):
        svc = AiChatService()
        events = list(svc.stream_chat(
            messages=[{"role": "user", "content": "bug 描述"}],
        ))

    names = [e[0] for e in events]
    assert names == ["step", "step", "draft", "done"]


@pytest.mark.django_db
def test_stream_chat_emits_ask_event_for_ask_action(site_settings):
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.chat",
        return_value='{"action":"ask","question":"哪个环境?"}',
    ):
        svc = AiChatService()
        events = list(svc.stream_chat(messages=[{"role": "user", "content": "bug"}]))

    names = [e[0] for e in events]
    assert names == ["step", "step", "ask", "done"]
    ask_payload = [e[1] for e in events if e[0] == "ask"][0]
    assert ask_payload["question"] == "哪个环境?"


@pytest.mark.django_db
def test_stream_chat_emits_submit_event_for_submit_action(site_settings):
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.chat",
        return_value='{"action":"submit"}',
    ):
        svc = AiChatService()
        events = list(svc.stream_chat(messages=[{"role": "user", "content": "OK"}]))

    names = [e[0] for e in events]
    assert names == ["step", "step", "submit", "done"]


@pytest.mark.django_db
def test_chat_endpoint_requires_authentication(api_client):
    resp = api_client.post(
        "/api/issues/ai-draft/chat/",
        {"messages": [{"role": "user", "content": "x"}], "project": 1},
        format="json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_chat_endpoint_requires_add_issue_permission(api_client):
    from tests.factories import UserFactory
    user = UserFactory()
    api_client.force_authenticate(user)
    resp = api_client.post(
        "/api/issues/ai-draft/chat/",
        {"messages": [{"role": "user", "content": "x"}], "project": 1},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_chat_endpoint_rejects_assistant_last_message(api_client, site_settings):
    from django.contrib.auth.models import Permission
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    LLMConfigFactory(is_default=True, is_active=True)
    project = ProjectFactory()
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename="add_issue"))
    api_client.force_authenticate(user)

    resp = api_client.post(
        "/api/issues/ai-draft/chat/",
        {
            "messages": [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "y"},
            ],
            "project": str(project.id),
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_chat_endpoint_streams_sse_with_multi_turn_history(api_client, site_settings):
    """End-to-end: 多轮 history 送进去, LLM 返回 submit 信号, SSE body 含 event: submit。"""
    from django.contrib.auth.models import Permission
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    LLMConfigFactory(is_default=True, is_active=True)
    project = ProjectFactory()
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename="add_issue"))
    api_client.force_authenticate(user)

    # 捕获实际传给 LLM 的 messages, 验证 history 完整透传
    captured = {}
    def fake_chat(self, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return '{"action":"submit"}'

    with patch("apps.issues.services_ai_wizard.LLMClient.chat", new=fake_chat):
        resp = api_client.post(
            "/api/issues/ai-draft/chat/",
            {
                "messages": [
                    {"role": "user", "content": "通知中心乱码"},
                    {"role": "assistant", "content": '{"action":"draft","title":"x"}'},
                    {"role": "user", "content": "OK 提交"},
                ],
                "project": str(project.id),
            },
            format="json",
        )
        body = b"".join(resp.streaming_content).decode()

    assert resp.status_code == 200
    assert "event: submit" in body
    assert "event: done" in body
    # 校验客户端送的 3 条 history 都到了 LLM 那里 (不计 service 自己注入的 system_prompt)
    assert captured["messages"] is not None
    assert len(captured["messages"]) == 3
    assert captured["messages"][0]["role"] == "user"
    assert captured["messages"][-1]["content"] == "OK 提交"


@pytest.mark.django_db
def test_chat_draft_description_includes_first_user_text_env_and_images(site_settings, monkeypatch):
    """chat 路径的 draft 必须把"原始用户描述 + AI 推断环境 + 本轮上传图片 markdown"塞进 description。
    LLM schema 不输出 description, 服务端负责拼装 (与老 oneshot 一致)。"""
    from apps.issues.services_ai_wizard import AiChatService, AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(
        modules=["通知中心"],
        labels={"Bug": {"foreground": "#fff", "background": "#d00", "description": ""}},
    )

    # Mock attachment metadata so we don't need real DB rows for images
    def fake_load_image_metadata(self, attachment_ids, owner):
        if not attachment_ids:
            return []
        return [
            {"file_name": "screenshot.png", "file_url": "/uploads/2026/05/screenshot.png"},
        ]
    monkeypatch.setattr(AiWizardService, "_load_image_metadata", fake_load_image_metadata)

    fake = (
        '{"action":"draft","title":"通知中心乱码","priority":"P2","module":"通知中心",'
        '"repro_steps":"1. x","expected_behavior":"y","labels":[],'
        '"follow_up_questions":[],"inferred_env":"环境: prod | 角色: 普通用户 | 页面: 首页"}'
    )
    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake):
        svc = AiChatService()
        result = svc.chat(
            messages=[{"role": "user", "content": "通知中心显示乱码"}],
            attachment_ids=["00000000-0000-0000-0000-000000000001"],
            user=None,
        )

    desc = result["description"]
    assert "通知中心显示乱码" in desc                                 # 原始用户文本
    assert "环境: prod | 角色: 普通用户 | 页面: 首页" in desc        # AI 推断环境
    assert "![screenshot.png](/uploads/2026/05/screenshot.png)" in desc  # 图片 markdown


@pytest.mark.django_db
def test_chat_draft_uses_cumulative_attachments_for_description_after_ask_reply(site_settings, monkeypatch):
    """重现用户报告的 bug: turn 1 附图触发 AI ask, turn 2 用户回答(无新图)生成 draft.
    description 必须依然包含 turn 1 的图片 markdown (累计 attachment_ids 的作用)。"""
    from apps.issues.services_ai_wizard import AiChatService, AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})

    def fake_load_image_metadata(self, attachment_ids, owner):
        # 只对那张 turn 1 的图返回元数据; 其它 ID 返回空
        if "11111111-1111-1111-1111-111111111111" in [str(x) for x in attachment_ids]:
            return [{"file_name": "screenshot.png", "file_url": "/uploads/screenshot.png"}]
        return []
    monkeypatch.setattr(AiWizardService, "_load_image_metadata", fake_load_image_metadata)

    fake_draft = (
        '{"action":"draft","title":"刷新页面后 session 未清除","priority":"P2","module":"其他",'
        '"repro_steps":"1. 登录\\n2. 刷新页面","expected_behavior":"应清除当前 session",'
        '"labels":[],"follow_up_questions":[],"inferred_env":"环境: dev | 角色: 未知 | 页面: 未知"}'
    )
    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake_draft):
        svc = AiChatService()
        result = svc.chat(
            messages=[
                {"role": "user", "content": "刷新页面应该 clear session"},
                {"role": "assistant", "content": '{"action":"ask","question":"哪个环境?"}'},
                {"role": "user", "content": "dev"},
            ],
            attachment_ids=[],                                       # 本轮无新图
            conversation_attachment_ids=["11111111-1111-1111-1111-111111111111"],  # 但 turn 1 有
            user=None,
        )

    desc = result["description"]
    assert "刷新页面应该 clear session" in desc
    assert "![screenshot.png](/uploads/screenshot.png)" in desc, (
        "draft.description 应包含 turn 1 上传的截图 markdown, 即便本轮 attachment_ids 是空的"
    )


@pytest.mark.django_db
def test_chat_endpoint_accepts_conversation_attachment_ids(api_client, site_settings, monkeypatch):
    """端到端: 客户端送 conversation_attachment_ids, 服务端透传到 chat() 用于 description 渲染。"""
    from django.contrib.auth.models import Permission
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    LLMConfigFactory(is_default=True, is_active=True)
    project = ProjectFactory()
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename="add_issue"))
    api_client.force_authenticate(user)

    def fake_load_image_metadata(self, attachment_ids, owner):
        if attachment_ids:
            return [{"file_name": "old.png", "file_url": "/uploads/old.png"}]
        return []
    monkeypatch.setattr(AiWizardService, "_load_image_metadata", fake_load_image_metadata)

    fake_draft = (
        '{"action":"draft","title":"t","priority":"P2","module":"其他",'
        '"repro_steps":"","expected_behavior":"","labels":[],'
        '"follow_up_questions":[],"inferred_env":""}'
    )
    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake_draft):
        resp = api_client.post(
            "/api/issues/ai-draft/chat/",
            {
                "messages": [{"role": "user", "content": "dev"}],
                "project": str(project.id),
                "attachment_ids": [],
                "conversation_attachment_ids": ["11111111-1111-1111-1111-111111111111"],
            },
            format="json",
        )
        body = b"".join(resp.streaming_content).decode()

    assert resp.status_code == 200
    assert "event: draft" in body
    assert "/uploads/old.png" in body, "累计附件应出现在 draft.description 渲染里"


# ============================================================================
# Image vision diagnostics — surface size/read warnings instead of silent drop
# ============================================================================

@pytest.mark.django_db
def test_load_image_attachments_returns_warning_for_oversize(site_settings, monkeypatch):
    """超过 10MB 的截图被丢弃, 同时返回用户可见的警告字串。"""
    from apps.issues.services_ai_wizard import AiWizardService, MAX_IMAGE_BYTES
    from apps.tools.models import Attachment
    from tests.factories import UserFactory

    user = UserFactory()
    over = Attachment.objects.create(
        uploaded_by=user,
        file_name="big.png",
        file_key="2026/05/over.png",
        file_url="http://x/over.png",
        file_size=MAX_IMAGE_BYTES + 1024,
        mime_type="image/png",
    )

    helper = AiWizardService()
    images, warnings = helper._load_image_attachments_with_warnings([str(over.id)], user)
    assert images == []
    assert any("big.png" in w and "10MB" in w for w in warnings)


@pytest.mark.django_db
def test_chat_emits_warning_event_when_image_oversize(site_settings, monkeypatch):
    """大图被过滤时, stream_chat 应 emit 'warning' 事件让前端有机会显示给用户。"""
    from apps.issues.services_ai_wizard import AiChatService, MAX_IMAGE_BYTES
    from apps.tools.models import Attachment
    from tests.factories import LLMConfigFactory, UserFactory
    LLMConfigFactory(is_default=True, is_active=True)

    user = UserFactory()
    over = Attachment.objects.create(
        uploaded_by=user,
        file_name="huge.png",
        file_key="2026/05/huge.png",
        file_url="http://x/huge.png",
        file_size=MAX_IMAGE_BYTES + 1,
        mime_type="image/png",
    )

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.chat",
        return_value='{"action":"ask","question":"补充一下"}',
    ):
        svc = AiChatService()
        events = list(svc.stream_chat(
            messages=[{"role": "user", "content": "x"}],
            attachment_ids=[str(over.id)],
            user=user,
        ))

    names = [e[0] for e in events]
    assert "warning" in names, f"应包含 warning 事件, 实际: {names}"
    warning_payload = [e[1] for e in events if e[0] == "warning"][0]
    assert "huge.png" in warning_payload["message"]


@pytest.mark.django_db
def test_chat_no_warning_event_for_under_limit_images(site_settings, monkeypatch):
    """正常大小的图片不应触发警告事件 (smoke test 防回归)。"""
    from apps.issues.services_ai_wizard import AiChatService, AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    monkeypatch.setattr(AiWizardService, "_load_image_attachments_with_warnings",
                        lambda self, ids, owner: ([], []))

    with patch(
        "apps.issues.services_ai_wizard.LLMClient.chat",
        return_value='{"action":"ask","question":"x"}',
    ):
        svc = AiChatService()
        events = list(svc.stream_chat(
            messages=[{"role": "user", "content": "y"}],
            attachment_ids=[],
        ))

    assert "warning" not in [e[0] for e in events]


# ============================================================================
# Duplicate-check hint in chat flow (热插拔, 受 WIZARD_CHAT_DUP_CHECK_ENABLED 控制)
# ============================================================================

@pytest.mark.django_db
def test_stream_chat_emits_dup_event_on_first_draft_when_candidates_exist(site_settings, monkeypatch, settings):
    from apps.issues.services_ai_wizard import AiChatService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["其他"], labels={})
    settings.WIZARD_CHAT_DUP_CHECK_ENABLED = True
    project = ProjectFactory()

    fake_draft = (
        '{"action":"draft","title":"通知中心乱码","priority":"P2","module":"其他",'
        '"repro_steps":"","expected_behavior":"","labels":[],'
        '"follow_up_questions":[],"inferred_env":""}'
    )
    fake_candidates = [
        {"id": 145, "title": "通知中心乱码刷新就好", "status": "进行中", "reason": "几乎一致"},
    ]
    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake_draft), \
         patch("apps.issues.services.check_duplicates", return_value=fake_candidates):
        svc = AiChatService()
        events = list(svc.stream_chat(
            messages=[{"role": "user", "content": "通知中心显示乱码"}],
            project=project,
        ))

    dup_payloads = [e[1] for e in events if e[0] == "dup"]
    assert len(dup_payloads) == 1
    assert dup_payloads[0]["candidates"] == fake_candidates
    # 事件顺序: draft 在 dup 之前 (用户先看到草稿, 再看到查重提示)
    names = [e[0] for e in events]
    assert names.index("draft") < names.index("dup") < names.index("done")


@pytest.mark.django_db
def test_stream_chat_skips_dup_check_when_flag_disabled(site_settings, monkeypatch, settings):
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory, ProjectFactory
    LLMConfigFactory(is_default=True, is_active=True)
    settings.WIZARD_CHAT_DUP_CHECK_ENABLED = False
    project = ProjectFactory()

    fake_draft = (
        '{"action":"draft","title":"t","priority":"P2","module":"其他",'
        '"repro_steps":"","expected_behavior":"","labels":[],'
        '"follow_up_questions":[],"inferred_env":""}'
    )
    called = {"n": 0}
    def fake_check(*args, **kwargs):
        called["n"] += 1
        return [{"id": 1, "title": "x", "status": "进行中", "reason": "x"}]

    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake_draft), \
         patch("apps.issues.services.check_duplicates", side_effect=fake_check):
        svc = AiChatService()
        events = list(svc.stream_chat(
            messages=[{"role": "user", "content": "x"}],
            project=project,
        ))

    assert "dup" not in [e[0] for e in events], "WIZARD_CHAT_DUP_CHECK_ENABLED=False 时不应跑/发送 dup"
    assert called["n"] == 0, "flag 关闭时 check_duplicates 完全不被调用 (省 token)"


@pytest.mark.django_db
def test_stream_chat_skips_dup_check_on_revise(site_settings, monkeypatch, settings):
    """messages 里已经有过 action:draft 的 assistant 消息 = 用户在 revise, 跳过 dup-check"""
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory, ProjectFactory
    LLMConfigFactory(is_default=True, is_active=True)
    settings.WIZARD_CHAT_DUP_CHECK_ENABLED = True
    project = ProjectFactory()

    fake_draft = (
        '{"action":"draft","title":"t","priority":"P0","module":"其他",'
        '"repro_steps":"","expected_behavior":"","labels":[],'
        '"follow_up_questions":[],"inferred_env":""}'
    )
    called = {"n": 0}
    def fake_check(*args, **kwargs):
        called["n"] += 1
        return [{"id": 1, "title": "x", "status": "进行中", "reason": "x"}]

    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake_draft), \
         patch("apps.issues.services.check_duplicates", side_effect=fake_check):
        svc = AiChatService()
        events = list(svc.stream_chat(
            messages=[
                {"role": "user", "content": "通知中心乱码"},
                {"role": "assistant", "content": '{"action":"draft","title":"v1"}'},
                {"role": "user", "content": "改 P0"},
            ],
            project=project,
        ))

    assert "dup" not in [e[0] for e in events]
    assert called["n"] == 0, "revise 路径不该调 check_duplicates"


@pytest.mark.django_db
def test_stream_chat_no_dup_event_when_no_candidates(site_settings, monkeypatch, settings):
    """跑了 check_duplicates 但返回空 → 不 emit dup 事件保持 thread 干净"""
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory, ProjectFactory
    LLMConfigFactory(is_default=True, is_active=True)
    settings.WIZARD_CHAT_DUP_CHECK_ENABLED = True
    project = ProjectFactory()

    fake_draft = (
        '{"action":"draft","title":"t","priority":"P2","module":"其他",'
        '"repro_steps":"","expected_behavior":"","labels":[],'
        '"follow_up_questions":[],"inferred_env":""}'
    )
    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake_draft), \
         patch("apps.issues.services.check_duplicates", return_value=[]):
        svc = AiChatService()
        events = list(svc.stream_chat(
            messages=[{"role": "user", "content": "x"}],
            project=project,
        ))

    assert "dup" not in [e[0] for e in events]


@pytest.mark.django_db
def test_stream_chat_dup_check_failure_swallowed(site_settings, monkeypatch, settings):
    """check_duplicates 抛异常时不影响 draft / done 发送 (degrade gracefully)"""
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory, ProjectFactory
    LLMConfigFactory(is_default=True, is_active=True)
    settings.WIZARD_CHAT_DUP_CHECK_ENABLED = True
    project = ProjectFactory()

    fake_draft = (
        '{"action":"draft","title":"t","priority":"P2","module":"其他",'
        '"repro_steps":"","expected_behavior":"","labels":[],'
        '"follow_up_questions":[],"inferred_env":""}'
    )
    def boom(*args, **kwargs):
        raise RuntimeError("LLM down")

    with patch("apps.issues.services_ai_wizard.LLMClient.chat", return_value=fake_draft), \
         patch("apps.issues.services.check_duplicates", side_effect=boom):
        svc = AiChatService()
        events = list(svc.stream_chat(
            messages=[{"role": "user", "content": "x"}],
            project=project,
        ))

    names = [e[0] for e in events]
    assert "draft" in names and "done" in names
    assert "dup" not in names


@pytest.mark.django_db
def test_chat_injects_project_name_into_system_prompt(site_settings):
    """LLM 即使在 messages 被清空后, 也必须能从 system_prompt 知道当前项目.
    捕获实际送给 LLM 的 system_prompt, 断言包含项目名 + 说明。"""
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory, ProjectFactory
    LLMConfigFactory(is_default=True, is_active=True)
    project = ProjectFactory(name="贷后智能体", description="信贷催收自动化平台")

    captured = {}
    def fake_chat(self, **kwargs):
        captured["system_prompt"] = kwargs.get("system_prompt")
        return '{"action":"ask","question":"x"}'

    with patch("apps.issues.services_ai_wizard.LLMClient.chat", new=fake_chat):
        svc = AiChatService()
        svc.chat(
            messages=[{"role": "user", "content": "y"}],
            attachment_ids=[], user=None,
            project=project,
        )

    sp = captured["system_prompt"]
    assert "当前项目: 贷后智能体" in sp, f"system_prompt 缺项目名: {sp!r}"
    assert "信贷催收自动化平台" in sp, "system_prompt 缺项目说明"


@pytest.mark.django_db
def test_chat_omits_project_block_when_no_project(site_settings):
    """没传 project 时 (理论不应发生, 但容错) system_prompt 不该有空白的'当前项目:' 块"""
    from apps.issues.services_ai_wizard import AiChatService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

    captured = {}
    def fake_chat(self, **kwargs):
        captured["system_prompt"] = kwargs.get("system_prompt")
        return '{"action":"ask","question":"x"}'

    with patch("apps.issues.services_ai_wizard.LLMClient.chat", new=fake_chat):
        svc = AiChatService()
        svc.chat(messages=[{"role": "user", "content": "y"}], attachment_ids=[], user=None)

    assert "当前项目:" not in captured["system_prompt"]


def test_strip_assembled_blocks_removes_env_and_image_lines():
    """Unit: 服务端拼装的 env blockquote + 图片 markdown 行必须被剥掉, 段落文本保留."""
    from apps.issues.services_ai_wizard import _strip_assembled_blocks
    assembled = (
        "用户原话第一段\n\n"
        "用户原话第二段\n\n"
        "> 🤖 *AI 推断环境*: 环境: prod | 角色: 普通用户\n\n"
        "![screenshot.png](/uploads/x.png)\n\n"
        "![another.png](/uploads/y.png)"
    )
    out = _strip_assembled_blocks(assembled)
    assert out == "用户原话第一段\n\n用户原话第二段"


def test_strip_assembled_blocks_keeps_raw_when_no_appendix():
    from apps.issues.services_ai_wizard import _strip_assembled_blocks
    raw = "只有用户文本, 没有任何拼装块"
    assert _strip_assembled_blocks(raw) == raw


@pytest.mark.django_db
def test_chat_strips_assembled_blocks_from_history_before_calling_llm(site_settings, monkeypatch):
    """重现用户报告: 改描述时图片被重复显示 — 因为 history 里 description 含图片 markdown,
    LLM 照搬, 拼装时再追加. sanitize 必须把 history 里的拼装块剥掉, 再发给 LLM."""
    from apps.issues.services_ai_wizard import AiChatService, AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
    SiteSettings.objects.update(modules=["通知中心"], labels={})

    def fake_load_image_metadata(self, attachment_ids, owner):
        if not attachment_ids:
            return []
        return [{"file_name": "x.png", "file_url": "/uploads/x.png"}]
    monkeypatch.setattr(AiWizardService, "_load_image_metadata", fake_load_image_metadata)

    # 模拟 v1 已落地: assistant 历史里的 description 是服务端拼装后的成品
    assembled_v1 = (
        "用户原描述\n\n"
        "> 🤖 *AI 推断环境*: 环境: prod | 角色: 普通用户 | 页面: 看板\n\n"
        "![x.png](/uploads/x.png)"
    )
    history = [
        {"role": "user", "content": "用户原描述"},
        {"role": "assistant", "content": json.dumps({
            "action": "draft", "title": "T", "description": assembled_v1,
            "priority": "P2", "module": "通知中心", "repro_steps": "1. a",
            "expected_behavior": "b", "labels": [], "follow_up_questions": [],
            "inferred_env": "环境: prod | 角色: 普通用户 | 页面: 看板",
        }, ensure_ascii=False)},
        {"role": "user", "content": "改一下描述, 应该是 X"},
    ]

    captured_messages: list = []
    def fake_chat(self, **kwargs):
        captured_messages.extend(kwargs.get("messages") or [])
        # LLM 输出新描述 (按 prompt 规则: 只写纯文本)
        return json.dumps({
            "action": "draft", "title": "T", "description": "用户改写后的描述 X",
            "priority": "P2", "module": "通知中心", "repro_steps": "1. a",
            "expected_behavior": "b", "labels": [], "follow_up_questions": [],
            "inferred_env": "环境: prod | 角色: 普通用户 | 页面: 看板",
        }, ensure_ascii=False)

    with patch("apps.issues.services_ai_wizard.LLMClient.chat", new=fake_chat):
        svc = AiChatService()
        result = svc.chat(
            messages=history, attachment_ids=[], user=None,
            conversation_attachment_ids=["00000000-0000-0000-0000-000000000001"],
        )

    # LLM 应该只看到 raw 描述, 不应看到拼装块
    asst_msg = next(m for m in captured_messages if m.get("role") == "assistant")
    asst_content = json.loads(asst_msg["content"])
    assert asst_content["description"] == "用户原描述"
    assert "> 🤖" not in asst_content["description"]
    assert "![x.png]" not in asst_content["description"]

    # 最终拼装的 description: env + 图片各只出现一次
    final_desc = result["description"]
    assert final_desc.count("> 🤖 *AI 推断环境*") == 1
    assert final_desc.count("![x.png](/uploads/x.png)") == 1
    assert "用户改写后的描述 X" in final_desc
