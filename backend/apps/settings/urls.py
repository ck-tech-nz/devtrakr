from django.urls import path
from .views import SiteSettingsView, LabelSettingsView

urlpatterns = [
    path("", SiteSettingsView.as_view(), name="site-settings"),
    path("labels/", LabelSettingsView.as_view(), name="label-settings"),
]
