"""
Billing and prepaid balance services implementing SPEC DBDD §8, owner change C01,
DEC-04, DEC-24 and ImplementationGuide Phase 10.

Financial rules:
- Final = MAX(billed minimum, MealCount) x CommonDietRate + Extras + Fees/Fines.
- Billed minimum is the policy count less paused qualifying slots (DEC-04b),
  prorated by the student's assignment share of the mess's qualifying slots
  (DEC-24), never below zero. The MAX is applied last.
- Fees and fines are positive additions only; nothing reduces a bill (C01).
- Bills and adjustments are updated, never deleted. A LOCKED period is immutable
  at the database trigger level; the unlock service reopens it first.
- Every balance account is backed by an append-only signed ledger and its cached
  balance is updated under a row lock in the same transaction as each entry.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from typing import Any

import structlog
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q, Sum

from apps.attendance.models import ExtraTransaction, MealConsumption
from apps.attendance.selectors import get_effective_meal_consumptions
from apps.audit.services import record_audit_event
from apps.billing import selectors as billing_selectors
from apps.billing.models import (
    BalanceAccount,
    BalanceLedgerEntry,
    Bill,
    BillAdjustment,
    BillLine,
    BillingPeriod,
    BillingPolicy,
    Semester,
)
from apps.config.services import get_int_setting
from apps.core.clock import IST_ZONE, clock
from apps.core.concurrency import check_optimistic_lock
from apps.core.exceptions import ConflictError, NotFoundError, ValidationError
from apps.hostel.models import Student
from apps.identity.models import User
from apps.pause.models import MessPause
from apps.pause.services import is_slot_paused

logger = structlog.get_logger("apps.billing")

MONEY_PLACES = Decimal("0.0001")
ONE = Decimal("1")

# Fixed CalculationOrder groups for BillLine [DBDD §8.1].
MINIMUM_DIET_ORDER = 1
EXTRA_ORDER_START = 100
ADJUSTMENT_ORDER_START = 100_000

QUALIFYING_MEAL_CODES = ("BREAKFAST", "LUNCH", "DINNER")
SNACK_MEAL_CODES = ("EVENING_SNACKS", "SNACKS")


def _money(value: Any) -> Decimal:
    """Quantize any monetary value to the DBDD 4-decimal representation."""
    return Decimal(value or 0).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _round_half_up(value: Decimal) -> int:
    """Round a fractional count half up, as DEC-24 requires."""
    return int(value.quantize(ONE, rounding=ROUND_HALF_UP))


def _ist_period_bounds(period: BillingPeriod) -> tuple[datetime, datetime]:
    start = datetime.combine(period.period_start, time.min, tzinfo=IST_ZONE)
    end = datetime.combine(period.period_end + timedelta(days=1), time.min, tzinfo=IST_ZONE)
    return start, end


def _covers(assignment: dict[str, Any], on_date: date) -> bool:
    """Half-open assignment interval [effective_from, effective_to)."""
    start = assignment["effective_from"]
    end = assignment["effective_to"]
    return start <= on_date and (end is None or on_date < end)


def _policy_for(mess_id: int, on_date: date) -> BillingPolicy | None:
    return billing_selectors.get_policy_for_date(mess_id, on_date)


def _rate_for(mess_id: int, on_date: date) -> Decimal | None:
    return billing_selectors.get_rate_for_date(mess_id, on_date)


def _semester_for(period: BillingPeriod) -> Semester | None:
    return billing_selectors.get_semester_for_date(period.period_end)


def preflight_generation(period: BillingPeriod) -> dict[str, Any]:
    """Public pre-flight used by the API and the generation service."""
    return billing_selectors.generation_preflight(period)


# ---------------------------------------------------------------------------
# Configuration: semesters and effective-dated policies
# ---------------------------------------------------------------------------


@transaction.atomic
def create_semester(
    *,
    code: str,
    name: str,
    start_date: date,
    end_date: date,
    status: str = "UPCOMING",
    actor: User,
    correlation_id: str = "",
) -> Semester:
    """Creates an institutional semester used to key prepaid balances."""
    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not code or not name:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Semester code and name are required.",
        )
    if end_date < start_date:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Semester end date must be on or after its start date.",
        )
    if status not in dict(Semester.STATUS_CHOICES):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Invalid semester status '{status}'.",
        )
    if Semester.objects.filter(code=code).exists():
        raise ConflictError(
            code="CONFLICT",
            message=f"Semester code '{code}' already exists.",
        )

    semester = Semester.objects.create(
        code=code,
        name=name,
        start_date=start_date,
        end_date=end_date,
        status=status,
    )
    record_audit_event(
        event_type="SEMESTER_CREATED",
        actor_user=actor,
        entity_type="Semester",
        entity_id=semester.semester_id,
        new_values={
            "code": semester.code,
            "name": semester.name,
            "start_date": str(semester.start_date),
            "end_date": str(semester.end_date),
            "status": semester.status,
        },
        correlation_id=correlation_id,
    )
    return semester


@transaction.atomic
def create_billing_policy(
    *,
    mess_id: int,
    minimum_diet_count: int,
    effective_from: date,
    actor: User,
    effective_to: date | None = None,
    correlation_id: str = "",
) -> BillingPolicy:
    """
    Creates a new effective-dated minimum-diet policy.
    A new version closes the previous open row at its own effective_from in the
    same transaction; back-dated versions are refused [Phase 5 rule].
    """
    if minimum_diet_count < 0:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Minimum diet count cannot be negative.",
        )
    if effective_from < clock.today():
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="A billing policy cannot start in the past.",
        )
    if effective_to is not None and effective_to <= effective_from:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Policy effective_to must be after effective_from.",
        )

    from apps.mess.models import Mess

    mess = Mess.objects.filter(mess_id=mess_id).first()
    if not mess:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Mess not found.")

    previous = (
        BillingPolicy.objects.select_for_update()
        .filter(mess=mess, effective_from__lte=effective_from)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=effective_from))
        .order_by("-effective_from", "-billing_policy_id")
        .first()
    )
    if previous and previous.effective_from == effective_from:
        raise ConflictError(
            code="CONFLICT",
            message="A billing policy already starts on that date.",
        )
    if previous and (previous.effective_to is None or previous.effective_to > effective_from):
        previous.effective_to = effective_from
        previous.save(update_fields=["effective_to", "updated_at"])

    latest_version = (
        BillingPolicy.objects.filter(mess=mess).aggregate(
            max_version=Max("policy_version")
        )["max_version"]
        or 0
    )

    policy = BillingPolicy.objects.create(
        mess=mess,
        minimum_diet_count=minimum_diet_count,
        effective_from=effective_from,
        effective_to=effective_to,
        policy_version=latest_version + 1,
        created_by=actor,
    )
    record_audit_event(
        event_type="BILLING_POLICY_CREATED",
        actor_user=actor,
        entity_type="BillingPolicy",
        entity_id=policy.billing_policy_id,
        new_values={
            "mess_id": mess.mess_id,
            "minimum_diet_count": minimum_diet_count,
            "effective_from": str(effective_from),
            "effective_to": str(effective_to) if effective_to else None,
            "policy_version": policy.policy_version,
        },
        correlation_id=correlation_id,
    )
    return policy


# ---------------------------------------------------------------------------
# Period job and lifecycle
# ---------------------------------------------------------------------------


def open_billing_period(target_date: date | None = None) -> tuple[BillingPeriod, bool]:
    """
    Cron job helper: creates the OPEN period for the previous calendar month if
    missing. Runs on the 1st at 00:30 IST under an advisory lock.
    """
    today = target_date or clock.today()
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1

    period_start = date(year, month, 1)
    next_month = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    period_end = next_month - timedelta(days=1)

    period, created = BillingPeriod.objects.get_or_create(
        year=year,
        month=month,
        defaults={
            "period_start": period_start,
            "period_end": period_end,
            "status": "OPEN",
        },
    )
    if created:
        record_audit_event(
            event_type="BILLING_PERIOD_OPENED",
            entity_type="BillingPeriod",
            entity_id=period.billing_period_id,
            new_values={
                "year": year,
                "month": month,
                "period_start": str(period.period_start),
                "period_end": str(period.period_end),
                "status": period.status,
            },
        )
    return period, created


@transaction.atomic
def adjust_period_dates(
    *,
    billing_period_id: int,
    period_start: date,
    period_end: date,
    actor: User,
    version: int | None = None,
    correlation_id: str = "",
) -> BillingPeriod:
    """Super Admin may adjust the exact dates of an OPEN period; audited."""
    period = (
        BillingPeriod.objects.select_for_update()
        .filter(billing_period_id=billing_period_id)
        .first()
    )
    if not period:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND", message="Billing period not found."
        )
    if period.status != "OPEN":
        raise ConflictError(
            code="BILLING_PERIOD_LOCKED",
            message="Only an OPEN billing period may have its dates adjusted.",
        )
    check_optimistic_lock(period, version)
    if period_end < period_start:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Period end date must be on or after its start date.",
        )

    old_values = {
        "period_start": str(period.period_start),
        "period_end": str(period.period_end),
    }
    period.period_start = period_start
    period.period_end = period_end
    period.version = F("version") + 1
    period.save(update_fields=["period_start", "period_end", "version", "updated_at"])
    period.refresh_from_db()

    record_audit_event(
        event_type="BILLING_PERIOD_UPDATED",
        actor_user=actor,
        entity_type="BillingPeriod",
        entity_id=period.billing_period_id,
        old_values=old_values,
        new_values={
            "period_start": str(period.period_start),
            "period_end": str(period.period_end),
        },
        correlation_id=correlation_id,
    )
    return period


# ---------------------------------------------------------------------------
# Bill generation
# ---------------------------------------------------------------------------


def _assignment_slot_stats(
    student: Student, mess_id: int, period: BillingPeriod
) -> tuple[int, int, int]:
    """
    Returns (total qualifying slots in the mess period, slots covered by the
    student's assignment, paused qualifying slots). Uses the shared Phase 9
    is_slot_paused predicate [DEC-04b].
    """
    occurrences = list(billing_selectors.get_qualifying_occurrences(mess_id, period))
    total_slots = len(occurrences)
    if not total_slots:
        return 0, 0, 0

    assignments = billing_selectors.get_period_assignments(
        student.student_id, mess_id, period
    )
    covered_slots = sum(
        1
        for occurrence in occurrences
        if any(_covers(assignment, occurrence.meal_date) for assignment in assignments)
    )

    paused_slots = 0
    has_pause = MessPause.objects.filter(
        student=student,
        mess_id=mess_id,
        status__in=["SCHEDULED", "ACTIVE", "COMPLETED", "CANCELLED"],
        requested_end_date__gte=period.period_start,
        requested_start_date__lte=period.period_end,
    ).exists()
    if has_pause:
        paused_slots = sum(
            1 for occurrence in occurrences if is_slot_paused(student, occurrence)
        )

    return total_slots, covered_slots, paused_slots


def _effective_meal_count(student_id: int, mess_id: int, period: BillingPeriod) -> int:
    base = MealConsumption.objects.filter(meal_type__code__in=QUALIFYING_MEAL_CODES)
    qs = get_effective_meal_consumptions(
        base_queryset=base,
        student=student_id,
        mess=mess_id,
        start_date=period.period_start,
        end_date=period.period_end,
    )
    return qs.count()


def _extras_breakdown(
    student_id: int, mess_id: int, period: BillingPeriod
) -> tuple[list[ExtraTransaction], list[MealConsumption], Decimal]:
    """Accepted extras plus effective snacks, with their total."""
    extra_transactions = list(
        billing_selectors.get_accepted_extra_transactions(student_id, mess_id, period)
    )
    snack_consumptions = list(
        billing_selectors.get_snack_consumptions(student_id, mess_id, period)
    )
    total = sum((tx.total_amount for tx in extra_transactions), Decimal("0"))
    total += sum((meal.price_at_transaction for meal in snack_consumptions), Decimal("0"))
    return extra_transactions, snack_consumptions, _money(total)


def _adjustment_total(bill: Bill | None) -> Decimal:
    if bill is None:
        return _money(0)
    total = BillAdjustment.objects.filter(bill=bill).aggregate(total=Sum("amount"))["total"]
    return _money(total or 0)


def _rebuild_minimum_and_extra_lines(
    *,
    bill: Bill,
    policy: BillingPolicy | None,
    policy_count: int,
    paused_slots: int,
    billed_count: int,
    meal_count: int,
    rate: Decimal,
    meal_component: Decimal,
    extra_transactions: list[ExtraTransaction],
    snack_consumptions: list[MealConsumption],
) -> None:
    """Rebuilds the non-adjustment lines, preserving a fixed CalculationOrder."""
    BillLine.objects.filter(bill=bill).exclude(line_type="ADJUSTMENT").delete()

    billed_source = "minimum" if billed_count >= meal_count else "meals"
    BillLine.objects.create(
        bill=bill,
        line_type="MINIMUM_DIET",
        source_entity_type="BillingPolicy" if policy else "",
        source_entity_id=str(policy.billing_policy_id) if policy else "",
        description=(
            f"Minimum diet: policy={policy_count}, paused={paused_slots}, "
            f"billed minimum={billed_count}, meal count={meal_count}, "
            f"billed={billed_source}"
        ),
        quantity=billed_count,
        unit_rate=_money(rate),
        amount=_money(meal_component),
        calculation_order=MINIMUM_DIET_ORDER,
    )

    order = EXTRA_ORDER_START
    for tx in extra_transactions:
        BillLine.objects.create(
            bill=bill,
            line_type="EXTRA",
            source_entity_type="ExtraTransaction",
            source_entity_id=str(tx.extra_transaction_id),
            description=f"Extra: {tx.extra_item.name} x{tx.quantity}",
            quantity=tx.quantity,
            unit_rate=_money(tx.unit_price_at_transaction),
            amount=_money(tx.total_amount),
            calculation_order=order,
        )
        order += 1

    for snack in snack_consumptions:
        BillLine.objects.create(
            bill=bill,
            line_type="EXTRA",
            source_entity_type="MealConsumption",
            source_entity_id=str(snack.meal_consumption_id),
            description="Evening snacks (extra)",
            quantity=1,
            unit_rate=_money(snack.price_at_transaction),
            amount=_money(snack.price_at_transaction),
            calculation_order=order,
        )
        order += 1


def _rebuild_adjustment_lines(bill: Bill) -> None:
    BillLine.objects.filter(bill=bill, line_type="ADJUSTMENT").delete()
    order = ADJUSTMENT_ORDER_START
    for adjustment in BillAdjustment.objects.filter(bill=bill).select_related("created_by").order_by(
        "created_at", "adjustment_id"
    ):
        BillLine.objects.create(
            bill=bill,
            line_type="ADJUSTMENT",
            source_entity_type="BillAdjustment",
            source_entity_id=str(adjustment.adjustment_id),
            description=(
                f"{adjustment.adjustment_type}: {adjustment.reason} "
                f"(by user {adjustment.created_by_id} at {adjustment.created_at.isoformat()})"
            ),
            quantity=1,
            unit_rate=_money(adjustment.amount),
            amount=_money(adjustment.amount),
            calculation_order=order,
        )
        order += 1


def _save_bill(
    *,
    existing: Bill | None,
    student_id: int,
    mess_id: int,
    period: BillingPeriod,
    semester: Semester,
    meal_component: Decimal,
    extras_total: Decimal,
    adjustments_total: Decimal,
    rate: Decimal,
    billed_count: int,
    meal_count: int,
    now: datetime,
) -> Bill:
    final_amount = _money(meal_component + extras_total + adjustments_total)
    defaults = {
        "semester": semester,
        "meal_component_amount": _money(meal_component),
        "extra_charges_amount": _money(extras_total),
        "adjustment_amount": _money(adjustments_total),
        "final_amount": final_amount,
        "common_diet_rate_snapshot": _money(rate),
        "minimum_diet_count_snapshot": billed_count,
        "actual_meal_count": meal_count,
        "status": "DRAFT",
        "generated_at": now,
        "locked_at": None,
    }

    if existing is not None:
        for field, value in defaults.items():
            setattr(existing, field, value)
        existing.version = F("version") + 1
        existing.save()
        existing.refresh_from_db()
        return existing

    try:
        with transaction.atomic():
            return Bill.objects.create(
                student_id=student_id,
                mess_id=mess_id,
                billing_period=period,
                **defaults,
            )
    except IntegrityError:
        # A concurrent generation created the same (student, mess, period) row.
        existing = (
            Bill.objects.select_for_update()
            .filter(student_id=student_id, mess_id=mess_id, billing_period=period)
            .first()
        )
        if existing is None:
            raise
        for field, value in defaults.items():
            setattr(existing, field, value)
        existing.version = F("version") + 1
        existing.save()
        existing.refresh_from_db()
        return existing


def _generate_bill_for_pair(
    *,
    student: Student,
    mess_id: int,
    period: BillingPeriod,
    policy: BillingPolicy,
    rate: Decimal,
    semester: Semester,
    now: datetime,
) -> Bill:
    total_slots, covered_slots, paused_slots = _assignment_slot_stats(
        student, mess_id, period
    )
    policy_count = policy.minimum_diet_count
    billed_count = max(policy_count - paused_slots, 0)
    if total_slots > 0:
        billed_count = _round_half_up(
            Decimal(billed_count) * Decimal(covered_slots) / Decimal(total_slots)
        )
    billed_count = max(billed_count, 0)

    meal_count = _effective_meal_count(student.student_id, mess_id, period)
    meal_component = _money(Decimal(max(billed_count, meal_count)) * rate)

    extras, snacks, extras_total = _extras_breakdown(student.student_id, mess_id, period)

    existing = (
        Bill.objects.select_for_update()
        .filter(student=student, mess_id=mess_id, billing_period=period)
        .first()
    )
    adjustments_total = _adjustment_total(existing)

    bill = _save_bill(
        existing=existing,
        student_id=student.student_id,
        mess_id=mess_id,
        period=period,
        semester=semester,
        meal_component=meal_component,
        extras_total=extras_total,
        adjustments_total=adjustments_total,
        rate=rate,
        billed_count=billed_count,
        meal_count=meal_count,
        now=now,
    )

    _rebuild_minimum_and_extra_lines(
        bill=bill,
        policy=policy,
        policy_count=policy_count,
        paused_slots=paused_slots,
        billed_count=billed_count,
        meal_count=meal_count,
        rate=rate,
        meal_component=meal_component,
        extra_transactions=extras,
        snack_consumptions=snacks,
    )
    _rebuild_adjustment_lines(bill)
    return bill


def _zero_bill(bill: Bill, period: BillingPeriod, now: datetime) -> None:
    """A student who no longer qualifies keeps the row but with a zero meal charge."""
    adjustments_total = _adjustment_total(bill)
    rate = _money(bill.common_diet_rate_snapshot)
    bill.meal_component_amount = _money(0)
    bill.extra_charges_amount = _money(0)
    bill.adjustment_amount = adjustments_total
    bill.final_amount = _money(adjustments_total)
    bill.minimum_diet_count_snapshot = 0
    bill.actual_meal_count = 0
    bill.status = "DRAFT"
    bill.generated_at = now
    bill.locked_at = None
    bill.version = F("version") + 1
    bill.save()
    bill.refresh_from_db()

    _rebuild_minimum_and_extra_lines(
        bill=bill,
        policy=None,
        policy_count=0,
        paused_slots=0,
        billed_count=0,
        meal_count=0,
        rate=rate,
        meal_component=_money(0),
        extra_transactions=[],
        snack_consumptions=[],
    )
    _rebuild_adjustment_lines(bill)


def generate_bills(
    *,
    billing_period_id: int,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Generates or regenerates every bill for the period. Each student-and-mess
    bill is written in its own transaction so a rerun resumes where a failure
    stopped, and repeat runs are idempotent.
    """
    period = billing_selectors.get_billing_period(billing_period_id)
    if not period:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND", message="Billing period not found."
        )
    if period.status == "LOCKED":
        raise ConflictError(
            code="BILLING_PERIOD_LOCKED",
            message="A locked billing period cannot be regenerated.",
        )

    preflight = preflight_generation(period)
    problems: list[str] = []
    if preflight["missing_policies"]:
        problems.append(
            "missing billing policy for mess(es): "
            + ", ".join(preflight["missing_policies"])
        )
    if preflight["missing_rates"]:
        problems.append(
            "missing meal rate for mess(es): " + ", ".join(preflight["missing_rates"])
        )
    if preflight["missing_semester"]:
        problems.append(
            f"no semester covers the period's last day ({period.period_end})"
        )
    if problems:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Generation refused: " + "; ".join(problems) + ".",
        )

    semester = preflight["semester"]
    pairs = billing_selectors.get_scope_pairs(period)
    now = clock.now()
    failures: list[dict[str, Any]] = []
    generated = 0

    for student_id, mess_id in pairs:
        student = Student.objects.filter(student_id=student_id).first()
        policy = _policy_for(mess_id, period.period_start)
        rate = _rate_for(mess_id, period.period_start)
        if student is None or policy is None or rate is None:
            failures.append(
                {
                    "student_id": student_id,
                    "mess_id": mess_id,
                    "message": "Student, policy or rate disappeared during generation.",
                }
            )
            continue
        try:
            with transaction.atomic():
                _generate_bill_for_pair(
                    student=student,
                    mess_id=mess_id,
                    period=period,
                    policy=policy,
                    rate=rate,
                    semester=semester,
                    now=now,
                )
            generated += 1
        except Exception as exc:  # noqa: BLE001 - resumable run reports the row
            logger.error(
                "bill_generation_row_failed",
                billing_period_id=period.billing_period_id,
                student_id=student_id,
                mess_id=mess_id,
                error=str(exc),
            )
            failures.append(
                {"student_id": student_id, "mess_id": mess_id, "message": str(exc)}
            )

    if failures:
        raise ValidationError(
            code="BILL_GENERATION_INCOMPLETE",
            message=(
                f"Bill generation incomplete: {len(failures)} row(s) failed. "
                "Re-run generation to resume."
            ),
        )

    # Zero any previously generated bill whose pair no longer qualifies.
    zeroed = 0
    pair_set = set(pairs)
    with transaction.atomic():
        locked_period = (
            BillingPeriod.objects.select_for_update()
            .filter(billing_period_id=period.billing_period_id)
            .first()
        )
        if locked_period and locked_period.status == "LOCKED":
            raise ConflictError(
                code="BILLING_PERIOD_LOCKED",
                message="A locked billing period cannot be regenerated.",
            )
        for bill in Bill.objects.select_for_update().filter(billing_period=period):
            if (bill.student_id, bill.mess_id) not in pair_set:
                _zero_bill(bill, period, now)
                zeroed += 1

        period.status = "BILL_GENERATED"
        period.generated_at = now
        period.reviewed_at = None
        period.version = F("version") + 1
        period.save(
            update_fields=[
                "status",
                "generated_at",
                "reviewed_at",
                "version",
                "updated_at",
            ]
        )
        period.refresh_from_db()

        record_audit_event(
            event_type="BILLING_PERIOD_GENERATED",
            actor_user=actor,
            entity_type="BillingPeriod",
            entity_id=period.billing_period_id,
            new_values={
                "status": period.status,
                "period_start": str(period.period_start),
                "period_end": str(period.period_end),
                "generated_bills": generated,
                "zeroed_bills": zeroed,
            },
            correlation_id=correlation_id,
        )

    return {
        "billing_period_id": period.billing_period_id,
        "status": period.status,
        "generated": generated,
        "zeroed": zeroed,
    }


