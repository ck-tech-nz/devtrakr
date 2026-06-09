from django.urls import path
from .views import (
    NotificationListView, NotificationDetailView, UnreadCountView,
    MarkReadView, MarkAllReadView,
    ManageListView, ManageDetailView, ManageCreateView, ManageUpdateView, ManagePublishView,
    BulletinActiveListView,
)

urlpatterns = [
    # User-facing (IsAuthenticated only)
    path("", NotificationListView.as_view(), name="notification-list"),
    path("unread-count/", UnreadCountView.as_view(), name="notification-unread-count"),
    path("<uuid:pk>/read/", MarkReadView.as_view(), name="notification-read"),
    path("read-all/", MarkAllReadView.as_view(), name="notification-read-all"),
    path("<uuid:pk>/", NotificationDetailView.as_view(), name="notification-detail"),
    # Admin manage (requires notifications permissions)
    path("manage/", ManageListView.as_view(), name="notification-manage-list"),
    path("manage/create/", ManageCreateView.as_view(), name="notification-manage-create"),
    path("manage/<uuid:pk>/", ManageDetailView.as_view(), name="notification-manage-detail"),
    path("manage/<uuid:pk>/update/", ManageUpdateView.as_view(), name="notification-manage-update"),
    path("manage/<uuid:pk>/publish/", ManagePublishView.as_view(), name="notification-manage-publish"),
    # Bulletins (header carousel)
    path("bulletins/active/", BulletinActiveListView.as_view(), name="bulletin-active"),
]
