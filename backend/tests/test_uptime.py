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


from unittest.mock import patch, MagicMock
import requests as req_lib
from apps.uptime.http_check import perform_check


def _mock_response(status_code: int, text: str = "OK"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestPerformCheck:
    def test_200_with_default_expected(self):
        monitor = UptimeMonitorFactory(expected_status="200")
        with patch("apps.uptime.http_check.requests.get", return_value=_mock_response(200)):
            result = perform_check(monitor)
        assert result.is_up is True
        assert result.status_code == 200
        assert result.error == ""

    def test_204_when_expected_200(self):
        monitor = UptimeMonitorFactory(expected_status="200")
        with patch("apps.uptime.http_check.requests.get", return_value=_mock_response(204)):
            result = perform_check(monitor)
        assert result.is_up is False
        assert result.status_code == 204
        assert "status 204" in result.error

    def test_204_when_expected_200_or_204(self):
        monitor = UptimeMonitorFactory(expected_status="200,204")
        with patch("apps.uptime.http_check.requests.get", return_value=_mock_response(204)):
            result = perform_check(monitor)
        assert result.is_up is True

    def test_body_match_passes(self):
        monitor = UptimeMonitorFactory(expected_status="200", expected_body="healthy")
        with patch("apps.uptime.http_check.requests.get",
                   return_value=_mock_response(200, '{"status":"healthy"}')):
            result = perform_check(monitor)
        assert result.is_up is True

    def test_body_match_fails(self):
        monitor = UptimeMonitorFactory(expected_status="200", expected_body="healthy")
        with patch("apps.uptime.http_check.requests.get",
                   return_value=_mock_response(200, '{"status":"degraded"}')):
            result = perform_check(monitor)
        assert result.is_up is False
        assert "body mismatch" in result.error

    def test_timeout(self):
        monitor = UptimeMonitorFactory()
        with patch("apps.uptime.http_check.requests.get",
                   side_effect=req_lib.exceptions.Timeout()):
            result = perform_check(monitor)
        assert result.is_up is False
        assert result.status_code is None
        assert result.error == "timeout"

    def test_connection_error(self):
        monitor = UptimeMonitorFactory()
        with patch("apps.uptime.http_check.requests.get",
                   side_effect=req_lib.exceptions.ConnectionError()):
            result = perform_check(monitor)
        assert result.is_up is False
        assert result.status_code is None
        assert "connection" in result.error.lower()

    def test_response_time_captured(self):
        monitor = UptimeMonitorFactory()
        with patch("apps.uptime.http_check.requests.get", return_value=_mock_response(200)):
            result = perform_check(monitor)
        assert result.response_ms is not None
        assert result.response_ms >= 0


from apps.uptime.tasks import check_monitor
from apps.uptime.http_check import CheckResult
from apps.uptime.models import UptimeMonitor, UptimeCheck


class TestCheckMonitorTask:
    def test_writes_check_record(self, site_settings):
        UserFactory(username="bot")
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=0)
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=True, status_code=200, response_ms=80, error="")):
            check_monitor(monitor.pk)
        assert UptimeCheck.objects.filter(monitor=monitor).count() == 1
        check = UptimeCheck.objects.get(monitor=monitor)
        assert check.is_up is True
        assert check.status_code == 200
        assert check.response_ms == 80

    def test_advances_next_check_at(self, site_settings):
        UserFactory(username="bot")
        monitor = UptimeMonitorFactory(interval_minutes=5, next_check_at=None)
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=True, status_code=200, response_ms=50, error="")):
            check_monitor(monitor.pk)
        monitor.refresh_from_db()
        assert monitor.next_check_at is not None
        delta = monitor.next_check_at - timezone.now()
        assert timedelta(minutes=4, seconds=50) < delta < timedelta(minutes=5, seconds=10)

    def test_third_consecutive_failure_fires_failure(self, site_settings):
        UserFactory(username="bot")
        project = ProjectFactory()
        monitor = UptimeMonitorFactory(
            project=project, last_status="up", consecutive_failures=2,
        )
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=False, status_code=500, response_ms=10, error="status 500")):
            check_monitor(monitor.pk)
        monitor.refresh_from_db()
        assert monitor.last_status == "down"
        assert monitor.active_incident_issue is not None
        assert monitor.consecutive_failures == 3

    def test_recovery_from_down_to_up(self, site_settings):
        bot = UserFactory(username="bot")
        project = ProjectFactory()
        issue = Issue.objects.create(
            project=project, title="x", description="x", priority="P1",
            status="待处理", created_by=bot, reporter="",
        )
        monitor = UptimeMonitorFactory(
            project=project, last_status="down", consecutive_failures=5,
            outage_started_at=timezone.now() - timedelta(minutes=10),
            active_incident_issue=issue,
        )
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=True, status_code=200, response_ms=70, error="")):
            check_monitor(monitor.pk)
        monitor.refresh_from_db()
        assert monitor.last_status == "up"
        assert monitor.consecutive_failures == 0
        assert monitor.active_incident_issue is None

    def test_disabled_monitor_skipped_silently(self, site_settings):
        monitor = UptimeMonitorFactory(is_enabled=False)
        with patch("apps.uptime.tasks.perform_check") as mocked:
            check_monitor(monitor.pk)
        mocked.assert_not_called()
        assert UptimeCheck.objects.filter(monitor=monitor).count() == 0

    def test_first_failure_does_not_fire(self, site_settings):
        UserFactory(username="bot")
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=0)
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=False, status_code=500, response_ms=10, error="status 500")):
            check_monitor(monitor.pk)
        monitor.refresh_from_db()
        assert monitor.consecutive_failures == 1
        assert monitor.last_status == "up"
        assert monitor.active_incident_issue is None


