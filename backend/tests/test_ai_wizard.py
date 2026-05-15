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
