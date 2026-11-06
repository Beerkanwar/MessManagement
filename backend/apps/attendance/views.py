"""
Views for attendance, extras, and corrections [SPEC SDD §64, Appendix A, ImplementationGuide Phase 7].
Provides:
- GET /attendance: Scoped effective meal attendance records.
- GET /attendance/summary: Monthly aggregated meal counts and monetary totals.
- GET /extras/transactions: Scoped extra transactions history.
- POST /attendance/corrections: Online attendance correction submission (ADD_MISSING / REMOVE_INCORRECT).
- GET /attendance/corrections: Scoped correction history.
"""
from datetime import datetime

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.attendance.selectors import (
    get_attendance_summary,
    get_scoped_attendance_corrections,
    get_scoped_extra_transactions,
    get_scoped_meal_consumptions,
)
from apps.attendance.serializers import (
    AttendanceCorrectionCreateSerializer,
    AttendanceCorrectionSerializer,
    AttendanceSummarySerializer,
    ExtraTransactionSerializer,
    MealConsumptionSerializer,
)
from apps.attendance.services import apply_attendance_correction
from apps.core.pagination import StandardPageNumberPagination
from apps.identity.authentication import DeviceBindingJWTAuthentication


def _parse_date(date_str: str | None):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@extend_schema(
    summary="List Effective Attendance",
    description=(
        "Lists effective meal attendance records scoped to caller role [SPEC SDD §64, ImplementationGuide Phase 7]. "
        "A record is included unless its latest applied correction is REMOVE_INCORRECT."
    ),
    tags=["attendance"],
    parameters=[
        OpenApiParameter("start_date", str, description="Filter meals on or after YYYY-MM-DD"),
        OpenApiParameter("end_date", str, description="Filter meals on or before YYYY-MM-DD"),
        OpenApiParameter("meal_type", str, description="Filter by meal type code (BREAKFAST, LUNCH, DINNER)"),
        OpenApiParameter("student_id", int, description="Filter by student ID"),
        OpenApiParameter("mess_id", int, description="Filter by mess ID"),
        OpenApiParameter("hostel_id", int, description="Filter by hostel ID"),
    ],
    responses={200: MealConsumptionSerializer(many=True)},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def attendance_list_view(request):
    """Returns effective meal consumptions scoped to the user."""
    start_date = _parse_date(request.query_params.get("start_date"))
    end_date = _parse_date(request.query_params.get("end_date"))
    meal_type = request.query_params.get("meal_type")
    student_id = request.query_params.get("student_id")
    mess_id = request.query_params.get("mess_id")
    hostel_id = request.query_params.get("hostel_id")

    qs = get_scoped_meal_consumptions(
        request.user,
        student_id=int(student_id) if student_id and student_id.isdigit() else None,
        mess_id=int(mess_id) if mess_id and mess_id.isdigit() else None,
        hostel_id=int(hostel_id) if hostel_id and hostel_id.isdigit() else None,
        meal_type=meal_type,
        start_date=start_date,
        end_date=end_date,
    )

    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = MealConsumptionSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    summary="Get Attendance Summary",
    description="Returns aggregated counts of meals by type and total price snapshot for the caller scope.",
    tags=["attendance"],
    parameters=[
        OpenApiParameter("start_date", str, description="Summary start date YYYY-MM-DD"),
        OpenApiParameter("end_date", str, description="Summary end date YYYY-MM-DD"),
        OpenApiParameter("student_id", int, description="Filter by student ID"),
        OpenApiParameter("mess_id", int, description="Filter by mess ID"),
        OpenApiParameter("hostel_id", int, description="Filter by hostel ID"),
    ],
    responses={200: AttendanceSummarySerializer},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def attendance_summary_view(request):
    """Returns aggregated attendance counts and totals."""
    start_date = _parse_date(request.query_params.get("start_date"))
    end_date = _parse_date(request.query_params.get("end_date"))
    student_id = request.query_params.get("student_id")
    mess_id = request.query_params.get("mess_id")
    hostel_id = request.query_params.get("hostel_id")

    summary_data = get_attendance_summary(
        request.user,
        student_id=int(student_id) if student_id and student_id.isdigit() else None,
        mess_id=int(mess_id) if mess_id and mess_id.isdigit() else None,
        hostel_id=int(hostel_id) if hostel_id and hostel_id.isdigit() else None,
        start_date=start_date,
        end_date=end_date,
    )
    serializer = AttendanceSummarySerializer(summary_data)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Extra Transactions",
    description="Lists extra item purchase transactions scoped to caller role [SPEC SDD §64].",
    tags=["extras"],
    parameters=[
        OpenApiParameter("start_date", str, description="Filter extras on or after YYYY-MM-DD"),
        OpenApiParameter("end_date", str, description="Filter extras on or before YYYY-MM-DD"),
        OpenApiParameter("extra_item_id", int, description="Filter by extra item ID"),
        OpenApiParameter("student_id", int, description="Filter by student ID"),
        OpenApiParameter("mess_id", int, description="Filter by mess ID"),
        OpenApiParameter("hostel_id", int, description="Filter by hostel ID"),
    ],
    responses={200: ExtraTransactionSerializer(many=True)},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def extra_transactions_list_view(request):
    """Lists extra item transactions scoped to user."""
    start_date = _parse_date(request.query_params.get("start_date"))
    end_date = _parse_date(request.query_params.get("end_date"))
    extra_item_id = request.query_params.get("extra_item_id")
    student_id = request.query_params.get("student_id")
    mess_id = request.query_params.get("mess_id")
    hostel_id = request.query_params.get("hostel_id")

    qs = get_scoped_extra_transactions(
        request.user,
        student_id=int(student_id) if student_id and student_id.isdigit() else None,
        mess_id=int(mess_id) if mess_id and mess_id.isdigit() else None,
        hostel_id=int(hostel_id) if hostel_id and hostel_id.isdigit() else None,
        extra_item_id=int(extra_item_id) if extra_item_id and extra_item_id.isdigit() else None,
        start_date=start_date,
        end_date=end_date,
    )

    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ExtraTransactionSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    summary="List or Submit Attendance Corrections",
    description=(
        "GET: Lists correction history scoped to caller role.\n"
        "POST: Submits an online attendance correction (ADD_MISSING or REMOVE_INCORRECT) "
        "[SPEC SRS §32, DEC-12, DEC-22]. Allowed for Super Admin, Hostel Clerk (own hostel), "
        "and Mess Manager (own mess). Reason required (min 5 chars)."
    ),
    tags=["attendance"],
    request=AttendanceCorrectionCreateSerializer,
    parameters=[
        OpenApiParameter("start_date", str, description="Filter corrections on or after YYYY-MM-DD"),
        OpenApiParameter("end_date", str, description="Filter corrections on or before YYYY-MM-DD"),
        OpenApiParameter("action", str, description="Filter by action (ADD_MISSING or REMOVE_INCORRECT)"),
        OpenApiParameter("student_id", int, description="Filter by student ID"),
        OpenApiParameter("mess_id", int, description="Filter by mess ID"),
    ],
    responses={
        200: AttendanceCorrectionSerializer(many=True),
        201: OpenApiResponse(response=AttendanceCorrectionSerializer, description="Correction applied"),
        400: OpenApiResponse(description="Validation error, missing reason, or locked billing period"),
        404: OpenApiResponse(description="Student or scope not found [D12]"),
    },
)
@api_view(["GET", "POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def attendance_corrections_list_create_view(request):
    """Handles GET (list) and POST (submit) for attendance corrections."""
    if request.method == "POST":
        serializer = AttendanceCorrectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        correlation_id = getattr(request, "correlation_id", "")

        correction = apply_attendance_correction(
            correction_transaction_id=data["correction_transaction_id"],
            student_id=data["student_id"],
            meal_date=data["meal_date"],
            meal_type=data["meal_type"],
            action=data["action"],
            reason=data["reason"],
            actor=request.user,
            correlation_id=correlation_id,
        )

        resp_serializer = AttendanceCorrectionSerializer(correction)
        return Response(resp_serializer.data, status=status.HTTP_201_CREATED)

    # GET
    start_date = _parse_date(request.query_params.get("start_date"))
    end_date = _parse_date(request.query_params.get("end_date"))
    action = request.query_params.get("action")
    student_id = request.query_params.get("student_id")
    mess_id = request.query_params.get("mess_id")

    qs = get_scoped_attendance_corrections(
        request.user,
        student_id=int(student_id) if student_id and student_id.isdigit() else None,
        mess_id=int(mess_id) if mess_id and mess_id.isdigit() else None,
        action=action,
        start_date=start_date,
        end_date=end_date,
    )

    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = AttendanceCorrectionSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)
