from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from apps.issues.models import Issue, Activity
from .authentication import APIKeyAuthentication
from .serializers import ExternalIssueCreateSerializer, ExternalIssueResponseSerializer


class ExternalPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ExternalIssueListCreateView(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        if not hasattr(request, "api_key") or request.api_key is None:
            return Response(
                {"detail": "认证失败"}, status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = ExternalIssueCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Duplicate check
        feedback_id = data.get("source_feedback_id", "")
        if feedback_id:
            existing = Issue.objects.filter(
                source="agent_platform",
                source_meta__feedback_id=feedback_id,
                project=request.api_key.project,
            ).first()
            if existing:
                return Response(
                    {"detail": "反馈已存在", "existing_issue_id": existing.pk},
                    status=status.HTTP_409_CONFLICT,
                )

        # Build source_meta
        source_meta = {}
        if feedback_id:
            source_meta["feedback_id"] = feedback_id
        if data.get("reporter"):
            source_meta["reporter"] = data["reporter"]
        if data.get("context"):
            source_meta["context"] = data["context"]
        if data.get("attachments"):
            source_meta["attachments"] = data["attachments"]

        reporter_name = ""
        if data.get("reporter") and isinstance(data["reporter"], dict):
            reporter_name = data["reporter"].get("user_name", "")

        issue = Issue.objects.create(
            title=data["title"],
            description=data.get("description", ""),
            priority=data.get("priority", "P2"),
            labels=data.get("_labels", []),
            status="待分配",
            source="agent_platform",
            source_meta=source_meta or None,
            project=request.api_key.project,
            created_by=request.api_key.default_assignee,
            reporter=reporter_name,
        )

        Activity.objects.create(
            user=request.api_key.default_assignee,
            issue=issue,
            action="created",
            detail="通过外部 API 创建",
        )

        response_serializer = ExternalIssueResponseSerializer(issue)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def get(self, request):
        if not hasattr(request, "api_key") or request.api_key is None:
            return Response(
                {"detail": "认证失败"}, status=status.HTTP_401_UNAUTHORIZED
            )

        qs = Issue.objects.select_related("assignee").filter(
            source="agent_platform",
            project=request.api_key.project,
        )

        # Filters
        feedback_id = request.query_params.get("feedback_id")
        if feedback_id:
            qs = qs.filter(source_meta__feedback_id=feedback_id)
        issue_status = request.query_params.get("status")
        if issue_status:
            qs = qs.filter(status=issue_status)
        priority = request.query_params.get("priority")
        if priority:
            qs = qs.filter(priority=priority)

        paginator = ExternalPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ExternalIssueResponseSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ExternalIssueDetailView(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, pk):
        if not hasattr(request, "api_key") or request.api_key is None:
            return Response(
                {"detail": "认证失败"}, status=status.HTTP_401_UNAUTHORIZED
            )

        issue = Issue.objects.select_related("assignee").filter(
            pk=pk,
            source="agent_platform",
            project=request.api_key.project,
        ).first()

        if not issue:
            return Response(
                {"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = ExternalIssueResponseSerializer(issue)
        return Response(serializer.data)