@transaction.atomic
def review_period(
    *, billing_period_id: int, actor: User, correlation_id: str = ""
) -> BillingPeriod:
    """BILL_GENERATED -> REVIEWED. Bills become FINAL."""
    period = (
        BillingPeriod.objects.select_for_update()
        .filter(billing_period_id=billing_period_id)
        .first()
    )
    if not period:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND", message="Billing period not found."
        )
    if period.status != "BILL_GENERATED":
        raise ConflictError(
            code="CONFLICT",
            message=(
                "Only a BILL_GENERATED period can be reviewed "
                f"(current status: {period.status})."
            ),
        )

    now = clock.now()
    for bill in Bill.objects.select_for_update().filter(billing_period=period):
        bill.status = "FINAL"
        bill.version = F("version") + 1
        bill.save(update_fields=["status", "version", "updated_at"])

    period.status = "REVIEWED"
    period.reviewed_at = now
    period.version = F("version") + 1
    period.save(update_fields=["status", "reviewed_at", "version", "updated_at"])
    period.refresh_from_db()

    record_audit_event(
        event_type="BILLING_PERIOD_REVIEWED",
        actor_user=actor,
        entity_type="BillingPeriod",
        entity_id=period.billing_period_id,
        old_values={"status": "BILL_GENERATED"},
        new_values={"status": "REVIEWED", "reviewed_at": now.isoformat()},
        correlation_id=correlation_id,
    )
    return period


