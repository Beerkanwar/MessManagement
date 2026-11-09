"""
System configuration services — Phase 5.
Implements:
- Registry of institutional SystemSetting parameters (Appendix B2, DEC-11, DEC-06, DEC-07).
- Effective-dated SystemSetting reads/writes (never edits history, audited, sensitive masking).
- In-memory per-request/short-TTL setting cache with typed getters.
- ApplicationVersionPolicy CRUD.
"""
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_audit_event
from apps.config.models import ApplicationVersionPolicy, SystemSetting
from apps.core.clock import clock
from apps.core.concurrency import check_optimistic_lock
from apps.core.exceptions import ConflictError, NotFoundError, ValidationError
from apps.identity.models import User

# (data_type, default_value, description, is_sensitive)
CONFIG_REGISTRY: dict[str, tuple[str, str, str, bool]] = {
    # DEC-11 Institutional Parameters
    "auth.password.min_length": ("INTEGER", "10", "Minimum length for user passwords", False),
    "auth.otp.length": ("INTEGER", "6", "Number of digits in password reset OTP", False),
    "auth.otp.validity_minutes": ("INTEGER", "10", "Validity duration of password reset OTP in minutes", False),
    "auth.otp.max_attempts": ("INTEGER", "5", "Maximum failed OTP attempts before invalidation", False),
    "auth.otp.resend_cooldown_seconds": ("INTEGER", "60", "Cooldown period between OTP resend requests in seconds", False),
    "auth.otp.max_per_hour_per_email": ("INTEGER", "5", "Maximum OTP requests per email per hour", False),
    "auth.login.max_failures": ("INTEGER", "5", "Failed login attempts before temporary lockout", False),
    "auth.login.lockout_minutes": ("INTEGER", "15", "Lockout duration after repeated failed logins in minutes", False),
    "attendance.correction_window_hours": ("INTEGER", "48", "Window after MealDate within which corrections may be submitted", False),
    "time.trusted_anchor_max_age_hours": ("INTEGER", "48", "Maximum age of trusted-time server anchor before expiry", False),
    "time.trusted_anchor_expiring_hours": ("INTEGER", "6", "Window before expiry when trusted-time enters EXPIRING state", False),
    "qr.step_seconds": ("INTEGER", "30", "Time-step interval for dynamic QR HMAC counter in seconds", False),
    "qr.window_steps": ("INTEGER", "1", "Verification step window tolerance (±1 step)", False),
    "offline.normal_hours": ("INTEGER", "24", "Normal allowed offline operational duration in hours", False),
    "offline.grace_hours": ("INTEGER", "24", "Additional grace period for offline operation in hours", False),
    "sync.batch_max_transactions": ("INTEGER", "500", "Maximum transactions accepted per sync batch [D11]", False),
    "sync.overlap_minutes": ("INTEGER", "2", "Overlap window before the cursor issue time for late commits", False),
    "sync.student_page_size": ("INTEGER", "500", "Students per bootstrap sync page", False),
    "sync.attendance_window_days": ("INTEGER", "3", "Days of effective attendance returned in the sync download", False),
    "sync.rate_limit_per_minute": ("INTEGER", "6", "Maximum sync calls per device per minute", False),
    "billing.period_lock_window_days": ("INTEGER", "2", "Days after month end when billing period moves to LOCKED", False),

    # DEC-06 Meal End Times (IST)
    "meal.BREAKFAST.end_time": ("TIME", "10:00", "Breakfast service end time in IST", False),
    "meal.LUNCH.end_time": ("TIME", "14:30", "Lunch service end time in IST", False),
    "meal.EVENING_SNACKS.end_time": ("TIME", "18:30", "Evening snacks service end time in IST", False),
    "meal.DINNER.end_time": ("TIME", "22:00", "Dinner service end time in IST", False),

    # DEC-07 Rollover Time & Horizon
    "meal.rollover_time": ("TIME", "03:00", "Midnight shift rollover time in IST", False),
    "meal.occurrence_horizon_days": ("INTEGER", "35", "Occurrence generator forward horizon in days", False),

    # Appendix B2 Configuration Registry
    "sync.cursor_lookback": ("INTEGER", "50", "Cursor version lookback window", False),
    "pause.qualifying_slots": ("INTEGER", "3", "Number of qualifying slots before pause activates", False),
    "feedback.max_comment_length": ("INTEGER", "1000", "Maximum character length for feedback comment", False),
    "import.max_rows": ("INTEGER", "2000", "Maximum student rows in a single import batch", False),
    "report.max_range_days": ("INTEGER", "366", "Maximum date range for generated reports", False),
    "backup.retention_days": ("INTEGER", "30", "Backup retention period in days", False),

    # Sensitive key for security / masking validation
    "system.sensitive_token": ("STRING", "sample-secret", "Sample sensitive token", True),
}

