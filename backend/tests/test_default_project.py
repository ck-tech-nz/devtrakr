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
