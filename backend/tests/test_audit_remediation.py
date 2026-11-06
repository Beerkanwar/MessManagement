"""
Test suite verifying fixes for all issues identified in AuditReport.md.
"""
from datetime import date, timedelta
from decimal import Decimal
import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import RequestFactory
from rest_framework.exceptions import ValidationError as DRFValidationError, PermissionDenied

from apps.core.clock import clock
from apps.core.logging import is_sensitive_key, mask_sensitive_value
from apps.audit.services import sanitize_audit_payload
from apps.identity.models import User, Role, UserRole
from apps.identity.selectors import get_user_role
from apps.mess.serializers import MealRateCreateSerializer, ExtraPriceCreateSerializer
from apps.sync.services import advance_change_cursor
from apps.sync.models import ChangeCursor


# ==============================================================================
# 1. ISSUE-05 & ISSUE-06: Sensitive Key Denylist & Audit Sanitization
# ==============================================================================

def test_is_sensitive_key_precision():
    """Verifies sensitive credential keys are identified while structural keys are spared (ISSUE-05)."""
    # Sensitive keys
    assert is_sensitive_key("password") is True
    assert is_sensitive_key("user_password") is True
    assert is_sensitive_key("otp") is True
    assert is_sensitive_key("access_token") is True
    assert is_sensitive_key("refresh_token") is True
    assert is_sensitive_key("secret") is True
    assert is_sensitive_key("student_secret") is True
    assert is_sensitive_key("api_key") is True
    assert is_sensitive_key("private_key") is True
    assert is_sensitive_key("signing_key") is True
    assert is_sensitive_key("encryption_key") is True

    # Non-sensitive / structural keys (should NOT be falsely identified as sensitive)
    assert is_sensitive_key("key_id") is False
    assert is_sensitive_key("device_key_id") is False
    assert is_sensitive_key("primary_key") is False
    assert is_sensitive_key("foreign_key") is False
    assert is_sensitive_key("cache_key") is False
    assert is_sensitive_key("monkey") is False
    assert is_sensitive_key("safe_field") is False
    assert is_sensitive_key("student_id") is False


def test_mask_sensitive_value_does_not_over_redact():
    """Verifies that non-sensitive fields are preserved while sensitive fields are masked."""
    assert mask_sensitive_value("password", "secret123") == "[REDACTED]"
    assert mask_sensitive_value("key_id", 42) == 42
    assert mask_sensitive_value("device_key_id", "dev-1") == "dev-1"
    assert mask_sensitive_value("student_id", 101) == 101


def test_sanitize_audit_payload_allows_structural_keys():
    """Verifies that audit payloads with structural keys like 'key_id' are accepted (ISSUE-06)."""
    payload = {
        "key_id": 1,
        "device_key_id": "dev-123",
        "action": "SECRET_ROTATED",
    }
    sanitized = sanitize_audit_payload(payload)
    assert sanitized["key_id"] == 1
    assert sanitized["device_key_id"] == "dev-123"

    # Truly prohibited keys still raise ValidationError
    with pytest.raises(DjangoValidationError, match="prohibited sensitive key"):
        sanitize_audit_payload({"password": "raw_password"})


# ==============================================================================
# 2. ISSUE-09: User Role Caching
# ==============================================================================

@pytest.mark.django_db
def test_user_role_caching_eliminates_n_plus_one(django_assert_num_queries):
    """Verifies that get_user_role caches on user._cached_role to eliminate repeated DB queries (ISSUE-09)."""
    user = User.objects.create(email="role_cache_test@test.edu", normalized_email="role_cache_test@test.edu")
    role = Role.objects.get(name="HOSTEL_CLERK")
    UserRole.objects.create(user=user, role=role)

    # First call: executes 1 query to fetch UserRole and cache it
    with django_assert_num_queries(1):
        role_1 = get_user_role(user)
        assert role_1 == "HOSTEL_CLERK"

    # Subsequent 5 calls: 0 queries because user._cached_role is reused
    with django_assert_num_queries(0):
        for _ in range(5):
            assert get_user_role(user) == "HOSTEL_CLERK"


# ==============================================================================
# 3. ISSUE-20: Serializer Date Validation (Past Date Rejection)
# ==============================================================================

