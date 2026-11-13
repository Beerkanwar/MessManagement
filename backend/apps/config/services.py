"""
System configuration services — Phase 5.
Implements:
- Registry of institutional SystemSetting parameters (Appendix B2, DEC-11, DEC-06, DEC-07).
- Effective-dated SystemSetting reads/writes (never edits history, audited, sensitive masking).
- In-memory per-request/short-TTL setting cache with typed getters.
- ApplicationVersionPolicy CRUD.
"""
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.audit.services import record_audit_event
from apps.config.models import ApplicationVersionPolicy, SystemSetting
from apps.core.clock import clock
from apps.core.concurrency import check_optimistic_lock
from apps.core.exceptions import NotFoundError, ValidationError
from apps.identity.models import User


@dataclass(frozen=True)
class SettingSpec:
    """
    Appendix B2 parameter metadata enforced by the configuration API.

    ``env_only`` values are deployment secrets or environment switches; they are
    documented in the registry but can never become SystemSetting rows
    [SPEC DBDD §12, SDD §102].
    """

    key: str
    data_type: str
    default: str
    description: str
    is_sensitive: bool = False
    minimum: int | Decimal | None = None
    maximum: int | Decimal | None = None
    phase: str = ""
    env_only: bool = False
    max_length: int | None = None


def _spec(
    key: str,
    data_type: str,
    default: str,
    description: str,
    *,
    is_sensitive: bool = False,
    minimum=None,
    maximum=None,
    phase: str = "",
    env_only: bool = False,
    max_length=None,
) -> SettingSpec:
    return SettingSpec(
        key=key,
        data_type=data_type,
        default=default,
        description=description,
        is_sensitive=is_sensitive,
        minimum=minimum,
        maximum=maximum,
        phase=phase,
        env_only=env_only,
        max_length=max_length,
    )