# Per-process cache for settings
_SETTINGS_CACHE: dict[str, str] = {}


def clear_settings_cache():
    """Clear all cached setting values."""
    _SETTINGS_CACHE.clear()


def validate_setting_value(data_type: str, value: str) -> None:
    """Validate setting value according to its declared data_type."""
    if data_type == "INTEGER":
        try:
            int(value)
        except (ValueError, TypeError):
            raise ValidationError(
                code="VALIDATION_ERROR",
                message=f"Value '{value}' must be a valid integer.",
            )
    elif data_type == "BOOLEAN":
        if str(value).lower() not in ("true", "false", "1", "0"):
            raise ValidationError(
                code="VALIDATION_ERROR",
                message=f"Value '{value}' must be a boolean ('true' or 'false').",
            )
    elif data_type == "DECIMAL":
        try:
            Decimal(value)
        except Exception:
            raise ValidationError(
                code="VALIDATION_ERROR",
                message=f"Value '{value}' must be a valid decimal number.",
            )
    elif data_type == "TIME":
        parts = str(value).strip().split(":")
        if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
            raise ValidationError(
                code="VALIDATION_ERROR",
                message=f"Value '{value}' must be in HH:MM or HH:MM:SS time format.",
            )
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValidationError(
                code="VALIDATION_ERROR",
                message=f"Value '{value}' contains invalid hours or minutes.",
            )


def get_setting(key: str, default: Any = None) -> Any:
    """
    Get current effective value of a configuration setting.
    Checks memory cache first, then database for latest effective_from <= clock.now().
    Falls back to CONFIG_REGISTRY default or the passed default.
    """
    if key in _SETTINGS_CACHE:
        return _SETTINGS_CACHE[key]

    now = clock.now()
    setting = (
        SystemSetting.objects
        .filter(key=key, effective_from__lte=now)
        .order_by("-effective_from")
        .first()
    )

    if setting is not None:
        val = setting.value
        _SETTINGS_CACHE[key] = val
        return val

    if key in CONFIG_REGISTRY:
        return CONFIG_REGISTRY[key][1]

    return default


def get_int_setting(key: str, default: int = 0) -> int:
    """Get typed integer setting."""
    val = get_setting(key, default)
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def get_bool_setting(key: str, default: bool = False) -> bool:
    """Get typed boolean setting."""
    val = get_setting(key, default)
    return str(val).lower() in ("true", "1")


def get_time_setting(key: str, default: time | None = None) -> time | None:
    """Get typed time setting (IST clock)."""
    val = get_setting(key, None)
    if not val:
        return default
    try:
        parts = str(val).strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return time(h, m, s)
    except Exception:
        return default


def get_str_setting(key: str, default: str = "") -> str:
    """Get string setting."""
    val = get_setting(key, default)
    return str(val) if val is not None else default


@transaction.atomic
def update_setting(
    *,
    key: str,
    value: str,
    reason: str = "",
    actor: User | None = None,
    correlation_id: str = "",
) -> SystemSetting:
    """
    Update a system setting by creating a new effective-dated row [SPEC DBDD §12].
    Never edits existing rows. Unknown keys are rejected against CONFIG_REGISTRY.
    Masks sensitive values in audit logs.
    """
    if key not in CONFIG_REGISTRY:
        raise ValidationError(
            code="UNKNOWN_SETTING_KEY",
            message=f"Configuration key '{key}' is unknown. Must be defined in system registry.",
        )

    data_type, default_val, description, is_sensitive = CONFIG_REGISTRY[key]
    validate_setting_value(data_type, value)

    now = clock.now()
    latest = (
        SystemSetting.objects
        .filter(key=key)
        .order_by("-effective_from")
        .first()
    )

    new_version = (latest.version + 1) if latest else 1

    setting = SystemSetting.objects.create(
        key=key,
        value=str(value),
        data_type=data_type,
        description=description,
        is_sensitive=is_sensitive,
        effective_from=now,
        version=new_version,
    )

    # Invalidate cache
    _SETTINGS_CACHE.pop(key, None)

    # Prepare audit values
    if is_sensitive:
        old_val_audit = {"value": "******"} if latest else None
        new_val_audit = {"value": "******"}
    else:
        old_val_audit = {"value": latest.value} if latest else None
        new_val_audit = {"value": str(value)}

    record_audit_event(
        event_type="SETTING_CHANGED",
        actor_user=actor,
        entity_type="SystemSetting",
        entity_id=setting.setting_id,
        reason=reason or f"Updated {key}",
        old_values=old_val_audit,
        new_values=new_val_audit,
        correlation_id=correlation_id,
    )

    return setting


