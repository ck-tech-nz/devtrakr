from django.urls import path, include

from apps.settings.about_views import AboutView

urlpatterns = [
    path("auth/", include("apps.users.auth_urls")),
    path("settings/", include("apps.settings.urls")),
    path("users/", include("apps.users.urls")),
    path("projects/", include("apps.projects.urls")),
    path("issues/", include("apps.issues.urls")),
    path("dashboard/", include("apps.issues.dashboard_urls")),
    path("repos/", include("apps.repos.urls")),
    path("ai/", include("apps.ai.urls")),
    path("tools/", include("apps.tools.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("uptime/", include("apps.uptime.urls")),
    path("kpi/", include("apps.kpi.urls")),
    path("page-perms/", include("page_perms.urls")),
    path("external/", include("apps.external.urls")),
    path("about/", AboutView.as_view(), name="about"),
]
