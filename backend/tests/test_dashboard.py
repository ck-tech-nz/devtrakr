import pytest
from datetime import timedelta
from django.utils import timezone
from tests.factories import UserFactory, IssueFactory, ActivityFactory, SiteSettingsFactory

pytestmark = pytest.mark.django_db


class TestDashboardStats:
    def test_stats(self, auth_client, site_settings):
        IssueFactory(status="待分配")
        IssueFactory(status="待分配")
        IssueFactory(status="进行中")
        IssueFactory(status="已解决", resolved_at=timezone.now())
        response = auth_client.get("/api/dashboard/stats/")
        assert response.status_code == 200
        assert response.data["total"] == 4
        assert response.data["pending"] == 2
        assert response.data["in_progress"] == 1
        assert response.data["resolved_this_week"] >= 1


class TestDashboardTrends:
    def test_trends_returns_30_days(self, auth_client, site_settings):
        IssueFactory()
        response = auth_client.get("/api/dashboard/trends/")
        assert response.status_code == 200
        assert len(response.data) == 30

    def test_trends_shape(self, auth_client, site_settings):
        IssueFactory()
        response = auth_client.get("/api/dashboard/trends/")
        entry = response.data[0]
        assert "date" in entry
        assert "created" in entry
        assert "resolved" in entry


class TestDashboardPriorityDistribution:
    def test_priority_distribution(self, auth_client, site_settings):
        IssueFactory(priority="P0")
        IssueFactory(priority="P0")
        IssueFactory(priority="P1")
        response = auth_client.get("/api/dashboard/priority-distribution/")
        assert response.status_code == 200
        p0 = next(d for d in response.data if d["priority"] == "P0")
        assert p0["count"] == 2


class TestDashboardLeaderboard:
    def test_leaderboard(self, auth_client, site_settings):
        user = UserFactory(name="高手")
        for _ in range(5):
            IssueFactory(assignee=user, status="已解决", resolved_at=timezone.now())
        response = auth_client.get("/api/dashboard/developer-leaderboard/")
        assert response.status_code == 200
        assert len(response.data) <= 5
        assert response.data[0]["user_name"] == "高手"
        assert response.data[0]["monthly_resolved_count"] == 5


class TestDashboardRecentActivity:
    def test_recent_activity(self, auth_client, site_settings):
        ActivityFactory.create_batch(5)
        response = auth_client.get("/api/dashboard/recent-activity/")
        assert response.status_code == 200
        assert len(response.data) == 5

    def test_recent_activity_max_20(self, auth_client, site_settings):
        ActivityFactory.create_batch(25)
        response = auth_client.get("/api/dashboard/recent-activity/")
        assert len(response.data) == 20

    def test_recent_activity_shape(self, auth_client, site_settings):
        ActivityFactory()
        response = auth_client.get("/api/dashboard/recent-activity/")
        entry = response.data[0]
        assert "user_name" in entry
        assert "action" in entry
        assert "issue_title" in entry
        assert "issue_id" in entry
