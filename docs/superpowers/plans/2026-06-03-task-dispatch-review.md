# 任务派发与多维点评 — 实现计划（P0）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `ImprovementPlan`/`ActionItem` 上做出"管理者即时派发任务 → 员工执行反馈 → 管理者按逐任务可配维度打分+总评"的闭环，并隐藏奖赏、把待办任务搬上工作台。

**Architecture:** 复用 KPI 模块的计划/行动项数据骨架。后端新增字段（截止日期、维度评分、总评、逐任务维度快照）+ 派发接口 + 改造评分接口，全程 pytest TDD。前端改造员工页/管理页/点评页/工作台 4 个页面 + 一个共用维度编辑器组件，验证靠 `npx nuxi typecheck` + 手动 QA（项目无前端单测）。奖赏字段一律保留数据、仅 UI 隐藏。

**Tech Stack:** Django 6 + DRF + django-solo + pytest-django/factory-boy（后端）；Nuxt 4 SPA + Nuxt UI（`U*` 组件）+ TypeScript（前端）；uv 管理后端依赖。

**Spec:** `docs/superpowers/specs/2026-06-03-task-dispatch-review-design.md`

**约定：** 后端命令在 `backend/` 下用 `uv run` 执行；前端命令在 `frontend/` 下。每个任务结束 commit 一次。

---

## 文件结构（本计划涉及）

**后端（`backend/`）**
- 改 `apps/kpi/models.py` — `KPIScoringConfig.review_dimensions`（维度库）+ `ActionItem` 新字段 + `overall_score` 属性
- 新增迁移 `apps/kpi/migrations/00XX_*.py`
- 改 `apps/kpi/plan_serializers.py` — `ActionItemSerializer` 输出新字段
- 改 `apps/kpi/plan_views.py` — 新增 `TaskDispatchView`；改 `ActionItemVerifyView`、`ActionItemStatusView`
- 改 `apps/kpi/urls.py` — 注册 `tasks/dispatch/`
- 改 `apps/kpi/views.py` — `KPIScoringConfigView` GET/PUT 带 `review_dimensions`
- 改 `apps/kpi/admin.py` — 注册 `KPIScoringConfig` 单例
- 改 `tests/test_plan_api.py`、`tests/test_plan_models.py` — 新增/更新测试

**前端（`frontend/`）**
- 新增 `app/components/ReviewDimensionEditor.vue` — 维度编辑器（派发弹窗 + 点评共用）
- 改 `app/pages/app/ai/my-plan.vue` — 员工「我的任务」，隐藏奖赏、展示点评
- 改 `app/pages/app/ai/plans/index.vue` — 「派发任务」按钮 + 监督列
- 改 `app/pages/app/ai/plans/[id].vue` — 维度打分 + 总评、修 `failed` bug
- 改 `app/pages/app/home.vue` — 「我的提升计划」卡 → 「我的任务」待办
- 改 `app/composables/useNavigation.ts` — 文案微调

---

## Phase A — 后端模型与迁移

### Task 1：维度库字段 `KPIScoringConfig.review_dimensions`

**Files:**
- Modify: `apps/kpi/models.py`
- Test: `tests/test_plan_models.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_plan_models.py` 末尾追加：

```python
def test_scoring_config_has_default_review_dimensions():
    from apps.kpi.models import KPIScoringConfig
    cfg = KPIScoringConfig.get_solo()
    dims = cfg.review_dimensions
    assert isinstance(dims, list)
    assert {d["key"] for d in dims} == {"initiative", "understanding", "quality", "delivery"}
    assert all("label" in d and "weight" in d for d in dims)
```

> 该文件顶部已有 `pytestmark = pytest.mark.django_db`（若无则加）。

- [ ] **Step 2：运行，确认失败**

Run: `cd backend && uv run pytest tests/test_plan_models.py::test_scoring_config_has_default_review_dimensions -v`
Expected: FAIL（`AttributeError: 'KPIScoringConfig' object has no attribute 'review_dimensions'`）

- [ ] **Step 3：实现**

在 `apps/kpi/models.py`，于 `_default_piece_rate_config` 之后、`class KPIScoringConfig` 之前加默认函数：

```python
def _default_review_dimensions():
    """点评维度候选库/默认池。派发新任务时默认从此快照。"""
    return [
        {"key": "initiative", "label": "主动性", "weight": 0.25},
        {"key": "understanding", "label": "理解深度", "weight": 0.25},
        {"key": "quality", "label": "完成质量", "weight": 0.25},
        {"key": "delivery", "label": "交付与沟通", "weight": 0.25},
    ]
```

在 `KPIScoringConfig` 内、`updated_at` 字段之前加：

```python
    review_dimensions = models.JSONField(
        default=_default_review_dimensions,
        verbose_name="点评维度库",
        help_text="点评维度候选库/默认池，每项 {key,label,weight}；派发新任务时默认从此填充，之后逐任务可改",
    )
```

- [ ] **Step 4：运行，确认通过**

Run: `cd backend && uv run pytest tests/test_plan_models.py::test_scoring_config_has_default_review_dimensions -v`
Expected: PASS

- [ ] **Step 5：提交**

```bash
git add backend/apps/kpi/models.py backend/tests/test_plan_models.py
git commit -m "feat(kpi): add review_dimensions pool to KPIScoringConfig"
```

---

### Task 2：`ActionItem` 新字段 + `overall_score` 属性

**Files:**
- Modify: `apps/kpi/models.py`
- Test: `tests/test_plan_models.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_plan_models.py` 末尾追加：

```python
def test_overall_score_weighted():
    from tests.factories import ActionItemFactory
    item = ActionItemFactory(
        review_dimensions=[{"key": "a", "label": "A", "weight": 0.5},
                           {"key": "b", "label": "B", "weight": 0.5}],
        scores={"a": 4, "b": 2},
    )
    assert item.overall_score == 3.0


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
```

- [ ] **Step 2：运行，确认失败**

Run: `cd backend && uv run pytest tests/test_plan_models.py -k overall_score -v`
Expected: FAIL（`TypeError: 'ActionItem' got unexpected keyword 'review_dimensions'` 或属性缺失）

