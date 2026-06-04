from rest_framework import serializers
from .models import ImprovementPlan, ActionItem, ActionItemComment


class ActionItemCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.name", read_only=True)
    author_avatar = serializers.CharField(source="author.avatar", default="", read_only=True)

    class Meta:
        model = ActionItemComment
        fields = [
            "id", "author", "author_name", "author_avatar",
            "content", "attachment_url", "created_at",
        ]
        read_only_fields = ["id", "author", "author_name", "author_avatar", "created_at"]


class ActionItemSerializer(serializers.ModelSerializer):
    earned_points = serializers.IntegerField(read_only=True)
    overall_score = serializers.FloatField(read_only=True)
    self_overall_score = serializers.FloatField(read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.name", default="", read_only=True)
    not_achieved_reason_display = serializers.CharField(source="get_not_achieved_reason_display", default="", read_only=True)
    was_carried_over = serializers.SerializerMethodField()
    comments = ActionItemCommentSerializer(many=True, read_only=True)

    def get_was_carried_over(self, obj):
        return obj.carried_to.exists()

    class Meta:
        model = ActionItem
        fields = [
            "id", "source", "dimension", "title", "description",
            "measurable_target", "points", "priority", "status",
            "quality_factor", "earned_points", "sort_order",
            "due_date", "scores", "review_comment", "review_dimensions",
            "overall_score", "reviewed_by", "reviewed_by_name", "reviewed_at",
            "self_scores", "self_assessment", "self_assessed_at", "self_overall_score",
            "start_plan", "self_eta",
            "not_achieved_reason", "not_achieved_reason_display", "was_carried_over",
            "acknowledged", "acknowledged_at", "improve_note",
            "comments", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "source", "earned_points", "overall_score",
            "reviewed_by", "reviewed_by_name", "reviewed_at",
            "self_scores", "self_assessment", "self_assessed_at", "self_overall_score",
            "start_plan", "self_eta",
            "not_achieved_reason", "not_achieved_reason_display", "was_carried_over",
            "acknowledged", "acknowledged_at", "improve_note",
            "created_at", "updated_at",
        ]


class ActionItemBriefSerializer(serializers.ModelSerializer):
    """行动项简要信息（用于计划列表和工作台）。"""
    earned_points = serializers.IntegerField(read_only=True)

    class Meta:
        model = ActionItem
        fields = ["id", "title", "points", "priority", "status", "earned_points", "dimension"]


class PlanDetailSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_avatar = serializers.CharField(source="user.avatar", default="", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.name", default="", read_only=True)
    action_items = ActionItemSerializer(many=True, read_only=True)
    total_points = serializers.SerializerMethodField()
    earned_points = serializers.SerializerMethodField()

    class Meta:
        model = ImprovementPlan
        fields = [
            "id", "user", "user_name", "user_avatar", "period", "status",
            "source_kpi_scores", "reviewed_by", "reviewed_by_name",
            "published_at", "archived_at", "action_items",
            "total_points", "earned_points", "created_at", "updated_at",
            "ai_summary", "ai_summary_at", "ai_summary_model", "employee_evaluation",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # AI 小结仅管理者可见；员工视角（无 manager context）一律剔除
        if not self.context.get("manager"):
            for f in ("ai_summary", "ai_summary_at", "ai_summary_model"):
                data.pop(f, None)
        return data

    def get_total_points(self, obj):
        return sum(item.points for item in obj.action_items.all())

    def get_earned_points(self, obj):
        return sum(item.earned_points for item in obj.action_items.all())


class PlanListSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_avatar = serializers.CharField(source="user.avatar", default="", read_only=True)
    item_count = serializers.SerializerMethodField()
    total_points = serializers.SerializerMethodField()
    earned_points = serializers.SerializerMethodField()
    reviewing_count = serializers.SerializerMethodField()
    done_count = serializers.SerializerMethodField()

    class Meta:
        model = ImprovementPlan
        fields = [
            "id", "user", "user_name", "user_avatar", "period", "status",
            "item_count", "total_points", "earned_points",
            "reviewing_count", "done_count",
            "published_at", "created_at",
        ]
        read_only_fields = fields

    def get_item_count(self, obj):
        return len(obj.action_items.all())  # 复用 prefetch 缓存，避免额外 COUNT 查询

    def get_total_points(self, obj):
        return sum(item.points for item in obj.action_items.all())

    def get_earned_points(self, obj):
        return sum(item.earned_points for item in obj.action_items.all())

    def get_reviewing_count(self, obj):
        return sum(1 for i in obj.action_items.all() if i.status == "submitted")

    def get_done_count(self, obj):
        return sum(1 for i in obj.action_items.all() if i.status == "verified")
