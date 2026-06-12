import json
from django.forms import Widget
from unfold.widgets import UnfoldAdminTextInputWidget


class ApiKeyGeneratorWidget(UnfoldAdminTextInputWidget):
    """Text input with an inline button that fills the field with a random hex token."""

    template_name = "widgets/api_key_generator.html"


class ColorOptionListWidget(Widget):
    """带主色的选项对象列表行编辑器:每行 value(只读)/label/主色(原生取色器),支持上下移.

    通用于 priorities / issue_statuses 这类 [{"value","label","background"},...] JSONField;
    hint/占位文案由调用方按字段语义传入.档位 value 锁定不可增删改——Issue 模型
    choices 与状态流转逻辑硬编码这些 value,放开编辑只会产生前端可选、后端 400 的档位.
    """

    template_name = "widgets/color_option_list.html"

    def __init__(self, *, hint="",
                 value_placeholder="值", label_placeholder="显示名", attrs=None):
        super().__init__(attrs)
        self.hint = hint
        self.value_placeholder = value_placeholder
        self.label_placeholder = label_placeholder

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
        # 模板把这段 JSON 以 |safe 注入 <script>,必须转义 HTML 敏感字符防止
        # 存储值里的 </script> 突破脚本块(同 Django json_script 的处理)
        context["widget"]["items_json"] = (
            json.dumps(items, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        context["widget"]["hint"] = self.hint
        context["widget"]["value_placeholder"] = self.value_placeholder
        context["widget"]["label_placeholder"] = self.label_placeholder
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
