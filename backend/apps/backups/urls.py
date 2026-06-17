from django.urls import path

from apps.backups.views import (
    BackupTargetListCreateView, BackupTargetDetailView, BackupTargetRunView,
    BackupListView, BackupDownloadView, BackupDeleteView,
)

urlpatterns = [
    path("targets/", BackupTargetListCreateView.as_view(), name="backup-target-list"),
    path("targets/<int:pk>/", BackupTargetDetailView.as_view(), name="backup-target-detail"),
    path("targets/<int:pk>/run/", BackupTargetRunView.as_view(), name="backup-target-run"),
    path("backups/", BackupListView.as_view(), name="backup-list"),
    path("backups/<int:pk>/download/", BackupDownloadView.as_view(), name="backup-download"),
    path("backups/<int:pk>/", BackupDeleteView.as_view(), name="backup-delete"),
]