- [ ] **Step 3：实现**

在 `apps/kpi/models.py` 的 `ActionItem` 内，`updated_at` 字段之后追加字段：

```python
    due_date = models.DateField(null=True, blank=True, verbose_name="截止日期")
    scores = models.JSONField(default=dict, blank=True, verbose_name="维度评分")  # {dim_key: 1..5}
    review_comment = models.TextField(blank=True, default="", verbose_name="总评")
    review_dimensions = models.JSONField(default=list, blank=True, verbose_name="本任务维度")  # [{key,label,weight}]
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="评分人",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="评分时间")
```

在同类 `earned_points` 属性之后追加：

```python
    @property
    def overall_score(self):
        """按本任务自己的 review_dimensions 权重对已打分维度加权平均（1-5）；未打分返回 None。"""
        if not self.scores:
            return None
        dims = {d["key"]: float(d.get("weight", 0)) for d in (self.review_dimensions or [])}
        den = sum(dims.get(k, 0) for k in self.scores)
        if dims and den:
            num = sum(v * dims.get(k, 0) for k, v in self.scores.items())
            return round(num / den, 1)
        vals = list(self.scores.values())  # 无权重信息 → 等权平均
        return round(sum(vals) / len(vals), 1)
```

- [ ] **Step 4：运行，确认通过**

Run: `cd backend && uv run pytest tests/test_plan_models.py -k overall_score -v`
Expected: PASS（3 个）

- [ ] **Step 5：提交**

```bash
git add backend/apps/kpi/models.py backend/tests/test_plan_models.py
git commit -m "feat(kpi): ActionItem review fields + overall_score property"
```

---

### Task 3：生成并应用迁移

**Files:**
- Create: `apps/kpi/migrations/00XX_actionitem_review_fields.py`（由 makemigrations 生成）

- [ ] **Step 1：生成迁移**

Run: `cd backend && uv run python manage.py makemigrations kpi`
Expected: 输出新增 `KPIScoringConfig.review_dimensions` 及 `ActionItem` 的 `due_date/scores/review_comment/review_dimensions/reviewed_by/reviewed_at` 六个字段的迁移文件。

- [ ] **Step 2：应用迁移**

Run: `cd backend && uv run python manage.py migrate kpi`
Expected: `Applying kpi.00XX_... OK`

- [ ] **Step 3：跑一遍模型测试确认无回归**

Run: `cd backend && uv run pytest tests/test_plan_models.py -v`
Expected: PASS（含 Task 1/2 新增）

- [ ] **Step 4：提交**

```bash
git add backend/apps/kpi/migrations/
git commit -m "feat(kpi): migration for review fields"
```

---

## Phase B — 序列化器

### Task 4：`ActionItemSerializer` 输出新字段

**Files:**
- Modify: `apps/kpi/plan_serializers.py`
- Test: `tests/test_plan_api.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_plan_api.py` 的 `TestPlanDetailAPI` 类后追加：

```python
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
```

