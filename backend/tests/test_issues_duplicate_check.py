import json
from unittest.mock import patch

import pytest

from apps.ai.models import Prompt
from tests.factories import IssueFactory, ProjectFactory, LLMConfigFactory


@pytest.mark.django_db
def test_duplicate_check_prompt_is_seeded():
    """The data migration must have created the issue_duplicate_check Prompt row."""
    prompt = Prompt.objects.filter(slug="issue_duplicate_check").first()
    assert prompt is not None, "Prompt row was not seeded"
    assert prompt.is_active
    assert "{candidates_json}" in prompt.user_prompt_template
    assert "{new_title}" in prompt.user_prompt_template
    assert "{new_description}" in prompt.user_prompt_template
    assert prompt.llm_model == "deepseek-v4-flash"
    assert prompt.temperature == 0.2


def test_input_serializer_requires_project_and_title():
    from apps.issues.serializers import DuplicateCheckInputSerializer

    s = DuplicateCheckInputSerializer(data={"title": "abc"})
    assert not s.is_valid()
    assert "project" in s.errors

    s = DuplicateCheckInputSerializer(data={"project": 1})
    assert not s.is_valid()
    assert "title" in s.errors


def test_input_serializer_defaults_description_to_empty():
    from apps.issues.serializers import DuplicateCheckInputSerializer

    s = DuplicateCheckInputSerializer(data={"project": 1, "title": "abc"})
    assert s.is_valid(), s.errors
    assert s.validated_data["description"] == ""


@pytest.mark.django_db
def test_check_duplicates_returns_empty_when_title_too_short():
    from apps.issues.services import check_duplicates

    project = ProjectFactory()
    assert check_duplicates(project_id=project.id, title="ab", description="") == []


@pytest.mark.django_db
def test_check_duplicates_returns_empty_when_project_missing():
    from apps.issues.services import check_duplicates

    assert check_duplicates(project_id=None, title="登录页报错", description="") == []


@pytest.mark.django_db
def test_check_duplicates_returns_empty_when_no_open_candidates():
    from apps.issues.services import check_duplicates

    project = ProjectFactory()
    IssueFactory(project=project, status="已关闭", title="登录失败")
    IssueFactory(project=project, status="已发布", title="登录失败")
    assert check_duplicates(project_id=project.id, title="登录失败", description="") == []


@pytest.fixture
def duplicate_prompt():
    # Already seeded by migration 0003, but tests may have wiped it via
    # transactions on some setups — ensure it exists for these tests.
    return Prompt.objects.get(slug="issue_duplicate_check")


@pytest.fixture
def default_llm():
    return LLMConfigFactory(is_default=True, is_active=True)


@pytest.mark.django_db
def test_check_duplicates_returns_matches_from_llm(duplicate_prompt, default_llm):
    from apps.issues.services import check_duplicates

    project = ProjectFactory()
    a = IssueFactory(project=project, status="待分配", title="登录页 500", description="点登录后报错")
    IssueFactory(project=project, status="进行中", title="完全无关的问题")

    payload = json.dumps({"duplicates": [{"id": a.id, "reason": "同样描述登录页 500"}]})
    with patch("apps.issues.services.LLMClient") as MockClient:
        MockClient.return_value.complete.return_value = payload
        out = check_duplicates(project_id=project.id, title="登录页 500", description="登录按钮 500")

    assert out == [{"id": a.id, "title": "登录页 500", "status": "待分配", "reason": "同样描述登录页 500"}]


@pytest.mark.django_db
def test_check_duplicates_filters_hallucinated_ids(duplicate_prompt, default_llm):
    from apps.issues.services import check_duplicates

    project = ProjectFactory()
    real = IssueFactory(project=project, status="待分配", title="A")
    payload = json.dumps({"duplicates": [
        {"id": real.id, "reason": "真的"},
        {"id": 999999, "reason": "幻觉"},
    ]})
    with patch("apps.issues.services.LLMClient") as MockClient:
        MockClient.return_value.complete.return_value = payload
        out = check_duplicates(project_id=project.id, title="abc", description="")

    assert [c["id"] for c in out] == [real.id]


@pytest.mark.django_db
def test_check_duplicates_caps_at_five(duplicate_prompt, default_llm):
    from apps.issues.services import check_duplicates

    project = ProjectFactory()
    issues = [IssueFactory(project=project, status="待分配", title=f"T{i}") for i in range(7)]
    payload = json.dumps({"duplicates": [{"id": i.id, "reason": "x"} for i in issues]})
    with patch("apps.issues.services.LLMClient") as MockClient:
        MockClient.return_value.complete.return_value = payload
        out = check_duplicates(project_id=project.id, title="abc", description="")

    assert len(out) == 5


