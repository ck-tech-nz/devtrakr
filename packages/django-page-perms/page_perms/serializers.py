from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from .models import PageRoute


def resolve_permission(perm_string):
    """Resolve 'app_label.codename' string to a Permission instance."""
    if not perm_string:
        return None
    try:
        app_label, codename = perm_string.split(".", 1)
    except ValueError:
        raise serializers.ValidationError(
            {"permission": f"Invalid format: '{perm_string}'. Expected 'app_label.codename'."}
        )
    try:
        return Permission.objects.get(
            content_type__app_label=app_label, codename=codename
        )
    except Permission.DoesNotExist:
        raise serializers.ValidationError(
            {"permission": f"Permission '{perm_string}' does not exist."}
        )


class PageRouteSerializer(serializers.ModelSerializer):
    permission = serializers.CharField(allow_null=True, required=False, default=None)
    parent = serializers.CharField(allow_null=True, required=False, default=None)

    class Meta:
        model = PageRoute
        fields = [
            "id", "path", "label", "icon", "permission",
            "parent", "is_group",
            "show_in_nav", "sort_order", "is_active", "meta", "source",
        ]
        read_only_fields = ["source"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.permission:
            ct = instance.permission.content_type
            data["permission"] = f"{ct.app_label}.{instance.permission.codename}"
        else:
            data["permission"] = None
        data["parent"] = instance.parent.path if instance.parent_id else None
        return data

    def validate_permission(self, value):
        """Validate and resolve the permission string to a Permission instance."""
        return resolve_permission(value)

    def validate_parent(self, value):
        if not value:
            return None
        try:
            return PageRoute.objects.get(path=value)
        except PageRoute.DoesNotExist:
            raise serializers.ValidationError(
                f"Parent route '{value}' does not exist."
            )

    def validate(self, attrs):
        # Mirror PageRoute.clean() so the API can't bypass the hierarchy guard.
        # Admin runs clean() via ModelForm; DRF doesn't, so we do it explicitly.
        from django.core.exceptions import ValidationError as DjangoValidationError

        instance = self.instance or PageRoute(**{k: v for k, v in attrs.items() if k != "source"})
        for field, value in attrs.items():
            if field == "source":
                continue
            setattr(instance, field, value)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages})
        return attrs


class PermissionSerializer(serializers.ModelSerializer):
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)
    source = serializers.SerializerMethodField()
    full_codename = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ["id", "codename", "name", "app_label", "source", "full_codename"]
        read_only_fields = ["id", "codename", "name", "app_label", "source", "full_codename"]

    def get_source(self, obj):
        ct = obj.content_type
        if ct.app_label == "page_perms":
            return "custom"
        return "model"

    def get_full_codename(self, obj):
        return f"{obj.content_type.app_label}.{obj.codename}"


class CreatePermissionSerializer(serializers.Serializer):
    codename = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=255)

    def validate_codename(self, value):
        ct = ContentType.objects.get_for_model(PageRoute)
        if Permission.objects.filter(content_type=ct, codename=value).exists():
            raise serializers.ValidationError(f"Permission with codename '{value}' already exists.")
        return value

    def create(self, validated_data):
        ct = ContentType.objects.get_for_model(PageRoute)
        return Permission.objects.create(
            content_type=ct,
            codename=validated_data["codename"],
            name=validated_data["name"],
        )


class GroupSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name", "permissions"]
        read_only_fields = ["id", "name"]

    def get_permissions(self, obj):
        return [
            f"{p.content_type.app_label}.{p.codename}"
            for p in obj.permissions.select_related("content_type").all()
        ]


class GroupCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    permissions = serializers.ListField(child=serializers.CharField(), default=list)

    def validate_name(self, value):
        if Group.objects.filter(name=value).exists():
            raise serializers.ValidationError(f"组名 '{value}' 已存在。")
        return value

    def create(self, validated_data):
        group = Group.objects.create(name=validated_data["name"])
        perm_strings = validated_data.get("permissions", [])
        perms = []
        for perm_string in perm_strings:
            try:
                app_label, codename = perm_string.split(".", 1)
                perm = Permission.objects.get(content_type__app_label=app_label, codename=codename)
                perms.append(perm)
            except (ValueError, Permission.DoesNotExist):
                pass
        if perms:
            group.permissions.set(perms)
        return group


class GroupUpdateSerializer(serializers.Serializer):
    permissions = serializers.ListField(child=serializers.CharField())

    def update(self, instance, validated_data):
        perm_strings = validated_data["permissions"]
        perms = []
        for perm_string in perm_strings:
            try:
                app_label, codename = perm_string.split(".", 1)
            except ValueError:
                raise serializers.ValidationError(
                    {"permissions": f"Invalid format: '{perm_string}'. Expected 'app_label.codename'."}
                )
            try:
                perm = Permission.objects.get(
                    content_type__app_label=app_label, codename=codename
                )
                perms.append(perm)
            except Permission.DoesNotExist:
                raise serializers.ValidationError(
                    {"permissions": f"Permission '{perm_string}' does not exist."}
                )
        instance.permissions.set(perms)
        return instance
