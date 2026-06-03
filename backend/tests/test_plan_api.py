from unittest.mock import patch

import pytest
from django.utils import timezone
from tests.factories import (
    UserFactory, ImprovementPlanFactory, ActionItemFactory,
    ActionItemCommentFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager_client(api_client):
    from django.contrib.auth.models import Group, Permission
    user = UserFactory()
    group, _ = Group.objects.get_or_create(name="管理员")
    group.permissions.set(
        Permission.objects.filter(content_type__app_label__in=["kpi", "ai"])
    )
    user.groups.add(group)
    api_client.force_authenticate(user=user)
    return api_client, user


@pytest.fixture
def employee_client(api_client):
    from django.contrib.auth.models import Group, Permission
    user = UserFactory()
    group, _ = Group.objects.get_or_create(name="开发者")
    group.permissions.set(
        Permission.objects.filter(codename__in=["view_own_plan", "view_own_kpi"])
    )
    user.groups.add(group)
    api_client.force_authenticate(user=user)
    return api_client, user


class TestPlanListAPI:
    def test_manager_sees_all_plans(self, manager_client):
        client, _ = manager_client
        ImprovementPlanFactory(period="2026-04")
        ImprovementPlanFactory(period="2026-04")
        resp = client.get("/api/kpi/plans/?period=2026-04")
        assert resp.status_code == 200
        assert len(resp.data) == 2

    def test_employee_cannot_list_all(self, employee_client):
        client, _ = employee_client
        resp = client.get("/api/kpi/plans/")
        assert resp.status_code == 403


class TestMyPlanAPI:
    def test_employee_sees_own_published_plan(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published", period=timezone.now().strftime("%Y-%m"))
        ActionItemFactory(plan=plan, title="提高效率")
        resp = client.get("/api/kpi/plans/me/")
        assert resp.status_code == 200
        assert resp.data["current"] is not None
        assert resp.data["current"]["period"] == timezone.now().strftime("%Y-%m")

    def test_employee_cannot_see_draft(self, employee_client):
        client, user = employee_client
        ImprovementPlanFactory(user=user, status="draft", period=timezone.now().strftime("%Y-%m"))
        resp = client.get("/api/kpi/plans/me/")
        assert resp.data["current"] is None


class TestPlanDetailAPI:
    def test_manager_sees_plan_detail(self, manager_client):
        client, _ = manager_client
        plan = ImprovementPlanFactory()
        ActionItemFactory(plan=plan)
        resp = client.get(f"/api/kpi/plans/{plan.id}/")
        assert resp.status_code == 200
        assert len(resp.data["action_items"]) == 1


class TestPlanPublishAPI:
    def test_publish_plan(self, manager_client):
        client, manager = manager_client
        plan = ImprovementPlanFactory(status="draft")
        resp = client.post(f"/api/kpi/plans/{plan.id}/publish/")
        assert resp.status_code == 200
        plan.refresh_from_db()
        assert plan.status == "published"
        assert plan.reviewed_by == manager
        assert plan.published_at is not None


class TestPlanArchiveAPI:
    def test_archive_plan(self, manager_client):
        client, _ = manager_client
        plan = ImprovementPlanFactory(status="published")
        resp = client.post(f"/api/kpi/plans/{plan.id}/archive/")
        assert resp.status_code == 200
        plan.refresh_from_db()
        assert plan.status == "archived"


class TestActionItemStatusAPI:
    def test_employee_updates_own_item_status(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan, status="pending")
        resp = client.post(
            f"/api/kpi/action-items/{item.id}/status/",
            {"status": "in_progress", "start_plan": "先排查日志再改", "self_eta": "2026-06-20"},
            format="json",
        )
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.status == "in_progress"
        assert item.start_plan == "先排查日志再改"
        assert str(item.self_eta) == "2026-06-20"

    def test_start_requires_plan_and_eta(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan, status="pending")
        # 缺执行计划
        r1 = client.post(f"/api/kpi/action-items/{item.id}/status/",
                         {"status": "in_progress", "self_eta": "2026-06-20"}, format="json")
        assert r1.status_code == 400
        # 缺预计完成日期
        r2 = client.post(f"/api/kpi/action-items/{item.id}/status/",
                         {"status": "in_progress", "start_plan": "我的计划"}, format="json")
        assert r2.status_code == 400

    def test_employee_cannot_verify(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan, status="submitted")
        resp = client.post(
            f"/api/kpi/action-items/{item.id}/status/",
            {"status": "verified"}, format="json"
        )
        assert resp.status_code == 400


class TestActionItemVerifyAPI:
    def _submitted_item(self):
        dims = [{"key": "quality", "label": "完成质量", "weight": 1.0}]
        return ActionItemFactory(status="submitted", review_dimensions=dims)

    def test_manager_verifies_with_scores(self, manager_client):
        client, manager = manager_client
        item = self._submitted_item()
        resp = client.post(f"/api/kpi/action-items/{item.id}/verify/", {
            "status": "verified", "scores": {"quality": 4},
            "review_comment": "完成质量不错，但主动性欠缺",
        }, format="json")
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.status == "verified"
        assert item.scores == {"quality": 4}
        assert item.reviewed_by == manager
        assert item.review_comment

    def test_verify_requires_comment(self, manager_client):
        client, _ = manager_client
        item = self._submitted_item()
        resp = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                           {"status": "verified", "scores": {"quality": 4}}, format="json")
        assert resp.status_code == 400

    def test_verify_rejects_unknown_dimension(self, manager_client):
        client, _ = manager_client
        item = self._submitted_item()
        resp = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                           {"status": "verified", "scores": {"speed": 4}, "review_comment": "x"}, format="json")
        assert resp.status_code == 400

    def test_not_achieved(self, manager_client):
        client, _ = manager_client
        item = ActionItemFactory(status="submitted")
        resp = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                           {"status": "not_achieved", "review_comment": "目标没完成",
                            "not_achieved_reason": "effort"}, format="json")
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.status == "not_achieved"
        assert item.not_achieved_reason == "effort"

    def test_not_achieved_requires_reason_and_attribution(self, manager_client):
        client, _ = manager_client
        item = ActionItemFactory(status="submitted")
        # 缺原因
        r1 = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                         {"status": "not_achieved", "not_achieved_reason": "effort"}, format="json")
        assert r1.status_code == 400
        # 缺归因
        r2 = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                         {"status": "not_achieved", "review_comment": "x"}, format="json")
        assert r2.status_code == 400
        # 非法归因
        r3 = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                         {"status": "not_achieved", "review_comment": "x",
                          "not_achieved_reason": "nope"}, format="json")
        assert r3.status_code == 400

    def test_not_achieved_carry_over_clones_to_next_month(self, manager_client):
        from apps.kpi.models import ImprovementPlan
        client, _ = manager_client
        plan = ImprovementPlanFactory(period="2026-06", status="published")
        item = ActionItemFactory(plan=plan, status="submitted", title="顺延任务")
        resp = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                           {"status": "not_achieved", "review_comment": "下月再做",
                            "not_achieved_reason": "blocked", "next_action": "carry_over"}, format="json")
        assert resp.status_code == 200
        assert resp.data["carried_to_period"] == "2026-07"
        next_plan = ImprovementPlan.objects.get(user=plan.user, period="2026-07")
        clone = next_plan.action_items.get(title="顺延任务")
        assert clone.status == "pending"
        assert str(clone.carried_from_id) == str(item.id)

    def test_verify_rejects_non_dict_scores(self, manager_client):
        client, _ = manager_client
        item = self._submitted_item()
        resp = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                           {"status": "verified", "scores": [1, 2, 3], "review_comment": "x"}, format="json")
        assert resp.status_code == 400


