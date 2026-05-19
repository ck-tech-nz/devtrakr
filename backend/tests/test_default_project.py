import pytest

from apps.projects.utils import get_effective_default_project
from tests.factories import ProjectFactory, UserFactory


@pytest.mark.django_db
def test_returns_user_default_when_set():
    project = ProjectFactory()
    user = UserFactory(default_project=project)

    assert get_effective_default_project(user) == project


@pytest.mark.django_db
def test_falls_back_to_site_default(site_settings):
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


@pytest.mark.django_db
def test_me_endpoint_returns_effective_default_project(api_client, site_settings):
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
def test_me_endpoint_user_default_overrides_site(api_client, site_settings):
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
    # Response also reflects the new effective default
    assert resp.data["default_project"]["id"] == str(p.id)


@pytest.mark.django_db
def test_me_patch_with_invalid_project_id_returns_400(api_client):
    """Non-numeric / nonexistent project IDs return 400, not 500 or silent success."""
    user = UserFactory()
    api_client.force_authenticate(user)

    # Non-numeric string
    resp = api_client.patch("/api/auth/me/", {"default_project": "abc"}, format="json")
    assert resp.status_code == 400
    assert "default_project" in resp.data

    # Nonexistent numeric id
    resp = api_client.patch("/api/auth/me/", {"default_project": "999999"}, format="json")
    assert resp.status_code == 400
    assert "default_project" in resp.data


@pytest.mark.django_db
def test_me_patch_with_null_clears_user_default(api_client):
    """PATCH with default_project: null clears the user-level pref (falls back to site default)."""
    p = ProjectFactory()
    user = UserFactory(default_project=p)
    api_client.force_authenticate(user)

    resp = api_client.patch("/api/auth/me/", {"default_project": None}, format="json")
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.default_project_id is None


@pytest.mark.django_db
def test_settings_endpoint_returns_modules_and_default_project(api_client, site_settings):
    from apps.settings.models import SiteSettings
    SiteSettings.objects.update(default_project=None)
    user = UserFactory()
    api_client.force_authenticate(user)

    resp = api_client.get("/api/settings/")

    assert resp.status_code == 200
    assert isinstance(resp.data["modules"], list)
    assert "通知中心" in resp.data["modules"]
    assert "default_project" in resp.data
