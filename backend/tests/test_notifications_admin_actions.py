"""Tests for the Notification admin's publish-to-test/prod detail actions."""
from unittest.mock import patch

import pytest
from django.contrib import admin as django_admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory

from apps.notifications.models import Notification
from apps.notifications.services import RemotePublishError
from tests.factories import NotificationFactory, UserFactory


def _admin_request(method="post", path="/admin/", user=None):
    factory = RequestFactory()
    request = getattr(factory, method)(path)
    request.user = user or UserFactory(is_staff=True, is_superuser=True)
    setattr(request, "session", {})
    setattr(request, "_messages", FallbackStorage(request))
    return request


@pytest.fixture
def admin_instance():
    from apps.notifications.admin import NotificationAdmin
    return NotificationAdmin(Notification, django_admin.site)


@pytest.mark.django_db
class TestNotificationAdminPublishActions:
    def test_actions_detail_lists_both_buttons(self, admin_instance):
        assert "publish_to_test" in admin_instance.actions_detail
        assert "publish_to_prod" in admin_instance.actions_detail

    def test_publish_to_test_calls_service_with_test_env(self, admin_instance):
        notif = NotificationFactory()
        request = _admin_request()

        with patch("apps.notifications.admin.publish_notification_to_remote") as mock_pub:
            mock_pub.return_value = {"id": "remote-id", "recipients": 7}
            admin_instance.publish_to_test(request, str(notif.pk))

        mock_pub.assert_called_once()
        called_notif, kwargs = mock_pub.call_args.args[0], mock_pub.call_args.kwargs
        assert called_notif.pk == notif.pk
        assert kwargs == {"env": "test"}

    def test_publish_to_prod_calls_service_with_prod_env(self, admin_instance):
        notif = NotificationFactory()
        request = _admin_request()

        with patch("apps.notifications.admin.publish_notification_to_remote") as mock_pub:
            mock_pub.return_value = {"id": "remote-id", "recipients": 7}
            admin_instance.publish_to_prod(request, str(notif.pk))

        mock_pub.assert_called_once()
        called_notif, kwargs = mock_pub.call_args.args[0], mock_pub.call_args.kwargs
        assert called_notif.pk == notif.pk
        assert kwargs == {"env": "prod"}

    def test_success_shows_success_message(self, admin_instance):
        notif = NotificationFactory()
        request = _admin_request()

        with patch("apps.notifications.admin.publish_notification_to_remote") as mock_pub:
            mock_pub.return_value = {"id": "remote", "recipients": 12}
            admin_instance.publish_to_test(request, str(notif.pk))

        messages = list(request._messages)
        assert len(messages) == 1
        assert messages[0].level_tag == "success"
        assert "12" in messages[0].message  # recipient count surfaced

    def test_improperly_configured_shows_error_message(self, admin_instance):
        notif = NotificationFactory()
        request = _admin_request()

        with patch("apps.notifications.admin.publish_notification_to_remote") as mock_pub:
            mock_pub.side_effect = ImproperlyConfigured("DEVTRAKR_TEST_KEY is not set")
            admin_instance.publish_to_test(request, str(notif.pk))

        messages = list(request._messages)
        assert len(messages) == 1
        assert messages[0].level_tag == "error"
        assert "DEVTRAKR_TEST_KEY" in messages[0].message

    def test_remote_failure_shows_error_message(self, admin_instance):
        notif = NotificationFactory()
        request = _admin_request()

        with patch("apps.notifications.admin.publish_notification_to_remote") as mock_pub:
            mock_pub.side_effect = RemotePublishError("remote returned 401")
            admin_instance.publish_to_prod(request, str(notif.pk))

        messages = list(request._messages)
        assert len(messages) == 1
        assert messages[0].level_tag == "error"
        assert "401" in messages[0].message

    def test_returns_redirect_to_change_view(self, admin_instance):
        from django.http import HttpResponseRedirect

        notif = NotificationFactory()
        request = _admin_request()

        with patch("apps.notifications.admin.publish_notification_to_remote") as mock_pub:
            mock_pub.return_value = {"id": "x", "recipients": 1}
            resp = admin_instance.publish_to_test(request, str(notif.pk))

        assert isinstance(resp, HttpResponseRedirect)
        assert str(notif.pk) in resp.url


