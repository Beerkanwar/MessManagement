"""
Tests for custom exception handler and error envelopes [SPEC SDD §88, §89].
Checkpoints:
- Raising an unhandled error in a test view produces {code, message, traceId} with HTTP 500.
- No stack trace text or internal error details appear in the API response.
- The structured log record emitted carries the identical traceId.
- Domain application errors (e.g., ConflictError, NotFoundError) return standard envelopes.
"""
from unittest.mock import patch
import pytest
from django.urls import path
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIClient
from apps.core.exceptions import ConflictError, NotFoundError


@api_view(["GET"])
@permission_classes([AllowAny])
def unhandled_error_view(request):
    """View deliberately raising an unexpected internal server exception."""
    raise RuntimeError("Sensitive internal database connection string: postgresql://secret:123@db")


@api_view(["GET"])
@permission_classes([AllowAny])
def conflict_error_view(request):
    """View raising a domain conflict error."""
    raise ConflictError(code="VERSION_CONFLICT", message="Record modified by another user.")


@api_view(["GET"])
@permission_classes([AllowAny])
def not_found_error_view(request):
    """View raising a domain not found error."""
    raise NotFoundError(code="OBJECT_NOT_FOUND", message="The requested entity does not exist.")


# Dynamic test URLs
urlpatterns = [
    path("test/error/unhandled", unhandled_error_view),
    path("test/error/conflict", conflict_error_view),
    path("test/error/not-found", not_found_error_view),
]


@pytest.mark.urls(__name__)
def test_unhandled_error_envelope_and_trace_id_matching():
    client = APIClient()
    logged_events = []

    def mock_log_error(event, **kwargs):
        logged_events.append({"event": event, **kwargs})

    with patch("apps.core.exceptions.logger.error", side_effect=mock_log_error):
        response = client.get("/test/error/unhandled", HTTP_X_TRACE_ID="trace-checkpoint-123")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()

    # Enforce envelope {code, message, traceId}
    assert set(data.keys()) == {"code", "message", "traceId"}
    assert data["code"] == "INTERNAL_SERVER_ERROR"
    assert data["message"] == "An unexpected internal server error occurred."
    assert data["traceId"] == "trace-checkpoint-123"

    # Invariant: No internal stack text or sensitive content in response body
    response_text = str(response.content)
    assert "Sensitive internal database" not in response_text
    assert "Traceback" not in response_text
    assert "RuntimeError" not in response_text

    # Invariant: Log line carries the same traceId
    assert len(logged_events) == 1
    log_record = logged_events[0]
    assert log_record["trace_id"] == "trace-checkpoint-123"
    assert log_record["error_type"] == "RuntimeError"


@pytest.mark.urls(__name__)
def test_domain_conflict_error_envelope():
    client = APIClient()
    response = client.get("/test/error/conflict")

    assert response.status_code == status.HTTP_409_CONFLICT
    data = response.json()
    assert data["code"] == "VERSION_CONFLICT"
    assert data["message"] == "Record modified by another user."
    assert "traceId" in data and len(data["traceId"]) > 0


@pytest.mark.urls(__name__)
def test_domain_not_found_error_envelope():
    client = APIClient()
    response = client.get("/test/error/not-found")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["code"] == "OBJECT_NOT_FOUND"
    assert data["message"] == "The requested entity does not exist."
    assert "traceId" in data
