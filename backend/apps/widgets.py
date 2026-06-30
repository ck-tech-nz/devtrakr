import json
from django.forms import Widget


class JsonSchemaWidget(Widget):
    """
    将 JSONField 按 schema 定义拆分为独立的表单控件。

    用法:
        schema = {
            "sidebar_auto_collapse": {"type": "boolean", "label": "侧边栏自动折叠"},
            "issues_view_mode": {"type": "select", "label": "问题视图", "choices": ["kanban", "table"]},
            "theme": {"type": "select", "label": "主题", "choices": ["light", "dark", "auto"]},
        }
        widget = JsonSchemaWidget(schema=schema)

    支持的 type:
        - "text": 文本输入
        - "number": 数字输入
        - "boolean": 复选框
        - "select": 下拉选择 (需提供 choices)
        - "json": 多行 JSON 文本框 (用于数组/对象类设置)

    未在 schema 中列出的键不会丢失:模板把隐藏字段初始化为完整原值,JS 以原值为底做合并,
    仅覆盖 schema 中的键。这样即便 schema 不全(或新增了设置项),保存也不会抹掉其它键。
    """

    template_name = "widgets/json_schema.html"

    def __init__(self, schema=None, attrs=None):
        super().__init__(attrs)
        self.schema = schema or {}

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                value = {}
        if not isinstance(value, dict):
            value = {}

        fields = []
        for key, conf in self.schema.items():
            ftype = conf.get("type", "text")
            raw_val = value.get(key, conf.get("default", ""))
            # json 类型按多行美化串展示;None 显示为空;其余原样
            if ftype == "json":
                display = json.dumps(raw_val, ensure_ascii=False, indent=2)
            elif raw_val is None:
                display = ""
            else:
                display = raw_val
            fields.append(
                {
                    "key": key,
                    "type": ftype,
                    "label": conf.get("label", key),
                    "choices": conf.get("choices", []),
                    "value": display,
                }
            )

        context["widget"]["fields"] = fields
        context["widget"]["json_name"] = name
        # 完整原始 JSON:供模板初始化隐藏字段 + JS 合并的底值,避免未列出的键被丢弃
        context["widget"]["value_json"] = json.dumps(value, ensure_ascii=False)
        return context

    def value_from_datadict(self, data, files, name):
        # 隐藏字段由 JS 以「完整原值为底、覆盖 schema 字段」组装好(模板已将其初始化为原值,
        # 故即使禁用 JS 也只是原样保存、不丢键),直接采用。
        raw = data.get(name)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass

        # 降级(无隐藏值时):从各子字段收集 schema 列出的键
        result = {}
        prefix = f"{name}__"
        for key, conf in self.schema.items():
            field_name = f"{prefix}{key}"
            field_type = conf.get("type", "text")

            if field_type == "boolean":
                result[key] = field_name in data
            elif field_type == "number":
                val = data.get(field_name, "")
                result[key] = float(val) if val else conf.get("default")
            elif field_type == "json":
                val = data.get(field_name, "").strip()
                try:
                    result[key] = json.loads(val) if val else conf.get("default")
                except (json.JSONDecodeError, TypeError):
                    result[key] = conf.get("default")
            else:
                result[key] = data.get(field_name, conf.get("default", ""))
        return result
