"""
Structured logging and sensitive field redaction utilities.
Enforces SDD §63 and SDD §103 invariants.
"""
from typing import Any, Mapping

# Denylist for sensitive keys per SPEC SDD §63
SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "otp",
    "token",
    "authorization",
    "secret",
    "key",
    "qr",
    "payload",
)

REDACTED_PLACEHOLDER = "[REDACTED]"


def mask_sensitive_value(key: str, value: Any) -> Any:
    """Recursively mask values whose key contains sensitive keywords."""
    lower_key = key.lower()
    for sensitive_sub in SENSITIVE_KEY_SUBSTRINGS:
        if sensitive_sub in lower_key:
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
