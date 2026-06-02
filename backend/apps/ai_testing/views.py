import logging
import threading

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.issues.serializers import IssueListSerializer

from .models import BrowserArtifact, ProjectEnvironment, TestFlow, TestRun, TestStepRun
from .permissions import IsProjectManagerOrSuperuser, IsProjectMember
from .services import create_issue_for_failed_run
from .serializers import (
    BrowserArtifactSerializer,
    ProjectEnvironmentSerializer,
    TestFlowSerializer,
    TestRunSerializer,
    TestStepRunSerializer,
)
from .tasks import run_ai_test

logger = logging.getLogger(__name__)


def _run_ai_test_inline_fallback(run_id: int):
    """Fallback runner when Celery enqueue fails.

    Run in a background thread so sync Playwright never executes in request/ASGI loops.
    """
    try:
        from .services import execute_ai_test_run

        run = TestRun.objects.select_related("flow", "environment").get(pk=run_id)
        execute_ai_test_run(run)
    except Exception:  # pragma: no cover - runtime safeguard for fallback path
        logger.exception("Inline fallback ai-testing run failed: run=%s", run_id)


def _filter_by_project_membership(queryset, user, project_field: str = "project_id"):
    if user.is_superuser:
        return queryset
    kwargs = {f"{project_field}__in": user.projects.values_list("id", flat=True)}
    return queryset.filter(**kwargs)


class ProjectEnvironmentListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectEnvironmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = ProjectEnvironment.objects.select_related("project", "model_settings")
        queryset = _filter_by_project_membership(queryset, self.request.user)
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        project_id = serializer.validated_data["project"].id
        if not IsProjectManagerOrSuperuser.can_manage_project(self.request.user, project_id):
            raise PermissionDenied("仅项目经理或管理员可创建测试环境")
        serializer.save()


class ProjectEnvironmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectEnvironmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ProjectEnvironment.objects.select_related("project", "model_settings")
        return _filter_by_project_membership(queryset, self.request.user)

    def perform_update(self, serializer):
        project_id = serializer.instance.project_id
        if not IsProjectManagerOrSuperuser.can_manage_project(self.request.user, project_id):
            raise PermissionDenied("仅项目经理或管理员可修改测试环境")
        serializer.save()

    def perform_destroy(self, instance):
        if not IsProjectManagerOrSuperuser.can_manage_project(self.request.user, instance.project_id):
            raise PermissionDenied("仅项目经理或管理员可删除测试环境")
        instance.delete()


class TestFlowListCreateView(generics.ListCreateAPIView):
    serializer_class = TestFlowSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TestFlow.objects.select_related("project", "environment", "created_by")
        queryset = _filter_by_project_membership(queryset, self.request.user)
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        project_id = serializer.validated_data["project"].id
        if not IsProjectManagerOrSuperuser.can_manage_project(self.request.user, project_id):
            raise PermissionDenied("仅项目经理或管理员可创建测试流程")
        serializer.save(created_by=self.request.user)


class TestFlowDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TestFlowSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TestFlow.objects.select_related("project", "environment", "created_by")
        return _filter_by_project_membership(queryset, self.request.user)

    def perform_update(self, serializer):
        project_id = serializer.instance.project_id
        if not IsProjectManagerOrSuperuser.can_manage_project(self.request.user, project_id):
            raise PermissionDenied("仅项目经理或管理员可修改测试流程")
        serializer.save()

    def perform_destroy(self, instance):
        if not IsProjectManagerOrSuperuser.can_manage_project(self.request.user, instance.project_id):
            raise PermissionDenied("仅项目经理或管理员可删除测试流程")
        instance.delete()


class TestRunListCreateView(generics.ListCreateAPIView):
    serializer_class = TestRunSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TestRun.objects.select_related("project", "environment", "flow", "created_by")
        queryset = _filter_by_project_membership(queryset, self.request.user)
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        project_id = serializer.validated_data["project"].id
        if not IsProjectMember.can_access_project(self.request.user, project_id):
            raise PermissionDenied("仅项目成员可执行测试")
        run = serializer.save(created_by=self.request.user)
        try:
            run_ai_test.delay(run.id)
        except Exception:  # pragma: no cover - broker down fallback
            logger.exception("Failed to enqueue ai-testing run %s; using threaded fallback", run.id)
            threading.Thread(
                target=_run_ai_test_inline_fallback,
                args=(run.id,),
                daemon=True,
                name=f"ai-testing-fallback-{run.id}",
            ).start()