def list_system_settings(mask_sensitive: bool = True) -> list[dict[str, Any]]:
    """
    Lists the current effective configuration settings.
    If mask_sensitive is True, sensitive values are masked as '******'.
    """
    now = clock.now()
    results = []

    # Get distinct keys from DB and registry
    db_settings = (
        SystemSetting.objects
        .filter(effective_from__lte=now)
        .order_by("key", "-effective_from")
    )
    seen_keys: set[str] = set()

    for s in db_settings:
        if s.key in seen_keys:
            continue
        seen_keys.add(s.key)
        val = "******" if (s.is_sensitive and mask_sensitive) else s.value
        results.append({
            "setting_id": s.setting_id,
            "key": s.key,
            "value": val,
            "data_type": s.data_type,
            "description": s.description,
            "is_sensitive": s.is_sensitive,
            "effective_from": s.effective_from,
            "version": s.version,
        })

    # Add registry items not yet in DB
    for key, (dtype, dval, desc, is_sens) in CONFIG_REGISTRY.items():
        if key not in seen_keys:
            val = "******" if (is_sens and mask_sensitive) else dval
            results.append({
                "setting_id": None,
                "key": key,
                "value": val,
                "data_type": dtype,
                "description": desc,
                "is_sensitive": is_sens,
                "effective_from": None,
                "version": 1,
            })

    results.sort(key=lambda x: x["key"])
    return results


# ---------------------------------------------------------------------------
# Application Version Policy [SPEC DBDD §12, DEC-18]
# ---------------------------------------------------------------------------


def list_version_policies() -> list[ApplicationVersionPolicy]:
    """List all application version policies ordered by platform and app_version."""
    return list(ApplicationVersionPolicy.objects.all().order_by("platform", "app_version"))


@transaction.atomic
def create_or_update_version_policy(
    *,
    platform: str,
    app_version: str,
    status: str,
    force_update_message: str = "",
    actor: User | None = None,
    correlation_id: str = "",
) -> ApplicationVersionPolicy:
    """Create or update an application version policy [DEC-18]."""
    platform_norm = platform.strip().upper()
    version_norm = app_version.strip()
    status_norm = status.strip().upper()

    if platform_norm not in ("ANDROID", "IOS", "WEB"):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Platform must be ANDROID, IOS, or WEB.",
        )
    if status_norm not in ("SUPPORTED", "DEPRECATED", "BLOCKED"):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Status must be SUPPORTED, DEPRECATED, or BLOCKED.",
        )

    policy, created = ApplicationVersionPolicy.objects.get_or_create(
        platform=platform_norm,
        app_version=version_norm,
        defaults={
            "status": status_norm,
            "force_update_message": force_update_message,
            "version": 1,
        },
    )

    if not created:
        policy.status = status_norm
        policy.force_update_message = force_update_message
        policy.version += 1
        policy.save()

    record_audit_event(
        event_type="SETTING_CHANGED",
        actor_user=actor,
        entity_type="ApplicationVersionPolicy",
        entity_id=policy.policy_id,
        reason=f"Version policy for {platform_norm} {version_norm} set to {status_norm}",
        new_values={
            "platform": platform_norm,
            "app_version": version_norm,
            "status": status_norm,
        },
        correlation_id=correlation_id,
    )

    return policy


@transaction.atomic
def update_version_policy_by_id(
    *,
    policy_id: int,
    status: str,
    force_update_message: str = "",
    version: int,
    actor: User | None = None,
    correlation_id: str = "",
) -> ApplicationVersionPolicy:
    """Update version policy with optimistic locking."""
    policy = ApplicationVersionPolicy.objects.filter(policy_id=policy_id).first()
    if not policy:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Policy not found.")

    check_optimistic_lock(policy, version)

    status_norm = status.strip().upper()
    if status_norm not in ("SUPPORTED", "DEPRECATED", "BLOCKED"):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Status must be SUPPORTED, DEPRECATED, or BLOCKED.",
        )

    old_status = policy.status
    policy.status = status_norm
    policy.force_update_message = force_update_message
    policy.version += 1
    policy.save()

    record_audit_event(
        event_type="SETTING_CHANGED",
        actor_user=actor,
        entity_type="ApplicationVersionPolicy",
        entity_id=policy.policy_id,
        reason=f"Policy updated from {old_status} to {status_norm}",
        old_values={"status": old_status},
        new_values={"status": status_norm},
        correlation_id=correlation_id,
    )

    return policy


@transaction.atomic
def delete_version_policy(*, policy_id: int, actor: User | None = None, correlation_id: str = "") -> None:
    """Delete version policy."""
    policy = ApplicationVersionPolicy.objects.filter(policy_id=policy_id).first()
    if not policy:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Policy not found.")

    record_audit_event(
        event_type="SETTING_CHANGED",
        actor_user=actor,
        entity_type="ApplicationVersionPolicy",
        entity_id=policy.policy_id,
        reason=f"Deleted version policy {policy.platform} {policy.app_version}",
        old_values={"platform": policy.platform, "app_version": policy.app_version, "status": policy.status},
        correlation_id=correlation_id,
    )
    policy.delete()