# ---------------------------------------------------------------------------
# Balance ledger primitives
# ---------------------------------------------------------------------------


def _ensure_balance_account(
    *, student: Student, semester: Semester, now: datetime
) -> BalanceAccount:
    account = (
        BalanceAccount.objects.select_for_update()
        .filter(student=student, semester=semester)
        .first()
    )
    if account:
        return account
    try:
        with transaction.atomic():
            return BalanceAccount.objects.create(
                student=student,
                semester=semester,
                opening_balance=_money(0),
                current_balance=_money(0),
                last_calculated_at=now,
            )
    except IntegrityError:
        account = (
            BalanceAccount.objects.select_for_update()
            .filter(student=student, semester=semester)
            .first()
        )
        if account is None:
            raise
        return account


def _post_ledger_entry(
    *,
    account: BalanceAccount,
    entry_type: str,
    amount: Decimal,
    reference_type: str,
    reference_id: str,
    effective_date: date,
    description: str,
    actor: User,
    now: datetime,
) -> BalanceLedgerEntry:
    account = BalanceAccount.objects.select_for_update().get(
        balance_account_id=account.balance_account_id
    )
    entry = BalanceLedgerEntry.objects.create(
        balance_account=account,
        entry_type=entry_type,
        amount=_money(amount),
        reference_type=reference_type,
        reference_id=reference_id,
        effective_date=effective_date,
        description=description,
        created_by=actor,
    )
    account.current_balance = _money(account.current_balance + _money(amount))
    account.last_calculated_at = now
    account.version = F("version") + 1
    account.save(
        update_fields=[
            "current_balance",
            "last_calculated_at",
            "version",
            "updated_at",
        ]
    )
    return entry


