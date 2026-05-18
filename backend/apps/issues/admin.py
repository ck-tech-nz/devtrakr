from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from unfold.admin import ModelAdmin
from .models import Issue, Activity, IssueAssignment


@admin.register(Issue)
class IssueAdmin(SimpleHistoryAdmin, ModelAdmin):
    list_display = ("id", "title", "priority", "status", "assignee", "created_by", "is_deleted", "created_at")
    list_filter = ("priority", "status", "is_deleted")
    search_fields = ("title",)
    history_list_display = ("status", "priority", "assignee", "title")

    def get_queryset(self, request):
        return Issue.all_objects.all()


@admin.register(Activity)
class ActivityAdmin(ModelAdmin):
    list_display = ("issue", "user", "action", "created_at")
    list_filter = ("action",)


@admin.register(IssueAssignment)
class IssueAssignmentAdmin(ModelAdmin):
    list_display = ("id", "issue", "action", "from_user", "to_user", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("issue__title", "to_user__username", "from_user__username")
    raw_id_fields = ("issue", "from_user", "to_user", "actor")
    readonly_fields = ("created_at",)
