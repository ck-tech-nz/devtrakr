import pytest
from django.utils import timezone
from tests.factories import UserFactory, ImprovementPlanFactory, ActionItemFactory

pytestmark = pytest.mark.django_db


class TestImprovementPlan:
    def test_create_plan(self):
        plan = ImprovementPlanFactory()
        assert plan.status == "draft"
        assert plan.period
        assert plan.user is not None

    def test_unique_user_period(self):
        plan = ImprovementPlanFactory(period="2026-04")
        with pytest.raises(Exception):
            ImprovementPlanFactory(user=plan.user, period="2026-04")

    def test_plan_str(self):
        plan = ImprovementPlanFactory()
        assert plan.user.name in str(plan)
        assert plan.period in str(plan)


class TestActionItem:
    def test_create_action_item(self):
        item = ActionItemFactory()
        assert item.status == "pending"
        assert item.points > 0
        assert item.plan is not None

    def test_earned_points_verified(self):
        item = ActionItemFactory(status="verified", points=100, quality_factor=1.2)
        assert item.earned_points == 120

    def test_earned_points_not_verified(self):
        item = ActionItemFactory(status="pending", points=100)
        assert item.earned_points == 0

    def test_status_choices(self):
        for status in ("pending", "in_progress", "submitted", "verified", "not_achieved"):
            item = ActionItemFactory(status=status)
            assert item.status == status


def test_scoring_config_has_default_review_dimensions():
    from apps.kpi.models import KPIScoringConfig
    cfg = KPIScoringConfig.get_solo()
    dims = cfg.review_dimensions
    assert isinstance(dims, list)
    assert {d["key"] for d in dims} == {"initiative", "understanding", "quality", "delivery"}
    assert all("label" in d and "weight" in d for d in dims)


def test_overall_score_weighted():
    from tests.factories import ActionItemFactory
    item = ActionItemFactory(
        review_dimensions=[{"key": "a", "label": "A", "weight": 0.75},
                           {"key": "b", "label": "B", "weight": 0.25}],
        scores={"a": 5, "b": 1},
    )
    assert item.overall_score == 4.0


def test_overall_score_equal_weight_fallback_when_no_dims():
    from tests.factories import ActionItemFactory
    item = ActionItemFactory(review_dimensions=[], scores={"x": 3, "y": 5})
    assert item.overall_score == 4.0


def test_overall_score_partial_normalizes():
    from tests.factories import ActionItemFactory
    item = ActionItemFactory(
        review_dimensions=[{"key": "a", "label": "A", "weight": 0.7},
                           {"key": "b", "label": "B", "weight": 0.3}],
        scores={"a": 5},
    )
    assert item.overall_score == 5.0


def test_overall_score_none_when_unscored():
    from tests.factories import ActionItemFactory
    item = ActionItemFactory(scores={})
    assert item.overall_score is None
