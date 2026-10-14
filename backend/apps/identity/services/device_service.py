"""
Device registration and revocation service enforcing SPEC DBDD §3 and Owner Change D14.
"""
from typing import Any
from django.core.cache import cache
from rest_framework.exceptions import ValidationError
from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.core.exceptions import NotFoundError
from apps.identity.models import DeviceRegistration, RefreshToken, User
from apps.identity.selectors import get_user_role


def get_device_pending_sync_count(device: DeviceRegistration) -> int:
    """Returns the pending sync count reported by this device (cached from sync or model attribute)."""
    val = cache.get(f"device_pending_sync:{device.device_registration_id}")
    if val is not None:
        return int(val)
    return getattr(device, "pending_sync_count", 0)


def get_current_device_summary(device_registration: DeviceRegistration) -> dict[str, Any]:
    """Returns summary of current device binding and session state."""
    return {
        "device_registration_id": device_registration.device_registration_id,
        "device_id": device_registration.device_id,
        "platform": device_registration.platform,
        "app_version": device_registration.app_version,
        "device_name": device_registration.device_name,
        "session_status": device_registration.session_status,
        "registered_at": device_registration.registered_at,
        "last_active_at": device_registration.last_active_at,
    }


def update_device_metadata(
    device_registration: DeviceRegistration,
    app_version: str | None = None,
    device_name: str | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    """
    Updates client metadata for the currently authenticated device.
    Cannot activate new devices without credentials.
    """
    update_fields = ["last_active_at"]
    device_registration.last_active_at = clock.now()

    if app_version:
        device_registration.app_version = app_version
        update_fields.append("app_version")
    if device_name:
        device_registration.device_name = device_name
        update_fields.append("device_name")
    if platform and platform.upper() in ("ANDROID", "IOS", "WEB"):
        device_registration.platform = platform.upper()
        update_fields.append("platform")

    device_registration.save(update_fields=update_fields)
    return get_current_device_summary(device_registration)


def self_revoke_device(user: User, device_registration: DeviceRegistration, request=None) -> None:
    """Self-revokes the current authenticated device."""
    correlation_id = getattr(request, "correlation_id", "") if request else ""
    now = clock.now()

    device_registration.session_status = "REVOKED"
    device_registration.revoked_at = now
    device_registration.revoke_reason = "USER_SELF_REVOKE"
    device_registration.save(update_fields=["session_status", "revoked_at", "revoke_reason"])

    RefreshToken.objects.filter(device_registration=device_registration).update(is_revoked=True)

    record_audit_event(
        event_type="DEVICE_REVOKED",
        actor_user=user,
        device_registration=device_registration,
        entity_type="DeviceRegistration",
        entity_id=device_registration.device_registration_id,
        reason="USER_SELF_REVOKE",
        correlation_id=correlation_id,
    )


def admin_revoke_device(
    super_admin_user: User,
    device_registration_id: int,
    reason: str,
    request=None,
) -> dict[str, Any]:
    """
    Super Admin revokes a device session. Reason is mandatory [SPEC App Flow §15].
    Enforces Owner Change D14:
    - If Manager device has unsynced data, status moves to REVOKE_PENDING_SYNC.
    - Otherwise, immediately REVOKED and refresh tokens revoked.
    """
    if not reason or len(reason.strip()) < 5:
        raise ValidationError(
            {"code": "REASON_REQUIRED", "message": "A business reason of at least 5 characters is required."},
            code="reason_required",
        )

    try:
        device = DeviceRegistration.objects.select_related("user").get(
            device_registration_id=device_registration_id
        )
    except DeviceRegistration.DoesNotExist:
        raise NotFoundError("The specified device registration does not exist.")

    correlation_id = getattr(request, "correlation_id", "") if request else ""
    now = clock.now()
    target_user = device.user
    role = get_user_role(target_user)

    # Owner change D14 check: Manager device with unsynced data
    pending_sync_count = get_device_pending_sync_count(device)
    if role == "MESS_MANAGER" and pending_sync_count > 0:
        device.session_status = "REVOKE_PENDING_SYNC"
        device.revoke_reason = reason.strip()
        device.save(update_fields=["session_status", "revoke_reason"])

        record_audit_event(
            event_type="DEVICE_REVOKE_PENDING_SYNC",
            actor_user=super_admin_user,
            device_registration=device,
            entity_type="DeviceRegistration",
            entity_id=device.device_registration_id,
            reason=reason.strip(),
            metadata={"target_user": target_user.user_id, "pending_count": pending_sync_count},
            correlation_id=correlation_id,
        )
        return {
            "device_registration_id": device.device_registration_id,
            "session_status": "REVOKE_PENDING_SYNC",
            "message": "Device has unsynced transactions. Marked as REVOKE_PENDING_SYNC until sync completes.",
        }

    # Immediate revocation
    device.session_status = "REVOKED"
    device.revoked_at = now
    device.revoke_reason = reason.strip()
    device.save(update_fields=["session_status", "revoked_at", "revoke_reason"])

    RefreshToken.objects.filter(device_registration=device).update(is_revoked=True)

    record_audit_event(
        event_type="DEVICE_REVOKED",
        actor_user=super_admin_user,
        device_registration=device,
        entity_type="DeviceRegistration",
        entity_id=device.device_registration_id,
        reason=reason.strip(),
        metadata={"target_user": target_user.user_id},
        correlation_id=correlation_id,
    )

    return {
        "device_registration_id": device.device_registration_id,
        "session_status": "REVOKED",
        "message": "Device session successfully revoked.",
    }
