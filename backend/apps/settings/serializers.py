import re
from rest_framework import serializers
from .models import SiteSettings


class SiteSettingsSerializer(serializers.ModelSerializer):
    default_project = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = ["labels", "priorities", "issue_statuses", "modules", "default_project"]

    def get_default_project(self, obj):
        if obj.default_project is None:
            return None
        return {"id": str(obj.default_project.id), "name": obj.default_project.name}


class LabelSettingsSerializer(serializers.Serializer):
    labels = serializers.DictField(child=serializers.DictField())

    def validate_labels(self, value):
        hex_re = re.compile(r'^#[0-9a-fA-F]{3,8}$')
        for name, props in value.items():
            if not isinstance(props, dict):
                raise serializers.ValidationError(f"标签 '{name}' 格式错误")
            missing = {"foreground", "background", "description"} - set(props.keys())
            if missing:
                raise serializers.ValidationError(f"标签 '{name}' 缺少字段: {missing}")
            for color_field in ("foreground", "background"):
                if not hex_re.match(props[color_field]):
                    raise serializers.ValidationError(
                        f"标签 '{name}' 的 {color_field} 不是有效的十六进制颜色"
                    )
        return value
