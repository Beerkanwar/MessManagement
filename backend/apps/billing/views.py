"""
Views for the billing and prepaid balance endpoint group
[SPEC SDD §64, DBDD §8, ImplementationGuide Phase 10].

Business rules live in services.py and selectors.py; these views only handle
HTTP concerns, thin validation and the role gate.

Endpoint map:
- /billing/semesters                     Super Admin: configuration
- /billing/policies                      Super Admin: effective-dated minimum diet
- /billing/periods[/{id}]                Super Admin: lifecycle and pre-flight
- /billing/periods/{id}/generate|review|lock|unlock
- /billing/bills[/{id}]                  Student (own, LOCKED), Clerk (hostel), Super Admin
- /billing/bills/{id}/adjustments        Super Admin: append FEE/FINE
- /billing/balances                      Student (own read), Super Admin
- /billing/balances/{student}/credits    Super Admin: authorized credit
- /billing/opening-balances (+ import)   Super Admin: semester opening balance
"""
from decimal import Decimal

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    parser_classes,
    permission_classes,
)
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.billing import selectors as billing_selectors
from apps.billing import services as billing_services
from apps.billing.serializers import (
    BalanceSerializer,
    BillAdjustmentCreateSerializer,
    BillSerializer,
    BillingPeriodSerializer,
    BillingPeriodUpdateSerializer,
    BillingPolicyCreateSerializer,
    BillingPolicySerializer,
    CreditSerializer,
    OpeningBalanceImportSerializer,
    OpeningBalanceSerializer,
    SemesterCreateSerializer,
    SemesterSerializer,
    UnlockPeriodSerializer,
)
from apps.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from apps.core.pagination import StandardPageNumberPagination
from apps.core.permissions import IsSuperAdmin
from apps.identity.selectors import get_user_role

BILLING_READER_ROLES = ("SUPER_ADMIN", "HOSTEL_CLERK", "STUDENT")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_super_admin(user) -> bool:
    return bool(getattr(user, "is_superuser", False)) or get_user_role(user) == "SUPER_ADMIN"


def _require_billing_reader(user) -> str:
    """Bills and balances are closed to Mess Managers [Phase 10 visibility rules]."""
    role = get_user_role(user)
    if getattr(user, "is_superuser", False):
        return "SUPER_ADMIN"
    if role not in BILLING_READER_ROLES:
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Billing reads are limited to students, hostel clerks and the Super Admin.",
        )
    return role


def _int_param(request, name: str) -> int | None:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Query parameter '{name}' must be an integer.",
        )


def _period_payload(period, *, include_preflight: bool = False, summary=None) -> dict:
    data = dict(BillingPeriodSerializer(period).data)
    if summary is not None:
        data["bill_count"] = summary["bill_count"]
        data["stale_transaction_count"] = summary["stale_transaction_count"]
        data["totals"] = {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in summary["totals"].items()
        }
    else:
        data["bill_count"] = period.bills.count() if hasattr(period, "bills") else 0
        data["stale_transaction_count"] = billing_selectors.count_stale_transactions(period)
        data["totals"] = {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in billing_selectors.bill_totals(period).items()
        }
    if include_preflight:
        preflight = billing_selectors.generation_preflight(period)
        semester = preflight["semester"]
        data["preflight"] = {
            "student_mess_pairs": preflight["student_mess_pairs"],
            "missing_policies": preflight["missing_policies"],
            "missing_rates": preflight["missing_rates"],
            "missing_semester": preflight["missing_semester"],
            "semester_id": semester.semester_id if semester else None,
            "semester_code": semester.code if semester else None,
        }
    return data


def _paginate(request, queryset, serializer_class):
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(
            serializer_class(page, many=True).data
        )
    return Response(serializer_class(queryset, many=True).data)


# ---------------------------------------------------------------------------
# Semesters
# ---------------------------------------------------------------------------


