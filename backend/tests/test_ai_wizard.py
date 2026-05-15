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


@pytest.mark.django_db
def test_generate_returns_parsed_json():
    from apps.issues.services_ai_wizard import AiWizardService
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)

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
def test_stream_draft_emits_three_steps_then_draft_and_done(site_settings):
    from apps.issues.services_ai_wizard import AiWizardService
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory
    LLMConfigFactory(is_default=True, is_active=True)
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
def test_stream_draft_yields_error_when_step_fails(site_settings):
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
def test_ai_draft_endpoint_streams_sse_events(api_client, site_settings):
    """Smoke test: SSE response with correct content type and 3 step events + draft + done."""
    from django.contrib.auth.models import Permission
    from apps.settings.models import SiteSettings
    from tests.factories import LLMConfigFactory, ProjectFactory, UserFactory
    LLMConfigFactory(is_default=True, is_active=True)
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
            "status": "待处理",
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
            "status": "待处理",
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
            "status": "待处理",
            "labels": [],
            "source": "ai_wizard",
            "source_meta": huge,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "source_meta" in resp.data
    cache.clear()
