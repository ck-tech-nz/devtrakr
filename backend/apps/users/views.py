import logging
from datetime import timedelta
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.generics import RetrieveUpdateAPIView, ListCreateAPIView, CreateAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django.contrib.auth import get_user_model, login as django_login
from apps.permissions import FullDjangoModelPermissions
from .serializers import (
    UserSerializer, MeSerializer, RegisterSerializer,
    AdminUserSerializer, AdminUserUpdateSerializer, AdminCreateUserSerializer,
    ChangePasswordSerializer,
)

User = get_user_model()

logger = logging.getLogger("apps.users.impersonation")

IMPERSONATION_REFRESH_LIFETIME = timedelta(minutes=30)


class MeView(RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserListView(ListCreateAPIView):
    queryset = User.objects.all().order_by("-date_joined")
    permission_classes = [FullDjangoModelPermissions]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminCreateUserSerializer
        return AdminUserSerializer

    def create(self, request, *args, **_kwargs):
        serializer = AdminCreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(RetrieveUpdateAPIView):
    queryset = User.objects.all()
    permission_classes = [FullDjangoModelPermissions]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def update(self, request, *args, **kwargs):
        """Use AdminUserUpdateSerializer for input but return AdminUserSerializer for response."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = AdminUserUpdateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AdminUserSerializer(instance).data)


class RegisterView(CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class UserChoicesView(APIView):
    """轻量级用户选项接口，仅返回 id 和名称，排除机器人用户。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        users = User.objects.filter(is_active=True, is_bot=False).order_by("name")
        data = [{"id": u.id, "name": u.name or u.username} for u in users]
        return Response(data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"detail": "密码修改成功"})


class AdminSessionView(APIView):
    """JWT→session 桥接：用 SPA 的 JWT 登录后，写入 Django session cookie，
    使 /api/admin/ 能识别同源同账号，无需再次登录。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.is_staff:
            return Response({"detail": "无权访问管理后台"}, status=status.HTTP_403_FORBIDDEN)
        django_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response({"detail": "ok"})


class ImpersonateView(APIView):
    """超管模拟登录：签发目标用户的短期 JWT，带 impersonated_by 声明。
    安全边界完全由本接口校验，前端按钮可见性仅为装饰。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        actor = request.user
        # 纵深防御：禁止在模拟态中再次发起模拟
        if request.auth is not None and request.auth.get("impersonated_by"):
            return Response({"detail": "不可嵌套模拟"}, status=status.HTTP_403_FORBIDDEN)
        if not actor.is_superuser:
            return Response({"detail": "无权模拟登录"}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"detail": "缺少 user_id"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        # 唯一禁止的目标：超管（同时覆盖了模拟自己的情况）
        if target.is_superuser:
            return Response({"detail": "不能模拟管理员账号"}, status=status.HTTP_403_FORBIDDEN)
        # 功能性兜底：停用用户的 token 鉴权必失败，直接报错
        if not target.is_active:
            return Response({"detail": "该用户未激活"}, status=status.HTTP_400_BAD_REQUEST)

        refresh = RefreshToken.for_user(target)
        refresh.set_exp(lifetime=IMPERSONATION_REFRESH_LIFETIME)  # 模拟会话短期
        refresh["impersonated_by"] = actor.id
        refresh["impersonated_by_username"] = actor.username
        access = refresh.access_token
        # 审计：模拟登录是超管行为，留一条持久日志（token 内 claim 过期即丢失）
        logger.warning(
            "impersonation: actor=%s(id=%s) -> target=%s(id=%s)",
            actor.username, actor.id, target.username, target.id,
        )
        return Response({"access": str(access), "refresh": str(refresh)})
