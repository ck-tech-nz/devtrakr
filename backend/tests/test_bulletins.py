import pytest
from datetime import timedelta
from django.utils import timezone
from apps.notifications.models import Bulletin

pytestmark = pytest.mark.django_db


class TestBulletinQuerySet:
    def test_currently_active_filters_inactive_and_out_of_window(self):
        now = timezone.now()
        active = Bulletin.objects.create(category="quote", content="active now")
        inactive = Bulletin.objects.create(category="quote", content="inactive", is_active=False)
        future = Bulletin.objects.create(
            category="announcement", content="future",
            starts_at=now + timedelta(days=1),
        )
        expired = Bulletin.objects.create(
            category="announcement", content="expired",
            ends_at=now - timedelta(days=1),
        )
        within = Bulletin.objects.create(
            category="value", content="within window",
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1),
        )

        result = list(Bulletin.objects.currently_active())

        # NOTE: the test DB also contains the 5 seeded bulletins (migration 0004,
        # added in a later task), so assert membership, not absolute counts.
        assert active in result
        assert within in result
        assert inactive not in result
        assert future not in result
        assert expired not in result

    def test_ordering_by_sort_order(self):
        # Use high sort_order values so these sit after any seeded rows, then
        # assert relative order rather than absolute positions.
        b_later = Bulletin.objects.create(category="quote", content="later", sort_order=102)
        b_earlier = Bulletin.objects.create(category="quote", content="earlier", sort_order=101)
        result = list(Bulletin.objects.currently_active())
        assert result.index(b_earlier) < result.index(b_later)


from tests.factories import BulletinFactory


class TestBulletinActiveEndpoint:
    URL = "/api/notifications/bulletins/active/"

    def test_returns_only_active_to_regular_user(self, regular_client):
        BulletinFactory(content="shown", is_active=True)
        BulletinFactory(content="hidden", is_active=False)
        res = regular_client.get(self.URL)
        assert res.status_code == 200
        contents = [b["content"] for b in res.data]
        assert "shown" in contents
        assert "hidden" not in contents

    def test_response_shape_is_lean(self, regular_client):
        BulletinFactory(content="shape-probe", category="quote", source="Linus")
        res = regular_client.get(self.URL)
        assert res.status_code == 200
        item = next(b for b in res.data if b["content"] == "shape-probe")
        assert set(item.keys()) == {"id", "category", "content", "source", "link_url"}

    def test_requires_authentication(self, api_client):
        res = api_client.get(self.URL)
        assert res.status_code in (401, 403)