@pytest.mark.django_db
def test_check_duplicates_returns_empty_on_invalid_json(duplicate_prompt, default_llm):
    from apps.issues.services import check_duplicates

    project = ProjectFactory()
    IssueFactory(project=project, status="待分配", title="A")
    with patch("apps.issues.services.LLMClient") as MockClient:
        MockClient.return_value.complete.return_value = "not json at all"
        out = check_duplicates(project_id=project.id, title="abc", description="")

    assert out == []


@pytest.mark.django_db
def test_check_duplicates_returns_empty_on_llm_exception(duplicate_prompt, default_llm):
    from apps.issues.services import check_duplicates

    project = ProjectFactory()
    IssueFactory(project=project, status="待分配", title="A")
    with patch("apps.issues.services.LLMClient") as MockClient:
        MockClient.return_value.complete.side_effect = RuntimeError("boom")
        out = check_duplicates(project_id=project.id, title="abc", description="")

    assert out == []


@pytest.mark.django_db
def test_check_duplicates_returns_empty_when_no_llm_config(duplicate_prompt):
    from apps.issues.services import check_duplicates

    project = ProjectFactory()
    IssueFactory(project=project, status="待分配", title="A")
    # No LLMConfig with is_default=True exists.
    assert check_duplicates(project_id=project.id, title="abc", description="") == []


@pytest.mark.django_db
def test_check_duplicates_returns_empty_when_no_prompt(default_llm):
    from apps.issues.services import check_duplicates

    Prompt.objects.filter(slug="issue_duplicate_check").update(is_active=False)
    project = ProjectFactory()
    IssueFactory(project=project, status="待分配", title="A")
    assert check_duplicates(project_id=project.id, title="abc", description="") == []


@pytest.mark.django_db
def test_endpoint_returns_candidates(auth_client, site_settings, duplicate_prompt, default_llm):
    project = ProjectFactory()
    open_issue = IssueFactory(project=project, status="待分配", title="登录页 500", description="点登录后报错")

    payload = json.dumps({"duplicates": [{"id": open_issue.id, "reason": "同样描述登录页 500"}]})
    with patch("apps.issues.services.LLMClient") as MockClient:
        MockClient.return_value.complete.return_value = payload
        res = auth_client.post(
            "/api/issues/check-duplicate/",
            data={"project": project.id, "title": "登录页 500", "description": ""},
            format="json",
        )

    assert res.status_code == 200
    body = res.json()
    assert body["candidates"][0]["id"] == open_issue.id
    assert body["candidates"][0]["status"] == "待分配"
    assert body["candidates"][0]["reason"] == "同样描述登录页 500"


@pytest.mark.django_db
def test_endpoint_validates_input(auth_client, site_settings):
    res = auth_client.post("/api/issues/check-duplicate/", data={}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_endpoint_returns_empty_when_no_open_issues(auth_client, site_settings, duplicate_prompt, default_llm):
    project = ProjectFactory()
    IssueFactory(project=project, status="已关闭", title="A")
    res = auth_client.post(
        "/api/issues/check-duplicate/",
        data={"project": project.id, "title": "abc", "description": ""},
        format="json",
    )
    assert res.status_code == 200
    assert res.json() == {"candidates": []}


@pytest.mark.django_db
def test_endpoint_requires_auth(api_client):
    res = api_client.post(
        "/api/issues/check-duplicate/",
        data={"project": 1, "title": "abc"},
        format="json",
    )
    assert res.status_code in (401, 403)


@pytest.mark.django_db
def test_check_duplicates_passes_timeout_to_llm(duplicate_prompt, default_llm):
    from apps.issues.services import check_duplicates, LLM_TIMEOUT_SECONDS

    project = ProjectFactory()
    IssueFactory(project=project, status="待分配", title="A")
    payload = json.dumps({"duplicates": []})
    with patch("apps.issues.services.LLMClient") as MockClient:
        MockClient.return_value.complete.return_value = payload
        check_duplicates(project_id=project.id, title="abc", description="")

    # LLMClient.complete was called with timeout=LLM_TIMEOUT_SECONDS.
    call_kwargs = MockClient.return_value.complete.call_args.kwargs
    assert call_kwargs.get("timeout") == LLM_TIMEOUT_SECONDS


@pytest.mark.django_db
def test_endpoint_requires_view_issue_permission(api_client, site_settings):
    """A logged-in user without issues.view_issue must get 403, not data."""
    from tests.factories import UserFactory

    user = UserFactory()  # no groups, no perms
    api_client.force_authenticate(user=user)
    res = api_client.post(
        "/api/issues/check-duplicate/",
        data={"project": 1, "title": "abc"},
        format="json",
    )
    assert res.status_code == 403
