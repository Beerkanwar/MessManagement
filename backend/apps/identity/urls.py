"""
URL patterns for identity and devices.
"""
from django.urls import path
from apps.identity.views import login_stub_view, refresh_stub_view, device_current_stub_view

urlpatterns = [
    path("auth/login", login_stub_view, name="auth_login"),
    path("auth/refresh", refresh_stub_view, name="auth_refresh"),
    path("devices/current", device_current_stub_view, name="devices_current"),
]