class TestActionItemAcknowledge:
    def test_employee_acknowledges_not_achieved_with_improve_note(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan, status="not_achieved")
        resp = client.post(f"/api/kpi/action-items/{item.id}/acknowledge/",
                           {"improve_note": "下次先查日志"}, format="json")
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.acknowledged is True
        assert item.improve_note == "下次先查日志"

    def test_not_achieved_acknowledge_requires_improve_note(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan, status="not_achieved")
        resp = client.post(f"/api/kpi/action-items/{item.id}/acknowledge/", {}, format="json")
        assert resp.status_code == 400

    def test_cannot_acknowledge_others_task(self, employee_client):
        client, _ = employee_client
        item = ActionItemFactory(status="not_achieved")  # belongs to someone else
        resp = client.post(f"/api/kpi/action-items/{item.id}/acknowledge/",
                           {"improve_note": "x"}, format="json")
        assert resp.status_code == 403


class TestCommentAPI:
    def test_employee_adds_comment(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan)
        resp = client.post(
            f"/api/kpi/action-items/{item.id}/comments/",
            {"content": "已完成截图见附件"}, format="json"
        )
        assert resp.status_code == 201
        assert item.comments.count() == 1


class TestGeneratePlanAPI:
    def test_manager_generates_plan(self, manager_client):
        client, _ = manager_client
        user = UserFactory(is_active=True, is_bot=False)
        resp = client.post(
            "/api/kpi/plans/generate/",
            {"user_id": user.id}, format="json"
        )
        assert resp.status_code == 201
        assert resp.data["status"] == "draft"


