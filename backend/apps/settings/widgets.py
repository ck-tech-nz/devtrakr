import json
from django.forms import Widget
from unfold.widgets import UnfoldAdminTextInputWidget


class ApiKeyGeneratorWidget(UnfoldAdminTextInputWidget):
    """Text input with an inline button that fills the field with a random hex token."""

    template_name = "widgets/api_key_generator.html"


class PriorityListWidget(Widget):
    """优先级对象列表的行编辑器:每行 value/label/主色(原生取色器),支持增删与上下移."""

    template_name = "widgets/priority_list.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                value = []
        if not isinstance(value, list):
            value = []
        # 兼容旧版扁平列表,渲染前统一为对象格式
        items = []
        for p in value:
            if isinstance(p, dict):
                items.append({
                    "value": p.get("value", ""),
                    "label": p.get("label", p.get("value", "")),
                    "background": p.get("background", ""),
                })
            else:
                items.append({"value": p, "label": p, "background": ""})
        context["widget"]["items_json"] = json.dumps(items, ensure_ascii=False)
        return context

    def value_from_datadict(self, data, files, name):
        raw = data.get(name)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
        return []


class JsonReadonlyToggleWidget(Widget):
    """JSON field that defaults to a prettified readonly view with an edit button."""

    template_name = "widgets/json_readonly_toggle.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                value = {}
        if value is None:
            value = {}
        pretty = json.dumps(value, ensure_ascii=False, indent=2)
        context["widget"]["pretty_json"] = pretty
        context["widget"]["raw_json"] = pretty
        return context

    def value_from_datadict(self, data, files, name):
        raw = data.get(name)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
        return {}
