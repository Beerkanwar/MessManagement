"""
Password reset and initial password setup service enforcing SRS §5, SDD §12, DEC-03, and DEC-11.
Implements:
- forgot-password (always 202, 6-digit OTP, 10-minute expiry, Mailpit sink)
- verify-otp (rate-limited attempt counter, non-consuming check)
- reset-password (atomic password update, session revocation, PASSWORD_RESET audit)
"""
from datetime import timedelta
import hashlib
import secrets
from typing import Any
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, Throttled, ValidationError
from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.identity.models import DeviceRegistration, PasswordResetToken, RefreshToken, User

OTP_EXPIRY_MINUTES = 10  # DEC-11
OTP_MAX_ATTEMPTS = 5     # DEC-11
FORGOT_PASSWORD_HOURLY_LIMIT = 5


def hash_otp(raw_otp: str) -> str:
    """Computes SHA-256 hash of a 6-digit OTP code."""
    return hashlib.sha256(raw_otp.encode("utf-8")).hexdigest()


def request_password_reset(email: str, request=None) -> dict[str, str]:
    """
    Initiates password reset flow. Always returns HTTP 202 without revealing
    whether the user account exists.
    """
    normalized_email = email.strip().lower()

    # Hourly throttle: 5 requests per hour per email [DEC-11]
    cache_key = f"pwd_reset_rate:{normalized_email}"
    hourly_count = cache.get(cache_key, 0)
    if hourly_count >= FORGOT_PASSWORD_HOURLY_LIMIT:
        raise Throttled(
            wait=3600,
            detail={"code": "RATE_LIMIT_EXCEEDED", "message": "Too many password reset requests. Try again in an hour."},
        )
    cache.set(cache_key, hourly_count + 1, 3600)

    try:
        user = User.objects.get(normalized_email=normalized_email)
    except User.DoesNotExist:
        return {"message": "If an account with that email exists, an OTP has been dispatched."}

    if user.status != "ACTIVE":
        return {"message": "If an account with that email exists, an OTP has been dispatched."}

    now = clock.now()

    # Invalidate existing unused tokens for this user
    PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)

    # Generate 6-digit cryptographically secure OTP
    raw_otp = f"{secrets.randbelow(1000000):06d}"
    otp_h = hash_otp(raw_otp)

    # Generate random reset token to identify flow
    raw_token = secrets.token_urlsafe(32)
    t_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    PasswordResetToken.objects.create(
        user=user,
        token_hash=t_hash,
        otp_hash=otp_h,
        email=user.email,
        attempts=0,
        max_attempts=OTP_MAX_ATTEMPTS,
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        is_used=False,
    )

    # Dispatch email via Django backend (Mailpit in development)
    send_mail(
        subject="Hostel Mess Management - Your Password Reset OTP",
        message=f"Hello {user.full_name},\n\nYour 6-digit verification code is: {raw_otp}\nThis code will expire in 10 minutes.\nIf you did not request this, please ignore this email.",
        from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, "DEFAULT_FROM_EMAIL") else "no-reply@mess.local",
        recipient_list=[user.email],
        fail_silently=False,
    )

    return {"message": "If an account with that email exists, an OTP has been dispatched."}


def verify_password_reset_otp(email: str, otp: str) -> dict[str, Any]:
    """
    Verifies the submitted 6-digit OTP without consuming it.
    Increments attempt counter on failure; locks after 5 attempts.
    """
    normalized_email = email.strip().lower()
    now = clock.now()

    try:
        user = User.objects.get(normalized_email=normalized_email)
    except User.DoesNotExist:
        raise ValidationError({"code": "INVALID_OTP", "message": "Invalid OTP code or email."})

    token_rec = (
        PasswordResetToken.objects.filter(user=user, is_used=False)
        .order_by("-created_at")
        .first()
    )
    if not token_rec:
        raise ValidationError({"code": "INVALID_OTP", "message": "No active password reset request found."})

    if token_rec.attempts >= token_rec.max_attempts:
        raise ValidationError(
            {"code": "OTP_ATTEMPTS_EXCEEDED", "message": "Maximum OTP verification attempts exceeded. Request a new OTP."}
        )

    if token_rec.expires_at <= now:
        raise ValidationError({"code": "OTP_EXPIRED", "message": "The verification OTP has expired. Request a new OTP."})

    submitted_hash = hash_otp(otp.strip())
    if submitted_hash != token_rec.otp_hash:
        token_rec.attempts += 1
        token_rec.save(update_fields=["attempts"])
        remaining = token_rec.max_attempts - token_rec.attempts
        raise ValidationError(
            {
                "code": "INVALID_OTP",
                "message": f"Invalid verification code. {remaining} attempt(s) remaining.",
            }
        )

    return {
        "verified": True,
        "message": "OTP verified successfully. You may now submit your new password.",
    }


def reset_password(email: str, otp: str, new_password: str, request=None) -> None:
    """
    Completes password reset: verifies OTP, updates password, revokes all user sessions and refresh tokens,
    and records PASSWORD_RESET audit event [SPEC SDD §12].
    """
    correlation_id = getattr(request, "correlation_id", "") if request else ""
    normalized_email = email.strip().lower()
    now = clock.now()

    try:
        user = User.objects.get(normalized_email=normalized_email)
    except User.DoesNotExist:
        raise ValidationError({"code": "INVALID_OTP", "message": "Invalid email or OTP."})

    token_rec = (
        PasswordResetToken.objects.filter(user=user, is_used=False)
        .order_by("-created_at")
        .first()
    )
    if not token_rec:
        raise ValidationError({"code": "INVALID_OTP", "message": "No active password reset request found."})

    if token_rec.attempts >= token_rec.max_attempts:
        raise ValidationError({"code": "OTP_ATTEMPTS_EXCEEDED", "message": "Maximum attempts exceeded."})

    if token_rec.expires_at <= now:
        raise ValidationError({"code": "OTP_EXPIRED", "message": "OTP has expired."})

    if hash_otp(otp.strip()) != token_rec.otp_hash:
        token_rec.attempts += 1
        token_rec.save(update_fields=["attempts"])
        raise ValidationError({"code": "INVALID_OTP", "message": "Invalid verification code."})

    validate_password(new_password, user=user)

    with transaction.atomic():
        # Set new password
        user.set_password(new_password)
        user.save(update_fields=["password"])

        # Mark token used
        token_rec.is_used = True
        token_rec.save(update_fields=["is_used"])

        # Revoke all active devices and sessions for user [SPEC SDD §12]
        DeviceRegistration.objects.filter(user=user, session_status="ACTIVE").update(
            session_status="REVOKED",
            revoked_at=now,
            revoke_reason="PASSWORD_RESET",
        )
        RefreshToken.objects.filter(user=user).update(is_revoked=True)

        record_audit_event(
            event_type="PASSWORD_RESET",
            actor_user=user,
            entity_type="User",
            entity_id=user.user_id,
            reason="OTP_PASSWORD_RESET",
            metadata={"email": user.email},
            correlation_id=correlation_id,
        )
