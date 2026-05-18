from django.urls import path
from .views import UptimeMonitorDetailView, UptimeMonitorChecksView

urlpatterns = [
    path("monitors/<int:pk>/", UptimeMonitorDetailView.as_view(), name="uptime-monitor-detail"),
    path("monitors/<int:pk>/checks/", UptimeMonitorChecksView.as_view(), name="uptime-monitor-checks"),
]
