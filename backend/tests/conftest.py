import pytest
from rest_framework.test import APIClient
from tests.factories import UserFactory, SiteSettingsFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user():
    from django.contrib.auth.models import Group, Permission
    user = UserFactory()
    group, _ = Group.objects.get_or_create(name="管理员")
    group.permissions.set(
        Permission.objects.filter(content_type__app_label__in=["projects", "issues", "settings", "repos", "ai", "users", "notifications"])
    )
    user.groups.add(group)
    return user


@pytest.fixture
def auth_client(api_client, auth_user):
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.fixture
def ai_client(api_client):
    from django.contrib.auth.models import Group, Permission
    from tests.factories import UserFactory

    user = UserFactory()
    group, _ = Group.objects.get_or_create(name="AI用户")
    group.permissions.set(
        Permission.objects.filter(
            content_type__app_label="ai",
            codename__in=["view_analysis", "add_analysis"],
        )
    )
    user.groups.add(group)
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def site_settings():
    return SiteSettingsFactory()


@pytest.fixture
def superuser_client(api_client):
    user = UserFactory(is_superuser=True, is_staff=True)
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def regular_client(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def repo_with_token():
    from tests.factories import RepoFactory
    return RepoFactory(github_token="ghp_testtoken123", last_synced_at=None)


@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings):
    """所有测试用进程内通道层,避免依赖 Redis。"""
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
