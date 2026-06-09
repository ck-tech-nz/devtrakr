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