CONFIG_REGISTRY: dict[str, SettingSpec] = {
    spec.key: spec
    for spec in (
        # Authentication and session policy [DEC-11, Appendix B2]
        _spec("auth.password.min_length", "INTEGER", "10", "Minimum password length", minimum=8, maximum=128, phase="P3"),
        _spec("auth.otp.length", "INTEGER", "6", "Digits in a password reset OTP", minimum=4, maximum=8, phase="P3"),
        _spec("auth.otp.validity_minutes", "INTEGER", "10", "OTP validity in minutes", minimum=1, maximum=60, phase="P3"),
        _spec("auth.otp.max_attempts", "INTEGER", "5", "Failed OTP attempts before invalidation", minimum=1, maximum=10, phase="P3"),
        _spec("auth.otp.resend_cooldown_seconds", "INTEGER", "60", "OTP resend cooldown in seconds", minimum=0, maximum=3600, phase="P3"),
        _spec("auth.otp.max_per_hour_per_email", "INTEGER", "5", "OTP requests per email per hour", minimum=1, maximum=20, phase="P3"),
        _spec("auth.login.max_failures", "INTEGER", "5", "Failed logins before lockout", minimum=1, maximum=20, phase="P3"),
        _spec("auth.login.lockout_minutes", "INTEGER", "15", "Login lockout duration in minutes", minimum=1, maximum=1440, phase="P3"),
        _spec("auth.refresh_replay_grace_seconds", "INTEGER", "30", "Refresh-token replay grace window", minimum=0, maximum=300, phase="P3"),

        # Attendance, trusted time and QR [DEC-01, DEC-07]
        _spec("attendance.correction_window_hours", "INTEGER", "48", "Correction window after MealDate", minimum=1, maximum=168, phase="P7"),
        _spec("time.trusted_anchor_max_age_hours", "INTEGER", "48", "Maximum trusted-time anchor age", minimum=1, maximum=168, phase="P6"),
        _spec("time.trusted_anchor_expiring_hours", "INTEGER", "6", "Anchor expiry warning window", minimum=1, maximum=48, phase="P6"),
        _spec("qr.step_seconds", "INTEGER", "30", "QR HMAC time step in seconds", minimum=10, maximum=120, phase="P6"),
        _spec("qr.window_steps", "INTEGER", "1", "QR verification tolerance in steps", minimum=0, maximum=3, phase="P6"),

        # Offline and sync [DEC-10, DEC-11, D11/I02]
        _spec("offline.normal_hours", "INTEGER", "24", "Normal offline operation window", minimum=1, maximum=168, phase="P8"),
        _spec("offline.grace_hours", "INTEGER", "24", "Additional offline grace window", minimum=0, maximum=168, phase="P8"),
        _spec("sync.batch_max_transactions", "INTEGER", "500", "Maximum transactions per sync batch [D11]", minimum=1, maximum=500, phase="P8"),
        _spec("sync.overlap_minutes", "INTEGER", "2", "Cursor overlap for late commits", minimum=0, maximum=60, phase="P8"),
        _spec("sync.student_page_size", "INTEGER", "500", "Students per bootstrap page", minimum=1, maximum=1000, phase="P8"),
        _spec("sync.attendance_window_days", "INTEGER", "3", "Attendance days returned by sync", minimum=1, maximum=30, phase="P8"),
        _spec("sync.rate_limit_per_minute", "INTEGER", "6", "Sync calls per device per minute", minimum=1, maximum=120, phase="P8"),
        _spec("sync.cursor_lookback", "INTEGER", "50", "Cursor version lookback window", minimum=0, maximum=500, phase="P8"),

        # Billing, meals and pause [DEC-06, DEC-07]
        _spec("billing.period_lock_window_days", "INTEGER", "2", "Days after month end before locking", minimum=0, maximum=31, phase="P10"),
        _spec("meal.BREAKFAST.end_time", "TIME", "10:00", "Breakfast service end time (IST)", phase="P5"),
        _spec("meal.LUNCH.end_time", "TIME", "14:30", "Lunch service end time (IST)", phase="P5"),
        _spec("meal.EVENING_SNACKS.end_time", "TIME", "18:30", "Evening snacks end time (IST)", phase="P5"),
        _spec("meal.DINNER.end_time", "TIME", "22:00", "Dinner service end time (IST)", phase="P5"),
        _spec("meal.rollover_time", "TIME", "03:00", "Midnight shift rollover time (IST)", phase="P5"),
        _spec("meal.occurrence_horizon_days", "INTEGER", "35", "Occurrence generation horizon in days", minimum=1, maximum=365, phase="P5"),
        _spec("pause.qualifying_slots", "INTEGER", "3", "Qualifying meal slots before a pause activates", minimum=1, maximum=10, phase="P9"),

        # Feedback, import, reports and retention
        _spec("feedback.max_comment_length", "INTEGER", "1000", "Maximum feedback comment length", minimum=1, maximum=5000, phase="P11"),
        _spec("import.max_rows", "INTEGER", "2000", "Maximum student rows per import batch", minimum=1, maximum=10000, phase="P4"),
        _spec("import.max_size_mb", "INTEGER", "2", "Maximum student import file size in MB", minimum=1, maximum=10, phase="P4"),
        _spec("report.max_range_days", "INTEGER", "366", "Maximum report date range in days", minimum=1, maximum=366, phase="P12"),
        _spec("backup.retention_days", "INTEGER", "30", "Backup retention period in days", minimum=1, maximum=3650, phase="P24"),

        # Sensitive sentinel retained for masking tests; real secrets are env-only.
        _spec("system.sensitive_token", "STRING", "sample-secret", "Sample sensitive token", is_sensitive=True, phase="P13"),

        # Environment-only values: documented, never stored in SystemSetting.
        _spec("time.zone", "STRING", "Asia/Kolkata", "Institutional time zone [DEC-01]", phase="P1", env_only=True),
        _spec("auth.access_token_ttl_minutes", "INTEGER", "15", "Access token lifetime [SDD]", phase="P3", env_only=True),
        _spec("auth.refresh_ttl_mobile_days", "INTEGER", "30", "Mobile refresh token lifetime [DEC-10]", phase="P3", env_only=True),
        _spec("auth.refresh_ttl_web_hours", "INTEGER", "12", "Web refresh token lifetime [DEC-10]", phase="P3", env_only=True),
        _spec("secrets.jwt_signing_key", "STRING", "", "JWT signing key [SDD §102]", is_sensitive=True, phase="P3", env_only=True),
        _spec("secrets.database_password", "STRING", "", "Database password [SDD §102]", is_sensitive=True, phase="P1", env_only=True),
        _spec("secrets.secret_encryption_key", "STRING", "", "Student secret encryption key [SDD §63]", is_sensitive=True, phase="P6", env_only=True),
        _spec("secrets.smtp_password", "STRING", "", "SMTP password [SDD §102]", is_sensitive=True, phase="P3", env_only=True),
    )
}

