from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import Project, ProjectMember


class ProjectMemberInline(TabularInline):
    model = ProjectMember
    extra = 1
    fields = ("user", "is_manager")
    list_editable = ("is_manager",)


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ("name", "status", "created_at")
    inlines = [ProjectMemberInline]