from apps.uptime.serializers import UptimeMonitorSerializer


class TestUptimeMonitorSerializer:
    def _factory_data(self, **overrides):
        data = {
            "name": "test-monitor",
            "url": "https://example.com/health",
            "method": "GET",
            "expected_status": "200",
            "expected_body": "",
            "interval_minutes": 5,
            "timeout_secs": 20,
            "is_enabled": True,
        }
        data.update(overrides)
        return data

    def test_valid_data(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data())
        assert serializer.is_valid(), serializer.errors

    def test_url_must_have_protocol(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(url="example.com"))
        assert not serializer.is_valid()
        assert "url" in serializer.errors

    def test_method_post_rejected_in_v1(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(method="POST"))
        assert not serializer.is_valid()
        assert "method" in serializer.errors

    def test_expected_status_must_be_digits(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(expected_status="2xx"))
        assert not serializer.is_valid()
        assert "expected_status" in serializer.errors

    def test_expected_status_comma_separated_ok(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(expected_status="200,204"))
        assert serializer.is_valid(), serializer.errors

    def test_interval_min_1(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(interval_minutes=0))
        assert not serializer.is_valid()

    def test_interval_max_1440(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(interval_minutes=1441))
        assert not serializer.is_valid()

    def test_timeout_min_1(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(timeout_secs=0))
        assert not serializer.is_valid()

    def test_timeout_max_60(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(timeout_secs=61))
        assert not serializer.is_valid()

    def test_serialized_fields_include_read_only(self):
        monitor = UptimeMonitorFactory(
            last_status="up", last_check_at=timezone.now(), last_up_at=timezone.now(),
        )
        data = UptimeMonitorSerializer(monitor).data
        assert "last_status" in data
        assert "last_check_at" in data
        assert "last_up_at" in data
        assert "outage_started_at" in data
        assert "active_incident_issue_id" in data


from apps.uptime.tasks import tick_uptime_monitors, prune_old_checks


