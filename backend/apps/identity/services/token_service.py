"""
Token generation, verification, and rotation service enforcing SPEC DBDD §3, SDD §11.1, and SDD §100.
Access tokens: 15-minute JWTs bound to user, role, and active device registration.
Refresh tokens: 256-bit cryptographically secure random values stored as SHA-256 hashes,
with strict rotation and a 30-second replay grace window [REC, DEC-10].
"""
from datetime import timedelta
import hashlib
import secrets
from typing import Any
import jwt
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed
from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.core.error_codes import ErrorCodes
from apps.identity.models import DeviceRegistration, RefreshToken, User


def hash_token(raw_token: str) -> str:
    """Computes SHA-256 hash of a raw token string."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_access_token(user: User, role: str, device_registration: DeviceRegistration) -> str:
    """
    Generates a 15-minute HS256 JWT access token containing user_id, role,
    device_registration_id, issuer, and audience [SPEC SDD §11.1, §100].
    """
    now = clock.now()
    payload = {
        "user_id": user.user_id,
        "role": role,
        "device_registration_id": device_registration.device_registration_id,
        "device_id": device_registration.device_id,
        "iss": settings.SIMPLE_JWT.get("ISSUER", "mess-management-auth"),
        "aud": settings.SIMPLE_JWT.get("AUDIENCE", "mess-management-api"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "jti": secrets.token_hex(16),
    }

    signing_key = settings.SIMPLE_JWT.get("SIGNING_KEY")
    algorithm = settings.SIMPLE_JWT.get("ALGORITHM", "HS256")
    return jwt.encode(payload, signing_key, algorithm=algorithm)


def generate_refresh_token(
    user: User, device_registration: DeviceRegistration, platform: str
) -> tuple[str, RefreshToken]:
    """
    Generates a cryptographically random 256-bit refresh token and stores its hash.
    Lifetimes (DEC-10):
    - Mobile (ANDROID, IOS): 30 days
    - Web: 12 hours
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)

    now = clock.now()
    if platform.upper() == "WEB":
        expires_at = now + timedelta(hours=12)
    else:
        expires_at = now + timedelta(days=30)

    token_record = RefreshToken.objects.create(
        user=user,
        device_registration=device_registration,
        token_hash=token_hash,
        expires_at=expires_at,
        is_revoked=False,
    )
    return raw_token, token_record


def rotate_refresh_token(raw_token: str, correlation_id: str = "") -> dict[str, Any]:
    """
    Rotates a refresh token per SPEC DBDD §3 and DEC-10.
    Implements 30-second replay grace window for dropped network responses.
    Outside grace window, replaying a rotated token revokes the entire device chain and session.
    """
    if not raw_token:
        raise AuthenticationFailed(
            {"code": ErrorCodes.UNAUTHENTICATED, "message": "Refresh token is required."},
            code="token_required",
        )

    t_hash = hash_token(raw_token)
    now = clock.now()

    theft_detected = False
    with transaction.atomic():
        try:
            record = RefreshToken.objects.select_for_update().get(token_hash=t_hash)
        except RefreshToken.DoesNotExist:
            raise AuthenticationFailed(
                {"code": ErrorCodes.INVALID_TOKEN, "message": "Invalid refresh token."},
                code="invalid_token",
            )

        device = record.device_registration
        user = record.user

        # Invariant: Device session must be ACTIVE
        if device.session_status != "ACTIVE":
            raise AuthenticationFailed(
                {"code": ErrorCodes.DEVICE_REVOKED, "message": "Device session is not active."},
                code="device_revoked",
            )

        if user.status != "ACTIVE":
            raise AuthenticationFailed(
                {"code": ErrorCodes.UNAUTHENTICATED, "message": "User account is inactive or locked."},
                code="user_inactive",
            )

        if record.is_revoked:
            raise AuthenticationFailed(
                {"code": ErrorCodes.INVALID_TOKEN, "message": "Refresh token has been revoked."},
                code="token_revoked",
            )

        if record.expires_at <= now:
            raise AuthenticationFailed(
                {"code": ErrorCodes.TOKEN_EXPIRED, "message": "Refresh token has expired."},
                code="token_expired",
            )

        # Replay check: Token was already replaced
        if record.replaced_by_id is not None:
            grace_window_seconds = settings.SIMPLE_JWT.get("REFRESH_REPLAY_GRACE_SECONDS", 30)
            successor = record.replaced_by
            time_since_rotation = (now - successor.created_at).total_seconds()

            if time_since_rotation <= grace_window_seconds:
                # Inside grace window: Issue a fresh token pair without alarm
                from apps.identity.selectors import get_user_role

                role = get_user_role(user) or "STUDENT"
                new_raw_refresh, new_refresh_rec = generate_refresh_token(user, device, device.platform)
                successor.replaced_by = new_refresh_rec
                successor.save(update_fields=["replaced_by"])

                access_token = generate_access_token(user, role, device)
                return {
                    "access": access_token,
                    "refresh": new_raw_refresh,
                    "expires_in": 900,
                }

            # Outside grace window: Potential token theft! Revoke device and chain immediately
            device.session_status = "REVOKED"
            device.revoked_at = now
            device.revoke_reason = "TOKEN_REUSE_DETECTED"
            device.save(update_fields=["session_status", "revoked_at", "revoke_reason"])

            # Revoke all tokens for this device
            RefreshToken.objects.filter(device_registration=device).update(is_revoked=True)

            record_audit_event(
                event_type="TOKEN_REUSE_DETECTED",
                actor_user=user,
                device_registration=device,
                entity_type="DeviceRegistration",
                entity_id=device.device_registration_id,
                reason="Refresh token replayed outside 30s grace window",
                correlation_id=correlation_id,
            )
            record_audit_event(
                event_type="DEVICE_REVOKED",
                actor_user=user,
                device_registration=device,
                entity_type="DeviceRegistration",
                entity_id=device.device_registration_id,
                reason="TOKEN_REUSE_DETECTED",
                correlation_id=correlation_id,
            )
            theft_detected = True

        if not theft_detected:
            # Normal rotation: create new refresh token and link replaced_by
            from apps.identity.selectors import get_user_role

            role = get_user_role(user) or "STUDENT"
            new_raw_refresh, new_refresh_rec = generate_refresh_token(user, device, device.platform)

            record.replaced_by = new_refresh_rec
            record.save(update_fields=["replaced_by"])

            device.last_active_at = now
            device.save(update_fields=["last_active_at"])

            new_access_token = generate_access_token(user, role, device)

    if theft_detected:
        raise AuthenticationFailed(
            {
                "code": "TOKEN_REUSE_DETECTED",
                "message": "Token reuse detected. All sessions on this device have been revoked.",
            },
            code="token_reuse_detected",
        )

    return {
        "access": new_access_token,
        "refresh": new_raw_refresh,
        "expires_in": 900,
    }
