import json

import pytest
from django.core.management import call_command

from page_perms.models import PageRoute

pytestmark = pytest.mark.django_db


class TestDumpRoundTrip:
    def test_dump_includes_parent_and_is_group(self, tmp_path):
        group = PageRoute.objects.create(
            path="#group:proj", label="项目管理",
            is_group=True, sort_order=10, source="manual",
        )
        PageRoute.objects.create(
            path="/app/projects", label="项目列表",
            parent=group, sort_order=11, source="manual",
        )
        out = tmp_path / "out.json"
        call_command("dump_page_perms", output=str(out))
        data = json.loads(out.read_text())
        rows = {r["path"]: r for r in data["seed_routes"]}
        assert rows["#group:proj"]["is_group"] is True
        assert rows["#group:proj"]["parent"] is None
        assert rows["/app/projects"]["is_group"] is False
        assert rows["/app/projects"]["parent"] == "#group:proj"

    def test_round_trip_preserves_hierarchy(self, tmp_path, settings):
        group = PageRoute.objects.create(
            path="#group:proj", label="项目管理",
            is_group=True, sort_order=10, source="seed",
        )
        PageRoute.objects.create(
            path="/app/projects", label="项目列表",
            parent=group, sort_order=11, source="seed",
        )
        out = tmp_path / "out.json"
        call_command("dump_page_perms", output=str(out))

        # 清库，再从 dump 出来的 JSON 跑 sync
        PageRoute.objects.all().delete()
        settings.PAGE_PERMS_SEED_FILE = str(out)
        call_command("sync_page_perms")

        leaf = PageRoute.objects.get(path="/app/projects")
        assert leaf.parent and leaf.parent.path == "#group:proj"
        assert leaf.parent.is_group is True
