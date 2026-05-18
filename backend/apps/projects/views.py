from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404
from apps.permissions import FullDjangoModelPermissions
from .models import Project, ProjectMember
from .serializers import (
    ProjectListSerializer,
    ProjectDetailSerializer,
    ProjectCreateUpdateSerializer,
    ProjectMemberSerializer,
    ProjectMemberCreateSerializer,
    ProjectMemberUpdateSerializer,
)

User = get_user_model()


class ProjectListCreateView(generics.ListCreateAPIView):
    queryset = Project.objects.all()
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCreateUpdateSerializer
        return ProjectListSerializer


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return ProjectCreateUpdateSerializer
        return ProjectDetailSerializer


class ProjectMemberListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectMemberSerializer
    pagination_class = None

    def get_queryset(self):
        return ProjectMember.objects.filter(
            project_id=self.kwargs["project_pk"]
        ).select_related("user", "role")

    def create(self, request, project_pk=None):
        serializer = ProjectMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = get_object_or_404(Project, pk=project_pk)
        member = ProjectMember.objects.create(
            project=project,
            user_id=serializer.validated_data["user_id"],
            role=serializer.validated_data.get("role_id"),
            personal_description=serializer.validated_data.get("personal_description", ""),
        )
        return Response(
            ProjectMemberSerializer(member).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectMemberDetailView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectMemberUpdateSerializer

    def get_object(self):
        return get_object_or_404(
            ProjectMember,
            project_id=self.kwargs["project_pk"],
            user_id=self.kwargs["user_pk"],
        )

    def patch(self, request, *args, **kwargs):
        member = self.get_object()
        serializer = self.get_serializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ProjectMemberSerializer(member).data)

    def delete(self, request, *args, **kwargs):
        member = self.get_object()
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectIssuesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from apps.issues.models import Issue
        return Issue.objects.filter(project_id=self.kwargs["project_pk"])

    def get_serializer_class(self):
        from apps.issues.serializers import IssueListSerializer
        return IssueListSerializer


class ProjectMemberRoleChoicesView(APIView):
    """Lightweight endpoint for the project-member role selector.

    Returns id+name of every auth.Group so any authenticated user can populate
    the dropdown without needing superuser access to /api/page-perms/groups/.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        groups = Group.objects.order_by("name").values("id", "name")
        return Response(list(groups))