class TestTickTask:
    def test_dispatches_due_monitors(self, site_settings):
        now = timezone.now()
        due_no_schedule = UptimeMonitorFactory(next_check_at=None)
        due_overdue = UptimeMonitorFactory(next_check_at=now - timedelta(minutes=1))
        not_due = UptimeMonitorFactory(next_check_at=now + timedelta(minutes=5))
        disabled = UptimeMonitorFactory(is_enabled=False, next_check_at=None)

        with patch("apps.uptime.tasks.check_monitor.delay") as mocked:
            tick_uptime_monitors()

        called_ids = sorted([c.args[0] for c in mocked.call_args_list])
        assert called_ids == sorted([due_no_schedule.pk, due_overdue.pk])

    def test_no_due_monitors_dispatches_nothing(self, site_settings):
        UptimeMonitorFactory(next_check_at=timezone.now() + timedelta(minutes=10))
        with patch("apps.uptime.tasks.check_monitor.delay") as mocked:
            tick_uptime_monitors()
        mocked.assert_not_called()


class TestPruneTask:
    def test_deletes_old_checks(self, site_settings):
        monitor = UptimeMonitorFactory()
        cutoff = timezone.now() - timedelta(days=30)
        old = UptimeCheckFactory(monitor=monitor, checked_at=cutoff - timedelta(hours=1))
        recent = UptimeCheckFactory(monitor=monitor, checked_at=cutoff + timedelta(hours=1))

        prune_old_checks()

        assert not UptimeCheck.objects.filter(pk=old.pk).exists()
        assert UptimeCheck.objects.filter(pk=recent.pk).exists()


class TestUptimeMonitorDetailAPI:
    def test_retrieve_authenticated(self, regular_client):
        monitor = UptimeMonitorFactory()
        response = regular_client.get(f"/api/uptime/monitors/{monitor.pk}/")
        assert response.status_code == 200
        assert response.data["name"] == monitor.name

    def test_retrieve_unauthenticated_forbidden(self, api_client):
        monitor = UptimeMonitorFactory()
        response = api_client.get(f"/api/uptime/monitors/{monitor.pk}/")
        assert response.status_code in (401, 403)

    def test_update_non_superuser_forbidden(self, regular_client):
        monitor = UptimeMonitorFactory()
        response = regular_client.patch(f"/api/uptime/monitors/{monitor.pk}/", {"name": "x"})
        assert response.status_code == 403

    def test_update_superuser_ok(self, superuser_client):
        monitor = UptimeMonitorFactory()
        response = superuser_client.patch(
            f"/api/uptime/monitors/{monitor.pk}/", {"name": "renamed"}, format="json",
        )
        assert response.status_code == 200
        monitor.refresh_from_db()
        assert monitor.name == "renamed"

    def test_delete_non_superuser_forbidden(self, regular_client):
        monitor = UptimeMonitorFactory()
        response = regular_client.delete(f"/api/uptime/monitors/{monitor.pk}/")
        assert response.status_code == 403

    def test_delete_superuser_ok(self, superuser_client):
        monitor = UptimeMonitorFactory()
        response = superuser_client.delete(f"/api/uptime/monitors/{monitor.pk}/")
        assert response.status_code == 204
        assert not UptimeMonitor.objects.filter(pk=monitor.pk).exists()


class TestUptimeChecksAPI:
    def test_returns_recent_checks_newest_first(self, regular_client):
        monitor = UptimeMonitorFactory()
        now = timezone.now()
        UptimeCheckFactory(monitor=monitor, checked_at=now - timedelta(minutes=2), is_up=True)
        UptimeCheckFactory(monitor=monitor, checked_at=now - timedelta(minutes=1), is_up=False)
        UptimeCheckFactory(monitor=monitor, checked_at=now, is_up=True)

        response = regular_client.get(f"/api/uptime/monitors/{monitor.pk}/checks/")
        assert response.status_code == 200
        results = response.data
        assert len(results) == 3
        assert results[0]["is_up"] is True  # newest

    def test_limit_param(self, regular_client):
        monitor = UptimeMonitorFactory()
        for i in range(10):
            UptimeCheckFactory(monitor=monitor, checked_at=timezone.now() - timedelta(minutes=i))
        response = regular_client.get(f"/api/uptime/monitors/{monitor.pk}/checks/?limit=5")
        assert len(response.data) == 5