@transaction.atomic
def set_opening_balance(
    *,
    student_id: int,
    semester_id: int,
    amount: Decimal,
    actor: User,
    reference: str = "",
    description: str = "",
    correlation_id: str = "",
) -> BalanceAccount:
    """Creates a balance account and its single OPENING entry."""
    student = Student.objects.filter(student_id=student_id).first()
    if not student:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Student not found.")
    semester = Semester.objects.filter(semester_id=semester_id).first()
    if not semester:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Semester not found.")

    amount = _money(amount)
    if amount < 0:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Opening balance cannot be negative.",
        )
    if BalanceAccount.objects.filter(student=student, semester=semester).exists():
        raise ConflictError(
            code="CONFLICT",
            message="A balance account already exists for this student and semester.",
        )

    now = clock.now()
    account = BalanceAccount.objects.create(
        student=student,
        semester=semester,
        opening_balance=amount,
        current_balance=amount,
        last_calculated_at=now,
    )
    BalanceLedgerEntry.objects.create(
        balance_account=account,
        entry_type="OPENING",
        amount=amount,
        reference_type="FEE_SYSTEM",
        reference_id=reference or "",
        effective_date=clock.today(),
        description=description or "Opening balance from the college fee system",
        created_by=actor,
    )
    record_audit_event(
        event_type="BALANCE_OPENING_SET",
        actor_user=actor,
        entity_type="BalanceAccount",
        entity_id=account.balance_account_id,
        new_values={
            "student_id": student.student_id,
            "semester_id": semester.semester_id,
            "opening_balance": str(amount),
            "reference": reference,
        },
        correlation_id=correlation_id,
    )
    return account


