import pytest
from django.contrib.auth.models import Permission
from django.db import IntegrityError

from page_perms.models import PageRoute

pytestmark = pytest.mark.django_db


class TestPageRouteModel:
    def test_create_route_without_permission(self):
        route = PageRoute.objects.create(
            path="/app/test", label="Test", sort_order=0
        )
        assert route.permission is None
        assert route.is_active is True
        assert route.source == "manual"

    def test_create_route_with_permission(self):
        perm = Permission.objects.filter(codename="view_issue").first()
        route = PageRoute.objects.create(
            path="/app/test", label="Test", permission=perm
        )
        assert route.permission == perm

    def test_unique_path_constraint(self):
        PageRoute.objects.create(path="/app/test", label="Test")
        with pytest.raises(IntegrityError):
            PageRoute.objects.create(path="/app/test", label="Duplicate")

    def test_ordering_by_sort_order(self):
        PageRoute.objects.create(path="/app/b", label="B", sort_order=2)
        PageRoute.objects.create(path="/app/a", label="A", sort_order=1)
        routes = list(PageRoute.objects.values_list("path", flat=True))
        assert routes == ["/app/a", "/app/b"]

    def test_permission_set_null_on_delete(self):
        perm = Permission.objects.filter(codename="view_issue").first()
        route = PageRoute.objects.create(
            path="/app/test", label="Test", permission=perm
        )
        perm.delete()
        route.refresh_from_db()
        assert route.permission is None


class TestPageRouteHierarchy:
    def test_group_row_can_be_created(self):
        group = PageRoute.objects.create(
            path="#group:project-mgmt",
            label="项目管理",
            icon="i-heroicons-folder",
            is_group=True,
        )
        assert group.is_group is True
        assert group.parent is None

    def test_leaf_can_reference_parent(self):
        group = PageRoute.objects.create(
            path="#group:project-mgmt", label="项目管理", is_group=True,
        )
        leaf = PageRoute.objects.create(
            path="/app/projects", label="项目列表", parent=group,
        )
        leaf.refresh_from_db()
        assert leaf.parent == group
        assert list(group.children.all()) == [leaf]

    def test_parent_set_null_on_delete(self):
        group = PageRoute.objects.create(
            path="#group:tmp", label="临时", is_group=True,
        )
        leaf = PageRoute.objects.create(
            path="/app/x", label="X", parent=group,
        )
        group.delete()
        leaf.refresh_from_db()
        assert leaf.parent is None

    def test_leaf_defaults_to_not_group(self):
        leaf = PageRoute.objects.create(path="/app/x", label="X")
        assert leaf.is_group is False
