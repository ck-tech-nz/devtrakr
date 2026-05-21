import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command

from page_perms.models import PageRoute

pytestmark = pytest.mark.django_db


class TestSyncPagePerms:
    def test_creates_routes_from_seed(self, settings):
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "/app/test", "label": "Test", "sort_order": 0},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        assert PageRoute.objects.filter(path="/app/test", source="seed").exists()

    def test_idempotent_routes(self, settings):
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "/app/test", "label": "Test", "sort_order": 0},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        call_command("sync_page_perms")
        assert PageRoute.objects.filter(path="/app/test").count() == 1

    def test_does_not_touch_manual_routes(self, settings):
        PageRoute.objects.create(path="/app/custom", label="Custom", source="manual")
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "/app/test", "label": "Test", "sort_order": 0},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        assert PageRoute.objects.filter(path="/app/custom", source="manual").exists()

    def test_creates_groups(self, settings):
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [],
            "SEED_GROUPS": {
                "TestGroup": {"permissions_startswith": ["view_"]},
            },
        }
        call_command("sync_page_perms")
        group = Group.objects.get(name="TestGroup")
        assert group.permissions.count() > 0

    def test_inherit_snapshot_semantics(self, settings):
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [],
            "SEED_GROUPS": {
                "Base": {"permissions": ["view_issue"]},
                "Extended": {"inherit": "Base", "permissions": ["add_issue"]},
            },
        }
        call_command("sync_page_perms")
        extended = Group.objects.get(name="Extended")
        codenames = set(extended.permissions.values_list("codename", flat=True))
        assert "view_issue" in codenames
        assert "add_issue" in codenames

    def test_seed_supports_meta_and_show_in_nav_false(self, settings):
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "/app/admin-only", "label": "AdminOnly", "sort_order": 0,
                 "meta": {"adminOnly": True}},
                {"path": "/app/hidden", "label": "Hidden", "sort_order": 1,
                 "show_in_nav": False},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        admin_route = PageRoute.objects.get(path="/app/admin-only")
        assert admin_route.meta == {"adminOnly": True}
        hidden_route = PageRoute.objects.get(path="/app/hidden")
        assert hidden_route.show_in_nav is False

    def test_roadmap_route_seeded_from_production_config(self):
        # 不覆盖 settings.PAGE_PERMS，验证生产配置中 /app/roadmap 能被 sync 命令正确建立
        call_command("sync_page_perms")
        route = PageRoute.objects.get(path="/app/roadmap")
        assert route.label == "产品路线图"
        assert route.icon == "i-heroicons-map"
        assert route.permission is None
        assert route.show_in_nav is True
        assert route.source == "seed"


class TestSyncHierarchy:
    def test_sync_creates_group_with_is_group(self, settings):
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {
                    "path": "#group:proj",
                    "label": "项目管理",
                    "icon": "i-heroicons-folder",
                    "is_group": True,
                    "sort_order": 10,
                },
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        group = PageRoute.objects.get(path="#group:proj")
        assert group.is_group is True
        assert group.label == "项目管理"

    def test_sync_links_leaf_to_parent(self, settings):
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "#group:proj", "label": "项目管理",
                 "is_group": True, "sort_order": 10},
                {"path": "/app/projects", "label": "项目列表",
                 "parent": "#group:proj", "sort_order": 11},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        leaf = PageRoute.objects.get(path="/app/projects")
        assert leaf.parent and leaf.parent.path == "#group:proj"

    def test_sync_handles_child_before_parent_in_json(self, settings):
        # Child 行在 parent 之前出现 —— 两遍 sync 必须能搞定
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "/app/projects", "label": "项目列表",
                 "parent": "#group:proj", "sort_order": 11},
                {"path": "#group:proj", "label": "项目管理",
                 "is_group": True, "sort_order": 10},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        leaf = PageRoute.objects.get(path="/app/projects")
        assert leaf.parent and leaf.parent.path == "#group:proj"

    def test_sync_clears_parent_when_removed_from_seed(self, settings):
        # 先 sync 出 parent 关系
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "#group:proj", "label": "项目管理",
                 "is_group": True, "sort_order": 10},
                {"path": "/app/projects", "label": "项目列表",
                 "parent": "#group:proj", "sort_order": 11},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        # 再次 sync，叶子的 parent 字段被显式置空
        settings.PAGE_PERMS = {
            "SEED_ROUTES": [
                {"path": "#group:proj", "label": "项目管理",
                 "is_group": True, "sort_order": 10},
                {"path": "/app/projects", "label": "项目列表",
                 "parent": None, "sort_order": 11},
            ],
            "SEED_GROUPS": {},
        }
        call_command("sync_page_perms")
        leaf = PageRoute.objects.get(path="/app/projects")
        assert leaf.parent is None