@transaction.atomic
def add_balance_credit(
    *,
    student_id: int,
    semester_id: int,
    amount: Decimal,
    reference: str,
    reason: str,
    actor: User,
    correlation_id: str = "",
) -> BalanceAccount:
    """Posts an authorized positive CREDIT entry with a reference and reason."""
    amount = _money(amount)
    if amount <= 0:
        raise ValidationError(
            code="VALIDATION_ERROR", message="A credit amount must be greater than zero."
        )
    if not (reference or "").strip():
        raise ValidationError(
            code="VALIDATION_ERROR", message="A credit reference is required."
        )
    if not (reason or "").strip():
        raise ValidationError(
            code="VALIDATION_ERROR", message="A credit reason is required."
        )

    account = (
        BalanceAccount.objects.select_for_update()
        .filter(student_id=student_id, semester_id=semester_id)
        .first()
    )
    if not account:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="Balance account not found. Set an opening balance first.",
        )

    now = clock.now()
    _post_ledger_entry(
        account=account,
        entry_type="CREDIT",
        amount=amount,
        reference_type="CREDIT",
        reference_id=reference.strip(),
        effective_date=clock.today(),
        description=reason.strip(),
        actor=actor,
        now=now,
    )
    account.refresh_from_db()
    record_audit_event(
        event_type="BALANCE_CREDIT_ADDED",
        actor_user=actor,
        entity_type="BalanceAccount",
        entity_id=account.balance_account_id,
        new_values={
            "student_id": student_id,
            "semester_id": semester_id,
            "amount": str(amount),
            "reference": reference.strip(),
            "reason": reason.strip(),
            "current_balance": str(account.current_balance),
        },
        correlation_id=correlation_id,
    )
    return account


