"""
Billing selectors implementing role scoping and calculation pre-flight checks
[SPEC DBDD §8, ImplementationGuide Phase 10].

Read scoping:
- Student: own bills only once LOCKED, own balance and ledger always.
- Hostel Clerk: bills of students in the Clerk's assigned hostel.
- Super Admin: everything.
- Mess Manager: no billing reads; billing reaches managers through reports.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import (
    Case,
    Count,
    IntegerField,
    Prefetch,
    Q,
    QuerySet,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from apps.attendance.models import AttendanceCorrection, ExtraTransaction, MealConsumption
from apps.billing.models import (
    BalanceAccount,
    BalanceLedgerEntry,
    Bill,
    BillAdjustment,
    BillingPeriod,
    BillingPolicy,
    Semester,
)
from apps.core.clock import IST_ZONE
from apps.hostel.models import Student, StudentMessAssignment
from apps.identity.models import User
from apps.identity.selectors import get_user_role
from apps.mess.models import MealOccurrence, Mess
from apps.mess.services import get_clerk_scope, get_meal_rate

# Statuses that represent an accepted central extra transaction.
ACCEPTED_EXTRA_STATUSES = ("SYNCHRONIZED", "IDEMPOTENT_SUCCESS")
REJECTED_EXTRA_STATUSES = ("REJECTED", "CONFLICT", "DUPLICATE")

# Assignment statuses that make a student billable for a period. ENDED is included
# because a student who transferred mid-period still owes that mess for the days
# the assignment covered (DEC-24).
BILLABLE_ASSIGNMENT_STATUSES = ("ACTIVE", "ENDED")


def _ist_period_bounds(period: BillingPeriod) -> tuple[datetime, datetime]:
    """Return the half-open UTC instants covering the period's IST calendar days."""
    start = datetime.combine(period.period_start, time.min, tzinfo=IST_ZONE)
    end = datetime.combine(period.period_end + timedelta(days=1), time.min, tzinfo=IST_ZONE)
    return start, end


def list_semesters() -> QuerySet[Semester]:
    """All semesters, newest first."""
    return Semester.objects.all().order_by("-start_date", "-semester_id")


def list_policies() -> QuerySet[BillingPolicy]:
    """All effective-dated billing policies with their mess."""
    return (
        BillingPolicy.objects.select_related("mess", "created_by")
        .order_by("mess__code", "-effective_from")
    )


def list_billing_periods() -> QuerySet[BillingPeriod]:
    """All billing periods, newest first."""
    return BillingPeriod.objects.select_related("locked_by", "unlocked_by").order_by(
        "-year", "-month"
    )


