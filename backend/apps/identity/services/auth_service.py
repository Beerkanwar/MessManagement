"""
Authentication service enforcing SPEC DBDD §3, SDD §11, and SDD §100.
Implements:
- Argon2id password validation and dummy-hash timing attack prevention
- Single active device per user with atomic session replacement
- Surface access validation (Mobile: Student, Manager; Web: Clerk, Super Admin)
- Login throttling via shared cache (5 failures in 15 min [DEC-11])
- Manager unsynced transaction lock check [DEC-14, D14]
- Audit events: LOGIN_SUCCESS, LOGIN_FAILURE, DEVICE_REGISTERED, DEVICE_REVOKED
"""
from typing import Any
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, Throttled, ValidationError
from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.core.error_codes import ErrorCodes
from apps.core.exceptions import ConflictError
from apps.identity.models import DeviceRegistration, RefreshToken, User
from apps.identity.selectors import get_user_assignment_summary, get_user_role
from apps.identity.services.device_service import get_device_pending_sync_count
from apps.identity.services.token_service import generate_access_token, generate_refresh_token

# Dummy hash for timing attack mitigation on non-existent accounts
DUMMY_PASSWORD_HASH = make_password("AntigravityTimingMitigationDummyPassword123!")

LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 900  # 15 minutes per DEC-11


def get_client_ip(request) -> str:
    """Extracts client IP address safely from request headers."""
    if not request:
        return "127.0.0.1"
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


def check_login_throttle(email: str, ip: str) -> None:
    """Checks if email or IP address has exceeded failed login threshold."""
    ip_key = f"login_fails_ip:{ip}"
    email_key = f"login_fails_email:{email}"

    ip_fails = cache.get(ip_key, 0)
    email_fails = cache.get(email_key, 0)

    if ip_fails >= LOGIN_MAX_FAILURES or email_fails >= LOGIN_MAX_FAILURES:
        raise Throttled(
            wait=LOGIN_LOCKOUT_SECONDS,
            detail="Too many failed login attempts. Account temporarily locked for 15 minutes.",
        )


def increment_login_failure(email: str, ip: str) -> None:
    """Increments failure counters for email and IP address."""
    ip_key = f"login_fails_ip:{ip}"
    email_key = f"login_fails_email:{email}"

    ip_count = cache.get(ip_key, 0) + 1
    email_count = cache.get(email_key, 0) + 1

    cache.set(ip_key, ip_count, LOGIN_LOCKOUT_SECONDS)
    cache.set(email_key, email_count, LOGIN_LOCKOUT_SECONDS)


def clear_login_failure(email: str, ip: str) -> None:
    """Clears failure counters upon successful authentication."""
    cache.delete(f"login_fails_ip:{ip}")
    cache.delete(f"login_fails_email:{email}")