def import_opening_balances(
    *,
    semester_id: int,
    file_content: bytes,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Validates and atomically commits a CSV of opening balances.
    Columns: roll_number, amount[, reference, description].
    No rows are written unless every row is valid (Phase 4 staging semantics).
    """
    semester = Semester.objects.filter(semester_id=semester_id).first()
    if not semester:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Semester not found.")

    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = file_content.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "created": 0,
                "errors": [{"row": 0, "message": "File must be UTF-8 encoded CSV."}],
            }

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        return {
            "created": 0,
            "errors": [{"row": 0, "message": "CSV header is missing."}],
        }

    normalized_fields = {(name or "").strip().lower(): name for name in reader.fieldnames}
    if "roll_number" not in normalized_fields or "amount" not in normalized_fields:
        return {
            "created": 0,
            "errors": [
                {
                    "row": 0,
                    "message": "CSV must contain roll_number and amount columns.",
                }
            ],
        }

    max_rows = get_int_setting("import.max_rows", default=2000)
    errors: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    seen_rolls: set[str] = set()

    for index, raw in enumerate(reader, start=2):
        if index - 1 > max_rows:
            errors.append(
                {"row": index, "message": f"File exceeds the {max_rows} row limit."}
            )
            break
        roll = (raw.get(normalized_fields["roll_number"]) or "").strip().upper()
        amount_raw = (raw.get(normalized_fields["amount"]) or "").strip()
        reference = (
            (raw.get(normalized_fields.get("reference", "")) or "").strip()
            if "reference" in normalized_fields
            else ""
        )
        description = (
            (raw.get(normalized_fields.get("description", "")) or "").strip()
            if "description" in normalized_fields
            else ""
        )
        if not roll:
            errors.append({"row": index, "message": "roll_number is required."})
            continue
        if roll in seen_rolls:
            errors.append(
                {"row": index, "message": f"Duplicate roll_number '{roll}' in file."}
            )
            continue
        seen_rolls.add(roll)
        try:
            amount = _money(Decimal(amount_raw))
        except Exception:
            errors.append(
                {"row": index, "message": f"Invalid amount '{amount_raw}'."}
            )
            continue
        if amount < 0:
            errors.append(
                {"row": index, "message": "Opening balance cannot be negative."}
            )
            continue
        student = Student.objects.filter(roll_number__iexact=roll).first()
        if not student:
            errors.append(
                {"row": index, "message": f"Student '{roll}' not found."}
            )
            continue
        if BalanceAccount.objects.filter(student=student, semester=semester).exists():
            errors.append(
                {
                    "row": index,
                    "message": f"Balance account already exists for '{roll}'.",
                }
            )
            continue
        rows.append(
            {
                "student": student,
                "amount": amount,
                "reference": reference,
                "description": description,
            }
        )

    if errors:
        return {"created": 0, "errors": errors}

    now = clock.now()
    with transaction.atomic():
        for row in rows:
            account = BalanceAccount.objects.create(
                student=row["student"],
                semester=semester,
                opening_balance=row["amount"],
                current_balance=row["amount"],
                last_calculated_at=now,
            )
            BalanceLedgerEntry.objects.create(
                balance_account=account,
                entry_type="OPENING",
                amount=row["amount"],
                reference_type="FEE_SYSTEM",
                reference_id=row["reference"] or "",
                effective_date=clock.today(),
                description=(
                    row["description"]
                    or "Opening balance from the college fee system"
                ),
                created_by=actor,
            )
        record_audit_event(
            event_type="BALANCE_OPENING_IMPORTED",
            actor_user=actor,
            entity_type="Semester",
            entity_id=semester.semester_id,
            new_values={"created": len(rows)},
            correlation_id=correlation_id,
        )

    return {"created": len(rows), "errors": []}


# ---------------------------------------------------------------------------
# Lock and unlock
# ---------------------------------------------------------------------------


@transaction.atomic
def lock_period(
    *, billing_period_id: int, actor: User, correlation_id: str = ""
) -> dict[str, Any]:
    """
    REVIEWED -> LOCKED. Posts one BILL_CHARGE per bill, updates cached balances
    under row locks and writes BILL_LOCKED.
    """
    period = (
        BillingPeriod.objects.select_for_update()
        .filter(billing_period_id=billing_period_id)
        .first()
    )
    if not period:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND", message="Billing period not found."
        )
    if period.status == "LOCKED":
        raise ConflictError(
            code="BILLING_PERIOD_LOCKED",
            message="The billing period is already locked.",
        )
    if period.status != "REVIEWED":
        raise ConflictError(
            code="CONFLICT",
            message=(
                "Only a REVIEWED period can be locked "
                f"(current status: {period.status})."
            ),
        )

    stale_count = billing_selectors.count_stale_transactions(period)
    if stale_count:
        raise ConflictError(
            code="BILLING_PERIOD_STALE",
            message=(
                f"{stale_count} transaction(s) were recorded after generation. "
                "Regenerate the period before locking."
            ),
        )

    semester = _semester_for(period)
    if semester is None:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="No semester covers the period's last day; ledger entries cannot be posted.",
        )

    now = clock.now()
    bills = list(
        Bill.objects.select_for_update(of=("self",))
        .filter(billing_period=period)
        .select_related("student", "semester")
        .order_by("bill_id")
    )
    total_billed = Decimal("0")
    charged = 0
    for bill in bills:
        if bill.status == "LOCKED":
            continue
        bill_semester = bill.semester or semester
        account = _ensure_balance_account(
            student=bill.student, semester=bill_semester, now=now
        )
        _post_ledger_entry(
            account=account,
            entry_type="BILL_CHARGE",
            amount=-_money(bill.final_amount),
            reference_type="BILL",
            reference_id=str(bill.bill_id),
            effective_date=period.period_end,
            description=(
                f"Bill charge for {period.year}-{period.month:02d} "
                f"(student {bill.student_id}, mess {bill.mess_id})"
            ),
            actor=actor,
            now=now,
        )
        bill.status = "LOCKED"
        bill.locked_at = now
        bill.version = F("version") + 1
        bill.save(update_fields=["status", "locked_at", "version", "updated_at"])
        total_billed += bill.final_amount
        charged += 1

    # The period flips to LOCKED only after bills and ledger entries are written;
    # the Phase 2 trigger then makes the whole snapshot immutable.
    period.status = "LOCKED"
    period.locked_at = now
    period.locked_by = actor
    period.version = F("version") + 1
    period.save(
        update_fields=["status", "locked_at", "locked_by", "version", "updated_at"]
    )
    period.refresh_from_db()

    record_audit_event(
        event_type="BILL_LOCKED",
        actor_user=actor,
        entity_type="BillingPeriod",
        entity_id=period.billing_period_id,
        old_values={"status": "REVIEWED"},
        new_values={
            "status": "LOCKED",
            "locked_at": now.isoformat(),
            "locked_by": actor.user_id if actor else None,
            "bill_count": charged,
            "total_billed": str(_money(total_billed)),
        },
        reason="Billing period locked",
        correlation_id=correlation_id,
    )
    return {
        "billing_period_id": period.billing_period_id,
        "status": period.status,
        "bill_count": charged,
        "total_billed": str(_money(total_billed)),
    }


@transaction.atomic
def unlock_period(
    *,
    billing_period_id: int,
    reason: str,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    LOCKED -> REVIEWED. Reverses each BILL_CHARGE, reopens bills, stores the
    actor/reason/timestamp and writes BILL_UNLOCKED.
    """
    if not (reason or "").strip():
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="An unlock reason is required.",
        )

    period = (
        BillingPeriod.objects.select_for_update()
        .filter(billing_period_id=billing_period_id)
        .first()
    )
    if not period:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND", message="Billing period not found."
        )
    if period.status != "LOCKED":
        raise ConflictError(
            code="CONFLICT",
            message=(
                "Only a LOCKED period can be unlocked "
                f"(current status: {period.status})."
            ),
        )

    now = clock.now()
    previous_state = period.status

    # Flip the period first: the database guard rejects any bill write while the
    # period is still LOCKED.
    period.status = "REVIEWED"
    period.unlocked_at = now
    period.unlocked_by = actor
    period.unlock_reason = reason.strip()
    period.version = F("version") + 1
    period.save(
        update_fields=[
            "status",
            "unlocked_at",
            "unlocked_by",
            "unlock_reason",
            "version",
            "updated_at",
        ]
    )

    bills = list(
        Bill.objects.select_for_update(of=("self",))
        .filter(billing_period=period)
        .select_related("student", "semester")
        .order_by("bill_id")
    )
    total_reversed = Decimal("0")
    reversed_count = 0
    for bill in bills:
        if bill.status != "LOCKED":
            continue
        semester = bill.semester or _semester_for(period)
        if semester is None:
            raise ValidationError(
                code="VALIDATION_ERROR",
                message="No semester covers the bill; the reversal cannot be posted.",
            )
        account = _ensure_balance_account(
            student=bill.student, semester=semester, now=now
        )
        _post_ledger_entry(
            account=account,
            entry_type="BILL_REVERSAL",
            amount=_money(bill.final_amount),
            reference_type="BILL",
            reference_id=str(bill.bill_id),
            effective_date=clock.today(),
            description=(
                f"Reversal of bill {bill.bill_id} after unlocking "
                f"{period.year}-{period.month:02d}"
            ),
            actor=actor,
            now=now,
        )
        bill.status = "DRAFT"
        bill.locked_at = None
        bill.version = F("version") + 1
        bill.save(update_fields=["status", "locked_at", "version", "updated_at"])
        total_reversed += bill.final_amount
        reversed_count += 1

    period.refresh_from_db()
    record_audit_event(
        event_type="BILL_UNLOCKED",
        actor_user=actor,
        entity_type="BillingPeriod",
        entity_id=period.billing_period_id,
        old_values={"status": previous_state, "locked_at": period.locked_at.isoformat() if period.locked_at else None},
        new_values={
            "status": period.status,
            "unlocked_at": now.isoformat(),
            "unlocked_by": actor.user_id if actor else None,
            "reason": reason.strip(),
            "reversed_bill_count": reversed_count,
            "total_reversed": str(_money(total_reversed)),
        },
        reason=reason.strip(),
        correlation_id=correlation_id,
    )
    return {
        "billing_period_id": period.billing_period_id,
        "status": period.status,
        "reversed_bill_count": reversed_count,
        "total_reversed": str(_money(total_reversed)),
    }


