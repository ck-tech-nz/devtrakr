import pytest
from django.contrib.auth.models import Permission

from page_perms.models import PageRoute

pytestmark = pytest.mark.django_db


class TestPageRouteList:
    def test_authenticated_user_can_list_routes(self, regular_client):
        PageRoute.objects.create(path="/app/test", label="Test", is_active=True)
        response = regular_client.get("/api/page-perms/routes/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_unauthenticated_cannot_list(self, api_client):
        response = api_client.get("/api/page-perms/routes/")
        assert response.status_code == 401

    def test_inactive_routes_hidden_from_regular_user(self, regular_client):
        PageRoute.objects.create(path="/app/a", label="A", is_active=True)
        PageRoute.objects.create(path="/app/b", label="B", is_active=False)
        response = regular_client.get("/api/page-perms/routes/")
        assert len(response.data["results"]) == 1

    def test_superuser_sees_inactive_with_all_param(self, superuser_client):
        PageRoute.objects.create(path="/app/a", label="A", is_active=True)
        PageRoute.objects.create(path="/app/b", label="B", is_active=False)
        response = superuser_client.get("/api/page-perms/routes/?all=true")
        assert len(response.data["results"]) == 2

    def test_regular_user_all_param_ignored(self, regular_client):
        PageRoute.objects.create(path="/app/a", label="A", is_active=True)
        PageRoute.objects.create(path="/app/b", label="B", is_active=False)
        response = regular_client.get("/api/page-perms/routes/?all=true")
        assert len(response.data["results"]) == 1

    def test_permission_serialized_as_string(self, regular_client):
        perm = Permission.objects.get(codename="view_issue")
        PageRoute.objects.create(path="/app/test", label="Test", permission=perm)
        response = regular_client.get("/api/page-perms/routes/")
        assert response.data["results"][0]["permission"] == "issues.view_issue"

    def test_null_permission_serialized(self, regular_client):
        PageRoute.objects.create(path="/app/test", label="Test", permission=None)
        response = regular_client.get("/api/page-perms/routes/")
        assert response.data["results"][0]["permission"] is None


class TestPageRouteCRUD:
    def test_superuser_can_create(self, superuser_client):
        response = superuser_client.post("/api/page-perms/routes/", {
            "path": "/app/new",
            "label": "New Page",
            "permission": "issues.view_issue",
        }, format="json")
        assert response.status_code == 201
        assert PageRoute.objects.filter(path="/app/new").exists()

    def test_regular_user_cannot_create(self, regular_client):
        response = regular_client.post("/api/page-perms/routes/", {
            "path": "/app/new", "label": "New",
        }, format="json")
        assert response.status_code == 403

    def test_invalid_permission_returns_400(self, superuser_client):
        response = superuser_client.post("/api/page-perms/routes/", {
            "path": "/app/new",
            "label": "New",
            "permission": "nonexistent.perm",
        }, format="json")
        assert response.status_code == 400

    def test_partial_update(self, superuser_client):
        route = PageRoute.objects.create(path="/app/test", label="Old", is_active=True)
        response = superuser_client.patch(
            f"/api/page-perms/routes/{route.pk}/",
            {"label": "New"},
            format="json",
        )
        assert response.status_code == 200
        route.refresh_from_db()
        assert route.label == "New"

    def test_delete(self, superuser_client):
        route = PageRoute.objects.create(path="/app/test", label="Test")
        response = superuser_client.delete(f"/api/page-perms/routes/{route.pk}/")
        assert response.status_code == 204
        assert not PageRoute.objects.filter(pk=route.pk).exists()


class TestRoutesAPIHierarchy:
    def test_list_returns_parent_path_and_is_group(self, regular_client):
        group = PageRoute.objects.create(
            path="#group:proj", label="项目管理", is_group=True, source="manual",
        )
        PageRoute.objects.create(
            path="/app/projects", label="项目", parent=group, source="manual",
        )
        resp = regular_client.get("/api/page-perms/routes/")
        assert resp.status_code == 200
        data = resp.json()
        rows = data if isinstance(data, list) else data["results"]
        by_path = {r["path"]: r for r in rows}
        assert by_path["#group:proj"]["is_group"] is True
        assert by_path["#group:proj"]["parent"] is None
        assert by_path["/app/projects"]["is_group"] is False
        assert by_path["/app/projects"]["parent"] == "#group:proj"

    def test_create_leaf_with_parent_path(self, superuser_client):
        PageRoute.objects.create(
            path="#group:proj", label="项目管理", is_group=True, source="manual",
        )
        resp = superuser_client.post(
            "/api/page-perms/routes/",
            {
                "path": "/app/repos",
                "label": "仓库",
                "parent": "#group:proj",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        leaf = PageRoute.objects.get(path="/app/repos")
        assert leaf.parent and leaf.parent.path == "#group:proj"

    def test_create_with_missing_parent_returns_400(self, superuser_client):
        resp = superuser_client.post(
            "/api/page-perms/routes/",
            {"path": "/app/x", "label": "X", "parent": "#group:nope"},
            format="json",
        )
        assert resp.status_code == 400
        assert "parent" in resp.json()

    def test_create_with_leaf_as_parent_returns_400(self, superuser_client):
        PageRoute.objects.create(
            path="/app/leaf", label="Leaf", source="manual",
        )
        resp = superuser_client.post(
            "/api/page-perms/routes/",
            {"path": "/app/x", "label": "X", "parent": "/app/leaf"},
            format="json",
        )
        assert resp.status_code == 400
        assert "parent" in resp.json()

    def test_create_with_three_level_nesting_returns_400(self, superuser_client):
        a = PageRoute.objects.create(
            path="#group:a", label="A", is_group=True, source="manual",
        )
        PageRoute.objects.create(
            path="#group:b", label="B", is_group=True, parent=a, source="manual",
        )
        resp = superuser_client.post(
            "/api/page-perms/routes/",
            {"path": "/app/x", "label": "X", "parent": "#group:b"},
            format="json",
        )
        assert resp.status_code == 400
        assert "parent" in resp.json()
