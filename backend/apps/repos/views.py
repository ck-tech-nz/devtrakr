import logging

from django.db.models import Count, Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.permissions import FullDjangoModelPermissions
from .models import Repo, GitHubIssue, GitAuthorAlias
from .serializers import RepoSerializer, GitHubIssueBriefSerializer, GitHubIssueDetailSerializer, GitAuthorAliasSerializer
from .insights import DeveloperInsightsService
from concurrent.futures import ThreadPoolExecutor
from .services import GitHubSyncService, RepoCloneService, GitHubPreviewService, parse_github_ref

_clone_executor = ThreadPoolExecutor(max_workers=2)

logger = logging.getLogger(__name__)


class RepoListCreateView(generics.ListCreateAPIView):
    serializer_class = RepoSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Repo.objects.annotate(
            open_issues_count=Count(
                "github_issues", filter=Q(github_issues__state="open")
            ),
            closed_issues_count=Count(
                "github_issues", filter=Q(github_issues__state="closed")
            ),
        )


class RepoDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = RepoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Repo.objects.annotate(
            open_issues_count=Count(
                "github_issues", filter=Q(github_issues__state="open")
            ),
            closed_issues_count=Count(
                "github_issues", filter=Q(github_issues__state="closed")
            ),
        )


class GitHubIssueListView(generics.ListAPIView):
    serializer_class = GitHubIssueBriefSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = GitHubIssue.objects.select_related("repo").order_by("-github_created_at")
        repo = self.request.query_params.get("repo")
        if repo:
            qs = qs.filter(repo_id=repo)
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        return qs


class GitHubIssueDetailView(generics.RetrieveAPIView):
    queryset = GitHubIssue.objects.select_related("repo")
    serializer_class = GitHubIssueDetailSerializer
    permission_classes = [IsAuthenticated]


class RepoSyncView(APIView):
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    queryset = Repo.objects.none()  # FullDjangoModelPermissions 需要 queryset 确定模型

    def post(self, request, pk):
        try:
            repo = Repo.objects.annotate(
                open_issues_count=Count(
                    "github_issues", filter=Q(github_issues__state="open")
                ),
                closed_issues_count=Count(
                    "github_issues", filter=Q(github_issues__state="closed")
                ),
            ).get(pk=pk)
        except Repo.DoesNotExist:
            return Response(
                {"detail": "仓库不存在"}, status=status.HTTP_404_NOT_FOUND
            )
        try:
            GitHubSyncService().sync_repo(repo)
            repo = Repo.objects.annotate(
                open_issues_count=Count(
                    "github_issues", filter=Q(github_issues__state="open")
                ),
                closed_issues_count=Count(
                    "github_issues", filter=Q(github_issues__state="closed")
                ),
            ).get(pk=pk)
            serializer = RepoSerializer(repo)
            return Response(serializer.data)
        except Exception as e:
            logger.exception("GitHub sync failed for repo %s", pk)
            return Response(
                {"detail": f"GitHub 同步失败: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class RepoCloneView(APIView):
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    queryset = Repo.objects.none()

    def post(self, request, pk):
        try:
            repo = Repo.objects.get(pk=pk)
        except Repo.DoesNotExist:
            return Response({"detail": "仓库不存在"}, status=status.HTTP_404_NOT_FOUND)
        if repo.clone_status == "cloning":
            return Response(
                {"detail": "克隆任务进行中", "clone_status": "cloning"},
                status=status.HTTP_409_CONFLICT,
            )
        branch = request.data.get("branch")
        _clone_executor.submit(RepoCloneService().clone_or_pull, repo, branch)
        return Response(
            {"detail": "克隆任务已启动", "clone_status": "cloning"},
            status=status.HTTP_202_ACCEPTED,
        )


class RepoGitLogView(APIView):
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    queryset = Repo.objects.none()

    def get(self, request, pk):
        try:
            repo = Repo.objects.get(pk=pk)
        except Repo.DoesNotExist:
            return Response({"detail": "仓库不存在"}, status=status.HTTP_404_NOT_FOUND)
        if repo.clone_status != "cloned":
            return Response({"detail": "请先同步代码"}, status=status.HTTP_400_BAD_REQUEST)
        limit = min(int(request.query_params.get("limit", 50)), 200)
        commits = RepoCloneService().get_log(repo, limit=limit)
        return Response(commits)


class RepoBranchesView(APIView):
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    queryset = Repo.objects.none()

    def get(self, request, pk):
        try:
            repo = Repo.objects.get(pk=pk)
        except Repo.DoesNotExist:
            return Response({"detail": "仓库不存在"}, status=status.HTTP_404_NOT_FOUND)
        if repo.clone_status != "cloned":
            return Response({"detail": "请先同步代码"}, status=status.HTTP_400_BAD_REQUEST)
        branches = RepoCloneService().get_branches(repo)
        return Response(branches)


class DeveloperInsightsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            repo = Repo.objects.get(pk=pk)
        except Repo.DoesNotExist:
            return Response({"detail": "仓库不存在"}, status=status.HTTP_404_NOT_FOUND)
        days_param = request.query_params.get("days", "90")
        days = None if days_param == "all" else int(days_param)
        service = DeveloperInsightsService()
        developers = service.team_overview(repo, days=days)
        unlinked = service.unlinked_authors(repo)
        return Response({
            "developers": developers,
            "unlinked_count": len(unlinked),
            "unlinked_authors": unlinked,
        })


class DeveloperInsightsDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, alias_id):
        try:
            repo = Repo.objects.get(pk=pk)
        except Repo.DoesNotExist:
            return Response({"detail": "仓库不存在"}, status=status.HTTP_404_NOT_FOUND)
        try:
            days_param = request.query_params.get("days", "90")
            days = None if days_param == "all" else int(days_param)
            result = DeveloperInsightsService().individual_detail(repo, alias_id, days=days)
            return Response(result)
        except GitAuthorAlias.DoesNotExist:
            return Response({"detail": "作者不存在"}, status=status.HTTP_404_NOT_FOUND)


class SyncCommitsView(APIView):
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    queryset = Repo.objects.none()

    def post(self, request, pk):
        try:
            repo = Repo.objects.get(pk=pk)
        except Repo.DoesNotExist:
            return Response({"detail": "仓库不存在"}, status=status.HTTP_404_NOT_FOUND)
        if repo.clone_status != "cloned":
            return Response({"detail": "请先同步代码"}, status=status.HTTP_400_BAD_REQUEST)
        RepoCloneService().sync_commits(repo)
        return Response({"detail": "提交记录同步完成"})


class GitAuthorAliasPatchView(APIView):
    permission_classes = [IsAuthenticated, FullDjangoModelPermissions]
    queryset = GitAuthorAlias.objects.none()

    def patch(self, request, pk, alias_id):
        try:
            alias = GitAuthorAlias.objects.get(id=alias_id, repo_id=pk)
        except GitAuthorAlias.DoesNotExist:
            return Response({"detail": "作者映射不存在"}, status=status.HTTP_404_NOT_FOUND)
        serializer = GitAuthorAliasSerializer(alias, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class GitHubPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ref = parse_github_ref(request.query_params.get("url", ""))
        if not ref:
            return Response({"supported": False})
        data = GitHubPreviewService().fetch_preview(**ref)
        if not data:
            return Response({"supported": False})
        return Response(data)
