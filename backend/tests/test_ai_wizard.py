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
def test_stream_draft_v2_emits_step_duplicates_draft_done(site_settings):
    """The v2 stream emits exactly: step(running), duplicates, step(done), draft, done.

    Order of the duplicates event vs the step(done)/draft pair is not
    asserted — they are emitted as each thread finishes.
    transaction=True so the worker threads can see the LLMConfig/Prompt
    rows created in the test setup (default django_db transactional rollback
    isolates per-connection).
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
        return_value=[{"id": 7, "title": "old", "status": "待分配", "reason": "same"}],
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
    assert dup_event[1]["items"] == [{"id": 7, "title": "old", "status": "待分配", "reason": "same"}]


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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
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
    ), patch(
        "apps.issues.services_ai_wizard.check_duplicates",
        return_value=[],
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