def period_summaries(periods: list[BillingPeriod]) -> dict[int, dict[str, Any]]:
    """Batch the per-period tiles so a list page costs a constant query count.

    Equivalent to calling :func:`bill_totals` and
    :func:`count_stale_transactions` for each period, but groups the work into
    one bill aggregate plus one bucketed query per transaction source.
    """
    period_list = list(periods)
    if not period_list:
        return {}

    period_ids = [period.billing_period_id for period in period_list]

    bills_by_period = {
        row["billing_period_id"]: row
        for row in Bill.objects.filter(billing_period_id__in=period_ids)
        .values("billing_period_id")
        .annotate(
            bill_count=Count("bill_id"),
            student_count=Count("student_id", distinct=True),
            total_billed=Sum("final_amount"),
            total_extras=Sum("extra_charges_amount"),
            total_adjustments=Sum("adjustment_amount"),
        )
    }

    stale: dict[int, int] = {period_id: 0 for period_id in period_ids}

    def add_bucket_counts(queryset, conditions):
        whens = [
            When(condition, then=Value(period_id))
            for period_id, condition in conditions
        ]
        if not whens:
            return
        combined = Q(pk__in=[])
        for _period_id, condition in conditions:
            combined |= condition
        labeled = queryset.filter(combined).annotate(
            _period_id=Case(*whens, output_field=IntegerField())
        )
        for row in (
            labeled.values("_period_id").annotate(count=Count("*")).iterator()
        ):
            stale[row["_period_id"]] += row["count"]

    extra_conditions = []
    meal_conditions = []
    correction_conditions = []
    for period in period_list:
        if not period.generated_at:
            continue
        generated_at = period.generated_at
        start, end = _ist_period_bounds(period)
        extra_conditions.append(
            (
                period.billing_period_id,
                Q(transaction_timestamp__gte=start, transaction_timestamp__lt=end)
                & (
                    Q(accepted_at__gt=generated_at)
                    | Q(accepted_at__isnull=True, created_at__gt=generated_at)
                ),
            )
        )
        meal_conditions.append(
            (
                period.billing_period_id,
                Q(
                    meal_date__gte=period.period_start,
                    meal_date__lte=period.period_end,
                    accepted_at__gt=generated_at,
                ),
            )
        )
        correction_conditions.append(
            (
                period.billing_period_id,
                Q(
                    status="APPLIED",
                    meal_date__gte=period.period_start,
                    meal_date__lte=period.period_end,
                    applied_at__gt=generated_at,
                ),
            )
        )

    add_bucket_counts(
        ExtraTransaction.objects.exclude(sync_status__in=REJECTED_EXTRA_STATUSES),
        extra_conditions,
    )
    add_bucket_counts(MealConsumption.objects.all(), meal_conditions)
    add_bucket_counts(AttendanceCorrection.objects.all(), correction_conditions)

    summaries: dict[int, dict[str, Any]] = {}
    for period in period_list:
        period_id = period.billing_period_id
        totals = bills_by_period.get(period_id, {})
        summaries[period_id] = {
            "bill_count": totals.get("bill_count", 0),
            "stale_transaction_count": stale[period_id],
            "totals": {
                "student_count": totals.get("student_count", 0),
                "total_billed": totals.get("total_billed") or Decimal("0.0000"),
                "total_extras": totals.get("total_extras") or Decimal("0.0000"),
                "total_adjustments": totals.get("total_adjustments")
                or Decimal("0.0000"),
                "bill_count": totals.get("bill_count", 0),
            },
        }
    return summaries


def get_billing_period(billing_period_id: int) -> BillingPeriod | None:
    return BillingPeriod.objects.filter(billing_period_id=billing_period_id).first()


def _student_for_user(user: User) -> Student | None:
    return Student.objects.filter(user=user).first()


def get_bills_scoped(
    user: User,
    *,
    billing_period_id: int | None = None,
    student_id: int | None = None,
    mess_id: int | None = None,
    status: str | None = None,
) -> QuerySet[Bill]:
    """
    Returns bills the caller may read, applying period/student/mess/status filters.
    Students see only their own bills after the period is LOCKED.
    """
    role = get_user_role(user)
    qs = Bill.objects.select_related(
        "student",
        "student__user",
        "mess",
        "billing_period",
        "semester",
    ).prefetch_related(
        "lines",
        Prefetch(
            "adjustments",
            queryset=BillAdjustment.objects.select_related("created_by"),
        ),
    )

    if role == "SUPER_ADMIN" or getattr(user, "is_superuser", False):
        pass
    elif role == "HOSTEL_CLERK":
        hostel = get_clerk_scope(user)
        if not hostel:
            return Bill.objects.none()
        qs = qs.filter(
            student__hostel=hostel,
            billing_period__status__in=["BILL_GENERATED", "REVIEWED", "LOCKED"],
        )
    elif role == "STUDENT":
        student = _student_for_user(user)
        if not student:
            return Bill.objects.none()
        qs = qs.filter(
            student=student,
            status="LOCKED",
            billing_period__status="LOCKED",
        )
    else:
        return Bill.objects.none()

    if billing_period_id is not None:
        qs = qs.filter(billing_period_id=billing_period_id)
    if student_id is not None:
        qs = qs.filter(student_id=student_id)
    if mess_id is not None:
        qs = qs.filter(mess_id=mess_id)
    if status:
        qs = qs.filter(status=status)

    return qs.order_by("-billing_period__year", "-billing_period__month", "student__roll_number")


def get_bill_scoped(user: User, bill_id: int) -> Bill | None:
    return get_bills_scoped(user).filter(bill_id=bill_id).first()


