"""
Views for the mess pause endpoint group [SPEC SDD §64, DBDD §7].

Endpoints:
- POST /api/v1/pauses: Student submits a pause request.
- GET  /api/v1/pauses: Student lists their own pauses.
- GET  /api/v1/pauses/current: Student reads the current pause state.
- POST /api/v1/pauses/<id>/cancel: Student cancels their own pause.
- POST /api/v1/pauses/request: Backward-compatible alias for POST /pauses.

The guide's endpoint table exposes POST /pauses; the legacy /pauses/request path is
kept as an alias so existing clients do not break. Managers have no pause endpoint;
they receive pause state through the sync download.
"""
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import NotFoundError, PermissionDeniedError
from apps.core.pagination import StandardPageNumberPagination
from apps.identity.authentication import DeviceBindingJWTAuthentication
from apps.identity.selectors import get_user_role, get_visible_students_queryset
from apps.mess.models import Mess
from apps.pause.models import MessPause
from apps.pause.selectors import get_pause_by_id, get_pause_state
from apps.pause.serializers import (
    PauseCancelSerializer,
    PauseMealSlotSerializer,
    PauseRequestSerializer,
    PauseResponseSerializer,
)
from apps.pause.services import (
    ACTIVATION_SLOT_COUNT,
    cancel_pause,
    get_pauses_for_student,
    request_pause,
)


def _require_student(request):
    """Return the caller's Student profile, or raise the appropriate domain error."""
    if get_user_role(request.user) != "STUDENT":
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Only students may use the pause endpoints.",
        )
    student = get_visible_students_queryset(request.user).first()
    if not student:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="Student profile not found.",
        )
    return student


def _iso(value):
    """Render a date/datetime as an ISO string for the API contract."""
    return value.isoformat() if value is not None else None


def _serialize_pause(pause: MessPause) -> dict:
    """Serialize a pause, including counted and skipped activation slots."""
    slots = PauseMealSlotSerializer(
        pause.meal_slots.select_related("meal_occurrence__meal_type").order_by(
            "slot_sequence"
        ),
        many=True,
    ).data
    consumed = pause.meal_slots.filter(
        qualifies_for_activation=True,
        consumed_for_activation=True,
    ).count()
    return {
        "pause_id": pause.pause_id,
        "student_id": pause.student_id,
        "mess_id": pause.mess_id,
        "requested_start_date": _iso(pause.requested_start_date),
        "requested_end_date": _iso(pause.requested_end_date),
        "effective_start_date": _iso(pause.effective_start_date),
        "effective_end_date": _iso(pause.effective_end_date),
        "activation_meal_date": _iso(pause.activation_meal_date),
        "status": pause.status,
        "requested_at": _iso(pause.requested_at),
        "cancelled_at": _iso(pause.cancelled_at),
        "completed_at": _iso(pause.completed_at),
        "cancellation_reason": pause.cancellation_reason,
        "meal_slots": slots,
        "slots_remaining": max(0, ACTIVATION_SLOT_COUNT - consumed),
    }


def _create_pause(request) -> Response:
    """Shared submit implementation for POST /pauses and its alias."""
    student = _require_student(request)

    serializer = PauseRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    mess = Mess.objects.filter(
        mess_id=serializer.validated_data["mess_id"]
    ).first()
    if not mess:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Mess not found.")

    pause = request_pause(
        student=student,
        mess=mess,
        requested_start_date=serializer.validated_data["requested_start_date"],
        requested_end_date=serializer.validated_data["requested_end_date"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(_serialize_pause(pause), status=status.HTTP_201_CREATED)


@extend_schema(
    methods=["GET"],
    summary="List Mess Pauses",
    description="Lists the authenticated student's own pause history [SPEC DBDD §7].",
    tags=["pauses"],
    responses={200: PauseResponseSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    summary="Request Mess Pause",
    description=(
        "Student requests a mess pause [SPEC DBDD §7, DEC-06]. "
        "Pause starts in SCHEDULED status and becomes ACTIVE after three qualifying "
        "Breakfast, Lunch or Dinner slots pass."
    ),
    tags=["pauses"],
    request=PauseRequestSerializer,
    responses={
        201: PauseResponseSerializer,
        400: OpenApiResponse(description="Validation error"),
        403: OpenApiResponse(description="Permission denied"),
        409: OpenApiResponse(description="Conflict: existing pause"),
    },
)
@api_view(["GET", "POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def pause_collection_view(request):
    """List or create the authenticated student's pauses."""
    if request.method == "POST":
        return _create_pause(request)

    student = _require_student(request)
    pauses = get_pauses_for_student(student)

    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(pauses, request)
    if page is not None:
        return paginator.get_paginated_response(
            [_serialize_pause(pause) for pause in page]
        )
    return Response([_serialize_pause(pause) for pause in pauses])


@extend_schema(
    summary="Request Mess Pause (legacy path)",
    description="Alias of POST /api/v1/pauses retained for existing clients.",
    tags=["pauses"],
    request=PauseRequestSerializer,
    responses={201: PauseResponseSerializer, 400: OpenApiResponse(description="Validation error")},
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def pause_request_view(request):
    """Backward-compatible alias for pause submission."""
    return _create_pause(request)


@extend_schema(
    summary="Current Mess Pause",
    description=(
        "Returns the authenticated student's current SCHEDULED or ACTIVE pause, "
        "including its counted slots, effective start and end dates [DEC-06]."
    ),
    tags=["pauses"],
    responses={200: OpenApiResponse(description="Current pause state (or has_pause=false)")},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def pause_current_view(request):
    """Return the student's current pause state."""
    student = _require_student(request)
    return Response(get_pause_state(student), status=status.HTTP_200_OK)


@extend_schema(
    summary="Cancel Mess Pause",
    description=(
        "Cancels the authenticated student's own SCHEDULED or ACTIVE pause "
        "[SPEC DBDD §7, DEC-23]."
    ),
    tags=["pauses"],
    request=PauseCancelSerializer,
    responses={
        200: PauseResponseSerializer,
        400: OpenApiResponse(description="Validation error"),
        403: OpenApiResponse(description="Permission denied"),
        404: OpenApiResponse(description="Pause not found"),
        409: OpenApiResponse(description="Conflict: already terminated"),
    },
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def pause_cancel_view(request, pause_id: int):
    """Cancel a pause owned by the authenticated student."""
    student = _require_student(request)

    pause = get_pause_by_id(pause_id)
    if not pause or pause.student_id != student.student_id:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="Pause not found.",
        )

    serializer = PauseCancelSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    pause = cancel_pause(
        pause=pause,
        actor=request.user,
        reason=serializer.validated_data.get("reason", ""),
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(_serialize_pause(pause), status=status.HTTP_200_OK)
