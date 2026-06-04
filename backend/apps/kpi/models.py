import uuid

from django.conf import settings
from django.db import models
from solo.models import SingletonModel


# ---------------------------------------------------------------------------
# 评分配置（单例）
# ---------------------------------------------------------------------------

def _default_dimension_weights():
    return {
        "efficiency": 0.25,
        "output": 0.25,
        "quality": 0.25,
        "capability": 0.15,
        "growth": 0.10,
    }


def _default_efficiency_formula():
    return {
        "daily_resolved": 0.4,
        "speed": 0.4,
        "p0p1_speed": 0.2,
    }


def _default_output_formula():
    return {
        "weighted_issue_value": 0.4,
        "resolved_count": 0.3,
        "commit_volume": 0.2,
        "repo_breadth": 0.1,
    }


def _default_quality_formula():
    return {
        "inv_bug_rate": 0.30,
        "inv_churn_rate": 0.25,
        "commit_size": 0.20,
        "conventional_ratio": 0.25,
    }


def _default_capability_formula():
    return {
        "file_type_breadth": 0.25,
        "repo_coverage": 0.25,
        "p0_handling_ratio": 0.25,
        "helper_participation": 0.25,
    }


def _default_ceilings():
    return {
        "daily_resolved": 3.0,
        "avg_hours": 168.0,
        "p0p1_hours": 48.0,
        "weighted_value": 200.0,
        "resolved_count": 30.0,
        "commit_volume": 100.0,
        "repo_breadth": 5.0,
        "file_type": 8.0,
        "helper_count": 10.0,
    }


def _default_piece_rate_config():
    """Code Arena 工单计件与段位配置。

    - count_tiers: 按累计完成数量分段定价（小型工单走梯度）
    - hour_brackets: 单工单工时超过阈值时改用固定价（中/大型工单）
    - tier_thresholds: 综合分 → 段位
    - protection_days: 保护期天数（同问题在该窗口内复发记为重修）
    """
    return {
        "count_tiers": [
            {"max_count": 20, "price": 100},
            {"max_count": None, "price": 160},
        ],
        "hour_brackets": [
            {"min_hours": 4, "max_hours": 16, "price": 250, "label": "中型"},
            {"min_hours": 16, "max_hours": None, "price": 600, "label": "大型"},
        ],
        "tier_thresholds": {
            "bronze": 0,
            "silver": 50,
            "gold": 65,
            "platinum": 75,
            "diamond": 85,
            "master": 95,
        },
        "protection_days": 7,
    }


def _default_review_dimensions():
    """点评维度候选库/默认池。派发新任务时默认从此快照。"""
    return [
        {"key": "initiative", "label": "主动性", "weight": 0.25},
        {"key": "understanding", "label": "理解深度", "weight": 0.25},
        {"key": "quality", "label": "完成质量", "weight": 0.25},
        {"key": "delivery", "label": "交付与沟通", "weight": 0.25},
    ]


