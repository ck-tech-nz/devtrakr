from django.urls import path
from .views import (
    KPITeamView, KPIUserSummaryView, KPIUserIssuesView, KPIUserCommitsView,
    KPIUserWorkloadView, KPIUserTrendsView, KPIUserSuggestionsView, KPIRefreshView,
    KPIMeSummaryView, KPIMeIssuesView, KPIMeCommitsView, KPIMeWorkloadView,
    KPIMeTrendsView, KPIMeSuggestionsView,
    KPIScoringConfigView,
)
from .plan_views import (
    PlanListView, MyPlanView, PlanDetailView, PlanEditView,
    PlanPublishView, PlanArchiveView, PlanGenerateView,
    ActionItemStatusView, ActionItemVerifyView, ActionItemCommentListView,
)

urlpatterns = [
    path("team/", KPITeamView.as_view(), name="kpi-team"),
    path("refresh/", KPIRefreshView.as_view(), name="kpi-refresh"),
    path("scoring-config/", KPIScoringConfigView.as_view(), name="kpi-scoring-config"),
    path("me/summary/", KPIMeSummaryView.as_view(), name="kpi-me-summary"),
    path("me/issues/", KPIMeIssuesView.as_view(), name="kpi-me-issues"),
    path("me/commits/", KPIMeCommitsView.as_view(), name="kpi-me-commits"),
    path("me/workload/", KPIMeWorkloadView.as_view(), name="kpi-me-workload"),
    path("me/trends/", KPIMeTrendsView.as_view(), name="kpi-me-trends"),
    path("me/suggestions/", KPIMeSuggestionsView.as_view(), name="kpi-me-suggestions"),
    path("users/<int:user_id>/summary/", KPIUserSummaryView.as_view(), name="kpi-user-summary"),
    path("users/<int:user_id>/issues/", KPIUserIssuesView.as_view(), name="kpi-user-issues"),
    path("users/<int:user_id>/commits/", KPIUserCommitsView.as_view(), name="kpi-user-commits"),
    path("users/<int:user_id>/workload/", KPIUserWorkloadView.as_view(), name="kpi-user-workload"),
    path("users/<int:user_id>/trends/", KPIUserTrendsView.as_view(), name="kpi-user-trends"),
    path("users/<int:user_id>/suggestions/", KPIUserSuggestionsView.as_view(), name="kpi-user-suggestions"),
    # 提升计划
    path("plans/", PlanListView.as_view(), name="plan-list"),
    path("plans/me/", MyPlanView.as_view(), name="plan-me"),
    path("plans/generate/", PlanGenerateView.as_view(), name="plan-generate"),
    path("plans/<uuid:pk>/", PlanDetailView.as_view(), name="plan-detail"),
    path("plans/<uuid:pk>/edit/", PlanEditView.as_view(), name="plan-edit"),
    path("plans/<uuid:pk>/publish/", PlanPublishView.as_view(), name="plan-publish"),
    path("plans/<uuid:pk>/archive/", PlanArchiveView.as_view(), name="plan-archive"),
    # 行动项
    path("action-items/<uuid:pk>/status/", ActionItemStatusView.as_view(), name="action-item-status"),
    path("action-items/<uuid:pk>/verify/", ActionItemVerifyView.as_view(), name="action-item-verify"),
    path("action-items/<uuid:pk>/comments/", ActionItemCommentListView.as_view(), name="action-item-comments"),
]
