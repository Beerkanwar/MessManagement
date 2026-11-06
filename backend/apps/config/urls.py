"""
URL patterns for configuration and app version policy endpoints — Phase 5.
Mounted under /api/v1/admin/
"""
from django.urls import path
from apps.config import views

urlpatterns = [
    path("settings", views.settings_list_update_view, name="admin_settings"),
    path("app-versions", views.app_version_policy_list_create_view, name="admin_app_versions"),
    path("app-versions/<int:policy_id>", views.app_version_policy_detail_view, name="admin_app_version_detail"),
]
