import pytest
from django.contrib.auth.models import Group, Permission

pytestmark = pytest.mark.django_db


class TestGroupList:
    def test_superuser_can_list(self, superuser_client):
        Group.objects.create(name="TestGroup")
        response = superuser_client.get("/api/page-perms/groups/")
        assert response.status_code == 200
        assert any(g["name"] == "TestGroup" for g in response.data)

    def test_regular_user_cannot_list(self, regular_client):
        response = regular_client.get("/api/page-perms/groups/")
        assert response.status_code == 403

    def test_user_with_auth_view_group_can_list(self, api_client):
        from tests.factories import UserFactory
        user = UserFactory()
        user.user_permissions.add(Permission.objects.get(codename="view_group"))
        api_client.force_authenticate(user=user)
        Group.objects.create(name="TestGroup")
        response = api_client.get("/api/page-perms/groups/")
        assert response.status_code == 200
        assert any(g["name"] == "TestGroup" for g in response.data)


class TestGroupUpdate:
    def test_update_group_permissions(self, superuser_client):
        group = Group.objects.create(name="TestGroup")
        response = superuser_client.patch(
            f"/api/page-perms/groups/{group.pk}/",
            {"permissions": ["issues.view_issue", "projects.view_project"]},
            format="json",
        )
        assert response.status_code == 200
        assert len(response.data["permissions"]) == 2

    def test_invalid_permission_returns_400(self, superuser_client):
        group = Group.objects.create(name="TestGroup")
        response = superuser_client.patch(
            f"/api/page-perms/groups/{group.pk}/",
            {"permissions": ["nonexistent.perm"]},
            format="json",
        )
        assert response.status_code == 400

    def test_audit_log_created(self, superuser_client):
        from django.contrib.admin.models import LogEntry
        group = Group.objects.create(name="TestGroup")
        superuser_client.patch(
            f"/api/page-perms/groups/{group.pk}/",
            {"permissions": ["issues.view_issue"]},
            format="json",
        )
        assert LogEntry.objects.filter(object_repr="TestGroup").exists()
