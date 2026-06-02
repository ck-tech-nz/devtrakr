import pytest

from apps.projects.models import ProjectMember
from tests.factories import (
    AITestFlowFactory,
    AITestRunFactory,
    BrowserArtifactFactory,
    ProjectEnvironmentFactory,
    ProjectFactory,
    SiteSettingsFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def test_ai_testing_runs_requires_auth(api_client):
    response = api_client.get("/api/ai-testing/runs/")
    assert response.status_code == 401


def test_superuser_can_create_environment_and_password_not_returned(superuser_client):
    project = ProjectFactory()
    payload = {
        "project": project.id,
        "name": "staging",
        "base_url": "https://example.com",
        "login_type": "username_password",
        "login_username": "tester",
        "login_password": "secret-xyz",
        "allowed_url_patterns": ["https://example.com/*"],
    }
    response = superuser_client.post("/api/ai-testing/environments/", payload, format="json")
    assert response.status_code == 201
    assert "login_password" not in response.data
    assert response.data["has_login_password"] is True


def test_non_manager_cannot_create_environment(api_client):
    user = UserFactory()
    project = ProjectFactory()
    ProjectMember.objects.create(project=project, user=user, is_manager=False)
    api_client.force_authenticate(user=user)
    payload = {
        "project": project.id,
        "name": "staging",
        "base_url": "https://example.com",
        "login_type": "username_password",
        "login_username": "tester",
        "login_password": "secret-xyz",
    }
    response = api_client.post("/api/ai-testing/environments/", payload, format="json")
    assert response.status_code == 403


def test_project_member_can_create_run(api_client):
    user = UserFactory()
    project = ProjectFactory()
    ProjectMember.objects.create(project=project, user=user, is_manager=False)
    env = ProjectEnvironmentFactory(project=project)
    api_client.force_authenticate(user=user)
    payload = {
        "project": project.id,
        "environment": env.id,
        "name": "smoke run",
        "target_url": "https://example.com",
    }
    response = api_client.post("/api/ai-testing/runs/", payload, format="json")
    assert response.status_code == 201
    assert response.data["name"] == "smoke run"


def test_create_run_uses_threaded_fallback_when_enqueue_fails(api_client, monkeypatch):
    user = UserFactory()
    project = ProjectFactory()
    ProjectMember.objects.create(project=project, user=user, is_manager=False)
    env = ProjectEnvironmentFactory(project=project)
    api_client.force_authenticate(user=user)

    class _DummyThread:
        started = False
        last_target = None
        last_args = None

        def __init__(self, *, target, args, daemon, name):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name

        def start(self):
            _DummyThread.started = True
            _DummyThread.last_target = self.target
            _DummyThread.last_args = self.args

    def _boom(*args, **kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr("apps.ai_testing.views.run_ai_test.delay", _boom)
    monkeypatch.setattr("apps.ai_testing.views.threading.Thread", _DummyThread)

    payload = {
        "project": project.id,
        "environment": env.id,
        "name": "enqueue fallback run",
        "target_url": "https://example.com",
    }
    response = api_client.post("/api/ai-testing/runs/", payload, format="json")

    assert response.status_code == 201
    assert _DummyThread.started is True
    assert _DummyThread.last_target.__name__ == "_run_ai_test_inline_fallback"
    assert _DummyThread.last_args == (response.data["id"],)


def test_member_cannot_create_run_for_non_active_flow(api_client):
    user = UserFactory()
    project = ProjectFactory()
    ProjectMember.objects.create(project=project, user=user, is_manager=False)
    flow = AITestFlowFactory(project=project, status="draft")
    api_client.force_authenticate(user=user)
    payload = {
        "project": project.id,
        "flow": flow.id,
        "environment": flow.environment_id,
        "name": "draft flow run",
        "target_url": flow.target_url,
    }
    response = api_client.post("/api/ai-testing/runs/", payload, format="json")
    assert response.status_code == 400
    assert "flow" in response.data


def test_member_can_only_see_own_projects_runs(api_client):
    user = UserFactory()
    project = ProjectFactory()
    ProjectMember.objects.create(project=project, user=user, is_manager=False)
    visible_run = AITestRunFactory(project=project)
    hidden_run = AITestRunFactory()
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/ai-testing/runs/")
    assert response.status_code == 200
    ids = [item["id"] for item in response.data["results"]]
    assert visible_run.id in ids
    assert hidden_run.id not in ids


def test_create_issue_from_failed_run(superuser_client):
    SiteSettingsFactory()
    run = AITestRunFactory(status="failed")
    response = superuser_client.post(f"/api/ai-testing/runs/{run.id}/create-issue/", {}, format="json")
    assert response.status_code == 201
    assert response.data["source"] == "ai_testing"
    assert response.data["project"] == run.project_id


def test_create_issue_rejects_non_failed_run(superuser_client):
    run = AITestRunFactory(status="success")
    response = superuser_client.post(f"/api/ai-testing/runs/{run.id}/create-issue/", {}, format="json")
    assert response.status_code == 400


def test_member_can_list_own_run_artifacts(api_client):
    user = UserFactory()
    run = AITestRunFactory()
    ProjectMember.objects.create(project=run.project, user=user, is_manager=False)
    BrowserArtifactFactory(run=run, content="console line", attachment=None)
    api_client.force_authenticate(user=user)
    response = api_client.get(f"/api/ai-testing/runs/{run.id}/artifacts/")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["run"] == run.id


def test_member_cannot_list_other_project_run_artifacts(api_client):
    user = UserFactory()
    run = AITestRunFactory()
    BrowserArtifactFactory(run=run, content="console line", attachment=None)
    api_client.force_authenticate(user=user)
    response = api_client.get(f"/api/ai-testing/runs/{run.id}/artifacts/")
    assert response.status_code == 404


def test_failed_run_steps_fallback_when_no_step_records(api_client):
    user = UserFactory()
    run = AITestRunFactory(status="failed")
    run.failure_reason = "runtime crashed before step persistence"
    run.final_summary = "执行异常终止"
    run.save(update_fields=["failure_reason", "final_summary", "updated_at"])
    ProjectMember.objects.create(project=run.project, user=user, is_manager=False)
    api_client.force_authenticate(user=user)
    response = api_client.get(f"/api/ai-testing/runs/{run.id}/steps/")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["tool_name"] == "runtime_error"
    assert "runtime crashed" in response.data[0]["error_message"]


def test_failed_run_artifacts_fallback_when_no_artifact_records(api_client):
    user = UserFactory()
    run = AITestRunFactory(status="failed")
    run.failure_reason = "runtime crashed before artifacts"
    run.final_summary = "执行异常终止"
    run.save(update_fields=["failure_reason", "final_summary", "updated_at"])
    ProjectMember.objects.create(project=run.project, user=user, is_manager=False)
    api_client.force_authenticate(user=user)
    response = api_client.get(f"/api/ai-testing/runs/{run.id}/artifacts/")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["artifact_type"] == "console_log"
    assert "runtime crashed" in response.data[0]["content"]
