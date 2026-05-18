import pytest
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from tests.factories import UptimeMonitorFactory, UptimeCheckFactory
from apps.uptime.services import decide_transition, TransitionAction
from apps.uptime.services import fire_failure
from apps.issues.models import Issue
from apps.notifications.models import Notification, NotificationRecipient
from apps.projects.models import ProjectMember
from tests.factories import ProjectFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestDecideTransition:
    def test_up_to_up_no_action(self):
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=0)
        action = decide_transition(monitor, is_up=True)
        assert action == TransitionAction.NONE

    def test_unknown_to_up_no_action(self):
        monitor = UptimeMonitorFactory(last_status="unknown", consecutive_failures=0)
        action = decide_transition(monitor, is_up=True)
        assert action == TransitionAction.NONE

    def test_up_to_down_first_failure_no_action(self):
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=0)
        action = decide_transition(monitor, is_up=False)
        assert action == TransitionAction.NONE

    def test_up_to_down_second_failure_no_action(self):
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=1)
        action = decide_transition(monitor, is_up=False)
        assert action == TransitionAction.NONE

    def test_up_to_down_third_failure_fires_failure(self):
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=2)
        action = decide_transition(monitor, is_up=False)
        assert action == TransitionAction.FIRE_FAILURE

    def test_down_to_down_no_action(self):
        monitor = UptimeMonitorFactory(last_status="down", consecutive_failures=10)
        action = decide_transition(monitor, is_up=False)
        assert action == TransitionAction.NONE

    def test_down_to_up_fires_recovery(self):
        monitor = UptimeMonitorFactory(last_status="down", consecutive_failures=5)
        action = decide_transition(monitor, is_up=True)
        assert action == TransitionAction.FIRE_RECOVERY


class TestFireFailure:
    def _setup(self):
        bot = UserFactory(username="bot")
        project = ProjectFactory()
        member = UserFactory()
        ProjectMember.objects.create(project=project, user=member, role="开发者")
        monitor = UptimeMonitorFactory(
            project=project, name="api-prod",
            url="https://api.example.com/health",
            last_status="up", consecutive_failures=2,
        )
        return bot, project, member, monitor

    def test_creates_issue_in_project(self, site_settings):
        bot, project, member, monitor = self._setup()
        fire_failure(monitor, latest_error="timeout")
        issue = Issue.objects.get(project=project)
        assert "api-prod" in issue.title
        assert "不可达" in issue.title
        assert issue.priority == "P1"
        assert issue.status == "待处理"
        assert issue.created_by == bot
        assert "timeout" in issue.description

    def test_sets_active_incident_issue(self, site_settings):
        bot, project, member, monitor = self._setup()
        fire_failure(monitor, latest_error="timeout")
        monitor.refresh_from_db()
        assert monitor.active_incident_issue is not None
        assert monitor.last_status == "down"
        assert monitor.outage_started_at is not None

    def test_sends_notifications_to_project_members(self, site_settings):
        bot, project, member, monitor = self._setup()
        fire_failure(monitor, latest_error="timeout")
        notification = Notification.objects.get()
        assert "api-prod" in notification.title
        recipients = list(notification.recipients.values_list("user_id", flat=True))
        assert member.id in recipients

    def test_no_bot_user_raises(self, site_settings):
        project = ProjectFactory()
        monitor = UptimeMonitorFactory(
            project=project, last_status="up", consecutive_failures=2,
        )
        with pytest.raises(Exception):
            fire_failure(monitor, latest_error="timeout")


from apps.uptime.services import fire_recovery
from apps.issues.models import Activity


class TestFireRecovery:
    def _setup_in_outage(self):
        bot = UserFactory(username="bot")
        project = ProjectFactory()
        member = UserFactory()
        ProjectMember.objects.create(project=project, user=member, role="开发者")
        existing_issue = Issue.objects.create(
            project=project, title="[监控告警] api-prod 不可达",
            description="...", priority="P1", status="待处理",
            created_by=bot, reporter="",
        )
        monitor = UptimeMonitorFactory(
            project=project, name="api-prod",
            last_status="down", consecutive_failures=5,
            outage_started_at=timezone.now() - timedelta(minutes=15),
            active_incident_issue=existing_issue,
        )
        return bot, project, member, monitor, existing_issue

    def test_closes_issue_with_resolved_status(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        fire_recovery(monitor)
        issue.refresh_from_db()
        assert issue.status == "已解决"
        assert issue.resolved_at is not None

    def test_adds_activity_comment_with_duration(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        fire_recovery(monitor)
        activity = Activity.objects.get(issue=issue, action="resolved", user=bot)
        assert "恢复" in activity.detail
        assert "15" in activity.detail  # 15 minute outage

    def test_clears_monitor_outage_state(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        fire_recovery(monitor)
        monitor.refresh_from_db()
        assert monitor.active_incident_issue is None
        assert monitor.outage_started_at is None
        assert monitor.last_status == "up"
        assert monitor.last_up_at is not None
        assert monitor.consecutive_failures == 0

    def test_sends_recovery_notification(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        fire_recovery(monitor)
        notification = Notification.objects.get()
        assert "恢复" in notification.title
        recipients = list(notification.recipients.values_list("user_id", flat=True))
        assert member.id in recipients

    def test_active_issue_already_closed_still_sends_notification(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        issue.status = "已关闭"
        issue.save()
        fire_recovery(monitor)
        notification = Notification.objects.get()
        assert "恢复" in notification.title
        monitor.refresh_from_db()
        assert monitor.active_incident_issue is None
        assert monitor.last_status == "up"

    def test_no_active_issue_still_clears_state(self, site_settings):
        bot = UserFactory(username="bot")
        project = ProjectFactory()
        monitor = UptimeMonitorFactory(
            project=project, last_status="down", consecutive_failures=3,
            outage_started_at=timezone.now() - timedelta(minutes=5),
            active_incident_issue=None,
        )
        fire_recovery(monitor)
        monitor.refresh_from_db()
        assert monitor.last_status == "up"
        assert monitor.last_up_at is not None
        assert monitor.outage_started_at is None
