"""
Views for QR endpoint group [SPEC SDD §19-21, §64, ImplementationGuide Phase 6].
Enforces:
- Student-only secret fetch on active device session.
- Super Admin secret rotation with reason and audit trail.
- Cache-Control: no-store header on secret responses.
"""
import base64

from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.permissions import IsStudent, IsSuperAdmin
from apps.hostel.models import Student
from apps.identity.authentication import DeviceBindingJWTAuthentication
from apps.qr.serializers import (
    RotateSecretRequestSerializer,
    RotateSecretResponseSerializer,
    StudentSecretResponseSerializer,
)
from apps.qr.services import get_active_student_secret, rotate_student_secret


class QRSecretThrottle(ScopedRateThrottle):
    scope = "qr_secret"


@extend_schema(
    summary="Get Student QR Secret",
    description=(
        "Returns the active rolling QR secret key for the authenticated student on their active device "
        "[SPEC SDD §19, SDD §21]. Never cached outside secure storage."
    ),
    tags=["qr"],
    responses={
        200: OpenApiResponse(
            response=StudentSecretResponseSerializer,
            description="Active rolling secret key (base64) and version",
        ),
        401: OpenApiResponse(description="Unauthenticated or device session expired"),
        403: OpenApiResponse(description="Forbidden: Non-students or inactive device"),
    },
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated, IsStudent])
@throttle_classes([QRSecretThrottle])
def qr_secret_view(request):
    """
    Delivers the active 32-byte secret key material to the student's mobile app over HTTPS.
    Single decryption point [ImplementationGuide Phase 6 requirement 2].
    """
    # Enforce HTTPS in production environments (ISSUE-11)
    from django.conf import settings
    if not request.is_secure() and not settings.DEBUG and not getattr(settings, "TESTING", False):
        raise PermissionDenied("HTTPS is strictly required for QR secret delivery.")

    # Enforce active device registration
    device = getattr(request, "device", None)
    if device is not None and getattr(device, "session_status", "ACTIVE") != "ACTIVE":
        raise PermissionDenied("Device session is not active.")

    # Retrieve student profile
    student = Student.objects.filter(user=request.user, status="ACTIVE").first()
    if not student:
        raise PermissionDenied("Authenticated user has no active student profile.")

    student_secret, plain_bytes = get_active_student_secret(student)

    # Encode secret as base64 string
    base64_secret = base64.b64encode(plain_bytes).decode("ascii")

    serializer = StudentSecretResponseSerializer({
        "secret_version": student_secret.secret_version,
        "secret": base64_secret,
        "effective_from": student_secret.effective_from,
    })

    response = Response(serializer.data, status=status.HTTP_200_OK)
    # Never cache secret response outside secure client memory [SPEC SDD §21]
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    return response


@extend_schema(
    summary="Rotate Student Secret(s)",
    description=(
        "Super Admin rotates QR secret keys for a single student, a hostel, or a mess [SPEC SDD §21, DEC-13]. "
        "Retires active version, provisions version n+1, advances change cursor, and records SECRET_ROTATED audit."
    ),
    tags=["qr"],
    request=RotateSecretRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=RotateSecretResponseSerializer,
            description="Secrets rotated successfully (contains version numbers only, never secret keys)",
        ),
        400: OpenApiResponse(description="Validation error or reason required"),
        403: OpenApiResponse(description="Forbidden: Super Admin only"),
    },
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def qr_rotate_view(request):
    """
    Super Admin endpoint to rotate student secrets.
    Does not expose plaintext secrets in response or audit log.
    """
    serializer = RotateSecretRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    correlation_id = getattr(request, "correlation_id", "")

    rotations = rotate_student_secret(
        student_id=serializer.validated_data.get("student_id"),
        hostel_id=serializer.validated_data.get("hostel_id"),
        mess_id=serializer.validated_data.get("mess_id"),
        reason=serializer.validated_data["reason"],
        actor=request.user,
        correlation_id=correlation_id,
    )

    response_data = {
        "message": f"Successfully rotated secrets for {len(rotations)} student(s).",
        "affected_count": len(rotations),
        "rotations": rotations,
    }
    return Response(response_data, status=status.HTTP_200_OK)
