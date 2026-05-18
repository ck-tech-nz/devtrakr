from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from .models import Project, ProjectMember

User = get_user_model()


class ProjectMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)
    avatar = serializers.URLField(source="user.avatar", read_only=True)
    role = serializers.CharField(source="role.name", read_only=True, allow_null=True)
    role_id = serializers.PrimaryKeyRelatedField(
        source="role", queryset=Group.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = ProjectMember
        fields = ["user_id", "user_name", "avatar", "role", "role_id",
                  "personal_description", "is_manager"]


class ProjectMemberCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), allow_null=True, required=False
    )
    personal_description = serializers.CharField(
        allow_blank=True, required=False, default=""
    )
    is_manager = serializers.BooleanField(required=False, default=False)

    def validate_user_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("用户不存在")
        return value


class ProjectMemberUpdateSerializer(serializers.ModelSerializer):
    role_id = serializers.PrimaryKeyRelatedField(
        source="role", queryset=Group.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = ProjectMember
        fields = ["role_id", "personal_description", "is_manager"]


class ProjectListSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    issue_count = serializers.SerializerMethodField()
    repos = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "description", "status", "remark",
            "estimated_completion", "actual_hours", "repos",
            "member_count", "issue_count", "created_at", "updated_at",
        ]

    def get_member_count(self, obj):
        return obj.project_members.count()

    def get_issue_count(self, obj):
        return obj.issues.count() if hasattr(obj, "issues") else 0


class ProjectDetailSerializer(serializers.ModelSerializer):
    members = ProjectMemberSerializer(source="project_members", many=True, read_only=True)
    repos = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "description", "status", "remark",
            "estimated_completion", "actual_hours", "repos",
            "members", "created_at", "updated_at",
        ]


class ProjectCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "name", "description", "status", "remark",
            "estimated_completion", "actual_hours", "repos",
        ]
