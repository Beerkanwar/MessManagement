"""
URL patterns for authentication, session lifecycle, and device management.
Enforces SPEC SDD §64 and Appendix A paths.
"""
from django.urls import path
from apps.identity.views import (
    admin_device_revoke_view,
    auth_me_view,
    change_password_view,
    device_current_view,
    device_register_view,
    device_revoke_view,
    forgot_password_view,
    login_view,
    logout_view,
    refresh_view,
    reset_password_view,
    verify_otp_view,
)

urlpatterns = [
    # Auth lifecycle endpoints
    path("auth/login", login_view, name="auth_login"),
    path("auth/refresh", refresh_view, name="auth_refresh"),
    path("auth/logout", logout_view, name="auth_logout"),
    path("auth/change-password", change_password_view, name="auth_change_password"),
    path("auth/forgot-password", forgot_password_view, name="auth_forgot_password"),
    path("auth/verify-otp", verify_otp_view, name="auth_verify_otp"),
    path("auth/reset-password", reset_password_view, name="auth_reset_password"),
    path("auth/me", auth_me_view, name="auth_me"),

    # Device lifecycle endpoints
    path("devices/current", device_current_view, name="devices_current"),
    path("devices/register", device_register_view, name="devices_register"),
    path("devices/revoke", device_revoke_view, name="devices_revoke"),

    # Admin device revocation
    path("admin/devices/<int:device_id>/revoke", admin_device_revoke_view, name="admin_device_revoke"),
]
