"""
Audit logging service enforcing SPEC DBDD §12, Invariant 12, and SPEC SDD §63.
Append-only audit writes executed within the caller's database transaction.
Sanitizes all payload dictionaries against sensitive keywords and length caps.
"""
from typing import Any
from django.core.exceptions import ValidationError
from apps.audit.models import AuditLog
from apps.core.clock import clock
from apps.core.logging import SENSITIVE_KEY_SUBSTRINGS

MAX_AUDIT_STRING_LENGTH = 500


def sanitize_audit_payload(data: Any) -> Any:
    """
    Recursively inspects audit payload dictionaries and lists.
    Refuses sensitive keys (password, otp, token, authorization, secret, key, qr, payload).
    Enforces maximum string length to prevent accidental dumping of large blobs or tokens.
    """
    if data is None:
        return None

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            lower_key = str(key).lower()
            for sensitive_term in SENSITIVE_KEY_SUBSTRINGS:
                if sensitive_term in lower_key:
                    raise ValidationError(
                        f"Audit payload contains prohibited sensitive key: '{key}' [SPEC SDD §63]"
                    )
            sanitized[key] = sanitize_audit_payload(value)
        return sanitized

    if isinstance(data, (list, tuple)):
        return [sanitize_audit_payload(item) for item in data]

    if isinstance(data, str):
        if len(data) > MAX_AUDIT_STRING_LENGTH:
            raise ValidationError(
                f"Audit payload string value exceeds maximum allowed length of {MAX_AUDIT_STRING_LENGTH} characters."
            )
        return data

    return data


def record_audit_event(
    event_type: str,
    actor_user=None,
    device_registration=None,
    entity_type: str = "",
    entity_id: str | int = "",
    reason: str = "",
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    correlation_id: str = "",
) -> AuditLog:
    """
    Writes an append-only AuditLog record within the caller's transaction.
    Raises ValidationError if any sensitive keys or oversized values are detected.
    """
    clean_old = sanitize_audit_payload(old_values)
    clean_new = sanitize_audit_payload(new_values)
    clean_meta = sanitize_audit_payload(metadata)

    return AuditLog.objects.create(
        event_type=event_type,
        actor_user=actor_user,
        device_registration=device_registration,
        entity_type=entity_type,
        entity_id=str(entity_id),
        occurred_at=clock.now(),
        reason=reason or "",
        correlation_id=correlation_id or "",
        old_values_json=clean_old,
        new_values_json=clean_new,
        metadata_json=clean_meta,
    )