class TestActionItemSerializerFields:
    def test_detail_exposes_review_fields(self, manager_client):
        client, _ = manager_client
        plan = ImprovementPlanFactory()
        ActionItemFactory(
            plan=plan,
            review_dimensions=[{"key": "quality", "label": "完成质量", "weight": 1.0}],
            scores={"quality": 4}, review_comment="不错", status="verified",
        )
        resp = client.get(f"/api/kpi/plans/{plan.id}/")
        item = resp.data["action_items"][0]
        for key in ("scores", "review_comment", "overall_score", "due_date",
                    "review_dimensions", "reviewed_by_name", "reviewed_at"):
            assert key in item
        assert item["overall_score"] == 4.0


class TestTaskDispatchAPI:
    def test_dispatch_creates_published_plan_and_item(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        resp = client.post("/api/kpi/tasks/dispatch/", {
            "user_id": emp.id, "title": "读懂订单表设计并写200字理解",
            "due_date": "2026-06-30", "priority": "high",
        }, format="json")
        assert resp.status_code == 201
        from apps.kpi.models import ImprovementPlan, ActionItem, KPIScoringConfig
        plan = ImprovementPlan.objects.get(user=emp, period=timezone.now().strftime("%Y-%m"))
        assert plan.status == "published"
        item = ActionItem.objects.get(id=resp.data["id"])
        assert item.status == "pending"
        assert str(item.due_date) == "2026-06-30"
        assert item.review_dimensions == KPIScoringConfig.get_solo().review_dimensions

    def test_dispatch_requires_due_date(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        resp = client.post("/api/kpi/tasks/dispatch/", {"user_id": emp.id, "title": "x"}, format="json")
        assert resp.status_code == 400

    def test_dispatch_rejects_malformed_due_date(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        resp = client.post("/api/kpi/tasks/dispatch/",
                           {"user_id": emp.id, "title": "x", "due_date": "not-a-date"}, format="json")
        assert resp.status_code == 400

    def test_dispatch_reuses_and_publishes_current_month_plan(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        ImprovementPlanFactory(user=emp, period=timezone.now().strftime("%Y-%m"), status="draft")
        resp = client.post("/api/kpi/tasks/dispatch/", {"user_id": emp.id, "title": "任务A", "due_date": "2026-06-30"}, format="json")
        assert resp.status_code == 201
        from apps.kpi.models import ImprovementPlan
        plans = ImprovementPlan.objects.filter(user=emp, period=timezone.now().strftime("%Y-%m"))
        assert plans.count() == 1
        assert plans.first().status == "published"

    def test_dispatch_custom_dimensions_snapshot(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        dims = [{"key": "understanding", "label": "理解深度", "weight": 1.0}]
        resp = client.post("/api/kpi/tasks/dispatch/", {"user_id": emp.id, "title": "x", "due_date": "2026-06-30", "review_dimensions": dims}, format="json")
        from apps.kpi.models import ActionItem
        item = ActionItem.objects.get(id=resp.data["id"])
        assert item.review_dimensions == dims

    def test_employee_cannot_dispatch(self, employee_client):
        client, _ = employee_client
        emp = UserFactory()
        resp = client.post("/api/kpi/tasks/dispatch/", {"user_id": emp.id, "title": "x", "due_date": "2026-06-30"}, format="json")
        assert resp.status_code == 403

    def test_dispatch_empty_dims_falls_back_to_pool(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        resp = client.post("/api/kpi/tasks/dispatch/", {
            "user_id": emp.id, "title": "x", "due_date": "2026-06-30",
            "review_dimensions": [],
        }, format="json")
        assert resp.status_code == 201
        from apps.kpi.models import ActionItem, KPIScoringConfig
        item = ActionItem.objects.get(id=resp.data["id"])
        assert item.review_dimensions == KPIScoringConfig.get_solo().review_dimensions


class TestReviewDimensionsEndpoint:
    def test_any_authenticated_user_can_read_pool(self, employee_client):
        client, _ = employee_client
        resp = client.get("/api/kpi/review-dimensions/")
        assert resp.status_code == 200
        assert len(resp.data["review_dimensions"]) == 4


class TestActionItemSubmitNote:
    def test_submit_with_note_creates_comment(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan, status="in_progress")
        resp = client.post(f"/api/kpi/action-items/{item.id}/status/",
                           {"status": "submitted", "note": "线下已完成，说明见此",
                            "self_assessment": "我验证了 AI 给的方案并改了边界条件"}, format="json")
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.status == "submitted"
        assert item.comments.filter(content="线下已完成，说明见此").exists()


class TestActionItemSelfAssessment:
    def test_submit_requires_reflection(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan, status="in_progress")
        resp = client.post(f"/api/kpi/action-items/{item.id}/status/",
                           {"status": "submitted"}, format="json")
        assert resp.status_code == 400

    def test_submit_saves_self_scores_and_reflection(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        dims = [{"key": "quality", "label": "完成质量", "weight": 0.5},
                {"key": "delivery", "label": "交付与沟通", "weight": 0.5}]
        item = ActionItemFactory(plan=plan, status="in_progress", review_dimensions=dims)
        resp = client.post(f"/api/kpi/action-items/{item.id}/status/", {
            "status": "submitted",
            "self_assessment": "自己的判断与复盘",
            "self_scores": {"quality": 4, "delivery": 3},
        }, format="json")
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.self_assessment == "自己的判断与复盘"
        assert item.self_scores == {"quality": 4, "delivery": 3}
        assert item.self_assessed_at is not None
        assert item.self_overall_score == 3.5

    def test_submit_requires_all_dims_self_scored(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        dims = [{"key": "quality", "label": "完成质量", "weight": 0.5},
                {"key": "delivery", "label": "交付与沟通", "weight": 0.5}]
        item = ActionItemFactory(plan=plan, status="in_progress", review_dimensions=dims)
        resp = client.post(f"/api/kpi/action-items/{item.id}/status/", {
            "status": "submitted",
            "self_assessment": "只评了一个维度",
            "self_scores": {"quality": 4},
        }, format="json")
        assert resp.status_code == 400

    def test_submit_rejects_self_score_out_of_range(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        dims = [{"key": "quality", "label": "完成质量", "weight": 1.0}]
        item = ActionItemFactory(plan=plan, status="in_progress", review_dimensions=dims)
        resp = client.post(f"/api/kpi/action-items/{item.id}/status/", {
            "status": "submitted",
            "self_assessment": "超范围",
            "self_scores": {"quality": 9},
        }, format="json")
        assert resp.status_code == 400


class TestScoringConfigDimensions:
    def test_get_includes_review_dimensions(self, superuser_client):
        resp = superuser_client.get("/api/kpi/scoring-config/")
        assert resp.status_code == 200
        assert "review_dimensions" in resp.data
        assert len(resp.data["review_dimensions"]) == 4

    def test_put_updates_review_dimensions(self, superuser_client):
        dims = [{"key": "understanding", "label": "理解深度", "weight": 1.0}]
        resp = superuser_client.put("/api/kpi/scoring-config/", {"review_dimensions": dims}, format="json")
        assert resp.status_code == 200
        assert resp.data["review_dimensions"] == dims


class TestPlanListSupervisionCounts:
    def test_list_returns_reviewing_and_done_counts(self, manager_client):
        client, _ = manager_client
        period = "2026-06"
        plan = ImprovementPlanFactory(period=period, status="published")
        ActionItemFactory(plan=plan, status="submitted")
        ActionItemFactory(plan=plan, status="submitted")
        ActionItemFactory(plan=plan, status="verified")
        ActionItemFactory(plan=plan, status="in_progress")
        resp = client.get(f"/api/kpi/plans/?period={period}")
        assert resp.status_code == 200
        row = next(r for r in resp.data if str(r["id"]) == str(plan.id))
        assert row["reviewing_count"] == 2
        assert row["done_count"] == 1


class TestAdminRegistration:
    def test_scoring_config_registered(self):
        from django.contrib import admin as dj_admin
        from apps.kpi.models import KPIScoringConfig
        assert KPIScoringConfig in dj_admin.site._registry


class TestPlanEvaluation:
    """AI 小结 / 员工评价的保存（仅管理者）。"""

    def test_manager_saves_summary_and_evaluation(self, manager_client):
        client, _ = manager_client
        plan = ImprovementPlanFactory(period="2026-06", status="published")
        resp = client.put(f"/api/kpi/plans/{plan.id}/evaluation/", {
            "ai_summary": "内部小结",
            "employee_evaluation": "给员工看的评价",
        }, format="json")
        assert resp.status_code == 200
        plan.refresh_from_db()
        assert plan.ai_summary == "内部小结"
        assert plan.employee_evaluation == "给员工看的评价"

    def test_employee_cannot_save_evaluation(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, period="2026-06", status="published")
        resp = client.put(f"/api/kpi/plans/{plan.id}/evaluation/",
                          {"employee_evaluation": "x"}, format="json")
        assert resp.status_code == 403


class TestPlanEvaluationVisibility:
    """可见性边界：ai_summary 仅管理者可见，员工只能看到 employee_evaluation。"""

    def test_manager_detail_includes_ai_summary(self, manager_client):
        client, _ = manager_client
        plan = ImprovementPlanFactory(
            period="2026-06", status="published",
            ai_summary="内部机密", employee_evaluation="公开评价")
        resp = client.get(f"/api/kpi/plans/{plan.id}/")
        assert resp.status_code == 200
        assert resp.data["ai_summary"] == "内部机密"
        assert resp.data["employee_evaluation"] == "公开评价"

    def test_employee_my_plan_hides_summary_shows_evaluation(self, employee_client):
        client, user = employee_client
        ImprovementPlanFactory(
            user=user, period=timezone.now().strftime("%Y-%m"),
            status="published", ai_summary="内部机密",
            employee_evaluation="给你的评价")
        resp = client.get("/api/kpi/plans/me/")
        assert resp.status_code == 200
        cur = resp.data["current"]
        assert "ai_summary" not in cur
        assert "ai_summary_at" not in cur
        assert "ai_summary_model" not in cur
        assert cur["employee_evaluation"] == "给你的评价"

    def test_employee_past_month_also_hides_summary(self, employee_client):
        # ?period= 过往月份分支同样无 manager context，应一并剔除 ai_summary
        client, user = employee_client
        ImprovementPlanFactory(
            user=user, period="2026-05", status="archived",
            ai_summary="内部机密", employee_evaluation="上月评价")
        resp = client.get("/api/kpi/plans/me/?period=2026-05")
        assert resp.status_code == 200
        plan = resp.data["plan"]
        assert "ai_summary" not in plan
        assert "ai_summary_at" not in plan
        assert "ai_summary_model" not in plan
        assert plan["employee_evaluation"] == "上月评价"


class TestPlanAISummary:
    """LLM 月度小结生成（仅管理者，LLMClient 已 mock）。"""

    def _seed_prompt(self):
        # 迁移 0017 已在测试库种入该 prompt；这里改写模板/模型即可，避免 slug 撞唯一约束。
        from apps.ai.models import Prompt
        Prompt.objects.filter(slug="plan_monthly_summary").update(
            user_prompt_template="员工：{user_name} 周期：{period} 共 {total}\n{tasks}",
            llm_model="gpt-4o", is_active=True,
        )

    def test_manager_generates_summary(self, manager_client):
        client, _ = manager_client
        plan = ImprovementPlanFactory(period="2026-06", status="published")
        ActionItemFactory(plan=plan, status="verified")
        self._seed_prompt()
        with patch("apps.ai.client.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = \
                '{"summary": "本月表现稳定，建议加强复盘"}'
            resp = client.post(f"/api/kpi/plans/{plan.id}/ai-summary/")
        assert resp.status_code == 200
        assert resp.data["ai_summary"] == "本月表现稳定，建议加强复盘"
        plan.refresh_from_db()
        assert plan.ai_summary == "本月表现稳定，建议加强复盘"
        assert plan.ai_summary_at is not None
        assert plan.ai_summary_model  # 取自 prompt.llm_model

    def test_falls_back_to_raw_when_not_json(self, manager_client):
        client, _ = manager_client
        plan = ImprovementPlanFactory(period="2026-06", status="published")
        self._seed_prompt()
        with patch("apps.ai.client.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = "纯文本小结，不是 JSON"
            resp = client.post(f"/api/kpi/plans/{plan.id}/ai-summary/")
        assert resp.status_code == 200
        assert resp.data["ai_summary"] == "纯文本小结，不是 JSON"

    def test_missing_prompt_returns_400(self, manager_client):
        client, _ = manager_client
        # 停用种子 prompt，模拟"未配置"场景
        from apps.ai.models import Prompt
        Prompt.objects.filter(slug="plan_monthly_summary").update(is_active=False)
        plan = ImprovementPlanFactory(period="2026-06", status="published")
        resp = client.post(f"/api/kpi/plans/{plan.id}/ai-summary/")
        assert resp.status_code == 400

    def test_employee_cannot_generate_summary(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, period="2026-06", status="published")
        self._seed_prompt()
        resp = client.post(f"/api/kpi/plans/{plan.id}/ai-summary/")
        assert resp.status_code == 403
