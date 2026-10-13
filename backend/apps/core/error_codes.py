"""
Registry of API error codes across the system.
Enforces SPEC SDD §88 and §89 status code mappings.
"""
from typing import NamedTuple


class ErrorDefinition(NamedTuple):
    code: str
    http_status: int
    default_message: str


class ErrorCodes:
    # 400 Validation & Client errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    MALFORMED_REQUEST = "MALFORMED_REQUEST"

    # 401 Authentication errors
    UNAUTHENTICATED = "UNAUTHENTICATED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"

    # 403 Authorization & Scope errors
    FORBIDDEN = "FORBIDDEN"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    ROLE_NOT_PERMITTED = "ROLE_NOT_PERMITTED"
    WRONG_CLIENT = "WRONG_CLIENT"

    # 404 Not Found
    NOT_FOUND = "NOT_FOUND"
    OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"

    # 409 Concurrency & Domain State Conflicts
    CONFLICT = "CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    STATE_CONFLICT = "STATE_CONFLICT"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    DEVICE_REVOKED = "DEVICE_REVOKED"
    DEVICE_REVOKE_PENDING_SYNC = "DEVICE_REVOKE_PENDING_SYNC"
    BILLING_PERIOD_LOCKED = "BILLING_PERIOD_LOCKED"
    MEAL_NOT_SCHEDULED = "MEAL_NOT_SCHEDULED"
    CORRECTION_WINDOW_EXPIRED = "CORRECTION_WINDOW_EXPIRED"

    # 429 Throttling
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    THROTTLED = "THROTTLED"

    # 500 & 503 System errors
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# Status table mapping according to SDD §89
ERROR_REGISTRY: dict[str, ErrorDefinition] = {
    ErrorCodes.VALIDATION_ERROR: ErrorDefinition(
        code=ErrorCodes.VALIDATION_ERROR,
        http_status=400,
        default_message="Request validation failed.",
    ),
    ErrorCodes.BAD_REQUEST: ErrorDefinition(
        code=ErrorCodes.BAD_REQUEST,
        http_status=400,
        default_message="The request is invalid.",
    ),
    ErrorCodes.INVALID_PARAMETER: ErrorDefinition(
        code=ErrorCodes.INVALID_PARAMETER,
        http_status=400,
        default_message="An invalid query parameter or field was provided.",
    ),
    ErrorCodes.UNAUTHENTICATED: ErrorDefinition(
        code=ErrorCodes.UNAUTHENTICATED,
        http_status=401,
        default_message="Authentication credentials were not provided or are invalid.",
    ),
    ErrorCodes.TOKEN_EXPIRED: ErrorDefinition(
        code=ErrorCodes.TOKEN_EXPIRED,
        http_status=401,
        default_message="The authentication token has expired.",
    ),
    ErrorCodes.INVALID_TOKEN: ErrorDefinition(
        code=ErrorCodes.INVALID_TOKEN,
        http_status=401,
        default_message="The provided token is malformed or invalid.",
    ),
    ErrorCodes.FORBIDDEN: ErrorDefinition(
        code=ErrorCodes.FORBIDDEN,
        http_status=403,
        default_message="You do not have permission to perform this action.",
    ),
    ErrorCodes.PERMISSION_DENIED: ErrorDefinition(
        code=ErrorCodes.PERMISSION_DENIED,
        http_status=403,
        default_message="Access denied for the requested resource.",
    ),
    ErrorCodes.WRONG_CLIENT: ErrorDefinition(
        code=ErrorCodes.WRONG_CLIENT,
        http_status=403,
        default_message="This account cannot access this client application surface.",
    ),
    ErrorCodes.NOT_FOUND: ErrorDefinition(
        code=ErrorCodes.NOT_FOUND,
        http_status=404,
        default_message="The requested resource was not found.",
    ),
    ErrorCodes.OBJECT_NOT_FOUND: ErrorDefinition(
        code=ErrorCodes.OBJECT_NOT_FOUND,
        http_status=404,
        default_message="The target entity does not exist or is out of your authorized scope.",
    ),
    ErrorCodes.CONFLICT: ErrorDefinition(
        code=ErrorCodes.CONFLICT,
        http_status=409,
        default_message="Operation conflicted with the current resource state.",
    ),
    ErrorCodes.VERSION_CONFLICT: ErrorDefinition(
        code=ErrorCodes.VERSION_CONFLICT,
        http_status=409,
        default_message="This record was changed by someone else. Please reload and try again.",
    ),
    ErrorCodes.DEVICE_REVOKED: ErrorDefinition(
        code=ErrorCodes.DEVICE_REVOKED,
        http_status=409,
        default_message="Device session has been revoked.",
    ),
    ErrorCodes.DEVICE_REVOKE_PENDING_SYNC: ErrorDefinition(
        code=ErrorCodes.DEVICE_REVOKE_PENDING_SYNC,
        http_status=409,
        default_message="Previous device has unsynchronized transactions pending.",
    ),
    ErrorCodes.BILLING_PERIOD_LOCKED: ErrorDefinition(
        code=ErrorCodes.BILLING_PERIOD_LOCKED,
        http_status=409,
        default_message="The billing period is locked and cannot be modified.",
    ),
    ErrorCodes.RATE_LIMIT_EXCEEDED: ErrorDefinition(
        code=ErrorCodes.RATE_LIMIT_EXCEEDED,
        http_status=429,
        default_message="Rate limit exceeded. Please retry later.",
    ),
    ErrorCodes.INTERNAL_SERVER_ERROR: ErrorDefinition(
        code=ErrorCodes.INTERNAL_SERVER_ERROR,
        http_status=500,
        default_message="An unexpected internal server error occurred.",
    ),
    ErrorCodes.SERVICE_UNAVAILABLE: ErrorDefinition(
        code=ErrorCodes.SERVICE_UNAVAILABLE,
        http_status=503,
        default_message="The service is temporarily unavailable.",
    ),
}
