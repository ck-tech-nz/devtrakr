from django.urls import path
from .views import (
    IssueListCreateView, IssueDetailView, BatchUpdateView,
    IssueGitHubCreateView, IssueGitHubLinkView, IssueCloseWithGitHubView,
    IssueAIAnalyzeView, IssueAIStatusView, IssueAnalysesView,
    IssueAttachmentsView, IssueCheckDuplicateView, IssueHistoryView,
    IssueAiDraftView,
    IssueClaimView, IssueConfirmView, IssueTransferView, IssueAssignView,
)

urlpatterns = [
    path("", IssueListCreateView.as_view(), name="issue-list"),
    path("check-duplicate/", IssueCheckDuplicateView.as_view(), name="issue-check-duplicate"),
    path("ai-draft/", IssueAiDraftView.as_view(), name="issue-ai-draft"),
    path("batch-update/", BatchUpdateView.as_view(), name="issue-batch-update"),
    path("<int:pk>/", IssueDetailView.as_view(), name="issue-detail"),
    path("<int:pk>/attachments/", IssueAttachmentsView.as_view(), name="issue-attachments"),
    path("<int:pk>/github-create/", IssueGitHubCreateView.as_view(), name="issue-github-create"),
    path("<int:pk>/github-link/", IssueGitHubLinkView.as_view(), name="issue-github-link"),
    path("<int:pk>/close-with-github/", IssueCloseWithGitHubView.as_view(), name="issue-close-with-github"),
    path("<int:pk>/ai-analyze/", IssueAIAnalyzeView.as_view(), name="issue-ai-analyze"),
    path("<int:pk>/ai-status/", IssueAIStatusView.as_view(), name="issue-ai-status"),
    path("<int:pk>/analyses/", IssueAnalysesView.as_view(), name="issue-analyses"),
    path("<int:pk>/history/", IssueHistoryView.as_view(), name="issue-history"),
    path("<int:pk>/claim/", IssueClaimView.as_view(), name="issue-claim"),
    path("<int:pk>/confirm/", IssueConfirmView.as_view(), name="issue-confirm"),
    path("<int:pk>/transfer/", IssueTransferView.as_view(), name="issue-transfer"),
    path("<int:pk>/assign/", IssueAssignView.as_view(), name="issue-assign"),
]
