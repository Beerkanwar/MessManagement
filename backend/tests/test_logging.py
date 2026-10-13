"""
Tests for structured logging and sensitive field redaction [SPEC SDD §63, §103].
Checkpoints:
- Logging a dict containing password, token, otp, secret, key, authorization, qr, or payload keys
  masks values with [REDACTED].
- Request logs record method, route template, status, and duration, never bodies.
"""
from apps.core.logging import redact_sensitive_data, REDACTED_PLACEHOLDER


def test_sensitive_fields_redacted_in_structured_logging():
    """Confirms all sensitive keys and nested structures are masked with [REDACTED]."""
    test_event = {
        "event": "user_action",
        "username": "student_01",
        "user_id": 42,
        "password": "plain_password_123",
        "auth_token": "jwt.header.payload.signature",
        "user_otp": "492812",
        "authorization": "Bearer secret_jwt",
        "student_secret_key": "topsecretkeybytes",
        "api_key": "secret-api-key-value",
        "qr_payload": "ROLL123|987654",
        "raw_payload": {"data": "confidential"},
        "nested_user": {
            "name": "Beer Singh",
            "password_hash": "argon2id$v=19$m=65536...",
            "reset_token": "abcdef123456",
        },
        "safe_list": ["item1", "item2"],
        "sensitive_list": [
            {"access_token": "token1"},
            {"secret_code": "secret2"},
        ],
    }

    processed = redact_sensitive_data(None, "info", test_event)

    # Invariant: Sensitive keys masked
    assert processed["password"] == REDACTED_PLACEHOLDER
    assert processed["auth_token"] == REDACTED_PLACEHOLDER
    assert processed["user_otp"] == REDACTED_PLACEHOLDER
    assert processed["authorization"] == REDACTED_PLACEHOLDER
    assert processed["student_secret_key"] == REDACTED_PLACEHOLDER
    assert processed["api_key"] == REDACTED_PLACEHOLDER
    assert processed["qr_payload"] == REDACTED_PLACEHOLDER
    assert processed["raw_payload"] == REDACTED_PLACEHOLDER

    # Invariant: Nested dicts masked
    assert processed["nested_user"]["name"] == "Beer Singh"
    assert processed["nested_user"]["password_hash"] == REDACTED_PLACEHOLDER
    assert processed["nested_user"]["reset_token"] == REDACTED_PLACEHOLDER

    # Invariant: Nested lists masked
    assert processed["sensitive_list"][0]["access_token"] == REDACTED_PLACEHOLDER
    assert processed["sensitive_list"][1]["secret_code"] == REDACTED_PLACEHOLDER

    # Invariant: Benign keys preserved
    assert processed["username"] == "student_01"
    assert processed["user_id"] == 42
    assert processed["safe_list"] == ["item1", "item2"]


def test_request_logging_excludes_bodies(api_client):
    """Verifies that RequestLoggingMiddleware does not record request or response bodies."""
    from unittest.mock import patch

    captured_logs = []

    def mock_log_info(event, **kwargs):
        captured_logs.append({"event": event, **kwargs})

    with patch("apps.core.middleware.logger.info", side_effect=mock_log_info):
        api_client.post(
            "/api/v1/auth/login",
            data={"password": "secret_password", "email": "test@college.edu"},
            format="json",
        )

    # Check captured request log
    assert len(captured_logs) > 0
    request_log = captured_logs[0]

    assert request_log["service"] == "mess-management-backend"
    assert "method" in request_log and request_log["method"] == "POST"
    assert "duration" in request_log
    assert "status" in request_log
    assert "route_template" in request_log

    # Critical security invariant: No request or response bodies in log
    assert "body" not in request_log
    assert "request_body" not in request_log
    assert "response_body" not in request_log
    assert "secret_password" not in str(request_log)