# Per-process cache for settings
_SETTINGS_CACHE: dict[str, str] = {}


def clear_settings_cache():
    """Clear all cached setting values."""
    _SETTINGS_CACHE.clear()


def validate_setting_value(
    data_type: str,
    value: str,
    *,
    spec: SettingSpec | None = None,
) -> None:
    """
    Validate a setting value against its declared data_type and registry bounds.

    Bounds are part of Appendix B2: an out-of-range value is rejected here so no
    API path can persist a parameter the consumers cannot honour.
    """
    parsed: int | Decimal | None = None

    if data_type == "INTEGER":
        try:
            parsed = int(value)
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
            parsed = Decimal(value)
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
    elif data_type == "STRING":
        pass
    else:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Unsupported configuration data type '{data_type}'.",
        )

    if spec is None:
        return
    if spec.max_length is not None and len(str(value)) > spec.max_length:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Value for '{spec.key}' exceeds {spec.max_length} characters.",
        )
    if parsed is not None:
        if spec.minimum is not None and parsed < spec.minimum:
            raise ValidationError(
                code="VALIDATION_ERROR",
                message=f"Value for '{spec.key}' must be >= {spec.minimum}.",
            )
        if spec.maximum is not None and parsed > spec.maximum:
            raise ValidationError(
                code="VALIDATION_ERROR",
                message=f"Value for '{spec.key}' must be <= {spec.maximum}.",
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
        return CONFIG_REGISTRY[key].default

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
    spec = CONFIG_REGISTRY.get(key)
    if spec is None:
        raise ValidationError(
            code="UNKNOWN_SETTING_KEY",
            message=f"Configuration key '{key}' is unknown. Must be defined in system registry.",
        )
    if spec.env_only:
        raise ValidationError(
            code="ENV_ONLY_SETTING",
            message=(
                f"Configuration key '{key}' is deployment-managed and cannot be "
                "stored as a SystemSetting. Set it through the environment."
            ),
        )

    validate_setting_value(spec.data_type, value, spec=spec)

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
        data_type=spec.data_type,
        description=spec.description,
        is_sensitive=spec.is_sensitive,
        effective_from=now,
        version=new_version,
    )

    # Invalidate cache
    _SETTINGS_CACHE.pop(key, None)

    # Prepare audit values
    if spec.is_sensitive:
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


def _setting_output(
    *,
    key: str,
    setting: SystemSetting | None,
    spec: SettingSpec,
    mask_sensitive: bool,
) -> dict[str, Any]:
    """Build one registry row with Appendix B2 metadata for the admin API."""
    is_sensitive = spec.is_sensitive
    if setting is not None:
        value = "******" if (is_sensitive and mask_sensitive) else setting.value
        row = {
            "setting_id": setting.setting_id,
            "key": key,
            "value": value,
            "data_type": setting.data_type,
            "description": setting.description,
            "is_sensitive": is_sensitive,
            "effective_from": setting.effective_from,
            "version": setting.version,
        }
    else:
        value = "******" if (is_sensitive and mask_sensitive) else spec.default
        row = {
            "setting_id": None,
            "key": key,
            "value": value,
            "data_type": spec.data_type,
            "description": spec.description,
            "is_sensitive": is_sensitive,
            "effective_from": None,
            "version": 1,
        }
    row.update(
        {
            "minimum": None if spec.minimum is None else str(spec.minimum),
            "maximum": None if spec.maximum is None else str(spec.maximum),
            "max_length": spec.max_length,
            "phase": spec.phase,
            "env_only": spec.env_only,
            "editable": not spec.env_only,
        }
    )
    return row


def list_system_settings(mask_sensitive: bool = True) -> list[dict[str, Any]]:
    """
    Lists the current effective configuration settings with registry metadata.

    Rows come from the registry, so documented parameters that have never been
    changed still appear with their default. Sensitive values are masked.
    """
    now = clock.now()
    current: dict[str, SystemSetting] = {}

    db_settings = (
        SystemSetting.objects
        .filter(effective_from__lte=now)
        .order_by("key", "-effective_from")
    )
    for setting in db_settings:
        current.setdefault(setting.key, setting)

    results = [
        _setting_output(
            key=key,
            setting=current.get(key),
            spec=spec,
            mask_sensitive=mask_sensitive,
        )
        for key, spec in CONFIG_REGISTRY.items()
    ]
    results.sort(key=lambda row: row["key"])
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