@pytest.mark.django_db
class TestPublishDraftAction:
    def test_action_registered_in_actions_detail(self, admin_instance):
        assert "publish_draft" in admin_instance.actions_detail

    def test_publish_draft_flips_is_draft_and_generates_recipients(self, admin_instance):
        UserFactory()
        UserFactory()
        notif = NotificationFactory(target_type="all", is_draft=True)
        request = _admin_request()

        admin_instance.publish_draft(request, str(notif.pk))

        notif.refresh_from_db()
        assert notif.is_draft is False
        assert notif.recipients.count() >= 2

    def test_publish_draft_success_message_includes_count(self, admin_instance):
        UserFactory()
        notif = NotificationFactory(target_type="all", is_draft=True)
        request = _admin_request()

        admin_instance.publish_draft(request, str(notif.pk))

        msgs = list(request._messages)
        assert any(m.level_tag == "success" for m in msgs)

    def test_publish_draft_on_non_draft_warns(self, admin_instance):
        notif = NotificationFactory(target_type="all", is_draft=False)
        request = _admin_request()
        before_count = notif.recipients.count()

        admin_instance.publish_draft(request, str(notif.pk))

        notif.refresh_from_db()
        msgs = list(request._messages)
        assert any(m.level_tag == "warning" for m in msgs)
        assert notif.recipients.count() == before_count


@pytest.mark.django_db
class TestSaveModelDraftTransition:
    """save_model + save_related should auto-generate recipients on draft→published."""

    def _save_via_admin(self, admin_instance, notif, request, was_draft, now_draft, change=True):
        """Simulate Django admin's save_model + save_related lifecycle."""
        notif.is_draft = now_draft
        admin_instance.save_model(request, notif, form=None, change=change)
        from unittest.mock import MagicMock
        form = MagicMock()
        form.instance = notif
        admin_instance.save_related(request, form, formsets=[], change=change)

    def test_create_as_non_draft_generates_recipients(self, admin_instance):
        UserFactory()
        UserFactory()
        from apps.notifications.models import Notification
        request = _admin_request()
        notif = Notification(
            notification_type="broadcast",
            title="t", content="c", target_type="all", is_draft=False,
        )
        self._save_via_admin(admin_instance, notif, request, was_draft=None, now_draft=False, change=False)
        assert notif.recipients.count() >= 2

    def test_create_as_draft_does_not_generate(self, admin_instance):
        UserFactory()
        from apps.notifications.models import Notification
        request = _admin_request()
        notif = Notification(
            notification_type="broadcast",
            title="t", content="c", target_type="all", is_draft=True,
        )
        self._save_via_admin(admin_instance, notif, request, was_draft=None, now_draft=True, change=False)
        assert notif.recipients.count() == 0

    def test_edit_draft_to_published_generates_recipients(self, admin_instance):
        UserFactory()
        UserFactory()
        notif = NotificationFactory(target_type="all", is_draft=True)
        assert notif.recipients.count() == 0
        request = _admin_request()

        self._save_via_admin(admin_instance, notif, request, was_draft=True, now_draft=False, change=True)

        assert notif.recipients.count() >= 2

    def test_edit_published_stays_published_does_not_regenerate(self, admin_instance):
        UserFactory()
        notif = NotificationFactory(target_type="all", is_draft=False)
        # Pre-seed a recipient row
        from apps.notifications.models import NotificationRecipient
        from tests.factories import UserFactory as UF
        NotificationRecipient.objects.create(notification=notif, user=UF())
        existing = notif.recipients.count()
        request = _admin_request()

        self._save_via_admin(admin_instance, notif, request, was_draft=False, now_draft=False, change=True)

        # No duplicate rows created (bulk_create uses ignore_conflicts but also "publish_now" should be False)
        assert notif.recipients.count() == existing
