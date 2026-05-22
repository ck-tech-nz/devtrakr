from django.contrib import admin
from django.db.models import Case, IntegerField, When
from django.db.models.functions import Coalesce

from .models import PageRoute

try:
    from unfold.admin import ModelAdmin as BaseModelAdmin
except ImportError:
    BaseModelAdmin = admin.ModelAdmin


@admin.register(PageRoute)
class PageRouteAdmin(BaseModelAdmin):
    list_display = (
        "path", "description", "is_group",
        "permission", "show_in_nav", "is_active", "sort_order", "source",
    )
    list_filter = ("is_group", "is_active", "show_in_nav", "source")
    search_fields = ("path", "label")
    list_select_related = ("parent", "permission__content_type")
    autocomplete_fields = ("parent",)

    def description(self, obj):
        return f"{obj.parent.label} → {obj.label}" if obj.parent else obj.label
    description.short_description = "名称"


    def get_ordering(self, request):
        # 用 annotation 字段排序；类属性 ordering 会被 admin.E033 拒绝
        return ("-is_active", "_group_sort", "_is_child", "sort_order", "path")

    def get_search_results(self, request, queryset, search_term):
        queryset, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        # 父级菜单的 autocomplete 只能选分组（与 model clean() 校验一致）
        if request.GET.get("field_name") == "parent":
            queryset = queryset.filter(is_group=True)
        return queryset, may_have_duplicates

    @staticmethod
    def _annotate_ordering(qs):
        # 顶级项（含 group）用自己的 sort_order；子项继承父级 sort_order 聚类，并保证父先于子
        return qs.annotate(
            _group_sort=Coalesce("parent__sort_order", "sort_order"),
            _is_child=Case(
                When(parent__isnull=False, then=1),
                default=0,
                output_field=IntegerField(),
            ),
        )

    def get_queryset(self, request):
        # 不能直接 super().get_queryset()——它会在拿到的 qs 上立刻 order_by(self.get_ordering(...))，
        # 那时还没 annotate，"_group_sort" 会解析失败。所以先 annotate，再让 order_by 在 annotated qs 上跑。
        qs = self._annotate_ordering(self.model._default_manager.get_queryset())
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    def get_field_queryset(self, db, db_field, request):
        # change_view 通过此方法构造 parent (self-FK) 的 form field；
        # 默认实现会在裸 queryset 上 order_by(self.get_ordering(...))，annotation 字段会解析失败。
        if db_field.remote_field.model is PageRoute:
            manager = PageRoute._default_manager
            qs = manager.using(db).get_queryset() if db else manager.get_queryset()
            qs = self._annotate_ordering(qs)
            ordering = self.get_ordering(request)
            if ordering:
                qs = qs.order_by(*ordering)
            return qs
        return super().get_field_queryset(db, db_field, request)
    fieldsets = (
        ("基础", {"fields": ("path", "label", "icon", "is_group")}),
        ("层级", {"fields": ("parent", "sort_order")}),
        ("权限/可见性", {"fields": ("permission", "show_in_nav", "is_active", "meta")}),
        ("来源", {"fields": ("source",)}),
    )
    readonly_fields = ("source",)
