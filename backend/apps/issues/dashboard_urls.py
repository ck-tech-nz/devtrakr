from django.urls import path
from .views import (
    DashboardStatsView,
    DashboardTrendsView,
    DashboardPriorityDistributionView,
    DashboardLeaderboardView,
    DashboardRecentActivityView,
    GatewayStatusView,
)

urlpatterns = [
    path("stats/", DashboardStatsView.as_view(), name="dashboard-stats"),
    path("trends/", DashboardTrendsView.as_view(), name="dashboard-trends"),
    path("priority-distribution/", DashboardPriorityDistributionView.as_view(), name="dashboard-priority"),
    path("developer-leaderboard/", DashboardLeaderboardView.as_view(), name="dashboard-leaderboard"),
    path("recent-activity/", DashboardRecentActivityView.as_view(), name="dashboard-activity"),
    path("gateway-status/", GatewayStatusView.as_view(), name="dashboard-gateway-status"),
]
