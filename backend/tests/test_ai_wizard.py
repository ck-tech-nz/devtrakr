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