class KPIScoringConfig(SingletonModel):
    """KPI 评分规则配置（全局单例）。"""

    dimension_weights = models.JSONField(
        default=_default_dimension_weights,
        verbose_name="综合分维度权重",
        help_text="5 个维度在综合分中的权重，总和应为 1.0",
    )
    efficiency_formula = models.JSONField(
        default=_default_efficiency_formula,
        verbose_name="效率评分公式",
        help_text="效率维度各子指标权重",
    )
    output_formula = models.JSONField(
        default=_default_output_formula,
        verbose_name="产出评分公式",
        help_text="产出维度各子指标权重",
    )
    quality_formula = models.JSONField(
        default=_default_quality_formula,
        verbose_name="质量评分公式",
        help_text="质量维度各子指标权重",
    )
    capability_formula = models.JSONField(
        default=_default_capability_formula,
        verbose_name="能力评分公式",
        help_text="能力维度各子指标权重",
    )
    ceilings = models.JSONField(
        default=_default_ceilings,
        verbose_name="饱和天花板值",
        help_text="各指标达到满分 100 的阈值",
    )
    piece_rate_config = models.JSONField(
        default=_default_piece_rate_config,
        verbose_name="工单计件配置",
        help_text="Code Arena 工单单价梯度、工时分级、段位阈值与保护期",
    )
    review_dimensions = models.JSONField(
        default=_default_review_dimensions,
        verbose_name="点评维度库",
        help_text="点评维度候选库/默认池，每项 {key,label,weight}；派发新任务时默认从此填充，之后逐任务可改",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "KPI 评分规则"
        verbose_name_plural = "KPI 评分规则"

    def __str__(self):
        return "KPI 评分规则"


# ---------------------------------------------------------------------------
# KPI 快照
# ---------------------------------------------------------------------------

class KPISnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kpi_snapshots",
        verbose_name="用户",
    )
    period_start = models.DateField(verbose_name="统计起始日期")
    period_end = models.DateField(verbose_name="统计截止日期")
    issue_metrics = models.JSONField(default=dict, verbose_name="问题指标")
    commit_metrics = models.JSONField(default=dict, verbose_name="Commit 指标")
    workload_metrics = models.JSONField(default=dict, blank=True, verbose_name="工作量指标")
    scores = models.JSONField(default=dict, verbose_name="评分")
    rankings = models.JSONField(default=dict, verbose_name="排名")
    suggestions = models.JSONField(default=dict, verbose_name="改进建议")
    computed_at = models.DateTimeField(verbose_name="计算时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "KPI 快照"
        verbose_name_plural = "KPI 快照"
        unique_together = ("user", "period_start", "period_end")
        ordering = ["-period_end", "-computed_at"]
        permissions = [
            ("view_own_kpi", "Can view own KPI"),
            ("refresh_kpi", "Can refresh KPI data"),
        ]

    def __str__(self):
        return f"{self.user} | {self.period_start} ~ {self.period_end}"


# ---------------------------------------------------------------------------
# 提升计划
# ---------------------------------------------------------------------------

class ImprovementPlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草案"
        PUBLISHED = "published", "已发布"
        ARCHIVED = "archived", "已归档"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="improvement_plans", verbose_name="员工",
    )
    period = models.CharField(max_length=7, verbose_name="月度周期", help_text="格式: 2026-04")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, verbose_name="状态")
    source_kpi_scores = models.JSONField(default=dict, verbose_name="KPI 评分快照")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="创建人",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="审核人",
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="发布时间")
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="归档时间")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # —— LLM 月度小结：分析本月目标 + 各任务执行/自评/点评情况，整理汇总 ——
    # ai_summary 仅管理者可见、可编辑；employee_evaluation 为对员工公开的月度评价（可一键由小结复制而来）
    ai_summary = models.TextField(blank=True, default="", verbose_name="AI 月度小结")
    ai_summary_at = models.DateTimeField(null=True, blank=True, verbose_name="AI 小结生成时间")
    ai_summary_model = models.CharField(max_length=100, blank=True, default="", verbose_name="AI 小结所用模型")
    employee_evaluation = models.TextField(blank=True, default="", verbose_name="员工评价（对员工可见）")

    class Meta:
        verbose_name = "提升计划"
        verbose_name_plural = "提升计划"
        unique_together = ("user", "period")
        ordering = ["-period", "-created_at"]
        permissions = [
            ("view_own_plan", "Can view own improvement plan"),
        ]

    def __str__(self):
        return f"{self.user.name} | {self.period}"


