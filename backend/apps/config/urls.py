from django.urls import path
from apps.config.views import admin_settings_stub_view

urlpatterns = [
    path("settings", admin_settings_stub_view, name="admin_settings"),
]
