"""
Identity permissions and client application version policy enforcement.
Enforces DEC-18 (SUPPORTED, DEPRECATED, BLOCKED app version policies).
"""
from typing import Any
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from apps.config.models import ApplicationVersionPolicy
from apps.core.permissions import (  # re-export
    IsHostelClerk,
    IsMessManager,
    IsStudent,
    IsSuperAdmin,
)


class EnforceAppVersion(BasePermission):
    """
    Checks client version headers (X-App-Version and X-Platform) against ApplicationVersionPolicy.
    BLOCKED status refuses requests with 403 [DEC-18].
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        app_version = request.headers.get("X-App-Version")
        platform = request.headers.get("X-Platform", "").upper()

        if not app_version or not platform:
            # If not mobile headers (e.g. web browser or internal call), permit unless view demands mobile
            return True

        policy = ApplicationVersionPolicy.objects.filter(
            platform=platform,
            app_version=app_version,
        ).first()

        if policy and policy.status == "BLOCKED":
            msg = policy.force_update_message or "This application version is no longer supported. Please update."
            raise PermissionDenied(
                {"code": "APP_VERSION_BLOCKED", "message": msg},
                code="app_version_blocked",
            )

        return True
