from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMemberListCreateView,
    ProjectMemberDetailView,
    ProjectMemberRoleChoicesView,
    ProjectIssuesView,
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list"),
    path("role-choices/", ProjectMemberRoleChoicesView.as_view(), name="project-role-choices"),
    path("<int:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<int:project_pk>/members/", ProjectMemberListCreateView.as_view(), name="project-members"),
    path("<int:project_pk>/members/<int:user_pk>/", ProjectMemberDetailView.as_view(), name="project-member-detail"),
    path("<int:project_pk>/issues/", ProjectIssuesView.as_view(), name="project-issues"),
]
