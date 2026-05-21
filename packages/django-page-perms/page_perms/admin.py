from django.contrib import admin
from .models import PageRoute


@admin.register(PageRoute)
class PageRouteAdmin(admin.ModelAdmin):
    list_display = (
        "path", "label", "is_group", "parent",
        "permission", "show_in_nav", "is_active", "sort_order", "source",
    )
    list_filter = ("is_group", "is_active", "show_in_nav", "source")
    search_fields = ("path", "label")
    list_select_related = ("parent", "permission__content_type")
    autocomplete_fields = ("parent",)
    fieldsets = (
        ("基础", {"fields": ("path", "label", "icon", "is_group")}),
        ("层级", {"fields": ("parent", "sort_order")}),
        ("权限/可见性", {"fields": ("permission", "show_in_nav", "is_active", "meta")}),
        ("来源", {"fields": ("source",)}),
    )
    readonly_fields = ("source",)