class TestRunDetailView(generics.RetrieveAPIView):
    serializer_class = TestRunSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TestRun.objects.select_related("project", "environment", "flow", "created_by")
        return _filter_by_project_membership(queryset, self.request.user)


class TestRunCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        run = get_object_or_404(_filter_by_project_membership(TestRun.objects.all(), request.user), pk=pk)
        if run.status not in {TestRun.STATUS_PENDING, TestRun.STATUS_RUNNING}:
            return Response({"detail": "仅 pending/running 状态可取消"}, status=status.HTTP_400_BAD_REQUEST)
        run.status = TestRun.STATUS_CANCELLED
        run.save(update_fields=["status", "updated_at"])
        return Response(TestRunSerializer(run).data)


class TestRunCreateIssueView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        run = get_object_or_404(_filter_by_project_membership(TestRun.objects.select_related("project", "environment"), request.user), pk=pk)
        if not request.user.has_perm("issues.add_issue"):
            raise PermissionDenied("当前用户没有创建问题权限")
        try:
            issue = create_issue_for_failed_run(run=run, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        data = IssueListSerializer(issue, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED)


class TestRunStepsView(generics.ListAPIView):
    serializer_class = TestStepRunSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        run = get_object_or_404(_filter_by_project_membership(TestRun.objects.all(), self.request.user), pk=self.kwargs["pk"])
        self._run = run
        return TestStepRun.objects.filter(run=run).order_by("step_index", "id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        run = getattr(self, "_run", None)
        if queryset.exists() or not run:
            return super().list(request, *args, **kwargs)
        if run.status in {TestRun.STATUS_FAILED, TestRun.STATUS_TIMEOUT, TestRun.STATUS_CANCELLED}:
            synthetic = {
                "id": 0,
                "run": run.id,
                "step_index": 1,
                "skill_name": "system",
                "thought_summary": "历史执行未落步骤，已回填异常信息",
                "tool_name": "runtime_error",
                "tool_input": {},
                "tool_result": {},
                "page_url": run.target_url or "",
                "status": TestStepRun.STATUS_FAILED,
                "error_message": run.failure_reason or run.final_summary or "执行异常",
                "created_at": run.finished_at or run.updated_at or run.created_at,
            }
            return Response([synthetic])
        return Response([])


class TestRunArtifactsView(generics.ListAPIView):
    serializer_class = BrowserArtifactSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        run = get_object_or_404(
            _filter_by_project_membership(TestRun.objects.all(), self.request.user),
            pk=self.kwargs["pk"],
        )
        self._run = run
        return BrowserArtifact.objects.select_related("attachment", "step").filter(run=run).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        run = getattr(self, "_run", None)
        if queryset.exists() or not run:
            return super().list(request, *args, **kwargs)
        if run.status in {TestRun.STATUS_FAILED, TestRun.STATUS_TIMEOUT, TestRun.STATUS_CANCELLED} and (
            run.failure_reason or run.final_summary
        ):
            synthetic = {
                "id": 0,
                "run": run.id,
                "step": None,
                "artifact_type": BrowserArtifact.TYPE_CONSOLE,
                "attachment": None,
                "attachment_url": "",
                "attachment_name": "",
                "content": run.failure_reason or run.final_summary or "执行异常",
                "metadata": {"synthetic": True},
                "created_at": run.finished_at or run.updated_at or run.created_at,
            }
            return Response([synthetic])
        return Response([])


class BrowserArtifactDetailView(generics.RetrieveAPIView):
    serializer_class = BrowserArtifactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        run_ids = _filter_by_project_membership(TestRun.objects.all(), self.request.user).values_list("id", flat=True)
        return BrowserArtifact.objects.filter(run_id__in=run_ids)
