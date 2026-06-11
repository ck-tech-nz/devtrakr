import pytest
from apps.settings.models import SiteSettings

pytestmark = pytest.mark.django_db


class TestSiteSettingsModel:
    def test_singleton_only_one_instance(self, site_settings):
        """SiteSettings should only allow one row."""
        second = SiteSettings()
        second.save()
        assert SiteSettings.objects.count() == 1

    def test_default_labels(self, site_settings):
        assert "前端" in site_settings.labels
        assert "Bug" in site_settings.labels
        assert len(site_settings.labels) == 10
        assert site_settings.labels["前端"]["background"] == "#0075ca"

    def test_default_priorities(self, site_settings):
        # 对象列表(高→低),每档带显示名与主色;空 background 表示无底色
        assert [p["value"] for p in site_settings.priorities] == ["P0", "P1", "P2", "P3"]
        assert site_settings.priorities[0]["label"] == "紧急"
        assert site_settings.priorities[0]["background"] == "#ef4444"
        assert site_settings.priorities[3]["background"] == ""

    def test_default_issue_statuses(self, site_settings):
        # 对象列表,每个状态带显示名与主色(前端状态胶囊/看板列圆点据此着色)
        assert [s["value"] for s in site_settings.issue_statuses] == [
            "未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"
        ]
        assert site_settings.issue_statuses[0]["label"] == "未计划"
        assert site_settings.issue_statuses[0]["background"] == "#8b5cf6"
        assert all(s["background"].startswith("#") for s in site_settings.issue_statuses)


class TestColorOptionListWidget:
    def test_items_json_escapes_html(self):
        """items_json 以 |safe 注入 <script>,存储值里的 </script> 必须被转义防 XSS。"""
        from apps.settings.widgets import ColorOptionListWidget

        widget = ColorOptionListWidget()
        ctx = widget.get_context(
            "issue_statuses",
            [{"value": "</script><img src=x onerror=alert(1)>", "label": "x", "background": ""}],
            None,
        )
        items_json = ctx["widget"]["items_json"]
        assert "</script>" not in items_json
        assert "<img" not in items_json
        assert "\\u003c" in items_json


class TestSiteSettingsAPI:
    def test_get_settings_authenticated(self, auth_client, site_settings):
        response = auth_client.get("/api/settings/")
        assert response.status_code == 200
        assert response.data["labels"] == site_settings.labels
        assert response.data["priorities"] == site_settings.priorities
        assert response.data["issue_statuses"] == site_settings.issue_statuses

    def test_get_settings_unauthenticated(self, api_client, site_settings):
        response = api_client.get("/api/settings/")
        assert response.status_code == 401


class TestLabelSettingsAPI:
    def test_patch_labels(self, auth_client, site_settings):
        new_labels = {
            "前端": {"foreground": "#ffffff", "background": "#0075ca", "description": "前端相关"},
            "NewLabel": {"foreground": "#000000", "background": "#ff0000", "description": "新标签"},
        }
        response = auth_client.patch(
            "/api/settings/labels/",
            data={"labels": new_labels},
            format="json",
        )
        assert response.status_code == 200
        assert "NewLabel" in response.data["labels"]
        assert response.data["labels"]["NewLabel"]["background"] == "#ff0000"

    def test_patch_labels_unauthenticated(self, api_client, site_settings):
        response = api_client.patch(
            "/api/settings/labels/",
            data={"labels": {}},
            format="json",
        )
        assert response.status_code == 401

    def test_patch_labels_invalid_format(self, auth_client, site_settings):
        response = auth_client.patch(
            "/api/settings/labels/",
            data={"labels": {"Bad": {"foreground": "#fff"}}},
            format="json",
        )
        assert response.status_code == 400
