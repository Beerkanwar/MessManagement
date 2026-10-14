"""
Custom DRF exception handling and domain exception classes.
Enforces SPEC SDD §88 and §89 by returning standard error envelope {code, message, traceId}
and ensuring internal stack traces are never exposed to API callers.
"""
import uuid
from typing import Any
import structlog
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler
from apps.core.error_codes import ErrorCodes, ERROR_REGISTRY

logger = structlog.get_logger(__name__)


class ApplicationError(exceptions.APIException):
    """
    Base domain application error with explicit code and message.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = ErrorCodes.BAD_REQUEST
    default_detail = "Application error occurred."

    def __init__(self, message: str | None = None, code: str | None = None, status_code: int | None = None):
        self.message = message or self.default_detail
        self.code = code or self.default_code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=self.message, code=self.code)


class ConflictError(ApplicationError):
    status_code = status.HTTP_409_CONFLICT
    default_code = ErrorCodes.CONFLICT
    default_detail = "Resource conflict occurred."


class NotFoundError(ApplicationError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = ErrorCodes.NOT_FOUND
    default_detail = "The requested resource was not found."


class PermissionDeniedError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = ErrorCodes.PERMISSION_DENIED
    default_detail = "Permission denied."


class ValidationError(ApplicationError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = ErrorCodes.VALIDATION_ERROR
    default_detail = "Request validation failed."


def map_status_to_code(http_status: int) -> str:
    """Maps HTTP status codes to standard error codes per SDD §89."""
    if http_status == 400:
        return ErrorCodes.VALIDATION_ERROR
    elif http_status == 401:
        return ErrorCodes.UNAUTHENTICATED
    elif http_status == 403:
        return ErrorCodes.PERMISSION_DENIED
    elif http_status == 404:
        return ErrorCodes.NOT_FOUND
    elif http_status == 409:
        return ErrorCodes.CONFLICT
    elif http_status == 429:
        return ErrorCodes.RATE_LIMIT_EXCEEDED
    return ErrorCodes.INTERNAL_SERVER_ERROR


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """
    Standard DRF exception handler producing the {code, message, traceId} envelope.
    Ensures that internal stack traces or internal exception details never leak to API responses.
    """
    request = context.get("request")
    trace_id = getattr(request, "trace_id", None) if request else None
    if not trace_id:
        trace_id = str(uuid.uuid4())

    # Handle domain-specific ApplicationError
    if isinstance(exc, ApplicationError):
        return Response(
            {
                "code": exc.code,
                "message": exc.message,
                "traceId": trace_id,
            },
            status=exc.status_code,
        )

    # Invoke standard DRF handler
    response = exception_handler(exc, context)

    if response is not None:
        # Standard DRF APIException was handled
        http_status = response.status_code

        # Fix DRF 403 mutation: when a view lacks an authenticator header, DRF mutates
        # AuthenticationFailed / NotAuthenticated status from 401 to 403.
        # Enforces SPEC SDD §88 and §89: 401 UNAUTHORIZED for authentication failures.
        if isinstance(exc, (exceptions.AuthenticationFailed, exceptions.NotAuthenticated)):
            http_status = status.HTTP_401_UNAUTHORIZED
            response.status_code = status.HTTP_401_UNAUTHORIZED
            if "WWW-Authenticate" not in response:
                response["WWW-Authenticate"] = 'Bearer realm="api"'

        error_code = map_status_to_code(http_status)
        message = None

        if isinstance(response.data, dict):
            if "code" in response.data:
                error_code = str(response.data["code"])
            if "message" in response.data:
                message = str(response.data["message"])
            elif "detail" in response.data:
                detail_val = response.data["detail"]
                message = str(detail_val)
                if hasattr(detail_val, "code") and detail_val.code and detail_val.code not in ("invalid", "not_authenticated"):
                    candidate_code = str(detail_val.code).upper()
                    if candidate_code in ERROR_REGISTRY:
                        error_code = candidate_code
            else:
                first_key = next(iter(response.data), None)
                if first_key and isinstance(response.data[first_key], list) and response.data[first_key]:
                    message = f"{first_key}: {response.data[first_key][0]}"
                else:
                    message = "Validation failed. Check submitted fields."
        elif isinstance(response.data, list) and response.data:
            message = str(response.data[0])

        if not message:
            reg = ERROR_REGISTRY.get(error_code)
            message = reg.default_message if reg else "An error occurred."

        return Response(
            {
                "code": error_code,
                "message": message,
                "traceId": trace_id,
            },
            status=http_status,
        )

    # Unhandled server exception (e.g., unexpected Python Exception / 500)
    logger.error(
        "unhandled_server_exception",
        trace_id=trace_id,
        error_type=type(exc).__name__,
        exc_info=exc,
        path=request.path if request else "unknown",
        method=request.method if request else "unknown",
    )

    return Response(
        {
            "code": ErrorCodes.INTERNAL_SERVER_ERROR,
            "message": "An unexpected internal server error occurred.",
            "traceId": trace_id,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