class ActionItem(models.Model):
    class Source(models.TextChoices):
        AI = "ai_generated", "AI 生成"
        MANAGER = "manager_added", "管理员添加"

    class Priority(models.TextChoices):
        HIGH = "high", "高"
        MEDIUM = "medium", "中"
        LOW = "low", "低"

    class Status(models.TextChoices):
        PENDING = "pending", "待执行"
        IN_PROGRESS = "in_progress", "进行中"
        SUBMITTED = "submitted", "已提交"
        VERIFIED = "verified", "已验收"
        NOT_ACHIEVED = "not_achieved", "未达成"

    class NotAchievedReason(models.TextChoices):
        ABILITY = "ability", "能力/方法不足"
        EFFORT = "effort", "投入/主动性不够"
        UNREALISTIC = "unrealistic", "目标不合理"
        BLOCKED = "blocked", "外部阻塞"
        REPRIORITIZED = "reprioritized", "优先级调整"

    QUALITY_FACTORS = [("0.50", "0.5"), ("0.80", "0.8"), ("1.00", "1.0"), ("1.20", "1.2")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        ImprovementPlan, on_delete=models.CASCADE,
        related_name="action_items", verbose_name="所属计划",
    )
    source = models.CharField(max_length=15, choices=Source.choices, default=Source.MANAGER)
    dimension = models.CharField(max_length=20, default="general", verbose_name="KPI 维度")
    title = models.CharField(max_length=200, verbose_name="标题")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    measurable_target = models.CharField(max_length=200, blank=True, default="", verbose_name="可量化目标")
    points = models.PositiveIntegerField(default=10, verbose_name="分值")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    quality_factor = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, verbose_name="完成质量系数")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="排序")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateField(null=True, blank=True, verbose_name="截止日期")
    scores = models.JSONField(default=dict, blank=True, verbose_name="维度评分")  # {dim_key: 1..5}
    review_comment = models.TextField(blank=True, default="", verbose_name="总评")
    review_dimensions = models.JSONField(default=list, blank=True, verbose_name="本任务维度")  # [{key,label,weight}]
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="评分人",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="评分时间")
    # —— 立计划（开始执行时填写，制造承诺）——
    start_plan = models.TextField(blank=True, default="", verbose_name="执行计划")  # 我打算怎么做
    self_eta = models.DateField(null=True, blank=True, verbose_name="自评预计完成日期")
    # —— 员工自评（提交时填写，用于"自评 vs 他评"落差，驱动自我觉察）——
    self_scores = models.JSONField(default=dict, blank=True, verbose_name="自评评分")  # {dim_key: 1..5}
    self_assessment = models.TextField(blank=True, default="", verbose_name="自评复盘")  # 思考与判断/对 AI 输出的分析
    self_assessed_at = models.DateTimeField(null=True, blank=True, verbose_name="自评时间")
    # —— 未达成归因 + 闭环（员工确认 + 改进承诺）——
    not_achieved_reason = models.CharField(
        max_length=20, choices=NotAchievedReason.choices, blank=True, default="", verbose_name="未达成归因")
    carried_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="carried_to", verbose_name="顺延自")
    acknowledged = models.BooleanField(default=False, verbose_name="员工已确认")
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    improve_note = models.TextField(blank=True, default="", verbose_name="改进措施")

    class Meta:
        verbose_name = "行动项"
        verbose_name_plural = "行动项"
        ordering = ["sort_order", "-priority", "created_at"]

    def __str__(self):
        return self.title

    @property
    def earned_points(self) -> int:
        if self.status == self.Status.VERIFIED and self.quality_factor:
            return round(self.points * float(self.quality_factor))
        return 0

    @property
    def overall_score(self):
        """按本任务自己的 review_dimensions 权重对已打分维度加权平均（1-5）；未打分返回 None。"""
        if not self.scores:
            return None
        dims = {d["key"]: float(d.get("weight", 0)) for d in (self.review_dimensions or []) if isinstance(d, dict) and "key" in d}
        den = sum(dims.get(k, 0) for k in self.scores)
        if dims and den:
            num = sum(float(v) * dims.get(k, 0) for k, v in self.scores.items())
            return round(num / den, 1)
        vals = [float(v) for v in self.scores.values()]  # 无权重信息 → 等权平均
        return round(sum(vals) / len(vals), 1)

    @property
    def self_overall_score(self):
        """员工自评的加权综合分（1-5）；未自评返回 None。逻辑同 overall_score。"""
        if not self.self_scores:
            return None
        dims = {d["key"]: float(d.get("weight", 0)) for d in (self.review_dimensions or []) if isinstance(d, dict) and "key" in d}
        den = sum(dims.get(k, 0) for k in self.self_scores)
        if dims and den:
            num = sum(float(v) * dims.get(k, 0) for k, v in self.self_scores.items())
            return round(num / den, 1)
        vals = [float(v) for v in self.self_scores.values()]
        return round(sum(vals) / len(vals), 1)


class ActionItemComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_item = models.ForeignKey(
        ActionItem, on_delete=models.CASCADE,
        related_name="comments", verbose_name="行动项",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="+", verbose_name="作者",
    )
    content = models.TextField(verbose_name="内容")
    attachment_url = models.URLField(blank=True, default="", verbose_name="附件 URL")
    attachment_key = models.CharField(max_length=200, blank=True, default="", verbose_name="附件 Key")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "行动项评论"
        verbose_name_plural = "行动项评论"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author.name}: {self.content[:30]}"