def login_user(
    email: str,
    password: str,
    device_id: str,
    platform: str,
    app_version: str = "",
    device_name: str = "",
    request=None,
) -> dict[str, Any]:
    """
    Authenticates user, binds active device, and returns token pair and user profile.
    Enforces surface authorization and single active device invariant.
    """
    correlation_id = getattr(request, "correlation_id", "") if request else ""
    client_ip = get_client_ip(request)
    normalized_email = email.strip().lower()

    # 1. Throttling check
    check_login_throttle(normalized_email, client_ip)

    # 2. Lookup user
    try:
        user = User.objects.get(normalized_email=normalized_email)
        user_exists = True
    except User.DoesNotExist:
        user = None
        user_exists = False

    # Timing attack protection: run Argon2id check even when user does not exist
    if not user_exists:
        check_password(password, DUMMY_PASSWORD_HASH)
        increment_login_failure(normalized_email, client_ip)
        record_audit_event(
            event_type="LOGIN_FAILURE",
            entity_type="User",
            entity_id=normalized_email,
            reason="INVALID_CREDENTIALS",
            metadata={"ip": client_ip, "platform": platform},
            correlation_id=correlation_id,
        )
        raise AuthenticationFailed(
            {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."},
            code="invalid_credentials",
        )

    # Check password
    if not user.check_password(password):
        increment_login_failure(normalized_email, client_ip)
        record_audit_event(
            event_type="LOGIN_FAILURE",
            actor_user=user,
            entity_type="User",
            entity_id=user.user_id,
            reason="INVALID_CREDENTIALS",
            metadata={"ip": client_ip, "platform": platform},
            correlation_id=correlation_id,
        )
        raise AuthenticationFailed(
            {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."},
            code="invalid_credentials",
        )

    # Check account status
    if user.status != "ACTIVE":
        record_audit_event(
            event_type="LOGIN_FAILURE",
            actor_user=user,
            entity_type="User",
            entity_id=user.user_id,
            reason=f"ACCOUNT_{user.status}",
            metadata={"ip": client_ip},
            correlation_id=correlation_id,
        )
        raise AuthenticationFailed(
            {"code": "ACCOUNT_INACTIVE", "message": f"User account is {user.status.lower()}."},
            code="account_inactive",
        )

    # Look up role
    role = get_user_role(user)
    if not role:
        raise AuthenticationFailed(
            {"code": "NO_ROLE_ASSIGNED", "message": "User has no active application role assigned."},
            code="no_role",
        )

    # 3. Surface authorization check [SPEC App Flow §1, ImplementationGuide Phase 3 Table line 282]
    # Mobile (ANDROID, IOS): Student, Mess Manager
    # Web (WEB): Hostel Clerk, Super Admin
    platform_norm = platform.upper()
    if platform_norm in ("ANDROID", "IOS"):
        if role not in ("STUDENT", "MESS_MANAGER"):
            record_audit_event(
                event_type="LOGIN_FAILURE",
                actor_user=user,
                entity_type="User",
                entity_id=user.user_id,
                reason="WRONG_CLIENT",
                metadata={"role": role, "platform": platform_norm},
                correlation_id=correlation_id,
            )
            raise PermissionDenied(
                {
                    "code": ErrorCodes.WRONG_CLIENT,
                    "message": "Staff roles (Hostel Clerk, Super Admin) must sign in using the web application.",
                },
                code="wrong_client",
            )
    elif platform_norm == "WEB":
        if role not in ("HOSTEL_CLERK", "SUPER_ADMIN"):
            record_audit_event(
                event_type="LOGIN_FAILURE",
                actor_user=user,
                entity_type="User",
                entity_id=user.user_id,
                reason="WRONG_CLIENT",
                metadata={"role": role, "platform": platform_norm},
                correlation_id=correlation_id,
            )
            raise PermissionDenied(
                {
                    "code": ErrorCodes.WRONG_CLIENT,
                    "message": "Students and Mess Managers must sign in using the mobile application.",
                },
                code="wrong_client",
            )

    # 4. Check Owner Change D14 (Mess Managers only):
    # If the device being replaced still reports unsynced transactions, the new login is refused
    if role == "MESS_MANAGER":
        old_active_device = (
            DeviceRegistration.objects.filter(user=user, session_status="ACTIVE")
            .exclude(device_id=device_id)
            .first()
        )
        if old_active_device:
            # Check if old device is in or moves to REVOKE_PENDING_SYNC
            pending_count = get_device_pending_sync_count(old_active_device)
            if pending_count and pending_count > 0:
                old_active_device.session_status = "REVOKE_PENDING_SYNC"
                old_active_device.save(update_fields=["session_status"])
                record_audit_event(
                    event_type="DEVICE_REVOKE_PENDING_SYNC",
                    actor_user=user,
                    device_registration=old_active_device,
                    entity_type="DeviceRegistration",
                    entity_id=old_active_device.device_registration_id,
                    reason="Login from new device refused while unsynced transactions remain",
                    correlation_id=correlation_id,
                )
                raise ConflictError(
                    code=ErrorCodes.DEVICE_REVOKE_PENDING_SYNC,
                    message="Previous manager device has unsynchronized transactions pending. Sync previous device before switching.",
                )

    # 5. Single active device atomic replacement transaction
    now = clock.now()
    with transaction.atomic():
        # Lock user record
        User.objects.select_for_update().get(user_id=user.user_id)

        # Mark other ACTIVE registrations REPLACED
        replaced_devices = DeviceRegistration.objects.filter(
            user=user, session_status="ACTIVE"
        ).exclude(device_id=device_id)

        for old_dev in replaced_devices:
            old_dev.session_status = "REPLACED"
            old_dev.revoked_at = now
            old_dev.revoke_reason = "NEW_DEVICE_LOGIN"
            old_dev.save(update_fields=["session_status", "revoked_at", "revoke_reason", "version"])

            # Revoke refresh tokens of replaced device
            RefreshToken.objects.filter(device_registration=old_dev).update(is_revoked=True)

            record_audit_event(
                event_type="DEVICE_REVOKED",
                actor_user=user,
                device_registration=old_dev,
                entity_type="DeviceRegistration",
                entity_id=old_dev.device_registration_id,
                reason="NEW_DEVICE_LOGIN",
                correlation_id=correlation_id,
            )

        # Create or activate current device registration
        device_reg = DeviceRegistration.objects.filter(user=user, device_id=device_id).first()
        if device_reg:
            device_reg.platform = platform_norm
            device_reg.app_version = app_version
            device_reg.device_name = device_name
            device_reg.session_status = "ACTIVE"
            device_reg.last_active_at = now
            device_reg.revoked_at = None
            device_reg.revoke_reason = ""
            device_reg.save()
        else:
            device_reg = DeviceRegistration.objects.create(
                user=user,
                device_id=device_id,
                platform=platform_norm,
                app_version=app_version,
                device_name=device_name,
                session_status="ACTIVE",
                registered_at=now,
                last_active_at=now,
            )

        record_audit_event(
            event_type="DEVICE_REGISTERED",
            actor_user=user,
            device_registration=device_reg,
            entity_type="DeviceRegistration",
            entity_id=device_reg.device_registration_id,
            metadata={"platform": platform_norm, "app_version": app_version},
            correlation_id=correlation_id,
        )

        # Issue tokens
        access_token = generate_access_token(user, role, device_reg)
        raw_refresh, _ = generate_refresh_token(user, device_reg, platform_norm)

        # Update last login
        user.last_login = now
        user.save(update_fields=["last_login"])

        record_audit_event(
            event_type="LOGIN_SUCCESS",
            actor_user=user,
            device_registration=device_reg,
            entity_type="User",
            entity_id=user.user_id,
            metadata={"platform": platform_norm, "role": role},
            correlation_id=correlation_id,
        )

    # Clear failure counters on success
    clear_login_failure(normalized_email, client_ip)

    return {
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "full_name": user.full_name,
        },
        "role": role,
        "assignment": get_user_assignment_summary(user),
        "device": {
            "device_registration_id": device_reg.device_registration_id,
            "device_id": device_reg.device_id,
            "platform": device_reg.platform,
            "session_status": device_reg.session_status,
        },
        "tokens": {
            "access": access_token,
            "refresh": raw_refresh,
            "expires_in": 900,
        },
    }


def logout_user(user: User, device_registration: DeviceRegistration, request=None) -> None:
    """Revokes the current device session and refresh tokens immediately."""
    correlation_id = getattr(request, "correlation_id", "") if request else ""
    now = clock.now()

    device_registration.session_status = "LOGGED_OUT"
    device_registration.revoked_at = now
    device_registration.revoke_reason = "LOGOUT"
    device_registration.save(update_fields=["session_status", "revoked_at", "revoke_reason"])

    RefreshToken.objects.filter(device_registration=device_registration).update(is_revoked=True)

    record_audit_event(
        event_type="DEVICE_REVOKED",
        actor_user=user,
        device_registration=device_registration,
        entity_type="DeviceRegistration",
        entity_id=device_registration.device_registration_id,
        reason="LOGOUT",
        correlation_id=correlation_id,
    )


def change_password(user: User, current_password: str, new_password: str, request=None) -> None:
    """Changes password for authenticated user and audits the event."""
    correlation_id = getattr(request, "correlation_id", "") if request else ""

    if not user.check_password(current_password):
        raise ValidationError(
            {"code": "INVALID_CURRENT_PASSWORD", "message": "Current password is incorrect."},
            code="invalid_password",
        )

    validate_password(new_password, user=user)

    user.set_password(new_password)
    user.save(update_fields=["password"])

    record_audit_event(
        event_type="PASSWORD_RESET",
        actor_user=user,
        entity_type="User",
        entity_id=user.user_id,
        reason="PASSWORD_CHANGED",
        metadata={"kind": "CHANGE"},
        correlation_id=correlation_id,
    )
