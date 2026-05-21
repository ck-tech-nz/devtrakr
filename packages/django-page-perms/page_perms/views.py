from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .conf import get_config
from .models import PageRoute
from .permissions import IsSuperUser
from .serializers import (
    CreatePermissionSerializer,
    GroupCreateSerializer,
    GroupSerializer,
    GroupUpdateSerializer,
    PageRouteSerializer,
    PermissionSerializer,
)


class PageRouteViewSet(viewsets.ModelViewSet):
    serializer_class = PageRouteSerializer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.action == "list":
            config = get_config()
            perm_name = config.get("ROUTE_LIST_PERMISSION", "IsAuthenticated")
            if perm_name == "IsSuperUser":
                return [IsSuperUser()]
            return [IsAuthenticated()]
        return [IsSuperUser()]

    def get_queryset(self):
        qs = PageRoute.objects.select_related("permission__content_type").all()
        if not (self.request.user and self.request.user.is_superuser):
            qs = qs.filter(is_active=True)
        elif self.action == "list" and self.request.query_params.get("all") != "true":
            # 仅在列表接口默认过滤非活跃路由，detail 操作不过滤
            qs = qs.filter(is_active=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        config = get_config()
        if instance.path in config["PROTECTED_PATHS"]:
            return Response(
                {"detail": f"Cannot delete protected route: {instance.path}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        config = get_config()
        if instance.path in config["PROTECTED_PATHS"]:
            if "is_active" in request.data and not request.data["is_active"]:
                return Response(
                    {"detail": f"Cannot deactivate protected route: {instance.path}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().partial_update(request, *args, **kwargs)


class PermissionViewSet(viewsets.ViewSet):
    permission_classes = [IsSuperUser]

    def list(self, request):
        permissions = Permission.objects.select_related("content_type").all()
        serializer = PermissionSerializer(permissions, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = CreatePermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        perm = serializer.save()
        return Response(
            PermissionSerializer(perm).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, pk=None):
        try:
            perm = Permission.objects.select_related("content_type").get(pk=pk)
        except Permission.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        ct = ContentType.objects.get_for_model(PageRoute)
        if perm.content_type != ct:
            return Response(
                {"detail": "Cannot delete model-generated permissions."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        perm.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class _HasAuthGroupView(IsAuthenticated):
    def has_permission(self, request, view):
        return bool(
            super().has_permission(request, view)
            and request.user.has_perm("auth.view_group")
        )


class GroupViewSet(viewsets.ViewSet):
    def get_permissions(self):
        # Read-only access gated by auth.view_group (e.g. HR listing groups for
        # user mgmt); group mutation stays superuser-only.
        if self.action in ("list", "retrieve"):
            return [_HasAuthGroupView()]
        return [IsSuperUser()]

    def list(self, request):
        groups = Group.objects.prefetch_related("permissions__content_type").all()
        serializer = GroupSerializer(groups, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = GroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = serializer.save()
        return Response(GroupSerializer(group).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            group = Group.objects.get(pk=pk)
        except Group.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        old_perms = set(
            f"{p.content_type.app_label}.{p.codename}"
            for p in group.permissions.select_related("content_type").all()
        )

        serializer = GroupUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update(group, serializer.validated_data)

        new_perms = set(serializer.validated_data["permissions"])
        added = new_perms - old_perms
        removed = old_perms - new_perms

        if added or removed:
            ct = ContentType.objects.get_for_model(Group)
            LogEntry.objects.create(
                user_id=request.user.pk,
                content_type_id=ct.pk,
                object_id=str(group.pk),
                object_repr=group.name,
                action_flag=CHANGE,
                change_message=f"Permissions changed. Added: {sorted(added)}. Removed: {sorted(removed)}.",
            )

        return Response(GroupSerializer(group).data)