def get_period_bills(period: BillingPeriod) -> QuerySet[Bill]:
    return Bill.objects.filter(billing_period=period).select_related(
        "student", "student__user", "mess", "billing_period", "semester"
    ).prefetch_related(
        "lines",
        Prefetch(
            "adjustments",
            queryset=BillAdjustment.objects.select_related("created_by"),
        ),
    )


def get_balances_scoped(
    user: User,
    *,
    student_id: int | None = None,
    semester_id: int | None = None,
) -> QuerySet[BalanceAccount]:
    """Student reads own balance/ledger; Super Admin reads every account."""
    role = get_user_role(user)
    qs = BalanceAccount.objects.select_related(
        "student", "student__user", "semester"
    ).prefetch_related(
        Prefetch(
            "ledger_entries",
            queryset=BalanceLedgerEntry.objects.select_related("created_by").order_by(
                "ledger_entry_id"
            ),
        )
    )

    if role == "SUPER_ADMIN" or getattr(user, "is_superuser", False):
        pass
    elif role == "STUDENT":
        student = _student_for_user(user)
        if not student:
            return BalanceAccount.objects.none()
        qs = qs.filter(student=student)
    else:
        return BalanceAccount.objects.none()

    if student_id is not None:
        qs = qs.filter(student_id=student_id)
    if semester_id is not None:
        qs = qs.filter(semester_id=semester_id)

    return qs.order_by("student__roll_number", "-semester__start_date")


def get_balance_account(student_id: int, semester_id: int) -> BalanceAccount | None:
    return BalanceAccount.objects.filter(
        student_id=student_id, semester_id=semester_id
    ).first()


def get_semester_for_date(target_date: date) -> Semester | None:
    """Semester containing the given IST date (bills use the period's last day)."""
    return (
        Semester.objects.filter(start_date__lte=target_date, end_date__gte=target_date)
        .order_by("-start_date", "-semester_id")
        .first()
    )


def get_policy_for_date(mess_id: int, target_date: date) -> BillingPolicy | None:
    """Effective billing policy on a date; effective_to is exclusive."""
    return (
        BillingPolicy.objects.filter(mess_id=mess_id, effective_from__lte=target_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=target_date))
        .order_by("-effective_from", "-billing_policy_id")
        .first()
    )


def get_rate_for_date(mess_id: int, target_date: date) -> Decimal | None:
    return get_meal_rate(mess_id, target_date)


def get_scope_pairs(period: BillingPeriod) -> list[tuple[int, int]]:
    """
    Distinct (student_id, mess_id) pairs with an ACTIVE or ENDED assignment
    overlapping the period. Assignment effective_to is exclusive [Phase 5 rule].
    """
    return list(
        StudentMessAssignment.objects.filter(
            status__in=BILLABLE_ASSIGNMENT_STATUSES,
            effective_from__lte=period.period_end,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=period.period_start))
        .values_list("student_id", "mess_id")
        .distinct()
        .order_by("student_id", "mess_id")
    )


def get_period_assignments(student_id: int, mess_id: int, period: BillingPeriod):
    """Assignments to one mess that overlap the period, for proration (DEC-24)."""
    return list(
        StudentMessAssignment.objects.filter(
            student_id=student_id,
            mess_id=mess_id,
            status__in=BILLABLE_ASSIGNMENT_STATUSES,
            effective_from__lte=period.period_end,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=period.period_start))
        .order_by("effective_from", "assignment_id")
        .values("effective_from", "effective_to")
    )


def get_qualifying_occurrences(mess_id: int, period: BillingPeriod):
    """Scheduled Breakfast, Lunch and Dinner occurrences in the period."""
    return (
        MealOccurrence.objects.filter(
            mess_id=mess_id,
            meal_date__gte=period.period_start,
            meal_date__lte=period.period_end,
            status="SCHEDULED",
            meal_type__code__in=["BREAKFAST", "LUNCH", "DINNER"],
        )
        .select_related("meal_type")
        .order_by("meal_date", "meal_type__sequence_no", "meal_occurrence_id")
    )