@extend_schema(
    methods=["GET"],
    summary="List Semesters",
    description="Lists institutional semesters used to key prepaid balances [SPEC DBDD §8].",
    tags=["billing"],
    responses={200: SemesterSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    summary="Create Semester",
    description="Super Admin creates a semester [ImplementationGuide Phase 10 build 1].",
    tags=["billing"],
    request=SemesterCreateSerializer,
    responses={201: SemesterSerializer, 400: OpenApiResponse(description="Validation error")},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def semester_collection_view(request):
    if request.method == "POST":
        serializer = SemesterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        semester = billing_services.create_semester(
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
            **serializer.validated_data,
        )
        return Response(SemesterSerializer(semester).data, status=status.HTTP_201_CREATED)

    return _paginate(
        request, billing_selectors.list_semesters(), SemesterSerializer
    )


# ---------------------------------------------------------------------------
# Billing policies
# ---------------------------------------------------------------------------


@extend_schema(
    methods=["GET"],
    summary="List Billing Policies",
    description="Lists effective-dated minimum-diet policies per mess [DEC-04a].",
    tags=["billing"],
    responses={200: BillingPolicySerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    summary="Create Billing Policy",
    description=(
        "Super Admin creates a new policy version. A new version closes the previous "
        "open row at its own effective_from; back-dated versions are refused."
    ),
    tags=["billing"],
    request=BillingPolicyCreateSerializer,
    responses={201: BillingPolicySerializer, 400: OpenApiResponse(description="Validation error")},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def policy_collection_view(request):
    if request.method == "POST":
        serializer = BillingPolicyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = billing_services.create_billing_policy(
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
            **serializer.validated_data,
        )
        return Response(
            BillingPolicySerializer(policy).data, status=status.HTTP_201_CREATED
        )

    return _paginate(request, billing_selectors.list_policies(), BillingPolicySerializer)


# ---------------------------------------------------------------------------
# Billing periods and lifecycle
# ---------------------------------------------------------------------------


@extend_schema(
    summary="List Billing Periods",
    description="Lists billing periods and their lifecycle states [SPEC DBDD §8].",
    tags=["billing"],
    responses={200: BillingPeriodSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def period_collection_view(request):
    periods = billing_selectors.list_billing_periods()
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(periods, request)
    rows = list(page if page is not None else periods)
    summaries = billing_selectors.period_summaries(rows)
    data = [
        _period_payload(period, summary=summaries[period.billing_period_id])
        for period in rows
    ]
    if page is not None:
        return paginator.get_paginated_response(data)
    return Response(data)


@extend_schema(
    methods=["GET"],
    summary="Billing Period Detail",
    description=(
        "Returns one period with summary totals, the count of transactions recorded "
        "since generation, and the generation pre-flight [Phase 10 build 5]."
    ),
    tags=["billing"],
    responses={200: BillingPeriodSerializer, 404: OpenApiResponse(description="Not found")},
)
@extend_schema(
    methods=["PATCH"],
    summary="Adjust Billing Period Dates",
    description="Super Admin adjusts the dates of an OPEN period [SDD §151]; audited.",
    tags=["billing"],
    request=BillingPeriodUpdateSerializer,
    responses={200: BillingPeriodSerializer, 400: OpenApiResponse(description="Validation error")},
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def period_detail_view(request, billing_period_id: int):
    period = billing_selectors.get_billing_period(billing_period_id)
    if period is None:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND", message="Billing period not found."
        )

    if request.method == "PATCH":
        serializer = BillingPeriodUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        period = billing_services.adjust_period_dates(
            billing_period_id=period.billing_period_id,
            period_start=serializer.validated_data.get(
                "period_start", period.period_start
            ),
            period_end=serializer.validated_data.get("period_end", period.period_end),
            version=serializer.validated_data["version"],
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )

    return Response(_period_payload(period, include_preflight=True))


@extend_schema(
    summary="Generate Bills",
    description=(
        "Generates or regenerates every student-and-mess bill for the period "
        "[C01, DEC-04, DEC-24]. The run is resumable and idempotent."
    ),
    tags=["billing"],
    request=None,
    responses={200: BillingPeriodSerializer, 400: OpenApiResponse(description="Validation error")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def period_generate_view(request, billing_period_id: int):
    result = billing_services.generate_bills(
        billing_period_id=billing_period_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    period = billing_selectors.get_billing_period(billing_period_id)
    payload = _period_payload(period, include_preflight=True)
    payload.update(result)
    return Response(payload)


@extend_schema(
    summary="Review Bills",
    description="BILL_GENERATED -> REVIEWED; bills become FINAL.",
    tags=["billing"],
    request=None,
    responses={200: BillingPeriodSerializer, 409: OpenApiResponse(description="Invalid state")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def period_review_view(request, billing_period_id: int):
    period = billing_services.review_period(
        billing_period_id=billing_period_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(_period_payload(period, include_preflight=True))


@extend_schema(
    summary="Lock Billing Period",
    description=(
        "REVIEWED -> LOCKED. Posts one BILL_CHARGE per bill and makes the snapshot "
        "immutable at the database level [DBDD-AC-22]."
    ),
    tags=["billing"],
    request=None,
    responses={200: BillingPeriodSerializer, 409: OpenApiResponse(description="Invalid state or stale")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def period_lock_view(request, billing_period_id: int):
    result = billing_services.lock_period(
        billing_period_id=billing_period_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    period = billing_selectors.get_billing_period(billing_period_id)
    payload = _period_payload(period, include_preflight=True)
    payload.update(result)
    return Response(payload)


@extend_schema(
    summary="Unlock Billing Period",
    description=(
        "LOCKED -> REVIEWED with a mandatory reason. Posts a BILL_REVERSAL per "
        "earlier charge and audits the previous and new state [DBDD-AC-23]."
    ),
    tags=["billing"],
    request=UnlockPeriodSerializer,
    responses={
        200: BillingPeriodSerializer,
        400: OpenApiResponse(description="Missing reason"),
        409: OpenApiResponse(description="Invalid state"),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def period_unlock_view(request, billing_period_id: int):
    serializer = UnlockPeriodSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = billing_services.unlock_period(
        billing_period_id=billing_period_id,
        reason=serializer.validated_data["reason"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    period = billing_selectors.get_billing_period(billing_period_id)
    payload = _period_payload(period, include_preflight=True)
    payload.update(result)
    return Response(payload)


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------


@extend_schema(
    summary="List Bills",
    description=(
        "Students see their own bills only once LOCKED; Clerks see their hostel's "
        "generated, reviewed and locked bills; Super Admin sees all [Phase 10 build 9]."
    ),
    tags=["billing"],
    responses={200: BillSerializer(many=True), 403: OpenApiResponse(description="Permission denied")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bill_collection_view(request):
    _require_billing_reader(request.user)
    bills = billing_selectors.get_bills_scoped(
        request.user,
        billing_period_id=_int_param(request, "billing_period_id")
        or _int_param(request, "period_id"),
        student_id=_int_param(request, "student_id"),
        mess_id=_int_param(request, "mess_id"),
        status=request.query_params.get("status") or None,
    )
    return _paginate(request, bills, BillSerializer)


@extend_schema(
    summary="Bill Detail",
    description="Returns one bill with its calculation lines and adjustments.",
    tags=["billing"],
    responses={200: BillSerializer, 404: OpenApiResponse(description="Not found")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bill_detail_view(request, bill_id: int):
    _require_billing_reader(request.user)
    bill = billing_selectors.get_bill_scoped(request.user, bill_id)
    if bill is None:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Bill not found.")
    return Response(BillSerializer(bill).data)


@extend_schema(
    methods=["POST"],
    summary="Append Bill Adjustment",
    description=(
        "Super Admin appends a positive FEE or FINE with a mandatory reason. "
        "Nothing can reduce a bill; locked periods are rejected [C01, SRS §20]."
    ),
    tags=["billing"],
    request=BillAdjustmentCreateSerializer,
    responses={
        200: BillSerializer,
        400: OpenApiResponse(description="Validation error"),
        409: OpenApiResponse(description="Billing period locked"),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def bill_adjustment_view(request, bill_id: int):
    serializer = BillAdjustmentCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    bill = billing_services.add_bill_adjustment(
        bill_id=bill_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
        **serializer.validated_data,
    )
    return Response(BillSerializer(bill).data)


# ---------------------------------------------------------------------------
# Prepaid balances
# ---------------------------------------------------------------------------


@extend_schema(
    summary="List Prepaid Balances",
    description=(
        "Students read their own balance and ledger; the Super Admin reads every "
        "account. Negative balances are normal [DBDD-AC-25]."
    ),
    tags=["billing"],
    responses={200: BalanceSerializer(many=True), 403: OpenApiResponse(description="Permission denied")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def balance_collection_view(request):
    role = _require_billing_reader(request.user)
    if role not in ("SUPER_ADMIN", "STUDENT"):
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Balances are limited to the student themselves and the Super Admin.",
        )
    accounts = billing_selectors.get_balances_scoped(
        request.user,
        student_id=_int_param(request, "student_id"),
        semester_id=_int_param(request, "semester_id"),
    )
    return _paginate(request, accounts, BalanceSerializer)


@extend_schema(
    summary="Add Authorized Credit",
    description="Super Admin posts a CREDIT entry with a mandatory reference and reason.",
    tags=["billing"],
    request=CreditSerializer,
    responses={200: BalanceSerializer, 404: OpenApiResponse(description="Account not found")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def balance_credit_view(request, student_id: int):
    serializer = CreditSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    account = billing_services.add_balance_credit(
        student_id=student_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
        **serializer.validated_data,
    )
    return Response(BalanceSerializer(account).data)


@extend_schema(
    methods=["GET"],
    summary="List Opening Balances",
    description="Super Admin lists every student balance account.",
    tags=["billing"],
    responses={200: BalanceSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    summary="Set Opening Balance",
    description=(
        "Super Admin creates one student's prepaid account with its single OPENING "
        "entry, using the college fee system's figure [SRS §18]."
    ),
    tags=["billing"],
    request=OpeningBalanceSerializer,
    responses={201: BalanceSerializer, 409: OpenApiResponse(description="Account already exists")},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def opening_balance_collection_view(request):
    if request.method == "POST":
        serializer = OpeningBalanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = billing_services.set_opening_balance(
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
            **serializer.validated_data,
        )
        return Response(BalanceSerializer(account).data, status=status.HTTP_201_CREATED)

    accounts = billing_selectors.get_balances_scoped(
        request.user,
        student_id=_int_param(request, "student_id"),
        semester_id=_int_param(request, "semester_id"),
    )
    return _paginate(request, accounts, BalanceSerializer)


@extend_schema(
    summary="Import Opening Balances",
    description=(
        "Atomically imports a UTF-8 CSV with roll_number and amount columns, using "
        "the Phase 4 staging pattern: no row is written unless every row is valid."
    ),
    tags=["billing"],
    request=OpeningBalanceImportSerializer,
    responses={
        200: OpenApiResponse(description="Import summary"),
        400: OpenApiResponse(description="Validation errors; nothing was imported"),
    },
)
@api_view(["POST"])
@parser_classes([MultiPartParser, JSONParser])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def opening_balance_import_view(request):
    serializer = OpeningBalanceImportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    upload = serializer.validated_data["file"]
    result = billing_services.import_opening_balances(
        semester_id=serializer.validated_data["semester_id"],
        file_content=upload.read(),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    if result["errors"]:
        return Response(
            {
                "code": "IMPORT_VALIDATION_FAILED",
                "message": "No rows were imported; fix the reported rows and retry.",
                "errors": result["errors"],
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(result, status=status.HTTP_200_OK)
