"""
Views for identity and authentication routing shell.
"""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="User Login",
    description="Authenticates user credentials and device info, returning JWT access and refresh tokens [SPEC SDD §11].",
    tags=["auth"],
    request=None,
    responses={
        200: OpenApiResponse(description="Successful authentication"),
        401: OpenApiResponse(description="Invalid credentials"),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def login_stub_view(request):
    return Response({"message": "Auth shell stub"}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Rotate Refresh Token",
    description="Rotates refresh token and returns a new access/refresh token pair [SPEC SDD §11].",
    tags=["auth"],
    request=None,
    responses={
        200: OpenApiResponse(description="Token rotated successfully"),
        401: OpenApiResponse(description="Invalid or expired refresh token"),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_stub_view(request):
    return Response({"message": "Refresh shell stub"}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Get Current Device Binding",
    description="Returns current device registration state and last synchronization status [SPEC SDD §11].",
    tags=["devices"],
    responses={
        200: OpenApiResponse(description="Device details"),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def device_current_stub_view(request):
    return Response({"message": "Devices shell stub"}, status=status.HTTP_200_OK)