# ---------------------------------------------------------------------------
# Adjustments
# ---------------------------------------------------------------------------


@transaction.atomic
def add_bill_adjustment(
    *,
    bill_id: int,
    amount: Decimal,
    adjustment_type: str,
    reason: str,
    actor: User,
    correlation_id: str = "",
) -> Bill:
    """
    Appends a positive FEE or FINE to a bill and recalculates its totals.
    Rejected once the bill or its period is LOCKED (C01, DBDD-AC-22).
    """
    bill = (
        Bill.objects.select_for_update()
        .select_related("billing_period")
        .filter(bill_id=bill_id)
        .first()
    )
    if not bill:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Bill not found.")
    period = (
        BillingPeriod.objects.select_for_update()
        .filter(billing_period_id=bill.billing_period_id)
        .first()
    )
    if period is None:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND", message="Billing period not found."
        )
    if period.status == "LOCKED" or bill.status == "LOCKED":
        raise ConflictError(
            code="BILLING_PERIOD_LOCKED",
            message="The billing period is locked and cannot be modified.",
        )

    amount = _money(amount)
    if amount <= 0:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="A fee or fine amount must be greater than zero.",
        )
    if adjustment_type not in {"FEE", "FINE"}:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Adjustment type must be FEE or FINE.",
        )
    if not (reason or "").strip():
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="A reason is required for a fee or fine.",
        )

    old_final = bill.final_amount
    adjustment = BillAdjustment.objects.create(
        bill=bill,
        amount=amount,
        adjustment_type=adjustment_type,
        reason=reason.strip(),
        created_by=actor,
    )
    adjustments_total = _adjustment_total(bill)
    bill.adjustment_amount = adjustments_total
    bill.final_amount = _money(
        bill.meal_component_amount + bill.extra_charges_amount + adjustments_total
    )
    bill.version = F("version") + 1
    bill.save(
        update_fields=[
            "adjustment_amount",
            "final_amount",
            "version",
            "updated_at",
        ]
    )
    bill.refresh_from_db()
    _rebuild_adjustment_lines(bill)

    record_audit_event(
        event_type="BILL_ADJUSTED",
        actor_user=actor,
        entity_type="Bill",
        entity_id=bill.bill_id,
        old_values={"final_amount": str(old_final)},
        new_values={
            "final_amount": str(bill.final_amount),
            "adjustment_id": adjustment.adjustment_id,
            "adjustment_type": adjustment.adjustment_type,
            "amount": str(adjustment.amount),
            "reason": adjustment.reason,
            "adjustment_total": str(adjustments_total),
        },
        reason=adjustment.reason,
        correlation_id=correlation_id,
    )
    return bill


