"""
Middleware for Request ID / Trace ID correlation and structured request logging.
Enforces SPEC SDD §63, §103, and Phase 1 audit correlation requirements.
"""
import uuid
from typing import Callable
import structlog
from django.http import HttpRequest, HttpResponse
from django.urls import resolve
from apps.core.clock import clock

logger = structlog.get_logger("apps.core.request")


class RequestIdMiddleware:
    """
    Extracts or generates a unique Trace ID / Request ID per incoming HTTP request.
    Attaches traceId and CorrelationId to the request, binds them to structlog context,
    and returns X-Trace-ID header on responses.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        trace_id = (
            request.headers.get("X-Trace-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )

        request.trace_id = trace_id
        request.correlation_id = trace_id

        # Bind to structlog context variables for the current thread/async task
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            request_id=trace_id,
        )

        response = self.get_response(request)
        response["X-Trace-ID"] = trace_id
        return response


class RequestLoggingMiddleware:
    """
    Logs structured HTTP request telemetry satisfying SPEC SDD §103:
    Fields: timestamp, level, service, request_id, trace_id, user_id, device_id,
    operation, duration, outcome, method, route_template, status.
    Never records request or response bodies [SPEC SDD §63].
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start_time = clock.monotonic()

        response = self.get_response(request)

        duration_ms = round((clock.monotonic() - start_time) * 1000, 2)
        trace_id = getattr(request, "trace_id", "")
        device_id = request.headers.get("X-Device-Id")

        user_id = None
        if hasattr(request, "user") and request.user.is_authenticated:
            user_id = getattr(request.user, "user_id", None) or getattr(request.user, "pk", None)

        try:
            match = resolve(request.path)
            route_template = match.route or request.path
        except Exception:
            route_template = request.path

        outcome = "SUCCESS" if response.status_code < 400 else "FAILURE"

        logger.info(
            "http_request_completed",
            service="mess-management-backend",
            trace_id=trace_id,
            request_id=trace_id,
            method=request.method,
            route_template=route_template,
            status=response.status_code,
            duration=duration_ms,
            outcome=outcome,
            operation=f"{request.method} {route_template}",
            user_id=str(user_id) if user_id is not None else None,
            device_id=device_id,
        )

        return response
