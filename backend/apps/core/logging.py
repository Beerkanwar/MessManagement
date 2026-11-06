"""
Structured logging and sensitive field redaction utilities.
Enforces SDD §63 and SDD §103 invariants.
"""
from typing import Any, Mapping

# Denylist for sensitive keys per SPEC SDD §63
# Note: Replaced bare "key" substring with precise matching to prevent false positives (ISSUE-05).
SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "otp",
    "token",
    "authorization",
    "secret",
    "private_key",
    "signing_key",
    "encryption_key",
    "api_key",
    "client_key",
    "secret_key",
    "qr",
    "payload",
)

REDACTED_PLACEHOLDER = "[REDACTED]"


def is_sensitive_key(key: str) -> bool:
    """
    Checks if a key name corresponds to sensitive credential material.
    Avoids false-positive redaction/rejection for generic structural identifiers (ISSUE-05).
    """
    lower_key = str(key).lower().strip()
    if lower_key == "key" or lower_key.endswith("_key") or lower_key.endswith("-key"):
        # Exclude innocent DB structural identifiers
        if lower_key not in ("foreign_key", "primary_key", "entity_key", "partition_key", "cache_key"):
            return True
    return any(sub in lower_key for sub in SENSITIVE_KEY_SUBSTRINGS)


def mask_sensitive_value(key: str, value: Any) -> Any:
    """Recursively mask values whose key contains sensitive keywords."""
    if is_sensitive_key(key):
        return REDACTED_PLACEHOLDER

    if isinstance(value, dict):
        return {k: mask_sensitive_value(k, v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [mask_sensitive_value(key, item) if isinstance(item, (dict, list, tuple)) else item for item in value]
    return value


def redact_sensitive_data(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Structlog processor that traverses the event_dict and redacts any key containing
    sensitive terms (passwords, tokens, OTPs, secrets, keys, QR codes, payloads).
    """
    for key, value in list(event_dict.items()):
        event_dict[key] = mask_sensitive_value(key, value)
    return event_dict
