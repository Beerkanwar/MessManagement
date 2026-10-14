"""
Identity, authentication, and device management API views [SPEC SDD §11, §64, §88].
"""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from apps.core.permissions import IsSuperAdmin
from apps.identity.authentication import DeviceBindingJWTAuthentication
from apps.identity.selectors import get_user_assignment_summary, get_user_role
from apps.identity.serializers import (
    AdminRevokeDeviceSerializer,
    ChangePasswordRequestSerializer,
    ForgotPasswordRequestSerializer,
    LoginRequestSerializer,
    RefreshTokenRequestSerializer,
    ResetPasswordRequestSerializer,
    UpdateDeviceMetadataSerializer,
    VerifyOtpRequestSerializer,
)
from apps.identity.services.auth_service import change_password, login_user, logout_user
from apps.identity.services.device_service import (
    admin_revoke_device,
    get_current_device_summary,
    self_revoke_device,
    update_device_metadata,
)
from apps.identity.services.password_reset_service import (
    request_password_reset,
    reset_password,
    verify_password_reset_otp,
)
from apps.identity.services.token_service import rotate_refresh_token


# ==============================================================================
# Authentication Endpoints
# ==============================================================================


@extend_schema(
    summary="User Login",
    description="Authenticates credentials, binds single active device, and returns token pair [SPEC SDD §11].",
    tags=["auth"],
    request=LoginRequestSerializer,
    responses={
        200: OpenApiResponse(description="Successful authentication"),
        401: OpenApiResponse(description="Invalid credentials or inactive account"),
        403: OpenApiResponse(description="Wrong client surface for role"),
        409: OpenApiResponse(description="Previous manager device has unsynced transactions"),
        429: OpenApiResponse(description="Too many failed login attempts (locked 15 min)"),
    },
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = login_user(
        email=serializer.validated_data["email"],
        password=serializer.validated_data["password"],
        device_id=serializer.validated_data["device_id"],
        platform=serializer.validated_data["platform"],
        app_version=serializer.validated_data.get("app_version", ""),
        device_name=serializer.validated_data.get("device_name", ""),
        request=request,
    )
    return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    summary="Rotate Refresh Token",
    description="Rotates opaque refresh token with 30s replay grace window [SPEC SDD §11, DEC-10].",
    tags=["auth"],
    request=RefreshTokenRequestSerializer,
    responses={
        200: OpenApiResponse(description="New token pair issued"),
        401: OpenApiResponse(description="Invalid, expired, or stolen refresh token"),
    },
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def refresh_view(request):
    serializer = RefreshTokenRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    correlation_id = getattr(request, "correlation_id", "")
    result = rotate_refresh_token(
        raw_token=serializer.validated_data["refresh"],
        correlation_id=correlation_id,
    )
    return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    summary="User Logout",
    description="Revokes current device session and refresh tokens immediately [SPEC SDD §11].",
    tags=["auth"],
    request=None,
    responses={
        200: OpenApiResponse(description="Logged out successfully"),
        401: OpenApiResponse(description="Unauthenticated"),
    },
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def logout_view(request):
    device = getattr(request, "device", None)
    if device:
        logout_user(request.user, device, request=request)
    return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Change Password",
    description="Changes password for authenticated user [SPEC SDD §12].",
    tags=["auth"],
    request=ChangePasswordRequestSerializer,
    responses={
        200: OpenApiResponse(description="Password changed successfully"),
        400: OpenApiResponse(description="Incorrect current password or policy failure"),
        401: OpenApiResponse(description="Unauthenticated"),
    },
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    serializer = ChangePasswordRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    change_password(
        user=request.user,
        current_password=serializer.validated_data["current_password"],
        new_password=serializer.validated_data["new_password"],
        request=request,
    )
    return Response({"message": "Password changed successfully."}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Forgot Password / Request Reset OTP",
    description="Dispatches 6-digit verification OTP by email. Always returns 202 [SPEC SRS §5, SDD §12].",
    tags=["auth"],
    request=ForgotPasswordRequestSerializer,
    responses={
        202: OpenApiResponse(description="OTP dispatched if account exists"),
        429: OpenApiResponse(description="Hourly rate limit exceeded"),
    },
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def forgot_password_view(request):
    serializer = ForgotPasswordRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = request_password_reset(
        email=serializer.validated_data["email"],
        request=request,
    )
    return Response(result, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    summary="Verify Password Reset OTP",
    description="Validates OTP code without consuming it [SPEC SDD §12, DEC-11].",
    tags=["auth"],
    request=VerifyOtpRequestSerializer,
    responses={
        200: OpenApiResponse(description="OTP verified successfully"),
        400: OpenApiResponse(description="Invalid OTP or attempts exceeded"),
    },
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def verify_otp_view(request):
    serializer = VerifyOtpRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = verify_password_reset_otp(
        email=serializer.validated_data["email"],
        otp=serializer.validated_data["otp"],
    )
    return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    summary="Reset Password with OTP",
    description="Sets new password with verified OTP, revoking all active sessions [SPEC SDD §12].",
    tags=["auth"],
    request=ResetPasswordRequestSerializer,
    responses={
        200: OpenApiResponse(description="Password reset successfully"),
        400: OpenApiResponse(description="Invalid OTP or policy failure"),
    },
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_password_view(request):
    serializer = ResetPasswordRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    reset_password(
        email=serializer.validated_data["email"],
        otp=serializer.validated_data["otp"],
        new_password=serializer.validated_data["new_password"],
        request=request,
    )
    return Response({"message": "Password reset successfully. You may now sign in."}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Current User Profile & Scope [REC]",
    description="Returns current user identity, role, and assigned hostel/mess scopes [SPEC SDD §11].",
    tags=["auth"],
    responses={
        200: OpenApiResponse(description="User profile and role summary"),
        401: OpenApiResponse(description="Unauthenticated"),
    },
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def auth_me_view(request):
    role = get_user_role(request.user)
    device = getattr(request, "device", None)
    return Response(
        {
            "user": {
                "user_id": request.user.user_id,
                "email": request.user.email,
                "full_name": request.user.full_name,
            },
            "role": role,
            "assignment": get_user_assignment_summary(request.user),
            "device": get_current_device_summary(device) if device else None,
        },
        status=status.HTTP_200_OK,
    )


# ==============================================================================
# Device Management Endpoints
# ==============================================================================


@extend_schema(
    summary="Current Device Binding",
    description="Returns current device session state and last sync time [SPEC SDD §11].",
    tags=["devices"],
    responses={
        200: OpenApiResponse(description="Device details"),
        401: OpenApiResponse(description="Unauthenticated"),
    },
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def device_current_view(request):
    device = getattr(request, "device", None)
    if not device:
        return Response({"message": "No active device session."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(get_current_device_summary(device), status=status.HTTP_200_OK)


@extend_schema(
    summary="Update Device Metadata",
    description="Updates app version, device name, and platform for current device [SPEC SDD §11].",
    tags=["devices"],
    request=UpdateDeviceMetadataSerializer,
    responses={
        200: OpenApiResponse(description="Device metadata updated"),
        401: OpenApiResponse(description="Unauthenticated"),
    },
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def device_register_view(request):
    serializer = UpdateDeviceMetadataSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    device = getattr(request, "device", None)
    if not device:
        return Response({"message": "No active device session."}, status=status.HTTP_400_BAD_REQUEST)

    result = update_device_metadata(
        device_registration=device,
        app_version=serializer.validated_data.get("app_version"),
        device_name=serializer.validated_data.get("device_name"),
        platform=serializer.validated_data.get("platform"),
    )
    return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    summary="Self-Revoke Current Device",
    description="Revokes authority of current device session immediately [SPEC SDD §11].",
    tags=["devices"],
    request=None,
    responses={
        200: OpenApiResponse(description="Device revoked successfully"),
        401: OpenApiResponse(description="Unauthenticated"),
    },
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def device_revoke_view(request):
    device = getattr(request, "device", None)
    if device:
        self_revoke_device(request.user, device, request=request)
    return Response({"message": "Device revoked successfully."}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Admin Revoke Device",
    description="Super Admin revokes a device session. Enforces D14 sync waiting for managers [SPEC SDD §121].",
    tags=["admin"],
    request=AdminRevokeDeviceSerializer,
    responses={
        200: OpenApiResponse(description="Device revoked or marked pending sync"),
        400: OpenApiResponse(description="Reason required"),
        403: OpenApiResponse(description="Permission denied"),
        404: OpenApiResponse(description="Device not found"),
    },
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_device_revoke_view(request, device_id: int):
    serializer = AdminRevokeDeviceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = admin_revoke_device(
        super_admin_user=request.user,
        device_registration_id=device_id,
        reason=serializer.validated_data["reason"],
        request=request,
    )
    return Response(result, status=status.HTTP_200_OK)
