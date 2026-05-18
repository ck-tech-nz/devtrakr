from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMemberListCreateView,
    ProjectMemberDeleteView,
    ProjectIssuesView,
    ProjectMonitorsView,
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list"),
    path("<int:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<int:project_pk>/members/", ProjectMemberListCreateView.as_view(), name="project-members"),
    path("<int:project_pk>/members/<int:user_pk>/", ProjectMemberDeleteView.as_view(), name="project-member-delete"),
    path("<int:project_pk>/issues/", ProjectIssuesView.as_view(), name="project-issues"),
    path("<int:project_pk>/monitors/", ProjectMonitorsView.as_view(), name="project-monitors"),
]