- [ ] **Step 2：运行，确认失败**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestActionItemSerializerFields -v`
Expected: FAIL（`KeyError`/缺字段）

- [ ] **Step 3：实现**

在 `apps/kpi/plan_serializers.py` 改 `ActionItemSerializer`：

```python
class ActionItemSerializer(serializers.ModelSerializer):
    earned_points = serializers.IntegerField(read_only=True)
    overall_score = serializers.FloatField(read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.name", default="", read_only=True)
    comments = ActionItemCommentSerializer(many=True, read_only=True)

    class Meta:
        model = ActionItem
        fields = [
            "id", "source", "dimension", "title", "description",
            "measurable_target", "points", "priority", "status",
            "quality_factor", "earned_points", "sort_order",
            "due_date", "scores", "review_comment", "review_dimensions",
            "overall_score", "reviewed_by", "reviewed_by_name", "reviewed_at",
            "comments", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "source", "earned_points", "overall_score",
            "reviewed_by", "reviewed_by_name", "reviewed_at",
            "created_at", "updated_at",
        ]
```

- [ ] **Step 4：运行，确认通过**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestActionItemSerializerFields -v`
Expected: PASS

- [ ] **Step 5：提交**

```bash
git add backend/apps/kpi/plan_serializers.py backend/tests/test_plan_api.py
git commit -m "feat(kpi): serialize review fields on ActionItem"
```

---

## Phase C — 后端接口

### Task 5：派发接口 `TaskDispatchView`

**Files:**
- Modify: `apps/kpi/plan_views.py`、`apps/kpi/urls.py`
- Test: `tests/test_plan_api.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_plan_api.py` 末尾追加：

```python
class TestTaskDispatchAPI:
    def test_dispatch_creates_published_plan_and_item(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        resp = client.post("/api/kpi/tasks/dispatch/", {
            "user_id": emp.id, "title": "读懂订单表设计并写200字理解",
            "due_date": "2026-06-30", "priority": "high",
        }, format="json")
        assert resp.status_code == 201
        from apps.kpi.models import ImprovementPlan, ActionItem
        plan = ImprovementPlan.objects.get(user=emp, period=timezone.now().strftime("%Y-%m"))
        assert plan.status == "published"
        item = ActionItem.objects.get(id=resp.data["id"])
        assert item.status == "pending"
        assert str(item.due_date) == "2026-06-30"
        assert len(item.review_dimensions) == 4  # 默认从维度库快照

    def test_dispatch_requires_due_date(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        resp = client.post("/api/kpi/tasks/dispatch/",
                           {"user_id": emp.id, "title": "x"}, format="json")
        assert resp.status_code == 400

    def test_dispatch_reuses_and_publishes_current_month_plan(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        ImprovementPlanFactory(user=emp, period=timezone.now().strftime("%Y-%m"), status="draft")
        resp = client.post("/api/kpi/tasks/dispatch/",
                           {"user_id": emp.id, "title": "任务A", "due_date": "2026-06-30"},
                           format="json")
        assert resp.status_code == 201
        from apps.kpi.models import ImprovementPlan
        plans = ImprovementPlan.objects.filter(user=emp, period=timezone.now().strftime("%Y-%m"))
        assert plans.count() == 1
        assert plans.first().status == "published"

    def test_dispatch_custom_dimensions_snapshot(self, manager_client):
        client, _ = manager_client
        emp = UserFactory()
        dims = [{"key": "understanding", "label": "理解深度", "weight": 1.0}]
        resp = client.post("/api/kpi/tasks/dispatch/", {
            "user_id": emp.id, "title": "x", "due_date": "2026-06-30",
            "review_dimensions": dims}, format="json")
        from apps.kpi.models import ActionItem
        item = ActionItem.objects.get(id=resp.data["id"])
        assert item.review_dimensions == dims

    def test_employee_cannot_dispatch(self, employee_client):
        client, _ = employee_client
        emp = UserFactory()
        resp = client.post("/api/kpi/tasks/dispatch/",
                           {"user_id": emp.id, "title": "x", "due_date": "2026-06-30"},
                           format="json")
        assert resp.status_code == 403
```

- [ ] **Step 2：运行，确认失败**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestTaskDispatchAPI -v`
Expected: FAIL（404，路由不存在）

- [ ] **Step 3：实现 view**

在 `apps/kpi/plan_views.py` 顶部 import 区把 `from .models import ...` 改为包含 `KPIScoringConfig`：

```python
from .models import ImprovementPlan, ActionItem, ActionItemComment, KPIScoringConfig
```

在文件末尾新增：

```python
class TaskDispatchView(APIView):
    """POST /api/kpi/tasks/dispatch/ — 管理者即时派发任务（月度自动归桶、直接发布）。"""
    permission_classes = [FullDjangoModelPermissions]
    queryset = ImprovementPlan.objects.none()

    def post(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user_id = request.data.get("user_id")
        title = (request.data.get("title") or "").strip()
        due_date = request.data.get("due_date")
        if not user_id or not title or not due_date:
            return Response({"detail": "user_id、title、due_date 均为必填"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)

        period = timezone.now().strftime("%Y-%m")
        plan, _created = ImprovementPlan.objects.get_or_create(
            user=target, period=period,
            defaults={"status": ImprovementPlan.Status.PUBLISHED,
                      "source_kpi_scores": {}, "created_by": request.user},
        )
        if plan.status != ImprovementPlan.Status.PUBLISHED:
            plan.status = ImprovementPlan.Status.PUBLISHED
            if not plan.published_at:
                plan.published_at = timezone.now()
            plan.save(update_fields=["status", "published_at", "updated_at"])

        dims = request.data.get("review_dimensions")
        if not dims:
            dims = KPIScoringConfig.get_solo().review_dimensions

        last = plan.action_items.order_by("-sort_order").first()
        next_order = (last.sort_order + 1) if last else 0

        item = ActionItem.objects.create(
            plan=plan,
            source=ActionItem.Source.MANAGER,
            status=ActionItem.Status.PENDING,
            title=title,
            description=request.data.get("description", ""),
            measurable_target=request.data.get("measurable_target", ""),
            priority=request.data.get("priority", ActionItem.Priority.MEDIUM),
            due_date=due_date,
            review_dimensions=dims,
            sort_order=next_order,
        )
        return Response(ActionItemSerializer(item).data, status=status.HTTP_201_CREATED)
```

- [ ] **Step 4：注册路由**

在 `apps/kpi/urls.py` 的 `.plan_views` import 里加上 `TaskDispatchView`，并在 `# 提升计划` 段加一行：

```python
    path("tasks/dispatch/", TaskDispatchView.as_view(), name="task-dispatch"),
```

- [ ] **Step 5：运行，确认通过**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestTaskDispatchAPI -v`
Expected: PASS（5 个）

- [ ] **Step 6：提交**

```bash
git add backend/apps/kpi/plan_views.py backend/apps/kpi/urls.py backend/tests/test_plan_api.py
git commit -m "feat(kpi): task dispatch endpoint"
```

---

### Task 6：改造评分接口 `ActionItemVerifyView`

**Files:**
- Modify: `apps/kpi/plan_views.py`
- Test: `tests/test_plan_api.py`（替换旧 `TestActionItemVerifyAPI`）

- [ ] **Step 1：替换旧测试为新契约**

在 `tests/test_plan_api.py` 中，把整个 `class TestActionItemVerifyAPI: ...`（旧的 `test_manager_verifies_item`）替换为：

```python
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
                           {"status": "verified", "scores": {"speed": 4},
                            "review_comment": "x"}, format="json")
        assert resp.status_code == 400

    def test_not_achieved(self, manager_client):
        client, _ = manager_client
        item = ActionItemFactory(status="submitted")
        resp = client.post(f"/api/kpi/action-items/{item.id}/verify/",
                           {"status": "not_achieved"}, format="json")
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.status == "not_achieved"
```

- [ ] **Step 2：运行，确认失败**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestActionItemVerifyAPI -v`
Expected: FAIL（旧 view 仍要 `quality_factor`，`test_verify_requires_comment` 等不符合）

- [ ] **Step 3：实现**

在 `apps/kpi/plan_views.py` 把 `ActionItemVerifyView.post` 整个替换为：

```python
    def post(self, request, pk):
        try:
            item = ActionItem.objects.get(pk=pk)
        except ActionItem.DoesNotExist:
            return Response({"detail": "行动项不存在"}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        if new_status not in ("verified", "not_achieved"):
            return Response({"detail": "状态必须为 verified 或 not_achieved"},
                            status=status.HTTP_400_BAD_REQUEST)

        # 维度：请求带了用请求的（评分前最终调整），否则用任务已有的
        dims = request.data.get("review_dimensions")
        if dims is None:
            dims = item.review_dimensions or []

        if new_status == "verified":
            review_comment = (request.data.get("review_comment") or "").strip()
            if not review_comment:
                return Response({"detail": "验收需填写总评"}, status=status.HTTP_400_BAD_REQUEST)
            scores = request.data.get("scores") or {}
            valid_keys = {d["key"] for d in dims}
            for k, v in scores.items():
                if k not in valid_keys:
                    return Response({"detail": f"维度 {k} 不属于本任务"},
                                    status=status.HTTP_400_BAD_REQUEST)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not (1 <= v <= 5):
                    return Response({"detail": f"维度 {k} 评分须为 1-5"},
                                    status=status.HTTP_400_BAD_REQUEST)
            item.scores = scores
            item.review_comment = review_comment
            item.review_dimensions = dims

        item.status = new_status
        item.reviewed_by = request.user
        item.reviewed_at = timezone.now()
        item.save(update_fields=["status", "scores", "review_comment", "review_dimensions",
                                 "reviewed_by", "reviewed_at", "updated_at"])
        return Response(ActionItemSerializer(item).data)
```

- [ ] **Step 4：运行，确认通过**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestActionItemVerifyAPI -v`
Expected: PASS（4 个）

- [ ] **Step 5：提交**

```bash
git add backend/apps/kpi/plan_views.py backend/tests/test_plan_api.py
git commit -m "feat(kpi): verify by per-task dimensions + review comment"
```

---

### Task 7：提交带"成果说明" → `ActionItemStatusView`

**Files:**
- Modify: `apps/kpi/plan_views.py`
- Test: `tests/test_plan_api.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_plan_api.py` 末尾追加：

```python
class TestActionItemSubmitNote:
    def test_submit_with_note_creates_comment(self, employee_client):
        client, user = employee_client
        plan = ImprovementPlanFactory(user=user, status="published")
        item = ActionItemFactory(plan=plan, status="in_progress")
        resp = client.post(f"/api/kpi/action-items/{item.id}/status/",
                           {"status": "submitted", "note": "线下已完成，说明见此"},
                           format="json")
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.status == "submitted"
        assert item.comments.filter(content="线下已完成，说明见此").exists()
```

- [ ] **Step 2：运行，确认失败**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestActionItemSubmitNote -v`
Expected: FAIL（无评论生成）

- [ ] **Step 3：实现**

在 `apps/kpi/plan_views.py` 的 `ActionItemStatusView.post`，把结尾的 `return Response(...)` 之前插入：

```python
        # 可选的"成果说明" → 落成一条评论（支持线上/线下反馈）
        note = (request.data.get("note") or "").strip()
        if note:
            attachment_url = attachment_key = ""
            if "attachment" in request.FILES:
                attachment_url, attachment_key = upload_image(request.FILES["attachment"])
            ActionItemComment.objects.create(
                action_item=item, author=request.user, content=note,
                attachment_url=attachment_url, attachment_key=attachment_key,
            )
```

（`upload_image` 与 `ActionItemComment` 在该文件已导入。）

- [ ] **Step 4：运行，确认通过**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestActionItemSubmitNote -v`
Expected: PASS

- [ ] **Step 5：提交**

```bash
git add backend/apps/kpi/plan_views.py backend/tests/test_plan_api.py
git commit -m "feat(kpi): optional submit note becomes a comment"
```

---

### Task 8：维度库出现在 `scoring-config` GET/PUT

**Files:**
- Modify: `apps/kpi/views.py`
- Test: `tests/test_plan_api.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_plan_api.py` 末尾追加（注意用 `superuser_client`，因为该接口是 `IsAdminUser`）：

```python
class TestScoringConfigDimensions:
    def test_get_includes_review_dimensions(self, superuser_client):
        resp = superuser_client.get("/api/kpi/scoring-config/")
        assert resp.status_code == 200
        assert "review_dimensions" in resp.data
        assert len(resp.data["review_dimensions"]) == 4

    def test_put_updates_review_dimensions(self, superuser_client):
        dims = [{"key": "understanding", "label": "理解深度", "weight": 1.0}]
        resp = superuser_client.put("/api/kpi/scoring-config/",
                                    {"review_dimensions": dims}, format="json")
        assert resp.status_code == 200
        assert resp.data["review_dimensions"] == dims
```

- [ ] **Step 2：运行，确认失败**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestScoringConfigDimensions -v`
Expected: FAIL（响应无 `review_dimensions`）

- [ ] **Step 3：实现**

在 `apps/kpi/views.py` 的 `KPIScoringConfigView`：
- `get()` 返回的 dict 增加一行 `"review_dimensions": cfg.review_dimensions,`
- `put()` 的 `fields` 列表追加 `"review_dimensions"`
- `put()` 末尾返回的 dict 同样增加 `"review_dimensions": cfg.review_dimensions,`

- [ ] **Step 4：运行，确认通过**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestScoringConfigDimensions -v`
Expected: PASS（2 个）

- [ ] **Step 5：提交**

```bash
git add backend/apps/kpi/views.py backend/tests/test_plan_api.py
git commit -m "feat(kpi): expose review_dimensions in scoring-config API"
```

---

## Phase D — Django admin

### Task 9：注册 `KPIScoringConfig` 单例到 admin

**Files:**
- Modify: `apps/kpi/admin.py`
- Test: `tests/test_plan_api.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_plan_api.py` 末尾追加：

```python
class TestAdminRegistration:
    def test_scoring_config_registered(self):
        from django.contrib import admin as dj_admin
        from apps.kpi.models import KPIScoringConfig
        assert KPIScoringConfig in dj_admin.site._registry
```

- [ ] **Step 2：运行，确认失败**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestAdminRegistration -v`
Expected: FAIL（未注册）

- [ ] **Step 3：实现**

把 `apps/kpi/admin.py` 改为：

```python
from django.contrib import admin
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin
from .models import KPISnapshot, KPIScoringConfig


@admin.register(KPISnapshot)
class KPISnapshotAdmin(ModelAdmin):
    list_display = ("user", "period_start", "period_end", "computed_at")
    list_filter = ("period_start", "period_end")
    search_fields = ("user__username", "user__name")
    readonly_fields = ("id", "computed_at", "created_at")


@admin.register(KPIScoringConfig)
class KPIScoringConfigAdmin(SingletonModelAdmin, ModelAdmin):
    """单例：维度库等评分规则在此以 JSON 表单编辑。"""
```

> 若 `SingletonModelAdmin, ModelAdmin` 因 MRO 报错，退化为 `class KPIScoringConfigAdmin(SingletonModelAdmin):`（牺牲 unfold 样式，功能不受影响）。

- [ ] **Step 4：运行，确认通过**

Run: `cd backend && uv run pytest tests/test_plan_api.py::TestAdminRegistration -v`
Expected: PASS

- [ ] **Step 5：后端全量回归**

Run: `cd backend && uv run pytest tests/test_plan_api.py tests/test_plan_models.py -v`
Expected: 全部 PASS（确认没碰坏既有计划相关测试）

- [ ] **Step 6：提交**

```bash
git add backend/apps/kpi/admin.py backend/tests/test_plan_api.py
git commit -m "feat(kpi): register KPIScoringConfig singleton in admin"
```

---

## Phase E — 前端

> 前端无单测框架。每个任务的验证 = `cd frontend && npx nuxi typecheck` 通过 + 列出的手动 QA 点。奖赏元素一律删/隐，不再展示。

### Task 10：维度编辑器组件 `ReviewDimensionEditor.vue`

**Files:**
- Create: `frontend/app/components/ReviewDimensionEditor.vue`

- [ ] **Step 1：创建组件**

`v-model` 为维度数组 `Array<{key,label,weight}>`。可改名、改权重、删除、勾选库里的维度、临时加一条。

```vue
<template>
  <div class="space-y-2">
    <div
      v-for="(d, i) in model"
      :key="i"
      class="flex items-center gap-2"
    >
      <UInput v-model="d.label" size="xs" variant="outline" placeholder="维度名称" class="flex-1" />
      <UInput
        v-model.number="d.weight"
        size="xs" variant="outline" type="number" :step="0.05" :min="0" :max="1"
        class="w-20"
      />
      <UButton size="xs" variant="ghost" color="error" icon="i-heroicons-trash" @click="remove(i)" />
    </div>

    <div class="flex items-center gap-2 pt-1">
      <UButton size="xs" variant="outline" color="neutral" icon="i-heroicons-plus" @click="add">
        加维度
      </UButton>
      <UButton
        v-if="poolUnused.length"
        size="xs" variant="ghost" color="neutral" icon="i-heroicons-arrow-down-on-square"
        @click="addFromPool"
      >
        从维度库添加
      </UButton>
      <span class="text-xs text-gray-400">权重和：{{ weightSum.toFixed(2) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Dim { key: string; label: string; weight: number }

const model = defineModel<Dim[]>({ default: () => [] })
const props = defineProps<{ pool?: Dim[] }>()

const weightSum = computed(() => model.value.reduce((s, d) => s + (Number(d.weight) || 0), 0))
const poolUnused = computed(() =>
  (props.pool || []).filter(p => !model.value.some(d => d.key === p.key)),
)

function add() {
  model.value.push({ key: `custom_${Date.now()}`, label: '', weight: 0.1 })
}
function addFromPool() {
  const next = poolUnused.value[0]
  if (next) model.value.push({ ...next })
}
function remove(i: number) {
  model.value.splice(i, 1)
}
</script>
```

- [ ] **Step 2：验证**

Run: `cd frontend && npx nuxi typecheck`
Expected: 无新增类型错误。

- [ ] **Step 3：提交**

```bash
git add frontend/app/components/ReviewDimensionEditor.vue
git commit -m "feat(frontend): review dimension editor component"
```

---

### Task 11：员工「我的任务」页 `my-plan.vue`

**Files:**
- Modify: `frontend/app/pages/app/ai/my-plan.vue`

- [ ] **Step 1：标题与空态文案**

- 第 3 行标题 `我的提升计划` → `我的任务`。
- 第 15 行空态 `请联系管理员创建您的提升计划` → `暂无派发给你的任务`。

- [ ] **Step 2：隐藏奖赏汇总卡**

删除"总分值"卡（第 25-28 行）与"已得分"卡（第 29-32 行）两个 `<div>`；把汇总 grid 的 `lg:grid-cols-4` 改为 `lg:grid-cols-2`，保留"行动项数量"与"完成进度"。

- [ ] **Step 3：每项隐藏分值、显示截止日期**

把第 64-69 行标题右侧块替换为：

```vue
            <div class="flex items-center gap-3 flex-shrink-0 ml-3">
              <span
                v-if="item.due_date"
                class="text-xs"
                :class="isOverdue(item) ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-400 dark:text-gray-500'"
              >截止 {{ item.due_date }}</span>
              <UBadge :color="statusColor(item.status)" variant="subtle" size="xs">
                {{ statusLabel(item.status) }}
              </UBadge>
            </div>
```

并在 `<script setup>` 内加：

```ts
function isOverdue(item: any): boolean {
  if (!item.due_date || ['verified', 'not_achieved'].includes(item.status)) return false
  return new Date(item.due_date) < new Date(new Date().toDateString())
}
```

- [ ] **Step 4：把"验收行"换成点评展示**

把第 112-118 行 `item.status === 'verified'` 那段（含 `实得 X分 (×系数)`）替换为：

```vue
              <div v-if="item.status === 'verified'" class="w-full space-y-2">
                <div class="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                  <UIcon name="i-heroicons-check-badge" class="w-4 h-4" />
                  <span>已评分</span>
                </div>
                <div
                  v-for="d in (item.review_dimensions || [])"
                  :key="d.key"
                  class="flex items-center gap-2 text-sm"
                >
                  <span class="text-gray-500 dark:text-gray-400 w-20">{{ d.label }}</span>
                  <span class="text-amber-500">{{ '★'.repeat(item.scores?.[d.key] || 0) }}<span class="text-gray-300 dark:text-gray-600">{{ '★'.repeat(5 - (item.scores?.[d.key] || 0)) }}</span></span>
                </div>
                <div v-if="item.review_comment" class="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 rounded p-2">
                  <span class="text-xs text-gray-400 dark:text-gray-500">总评：</span>{{ item.review_comment }}
                </div>
              </div>
```

- [ ] **Step 5：提交完成时弹"成果说明"**

把"提交完成"按钮（第 98-107 行）的 `@click` 改为打开一个 prompt 弹窗；新增状态与方法。最简实现：用 `UModal` + textarea。在模板"状态操作"块后插入弹窗：

```vue
      <UModal v-model:open="submitModalOpen">
        <template #content>
          <div class="p-4 space-y-3">
            <h3 class="font-medium">提交完成</h3>
            <UTextarea v-model="submitNote" :rows="3" placeholder="成果说明（线上/线下完成情况，可留空）" class="w-full" />
            <div class="flex justify-end gap-2">
              <UButton variant="ghost" color="neutral" @click="submitModalOpen = false">取消</UButton>
              <UButton color="success" :loading="updatingStatus[submitItemId]" @click="confirmSubmit">确认提交</UButton>
            </div>
          </div>
        </template>
      </UModal>
```

把"提交完成"按钮 `@click.stop="updateStatus(item.id, 'submitted')"` 改为 `@click.stop="openSubmit(item.id)"`，并在 `<script setup>` 加：

```ts
const submitModalOpen = ref(false)
const submitNote = ref('')
const submitItemId = ref('')

function openSubmit(itemId: string) {
  submitItemId.value = itemId
  submitNote.value = ''
  submitModalOpen.value = true
}
async function confirmSubmit() {
  const id = submitItemId.value
  updatingStatus.value[id] = true
  try {
    await api(`/api/kpi/action-items/${id}/status/`, {
      method: 'POST',
      body: { status: 'submitted', note: submitNote.value.trim() },
    })
    submitModalOpen.value = false
    toast.add({ title: '已提交', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '提交失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    updatingStatus.value[id] = false
  }
}
```

- [ ] **Step 6：历史区隐藏分数**

把第 194-201 行历史分数 `{{ h.earned_points }} / {{ h.total_points }}分` 与百分比徽标，替换为周期文字即可（删除分数 span，仅保留 `h.period`）。

- [ ] **Step 7：验证**

Run: `cd frontend && npx nuxi typecheck`
Expected: 无新增类型错误。
手动 QA：以员工身份打开 `/app/ai/my-plan` → 看不到任何"分"；待验收→已评分项显示星级+总评；提交时弹说明框；逾期项截止日期标红。

- [ ] **Step 8：提交**

```bash
git add frontend/app/pages/app/ai/my-plan.vue
git commit -m "feat(frontend): my tasks page — hide rewards, show review, submit note"
```

---

### Task 12：管理页「派发任务」+ 监督列 `plans/index.vue`

**Files:**
- Modify: `frontend/app/pages/app/ai/plans/index.vue`

- [ ] **Step 1：顶部加「派发任务」按钮 + 弹窗**

把头部"批量生成草案"按钮（第 29-36 行）替换为「派发任务」按钮：

```vue
        <UButton size="sm" icon="i-heroicons-paper-airplane" @click="openDispatch">
          派发任务
        </UButton>
```

在模板根 `<div>` 末尾、`</div>` 前加派发弹窗：

```vue
    <UModal v-model:open="dispatchOpen">
      <template #content>
        <div class="p-5 space-y-3">
          <h3 class="text-base font-semibold">派发任务</h3>
          <USelectMenu v-model="form.user_id" :items="memberOptions" value-key="value" label-key="label" placeholder="选择成员" class="w-full" />
          <UInput v-model="form.title" placeholder="任务标题" class="w-full" />
          <UInput v-model="form.due_date" type="date" class="w-full" />
          <USelect v-model="form.priority" :items="priorityOptions" class="w-full" />
          <UTextarea v-model="form.description" :rows="2" placeholder="描述/可量化目标（可选）" class="w-full" />
          <div>
            <p class="text-xs text-gray-500 mb-1">点评维度（默认取自维度库，可改）</p>
            <ReviewDimensionEditor v-model="form.review_dimensions" :pool="pool" />
          </div>
          <div class="flex justify-end gap-2 pt-1">
            <UButton variant="ghost" color="neutral" @click="dispatchOpen = false">取消</UButton>
            <UButton :loading="dispatching" :disabled="!form.user_id || !form.title || !form.due_date" @click="submitDispatch">派发</UButton>
          </div>
        </div>
      </template>
    </UModal>
```

- [ ] **Step 2：脚本：成员列表、维度库、派发逻辑**

在 `<script setup>` 加：

```ts
const priorityOptions = [
  { label: '高', value: 'high' },
  { label: '中', value: 'medium' },
  { label: '低', value: 'low' },
]
const dispatchOpen = ref(false)
const dispatching = ref(false)
const pool = ref<any[]>([])
const memberOptions = ref<{ label: string; value: number }[]>([])
const form = ref<any>({ user_id: null, title: '', due_date: '', priority: 'medium', description: '', review_dimensions: [] })

async function openDispatch() {
  form.value = { user_id: null, title: '', due_date: '', priority: 'medium', description: '', review_dimensions: [] }
  try {
    const cfg = await api<any>('/api/kpi/scoring-config/')
    pool.value = cfg.review_dimensions || []
    form.value.review_dimensions = JSON.parse(JSON.stringify(pool.value))
  } catch { pool.value = [] }
  if (!memberOptions.value.length) {
    const data = await api<any>('/api/users/?page_size=200')
    const users = (data.results || data || []) as any[]
    memberOptions.value = users.map(u => ({ label: u.name || u.username, value: u.id }))
  }
  dispatchOpen.value = true
}

async function submitDispatch() {
  dispatching.value = true
  try {
    await api('/api/kpi/tasks/dispatch/', {
      method: 'POST',
      body: {
        user_id: form.value.user_id,
        title: form.value.title.trim(),
        due_date: form.value.due_date,
        priority: form.value.priority,
        description: form.value.description,
        review_dimensions: form.value.review_dimensions,
      },
    })
    dispatchOpen.value = false
    toast.add({ title: '已派发', color: 'success' })
    await fetchPlans()
  } catch (e: any) {
    toast.add({ title: '派发失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    dispatching.value = false
  }
}
```

> 确认 `/api/users/` 列表字段含 `id`/`name`/`username`；若分页字段不同按实际调整。

- [ ] **Step 3：监督列替换奖赏列**

把 `columns`（第 191-198 行）的 `total_points`/`earned_points` 两列改为 `pending`/`reviewing`/`done`：

```ts
const columns = [
  { accessorKey: 'user', header: '成员' },
  { accessorKey: 'status', header: '状态' },
  { accessorKey: 'items_count', header: '任务数' },
  { accessorKey: 'reviewing', header: '待验收' },
  { accessorKey: 'done', header: '已完成' },
  { accessorKey: 'actions', header: '操作' },
]
```

删除模板里 `#total_points-cell` 与 `#earned_points-cell`，新增两个单元格模板（放在 `#items_count-cell` 之后）：

```vue
        <template #reviewing-cell="{ row }">
          <span class="text-amber-600 dark:text-amber-400">{{ r(row).reviewing ?? 0 }}</span>
        </template>
        <template #done-cell="{ row }">
          <span class="text-emerald-600 dark:text-emerald-400">{{ r(row).done ?? 0 }}</span>
        </template>
```

`PlanRow` 接口与 `tableRows` 映射相应把 `total_points`/`earned_points` 换成 `reviewing`/`done`。由于 `PlanListSerializer` 暂不返回这两个计数，先在 `fetchPlans` 后用计划详情或 0 占位——P0 简化：`reviewing`/`done` 暂取 `0`，并在 §10/P1 用后端补真实计数（本任务不阻塞）。

> **简化说明（必须 `log` 给用户）**：监督列的"待验收/已完成"计数 P0 先占位为 0，真实计数在 P1 由后端 `PlanListSerializer` 补充。

- [ ] **Step 4：验证**

Run: `cd frontend && npx nuxi typecheck`
Expected: 无新增类型错误。
手动 QA：管理者打开 `/app/ai/plans` → 点"派发任务" → 选人/填标题/选截止日期/调维度 → 派发 → 该成员当月计划出现新任务；员工端 `/app/ai/my-plan` 立即可见。

- [ ] **Step 5：提交**

```bash
git add frontend/app/pages/app/ai/plans/index.vue
git commit -m "feat(frontend): dispatch task modal + supervision columns"
```

---

### Task 13：点评页打分 `plans/[id].vue`

**Files:**
- Modify: `frontend/app/pages/app/ai/plans/[id].vue`

- [ ] **Step 1：把"质量系数"验收块换成维度打分 + 总评**

把第 143-174 行的验收块（质量系数下拉 + 已验收/未达成）替换为：

```vue
          <!-- 验收/评分（仅 submitted 状态） -->
          <div v-if="item.status === 'submitted'" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-3">
            <p class="text-xs font-medium text-gray-500 dark:text-gray-400">点评维度（可改）</p>
            <ReviewDimensionEditor v-model="item.review_dimensions" :pool="pool" />
            <div v-for="d in (item.review_dimensions || [])" :key="d.key" class="flex items-center gap-2">
              <span class="text-sm text-gray-600 dark:text-gray-400 w-24">{{ d.label }}</span>
              <UButton
                v-for="star in 5" :key="star"
                size="xs" variant="ghost" :color="(scoreDraft[item.id]?.[d.key] || 0) >= star ? 'warning' : 'neutral'"
                icon="i-heroicons-star-solid"
                @click="setStar(item.id, d.key, star)"
              />
            </div>
            <UTextarea v-model="commentDraft[item.id]" :rows="2" placeholder="总评（必填）" class="w-full" />
            <div class="flex items-center gap-2">
              <UButton size="xs" color="success" icon="i-heroicons-check-circle"
                :loading="verifyingIds.has(item.id)" @click="verifyItem(item.id, 'verified')">
                通过评分
              </UButton>
              <UButton size="xs" variant="outline" color="error" icon="i-heroicons-x-circle"
                :loading="verifyingIds.has(item.id)" @click="verifyItem(item.id, 'not_achieved')">
                未达成
              </UButton>
            </div>
          </div>
```

- [ ] **Step 2：脚本：维度库、打分草稿、改造 verifyItem**

在 `<script setup>` 加/改：

```ts
const pool = ref<any[]>([])
const scoreDraft = ref<Record<string, Record<string, number>>>({})
const commentDraft = ref<Record<string, string>>({})

function setStar(itemId: string, key: string, star: number) {
  if (!scoreDraft.value[itemId]) scoreDraft.value[itemId] = {}
  scoreDraft.value[itemId][key] = star
}
```

把 `verifyItem` 整个替换为：

```ts
async function verifyItem(itemId: string, status: string) {
  const item = editItems.value.find((i: any) => i.id === itemId)
  if (status === 'verified' && !commentDraft.value[itemId]?.trim()) {
    toast.add({ title: '请填写总评', color: 'warning' })
    return
  }
  verifyingIds.value = new Set([...verifyingIds.value, itemId])
  const body: any = { status }
  if (status === 'verified') {
    body.scores = scoreDraft.value[itemId] || {}
    body.review_comment = commentDraft.value[itemId]?.trim()
    body.review_dimensions = item?.review_dimensions || []
  }
  try {
    await api(`/api/kpi/action-items/${itemId}/verify/`, { method: 'POST', body })
    toast.add({ title: status === 'verified' ? '已评分' : '已标记未达成', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '操作失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    verifyingIds.value = new Set([...verifyingIds.value].filter(id => id !== itemId))
  }
}
```

在 `fetchPlan()` 成功后加载维度库（若 `pool` 为空）：

```ts
  if (!pool.value.length) {
    try { pool.value = (await api<any>('/api/kpi/scoring-config/')).review_dimensions || [] } catch { /* ignore */ }
  }
```

删除不再使用的 `verifyFactors`、`qualityFactorOptions` 及其初始化（第 290、309-314、364-369 行相关）。

> 这同时修掉了旧 bug：旧代码"未达成"传 `'failed'`，新 `verifyItem` 传 `'not_achieved'`，与后端一致。

- [ ] **Step 3：隐藏"积分"输入框**

删除第 127-131 行"积分"那一格 `<div class="space-y-1">…item.points…</div>`，把该行 grid 从 `grid-cols-3` 改为 `grid-cols-2`（保留 优先级、维度）。

- [ ] **Step 4：验证**

Run: `cd frontend && npx nuxi typecheck`
Expected: 无新增类型错误。
手动 QA：管理者进某计划详情 → submitted 任务出现维度星级打分 + 总评；不填总评点"通过评分"被拦；"未达成"可用（不再 400）。

- [ ] **Step 5：提交**

```bash
git add frontend/app/pages/app/ai/plans/[id].vue
git commit -m "feat(frontend): dimension star rating + review comment; fix not_achieved"
```

---

### Task 14：工作台「我的任务」待办 `home.vue`

**Files:**
- Modify: `frontend/app/pages/app/home.vue`

- [ ] **Step 1：把"我的提升计划"卡改成"我的任务"待办清单**

把第 132-150 行整张"我的提升计划"卡替换为：

```vue
        <!-- 我的任务 -->
        <div v-if="hasPlan" class="section-card">
          <div class="section-header">
            <h3 class="section-title">
              我的任务
              <span class="section-badge">{{ myTasks.length }}</span>
            </h3>
            <NuxtLink to="/app/ai/my-plan" class="section-link">查看全部</NuxtLink>
          </div>
          <div class="todo-list">
            <NuxtLink
              v-for="t in myTasks"
              :key="t.id"
              to="/app/ai/my-plan"
              class="todo-row"
            >
              <span class="dot" :class="taskDotClass(t.priority)" />
              <span class="todo-title">{{ t.title }}</span>
              <span
                v-if="t.due_date"
                class="todo-priority"
                :class="taskOverdue(t) ? 'todo-priority--urgent' : 'todo-priority--low'"
              >截止 {{ t.due_date }}</span>
            </NuxtLink>
          </div>
        </div>
```

- [ ] **Step 2：脚本：用 `myTasks` 取代 `planData`**

把 `planData` 相关替换。`fetchPlanSummary` 改为只取未完成任务（隐藏分数）：

```ts
const myTasks = ref<any[]>([])

async function fetchPlanSummary() {
  try {
    const res = await api<any>('/api/kpi/plans/me/')
    const items = res.current?.action_items || []
    myTasks.value = items
      .filter((i: any) => !['verified', 'not_achieved'].includes(i.status))
      .slice(0, 8)
  } catch { /* 无计划时跳过 */ }
}

function taskDotClass(priority: string): string {
  if (priority === 'high') return 'dot--high'
  if (priority === 'medium') return 'dot--mid'
  return 'dot--low'
}
function taskOverdue(t: any): boolean {
  if (!t.due_date) return false
  return new Date(t.due_date) < new Date(new Date().toDateString())
}
```

把 `hasPlan` 改为：

```ts
const hasPlan = computed(() => myTasks.value.length > 0)
```

删除模板里再无引用的 `planData` 定义（第 210 行）。`onMounted` 内仍调用 `fetchPlanSummary()`（已存在）。

- [ ] **Step 3：清理 CSS（可选）**

`plan-summary`/`plan-progress`/`plan-items`/`plan-item*` 样式块如不再被引用可删；不删不影响功能。

- [ ] **Step 4：验证**

Run: `cd frontend && npx nuxi typecheck`
Expected: 无新增类型错误。
手动 QA：被派发任务的员工登录 → 工作台出现"我的任务"卡，行样式同"我的待办"，显示截止日期、逾期标红、无任何分数；点击进 `/app/ai/my-plan`。

- [ ] **Step 5：提交**

```bash
git add frontend/app/pages/app/home.vue
git commit -m "feat(frontend): workbench 'my tasks' todo list (rewards hidden)"
```

---

### Task 15：导航文案

**Files:**
- Modify: `frontend/app/composables/useNavigation.ts`

- [ ] **Step 1：改文案**

把指向 `/app/ai/my-plan` 的导航项 label 由"我的提升计划"改为"我的任务"，指向 `/app/ai/plans` 的由"团队计划"改为"团队任务"（按文件中实际 label 文案查找替换；路由不变）。

- [ ] **Step 2：验证**

Run: `cd frontend && npx nuxi typecheck`
Expected: 无新增类型错误。
手动 QA：侧边栏文案更新为"我的任务""团队任务"。

- [ ] **Step 3：提交**

```bash
git add frontend/app/composables/useNavigation.ts
git commit -m "chore(frontend): nav labels to task wording"
```

---

## 收尾验证

- [ ] **后端全量：** `cd backend && uv run pytest -q` → 全绿（重点 `test_plan_api.py`、`test_plan_models.py`）。
- [ ] **前端类型：** `cd frontend && npx nuxi typecheck` → 无新增错误。
- [ ] **端到端手动 QA：** 管理者派发（带截止日期+维度）→ 员工工作台/我的任务可见 → 员工开始执行→提交（带说明）→ 管理者维度打分+总评→ 员工看到星级+总评；全程看不到任何"分/系数/段位"。
- [ ] **维度库：** Django admin 进 KPI 评分规则单例，能编辑 `review_dimensions` JSON；改动只影响新派发任务。

---

## Self-Review（计划 vs spec）

- **Spec §2 决策表**：复用底座(Task 1-9)、多维打分(Task 6/13)、维度库 admin(Task 1/8/9)、逐任务维度勾选+加+调权重(Task 10/12/13)、1-5 星(Task 13)、综合分加权平均(Task 2)、即时派发+月度归桶+必填截止日期(Task 5)、工作台(Task 14)、奖赏仅隐藏(Task 11/13/14) — 均有对应任务。✓
- **Spec §3/§4/§5**：模型字段/属性(Task 2/3)、序列化(Task 4)、派发(Task 5)、评分(Task 6)、提交反馈(Task 7)、配置(Task 8)、admin(Task 9)、前端 4 页+组件+导航(Task 10-15) — 全覆盖。✓
- **类型一致性**：后端字段名 `due_date/scores/review_comment/review_dimensions/reviewed_by/reviewed_at` 在 model→serializer→view→test 全一致；前端 `review_dimensions`/`scores` 字段名与后端一致；`verifyItem` 统一传 `not_achieved`。✓
- **已知简化（已在任务内标注需 `log`）**：监督列"待验收/已完成"计数 P0 占位为 0，真实计数列入 P1；评分→`quality_factor` 的隐藏反推映射本期不做（奖赏恢复时再加）。
- **占位符扫描**：无 TBD/TODO；每个改代码的步骤都给了完整代码或精确行号锚点。
