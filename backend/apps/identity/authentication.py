"""
Device-bound JWT authentication class enforcing SPEC SDD §11.1 and SDD §100.
Validates HMAC signature, token expiry, issuer, audience, and active device binding.
"""
from typing import Any
import jwt
import structlog
from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from apps.core.error_codes import ErrorCodes
from apps.identity.models import DeviceRegistration, User


class DeviceBindingJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.identity.authentication.DeviceBindingJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }


class DeviceBindingJWTAuthentication(authentication.BaseAuthentication):
    """
    Validates HS256 JWT access tokens.
    Requires and enforces active device registration state on every request.
    If the device registration has been marked REPLACED, REVOKED, or LOGGED_OUT,
    the API request fails immediately with 401 [SPEC SDD §11.1].
    """

    def authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="api"'

    def authenticate(self, request: Request) -> tuple[User, dict[str, Any]] | None:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        raw_token = parts[1]
        signing_key = settings.SIMPLE_JWT.get("SIGNING_KEY")
        expected_issuer = settings.SIMPLE_JWT.get("ISSUER", "mess-management-auth")
        expected_audience = settings.SIMPLE_JWT.get("AUDIENCE", "mess-management-api")
        algorithms = [settings.SIMPLE_JWT.get("ALGORITHM", "HS256")]

        try:
            payload = jwt.decode(
                raw_token,
                signing_key,
                algorithms=algorithms,
                issuer=expected_issuer,
                audience=expected_audience,
                options={"require": ["exp", "iat", "iss", "aud", "user_id", "device_registration_id"]},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed(
                {"code": ErrorCodes.TOKEN_EXPIRED, "message": "Access token has expired."},
                code="token_expired",
            )
        except jwt.InvalidIssuerError:
            raise AuthenticationFailed(
                {"code": ErrorCodes.INVALID_TOKEN, "message": "Invalid token issuer."},
                code="invalid_issuer",
            )
        except jwt.InvalidAudienceError:
            raise AuthenticationFailed(
                {"code": ErrorCodes.INVALID_TOKEN, "message": "Invalid token audience."},
                code="invalid_audience",
            )
        except jwt.PyJWTError as e:
            raise AuthenticationFailed(
                {"code": ErrorCodes.INVALID_TOKEN, "message": f"Token validation failed: {str(e)}"},
                code="invalid_token",
            )

        user_id = payload.get("user_id")
        device_reg_id = payload.get("device_registration_id")

        try:
            device = DeviceRegistration.objects.get(device_registration_id=device_reg_id)
        except DeviceRegistration.DoesNotExist:
            raise AuthenticationFailed(
                {"code": ErrorCodes.DEVICE_REVOKED, "message": "Device registration not found."},
                code="device_not_found",
            )

        # Invariant: Device session must be ACTIVE
        if device.session_status != "ACTIVE":
            raise AuthenticationFailed(
                {
                    "code": ErrorCodes.DEVICE_REVOKED,
                    "message": f"Device session is {device.session_status.lower()}.",
                },
                code="device_revoked",
            )

        try:
            user = User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed(
                {"code": ErrorCodes.UNAUTHENTICATED, "message": "User account not found."},
                code="user_not_found",
            )

        # Invariant: User status must be ACTIVE
        if user.status != "ACTIVE":
            raise AuthenticationFailed(
                {
                    "code": ErrorCodes.UNAUTHENTICATED,
                    "message": f"User account is {user.status.lower()}.",
                },
                code="user_inactive",
            )

        # Attach device to request
        request.device = device

        # Bind user and device context to structlog
        structlog.contextvars.bind_contextvars(
            user_id=str(user.user_id),
            device_id=device.device_id,
        )

        return (user, payload)