# ---------------------------------------------------------------------------
# Daily balance verification
# ---------------------------------------------------------------------------


def verify_balances() -> dict[str, Any]:
    """
    Recomputes every account from its append-only ledger and reports drift.
    The cached balance is never silently "fixed"; a non-empty drift list is an
    alert for an operator.
    """
    accounts = (
        BalanceAccount.objects.annotate(ledger_sum=Sum("ledger_entries__amount"))
        .order_by("balance_account_id")
    )
    checked = 0
    drifts: list[dict[str, Any]] = []
    now = clock.now()
    for account in accounts.iterator():
        checked += 1
        ledger_sum = _money(account.ledger_sum or 0)
        cached = _money(account.current_balance)
        if ledger_sum != cached:
            drifts.append(
                {
                    "balance_account_id": account.balance_account_id,
                    "student_id": account.student_id,
                    "semester_id": account.semester_id,
                    "ledger_sum": str(ledger_sum),
                    "cached_balance": str(cached),
                    "difference": str(_money(ledger_sum - cached)),
                }
            )
            logger.error(
                "balance_drift_detected",
                balance_account_id=account.balance_account_id,
                student_id=account.student_id,
                semester_id=account.semester_id,
                ledger_sum=str(ledger_sum),
                cached_balance=str(cached),
            )
        else:
            BalanceAccount.objects.filter(
                balance_account_id=account.balance_account_id
            ).update(last_calculated_at=now)

    return {"checked": checked, "drifts": drifts}
