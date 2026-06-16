import pytest
from django.core.exceptions import ValidationError
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

    def test_default_issue_statuses_are_enabled(self, site_settings):
        # 新建默认每个状态都带 disabled=False(可被禁用功能的默认启用态)
        assert all(s["disabled"] is False for s in site_settings.issue_statuses)


class TestSiteSettingsClean:
    """clean() 兜底:系统自动赋值的「流程关键状态」不可被禁用,否则工单会流转进 UI 不可见的状态。"""

    def _set_disabled(self, settings, value, disabled):
        for s in settings.issue_statuses:
            if s["value"] == value:
                s["disabled"] = disabled

    def test_clean_passes_when_all_enabled(self, site_settings):
        site_settings.clean()  # 默认全启用,不应抛错

    @pytest.mark.parametrize("status", ["未计划", "已发布"])
    def test_clean_allows_disabling_non_locked_status(self, site_settings, status):
        # 未计划 / 已发布 是仅有的两个不被任何代码路径赋值的状态,可禁用
        self._set_disabled(site_settings, status, True)
        site_settings.clean()

    @pytest.mark.parametrize("locked", ["待分配", "待确认", "进行中", "已解决", "已关闭"])
    def test_clean_rejects_disabling_locked_status(self, site_settings, locked):
        # 待分配(新建初始)/待确认/进行中(自动流转目标)/已解决(uptime 自动恢复)/
        # 已关闭(关闭动作)均由代码路径赋值,禁用会产生 UI 不可见的工单
        self._set_disabled(site_settings, locked, True)
        with pytest.raises(ValidationError):
            site_settings.clean()


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

    def test_get_context_normalizes_legacy_flat_list(self):
        """旧版扁平列表 ["P0",...] 渲染前统一为对象格式(label=value,无主色)。"""
        import json

        from apps.settings.widgets import ColorOptionListWidget

        widget = ColorOptionListWidget()
        ctx = widget.get_context("priorities", ["P0", "P1"], None)
        items = json.loads(ctx["widget"]["items_json"])
        assert items == [
            {"value": "P0", "label": "P0", "background": ""},
            {"value": "P1", "label": "P1", "background": ""},
        ]

    def test_get_context_invalid_value_renders_empty_list(self):
        """非法 JSON 字符串 / 非列表值不应让 admin 页面崩溃,渲染为空列表。"""
        import json

        from apps.settings.widgets import ColorOptionListWidget

        widget = ColorOptionListWidget()
        for bad in ("{not json", {"value": "P0"}, None):
            ctx = widget.get_context("priorities", bad, None)
            assert json.loads(ctx["widget"]["items_json"]) == []

    def test_get_context_preserves_disabled_when_allow_disable(self):
        """allow_disable 时 disabled 标记必须在渲染时保留,否则每次打开 admin 都丢失禁用态。"""
        import json

        from apps.settings.widgets import ColorOptionListWidget

        widget = ColorOptionListWidget(allow_disable=True, locked_values=("进行中",))
        ctx = widget.get_context(
            "issue_statuses",
            [{"value": "已发布", "label": "已发布", "background": "#14b8a6", "disabled": True}],
            None,
        )
        items = json.loads(ctx["widget"]["items_json"])
        assert items[0]["disabled"] is True
        assert ctx["widget"]["allow_disable"] is True
        assert json.loads(ctx["widget"]["locked_values_json"]) == ["进行中"]

    def test_get_context_omits_disabled_when_not_allow_disable(self):
        """priorities 等不开启禁用功能的实例不应渲染 disabled 字段,保持原样。"""
        import json

        from apps.settings.widgets import ColorOptionListWidget

        widget = ColorOptionListWidget()
        ctx = widget.get_context(
            "priorities",
            [{"value": "P0", "label": "紧急", "background": "#ef4444"}],
            None,
        )
        items = json.loads(ctx["widget"]["items_json"])
        assert "disabled" not in items[0]
        assert ctx["widget"]["allow_disable"] is False

    def test_value_from_datadict_returns_raw_string(self):
        """返回原始 JSON 字符串(交给 forms.JSONField 解析);缺失/空回退为 "[]"。
        不可返回已解析对象:否则 forms.JSONField.bound_data 在校验失败重渲染时
        会对非字符串再次 json.loads 抛 TypeError(见下方 bound_data 兼容性测试)。"""
        from apps.settings.widgets import ColorOptionListWidget

        widget = ColorOptionListWidget()
        raw = '[{"value": "P0", "label": "紧急", "background": "#ef4444"}]'
        assert widget.value_from_datadict({"priorities": raw}, {}, "priorities") == raw
        assert widget.value_from_datadict({"priorities": "{broken"}, {}, "priorities") == "{broken"
        assert widget.value_from_datadict({}, {}, "priorities") == "[]"

    def test_value_from_datadict_compatible_with_jsonfield_bound_data(self):
        """复现并防回归:admin 表单校验失败重渲染时,forms.JSONField.bound_data 会对
        widget.value_from_datadict 的返回值 json.loads。返回已解析对象会 TypeError 崩溃
        (站点设置 clean() 拒绝禁用锁定状态时正是走这条重渲染路径)。"""
        from django import forms
        from apps.settings.widgets import ColorOptionListWidget

        widget = ColorOptionListWidget(allow_disable=True)
        raw = '[{"value": "进行中", "label": "进行中", "background": "#3b82f6", "disabled": true}]'
        submitted = widget.value_from_datadict({"issue_statuses": raw}, {}, "issue_statuses")
        # 重渲染路径——不应抛 TypeError
        result = forms.JSONField().bound_data(submitted, None)
        assert result == [
            {"value": "进行中", "label": "进行中", "background": "#3b82f6", "disabled": True}
        ]


class TestJsonReadonlyToggleWidget:
    """labels 字段用此 widget;与 ColorOptionListWidget 同理,必须返回原始字符串,
    否则站点设置表单(任一字段)校验失败重渲染时,labels 的 bound_data 会先崩溃。"""

    def test_value_from_datadict_returns_raw_string(self):
        from apps.settings.widgets import JsonReadonlyToggleWidget

        widget = JsonReadonlyToggleWidget()
        raw = '{"前端": {"foreground": "#fff", "background": "#000", "description": "x"}}'
        assert widget.value_from_datadict({"labels": raw}, {}, "labels") == raw
        assert widget.value_from_datadict({}, {}, "labels") == "{}"

    def test_value_from_datadict_compatible_with_jsonfield_bound_data(self):
        from django import forms
        from apps.settings.widgets import JsonReadonlyToggleWidget

        widget = JsonReadonlyToggleWidget()
        raw = '{"前端": {"foreground": "#fff", "background": "#000", "description": "x"}}'
        submitted = widget.value_from_datadict({"labels": raw}, {}, "labels")
        result = forms.JSONField().bound_data(submitted, None)
        assert result == {"前端": {"foreground": "#fff", "background": "#000", "description": "x"}}


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