def get_accepted_extra_transactions(
    student_id: int, mess_id: int, period: BillingPeriod
):
    """Accepted extra transactions whose transaction instant falls on an IST day in the period."""
    start, end = _ist_period_bounds(period)
    return (
        ExtraTransaction.objects.filter(
            student_id=student_id,
            mess_id=mess_id,
            transaction_timestamp__gte=start,
            transaction_timestamp__lt=end,
        )
        .filter(Q(accepted_at__isnull=False) | Q(sync_status__in=ACCEPTED_EXTRA_STATUSES))
        .exclude(sync_status__in=REJECTED_EXTRA_STATUSES)
        .select_related("extra_item")
        .order_by("transaction_timestamp", "extra_transaction_id")
    )


def get_snack_consumptions(student_id: int, mess_id: int, period: BillingPeriod):
    """
    Effective Evening Snacks consumptions in the period. Snacks are extras and
    never count toward MealCount [C01 owner clarification].
    """
    from apps.attendance.selectors import get_effective_meal_consumptions

    base = MealConsumption.objects.filter(
        meal_type__code__in=["EVENING_SNACKS", "SNACKS"]
    )
    return get_effective_meal_consumptions(
        base_queryset=base,
        student=student_id,
        mess=mess_id,
        start_date=period.period_start,
        end_date=period.period_end,
    )


def count_stale_transactions(period: BillingPeriod) -> int:
    """
    Counts accepted extras, meals and applied corrections dated in the period but
    recorded after generation. The period must be regenerated before it can lock.
    """
    if not period.generated_at:
        return 0

    generated_at = period.generated_at
    start, end = _ist_period_bounds(period)

    extras = (
        ExtraTransaction.objects.filter(
            transaction_timestamp__gte=start,
            transaction_timestamp__lt=end,
        )
        .filter(
            Q(accepted_at__gt=generated_at)
            | Q(accepted_at__isnull=True, created_at__gt=generated_at)
        )
        .exclude(sync_status__in=REJECTED_EXTRA_STATUSES)
        .count()
    )
    meals = MealConsumption.objects.filter(
        accepted_at__gt=generated_at,
        meal_date__gte=period.period_start,
        meal_date__lte=period.period_end,
    ).count()
    corrections = AttendanceCorrection.objects.filter(
        status="APPLIED",
        applied_at__gt=generated_at,
        meal_date__gte=period.period_start,
        meal_date__lte=period.period_end,
    ).count()
    return extras + meals + corrections


def generation_preflight(period: BillingPeriod) -> dict[str, Any]:
    """
    Lists messes in scope missing a policy or rate on the period's first day,
    and whether a semester covers the period's last day.
    """
    pairs = get_scope_pairs(period)
    mess_ids = sorted({mess_id for _student_id, mess_id in pairs})
    messes = {mess.mess_id: mess for mess in Mess.objects.filter(mess_id__in=mess_ids)}

    missing_policies: list[str] = []
    missing_rates: list[str] = []
    for mess_id in mess_ids:
        mess = messes.get(mess_id)
        code = mess.code if mess else str(mess_id)
        if get_policy_for_date(mess_id, period.period_start) is None:
            missing_policies.append(code)
        if get_rate_for_date(mess_id, period.period_start) is None:
            missing_rates.append(code)

    semester = get_semester_for_date(period.period_end)
    return {
        "student_mess_pairs": len(pairs),
        "mess_ids": mess_ids,
        "missing_policies": missing_policies,
        "missing_rates": missing_rates,
        "semester": semester,
        "missing_semester": semester is None,
    }


def bill_totals(period: BillingPeriod) -> dict[str, Any]:
    """Aggregate figures for period summary tiles."""
    from apps.billing.models import Bill

    aggregate = Bill.objects.filter(billing_period=period).aggregate(
        total_billed=Sum("final_amount"),
        total_extras=Sum("extra_charges_amount"),
        total_adjustments=Sum("adjustment_amount"),
    )
    # Count distinct students without a second query.
    student_count = (
        Bill.objects.filter(billing_period=period)
        .values("student_id")
        .distinct()
        .count()
    )
    return {
        "student_count": student_count,
        "total_billed": aggregate["total_billed"] or Decimal("0.0000"),
        "total_extras": aggregate["total_extras"] or Decimal("0.0000"),
        "total_adjustments": aggregate["total_adjustments"] or Decimal("0.0000"),
        "bill_count": Bill.objects.filter(billing_period=period).count(),
    }
