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
                 value_placeholder="值", label_placeholder="显示名",
                 allow_disable=False, locked_values=(), attrs=None):
        super().__init__(attrs)
        self.hint = hint
        self.value_placeholder = value_placeholder
        self.label_placeholder = label_placeholder
        # allow_disable: 是否渲染「禁用」复选框列;locked_values: 不可禁用(复选框置灰)的 value
        self.allow_disable = allow_disable
        self.locked_values = list(locked_values)

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
                item = {
                    "value": p.get("value", ""),
                    "label": p.get("label", p.get("value", "")),
                    "background": p.get("background", ""),
                }
                # 仅在启用禁用功能时保留 disabled,否则渲染时丢失会让禁用态归零
                if self.allow_disable:
                    item["disabled"] = bool(p.get("disabled", False))
                items.append(item)
            else:
                items.append({"value": p, "label": p, "background": ""})
        # 模板把这些 JSON 以 |safe 注入 <script>,必须转义 HTML 敏感字符防止
        # 存储值里的 </script> 突破脚本块(同 Django json_script 的处理)
        def _script_safe(data):
            return (
                json.dumps(data, ensure_ascii=False)
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("&", "\\u0026")
            )

        context["widget"]["items_json"] = _script_safe(items)
        context["widget"]["hint"] = self.hint
        context["widget"]["value_placeholder"] = self.value_placeholder
        context["widget"]["label_placeholder"] = self.label_placeholder
        context["widget"]["allow_disable"] = self.allow_disable
        context["widget"]["locked_values_json"] = _script_safe(self.locked_values)
        return context

    def value_from_datadict(self, data, files, name):
        # 返回原始 JSON 字符串交给 forms.JSONField 解析(to_python),而非在此预解析:
        # 预解析成对象后,表单校验失败重渲染时 forms.JSONField.bound_data 会对其再次
        # json.loads,非字符串会抛 TypeError 让 admin 页 500(站点设置 clean() 拒绝
        # 禁用锁定状态时正是这条路径)。空/缺失回退 "[]" 保持「无数据=空列表」语义。
        return data.get(name) or "[]"


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
        # 同 ColorOptionListWidget:返回原始 JSON 字符串交给 forms.JSONField 解析,
        # 不可预解析为对象——否则表单校验失败重渲染时 bound_data 对其 json.loads 崩溃。
        # 空/缺失回退 "{}" 保持「无数据=空对象」语义(labels 是对象)。
        return data.get(name) or "{}"