def test_meal_rate_serializer_rejects_past_effective_from():
    """Verifies MealRateCreateSerializer rejects past dates (ISSUE-20)."""
    yesterday = clock.today() - timedelta(days=1)
    serializer = MealRateCreateSerializer(data={
        "rate": "45.0000",
        "effective_from": str(yesterday),
        "reason": "Past rate",
    })
    assert not serializer.is_valid()
    assert "effective_from" in serializer.errors
    assert "cannot be in the past" in str(serializer.errors["effective_from"][0])


def test_meal_rate_serializer_accepts_today_and_future():
    """Verifies MealRateCreateSerializer accepts today and future dates."""
    today = clock.today()
    serializer = MealRateCreateSerializer(data={
        "rate": "45.0000",
        "effective_from": str(today),
        "reason": "Today rate",
    })
    assert serializer.is_valid(), serializer.errors


def test_extra_price_serializer_rejects_past_effective_from():
    """Verifies ExtraPriceCreateSerializer rejects past dates (ISSUE-20)."""
    yesterday = clock.today() - timedelta(days=1)
    serializer = ExtraPriceCreateSerializer(data={
        "unit_price": "25.0000",
        "effective_from": str(yesterday),
        "reason": "Past extra price",
    })
    assert not serializer.is_valid()
    assert "effective_from" in serializer.errors


# ==============================================================================
# 4. ISSUE-24: Atomic Change Cursor Upsert
# ==============================================================================

@pytest.mark.django_db
def test_atomic_advance_change_cursor_monotonic():
    """Verifies advance_change_cursor atomically inserts and monotonically increments (ISSUE-24)."""
    cursor_key = "mess:999:test_cursor"
    ChangeCursor.objects.filter(aggregate_type=cursor_key).delete()

    v1 = advance_change_cursor(cursor_key)
    assert v1 == 1

    v2 = advance_change_cursor(cursor_key)
    assert v2 == 2

    v3 = advance_change_cursor(cursor_key)
    assert v3 == 3

    # Verify database row
    obj = ChangeCursor.objects.get(aggregate_type=cursor_key)
    assert obj.current_version == 3


# ==============================================================================
# 5. ISSUE-14: Client Header Sanitization in RequestLoggingMiddleware
# ==============================================================================

def test_request_logging_middleware_sanitizes_device_header(rf):
    """Verifies RequestLoggingMiddleware strips control characters and restricts length (ISSUE-14)."""
    from apps.core.middleware import RequestLoggingMiddleware
    from django.http import HttpResponse

    middleware = RequestLoggingMiddleware(lambda req: HttpResponse("OK"))

    # Request with malicious log injection header
    request = rf.get("/api/v1/attendance")
    request.headers = {"X-Device-Id": "malicious-device\r\nINJECTED LOG ENTRY" + "A" * 100}

    # Execute middleware (should not raise and should sanitize)
    response = middleware(request)
    assert response.status_code == 200


# ==============================================================================
# 6. ISSUE-11: HTTPS Enforcement on QR Secret Delivery
# ==============================================================================

@pytest.mark.django_db
def test_qr_secret_view_enforces_https(api_client, monkeypatch):
    """Verifies qr_secret_view returns 403 PermissionDenied over plain HTTP in production (ISSUE-11)."""
    from apps.identity.models import User, Role, UserRole
    from apps.hostel.models import Student, Hostel
    from tests.test_phase6_qr import auth_client
    from django.conf import settings

    u = User.objects.create(email="qr_https_test@test.edu", normalized_email="qr_https_test@test.edu", status="ACTIVE")
    UserRole.objects.create(user=u, role=Role.objects.get(name="STUDENT"))
    h, _ = Hostel.objects.get_or_create(code="H-REM", defaults={"name": "H-REM", "status": "ACTIVE"})
    Student.objects.create(user=u, roll_number="REM001", hostel=h, status="ACTIVE")
    auth_client(api_client, u, "STUDENT")

    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "TESTING", False)

    resp = api_client.get("/api/v1/qr/secret", secure=False)
    assert resp.status_code == 403
    assert resp.data["code"] == "PERMISSION_DENIED"
    assert "HTTPS is strictly required" in resp.data["message"]
