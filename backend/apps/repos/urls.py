from django.urls import path
from .views import (
    RepoListCreateView, RepoDetailView, GitHubIssueListView,
    RepoSyncView, GitHubIssueDetailView,
    RepoCloneView, RepoGitLogView, RepoBranchesView,
    DeveloperInsightsListView, DeveloperInsightsDetailView,
    SyncCommitsView, GitAuthorAliasPatchView, GitHubPreviewView,
)

urlpatterns = [
    path("", RepoListCreateView.as_view(), name="repo-list"),
    path("github-preview/", GitHubPreviewView.as_view(), name="github-preview"),
    path("github-issues/", GitHubIssueListView.as_view(), name="github-issue-list"),
    path("github-issues/<int:pk>/", GitHubIssueDetailView.as_view(), name="github-issue-detail"),
    path("<int:pk>/sync/", RepoSyncView.as_view(), name="repo-sync"),
    path("<int:pk>/clone/", RepoCloneView.as_view(), name="repo-clone"),
    path("<int:pk>/git-log/", RepoGitLogView.as_view(), name="repo-git-log"),
    path("<int:pk>/branches/", RepoBranchesView.as_view(), name="repo-branches"),
    path("<int:pk>/sync-commits/", SyncCommitsView.as_view(), name="repo-sync-commits"),
    path("<int:pk>/developer-insights/", DeveloperInsightsListView.as_view(), name="developer-insights-list"),
    path("<int:pk>/developer-insights/<int:alias_id>/", DeveloperInsightsDetailView.as_view(), name="developer-insights-detail"),
    path("<int:pk>/git-author-aliases/<int:alias_id>/", GitAuthorAliasPatchView.as_view(), name="git-author-alias-patch"),
    path("<int:pk>/", RepoDetailView.as_view(), name="repo-detail"),
]
