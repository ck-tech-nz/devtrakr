import pytest
from unittest.mock import patch, MagicMock
from tests.factories import LLMConfigFactory, PromptFactory, AnalysisFactory


@pytest.mark.django_db
def test_llmconfig_creation():
    config = LLMConfigFactory(is_default=True)
    assert config.name
    assert config.is_default is True


@pytest.mark.django_db
def test_llmconfig_save_clears_other_defaults():
    from apps.ai.models import LLMConfig

    config1 = LLMConfigFactory(is_default=True)
    config2 = LLMConfigFactory(is_default=True)
    config1.refresh_from_db()
    assert config1.is_default is False
    assert config2.is_default is True


@pytest.mark.django_db
def test_prompt_creation():
    prompt = PromptFactory(slug="team_insights")
    assert prompt.slug == "team_insights"
    assert prompt.is_active is True


@pytest.mark.django_db
def test_analysis_defaults():
    analysis = AnalysisFactory()
    assert analysis.status == "pending"


@pytest.mark.django_db
def test_analysis_str():
    analysis = AnalysisFactory(analysis_type="team_insights", status="done")
    assert "team_insights" in str(analysis)


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

    assert captured["messages"][1] == {"role": "user", "content": "u"}
