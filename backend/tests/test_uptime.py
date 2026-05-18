import pytest
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from tests.factories import UptimeMonitorFactory, UptimeCheckFactory
from apps.uptime.services import decide_transition, TransitionAction

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
