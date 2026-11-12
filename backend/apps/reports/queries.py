"""
Query implementations for the nine Phase 12 reports [ImplementationGuide].

Each function returns either a queryset (paginated/streamed by the service) or
a small materialised list (comparison reports).  Every query reads from the
authoritative transactional tables; there is no reporting database [SPEC DBDD
§20].
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate

from apps.attendance.models import ExtraTransaction
from apps.attendance.selectors import get_effective_meal_consumptions
from apps.billing.models import BalanceAccount, BalanceLedgerEntry, Bill
from apps.core.clock import IST_ZONE
from apps.feedback.models import Feedback
from apps.hostel.models import Hostel, StudentMessAssignment
from apps.mess.models import Mess
from apps.pause.models import MessPause, MessPauseMealSlot

from apps.reports.scope import (
    REPORTABLE_ASSIGNMENT_STATUSES,
    ROLE_CLERK,
    ROLE_MANAGER,
    ReportContext,
    annotate_feedback_month,
    assignment_hostel_for_period_subquery,
    assignment_hostel_on_date_subquery,
    assignment_on_date_exists,
    assignment_overlap_exists,
    assignment_overlaps_period_exists,
    assignment_overlaps_range_q,
    coalesce_hostel_id,
    coalesce_hostel_name,
    feedback_assignment_exists,
    feedback_hostel_subquery,
)

ACCEPTED_EXTRA_STATUSES = ("SYNCHRONIZED", "IDEMPOTENT_SUCCESS")
MONEY_FIELD = DecimalField(max_digits=19, decimal_places=4)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _apply_mess_scope(queryset, ctx: ReportContext, mess_lookup: str = "mess_id"):
    """Applies the Manager's own-mess scope and any optional mess filter."""
    if ctx.role == ROLE_MANAGER:
        mess_id = ctx.scope_mess_id
        if mess_id is None:
            return queryset.none()
        return queryset.filter(**{mess_lookup: mess_id})
    if ctx.mess_id is not None:
        return queryset.filter(**{mess_lookup: ctx.mess_id})
    return queryset


def _apply_student_filter(queryset, ctx: ReportContext):
    if ctx.student_id is not None:
        return queryset.filter(student_id=ctx.student_id)
    return queryset


def _month_index(value: date) -> int:
    return value.year * 12 + value.month


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def _effective_meals(ctx: ReportContext):
    return get_effective_meal_consumptions(
        start_date=ctx.date_from, end_date=ctx.date_to
    )


# ---------------------------------------------------------------------------
# 1. Student billing
# ---------------------------------------------------------------------------


def billing_queryset(ctx: ReportContext):
    qs = (
        Bill.objects.select_related(
            "student__user", "student__hostel", "mess", "billing_period"
        )
        .filter(
            billing_period__period_start__lte=ctx.date_to,
            billing_period__period_end__gte=ctx.date_from,
        )
    )

    qs = _apply_mess_scope(qs, ctx)
    qs = _apply_student_filter(qs, ctx)

    if ctx.role == ROLE_MANAGER:
        # DEC-15: Managers see LOCKED bills only for their own mess.
        qs = qs.filter(status="LOCKED")
    elif ctx.role == ROLE_CLERK:
        hostel_id = ctx.scope_hostel_id
        if hostel_id is None:
            return qs.none()
        qs = qs.filter(
            assignment_overlaps_period_exists(
                hostel_id=hostel_id,
                start_field="billing_period__period_start",
                end_field="billing_period__period_end",
            )
        )

    if ctx.hostel_id is not None and ctx.role != ROLE_CLERK:
        qs = qs.filter(
            assignment_overlaps_period_exists(
                hostel_id=ctx.hostel_id,
                start_field="billing_period__period_start",
                end_field="billing_period__period_end",
            )
        )

    return qs.annotate(
        report_hostel_name=coalesce_hostel_name(
            assignment_hostel_for_period_subquery(
                start_field="billing_period__period_start",
                end_field="billing_period__period_end",
                names=True,
            )
        )
    ).order_by("billing_period__period_start", "student__roll_number", "bill_id")


def billing_row(bill: Bill) -> dict[str, Any]:
    period = bill.billing_period
    return {
        "student": bill.student.user.full_name,
        "roll_number": bill.student.roll_number,
        "hostel": bill.report_hostel_name,
        "mess": bill.mess.name,
        "period": f"{period.year}-{period.month:02d}",
        "billed_minimum_count": bill.minimum_diet_count_snapshot,
        "meal_count": bill.actual_meal_count,
        "rate": bill.common_diet_rate_snapshot,
        "meal_component": bill.meal_component_amount,
        "extras": bill.extra_charges_amount,
        "fees_and_fines": bill.adjustment_amount,
        "final_amount": bill.final_amount,
        "status": bill.status,
    }


def billing_totals(ctx: ReportContext) -> dict[str, Any]:
    qs = billing_queryset(ctx)
    aggregate = qs.aggregate(
        bill_count=Count("bill_id"),
        billed_minimum_count=Sum("minimum_diet_count_snapshot"),
        meal_count=Sum("actual_meal_count"),
        meal_component=Sum("meal_component_amount"),
        extras=Sum("extra_charges_amount"),
        fees_and_fines=Sum("adjustment_amount"),
        final_amount=Sum("final_amount"),
    )
    return {key: _decimal(value) if key not in ("bill_count",) else (value or 0) for key, value in aggregate.items()}


def billing_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    return []


# ---------------------------------------------------------------------------
# 2. Meal consumption
# ---------------------------------------------------------------------------


def meal_consumption_queryset(ctx: ReportContext):
    qs = _effective_meals(ctx)
    qs = _apply_mess_scope(qs, ctx)
    qs = _apply_student_filter(qs, ctx)

    if ctx.meal_type is not None:
        if isinstance(ctx.meal_type, int):
            qs = qs.filter(meal_type_id=ctx.meal_type)
        elif str(ctx.meal_type).isdigit():
            qs = qs.filter(meal_type_id=int(ctx.meal_type))
        else:
            qs = qs.filter(meal_type__code__iexact=str(ctx.meal_type))

    if ctx.role == ROLE_CLERK:
        hostel_id = ctx.scope_hostel_id
        if hostel_id is None:
            return qs.none()
        qs = qs.filter(assignment_on_date_exists(hostel_id=hostel_id, date_field="meal_date"))
    elif ctx.hostel_id is not None:
        qs = qs.filter(
            assignment_on_date_exists(hostel_id=ctx.hostel_id, date_field="meal_date")
        )

    return qs.annotate(
        report_hostel_name=coalesce_hostel_name(
            assignment_hostel_on_date_subquery("meal_date", names=True)
        )
    )


def meal_consumption_row(meal) -> dict[str, Any]:
    return {
        "date": meal.meal_date,
        "meal_type": meal.meal_type.name,
        "student": meal.student.user.full_name,
        "roll_number": meal.roll_number_snapshot,
        "mess": meal.mess.name,
        "hostel": meal.report_hostel_name,
        "price": meal.price_at_transaction,
        "source": meal.source,
    }


def meal_consumption_totals(ctx: ReportContext) -> dict[str, Any]:
    aggregate = meal_consumption_queryset(ctx).aggregate(
        meal_count=Count("meal_consumption_id"),
        amount=Sum("price_at_transaction"),
    )
    return {
        "meal_count": aggregate["meal_count"] or 0,
        "amount": _decimal(aggregate["amount"]),
    }


def meal_consumption_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    groups = (
        meal_consumption_queryset(ctx)
        .values("meal_date")
        .annotate(
            meal_count=Count("meal_consumption_id"),
            amount=Sum("price_at_transaction"),
        )
        .order_by("meal_date")
    )
    return [
        {
            "label": group["meal_date"].isoformat(),
            "meal_count": group["meal_count"] or 0,
            "amount": _decimal(group["amount"]),
        }
        for group in groups
    ]


# ---------------------------------------------------------------------------
# 3. Extra-item usage
# ---------------------------------------------------------------------------


def extra_item_queryset(ctx: ReportContext):
    qs = (
        ExtraTransaction.objects.filter(sync_status__in=ACCEPTED_EXTRA_STATUSES)
        .select_related("student__user", "student__hostel", "mess", "hostel", "extra_item")
        .annotate(report_date=TruncDate("transaction_timestamp", tzinfo=IST_ZONE))
        .filter(report_date__gte=ctx.date_from, report_date__lte=ctx.date_to)
    )

    qs = _apply_mess_scope(qs, ctx)
    qs = _apply_student_filter(qs, ctx)

    if ctx.extra_item_id is not None:
        qs = qs.filter(extra_item_id=ctx.extra_item_id)

    if ctx.role == ROLE_CLERK:
        hostel_id = ctx.scope_hostel_id
        if hostel_id is None:
            return qs.none()
        qs = qs.filter(hostel_id=hostel_id)
    elif ctx.hostel_id is not None:
        qs = qs.filter(hostel_id=ctx.hostel_id)

    return qs.order_by("report_date", "extra_transaction_id")


def extra_item_row(extra: ExtraTransaction) -> dict[str, Any]:
    return {
        "date": extra.report_date,
        "item": extra.extra_item.name,
        "quantity": extra.quantity,
        "unit_price": extra.unit_price_at_transaction,
        "total_amount": extra.total_amount,
        "student": extra.student.user.full_name,
        "mess": extra.mess.name,
        "hostel": extra.hostel.name,
    }


def extra_item_totals(ctx: ReportContext) -> dict[str, Any]:
    aggregate = extra_item_queryset(ctx).aggregate(
        transaction_count=Count("extra_transaction_id"),
        quantity=Sum("quantity"),
        amount=Sum("total_amount"),
    )
    return {
        "transaction_count": aggregate["transaction_count"] or 0,
        "quantity": aggregate["quantity"] or 0,
        "amount": _decimal(aggregate["amount"]),
    }


def extra_item_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    groups = (
        extra_item_queryset(ctx)
        .values("extra_item__name")
        .annotate(
            quantity=Sum("quantity"),
            amount=Sum("total_amount"),
        )
        .order_by("extra_item__name")
    )
    return [
        {
            "label": group["extra_item__name"],
            "quantity": group["quantity"] or 0,
            "amount": _decimal(group["amount"]),
        }
        for group in groups
    ]


# ---------------------------------------------------------------------------
# 4. Pause
# ---------------------------------------------------------------------------


def pause_queryset(ctx: ReportContext):
    qs = (
        MessPause.objects.select_related("student__user", "student__hostel", "mess")
        .annotate(
            report_start=Coalesce("effective_start_date", "requested_start_date"),
            report_end=Coalesce("effective_end_date", "requested_end_date"),
            counted_slots=Count(
                "meal_slots",
                filter=Q(meal_slots__qualifies_for_activation=True),
            ),
        )
        .filter(report_start__lte=ctx.date_to, report_end__gte=ctx.date_from)
    )

    qs = _apply_mess_scope(qs, ctx)
    qs = _apply_student_filter(qs, ctx)

    if ctx.role == ROLE_CLERK:
        hostel_id = ctx.scope_hostel_id
        if hostel_id is None:
            return qs.none()
        qs = qs.filter(
            assignment_overlaps_period_exists(
                hostel_id=hostel_id, start_field="report_start", end_field="report_end"
            )
        )
    elif ctx.hostel_id is not None:
        qs = qs.filter(
            assignment_overlaps_period_exists(
                hostel_id=ctx.hostel_id,
                start_field="report_start",
                end_field="report_end",
            )
        )

    return qs.order_by("report_start", "pause_id")


def pause_row(pause: MessPause) -> dict[str, Any]:
    return {
        "student": pause.student.user.full_name,
        "mess": pause.mess.name,
        "requested_start": pause.requested_start_date,
        "requested_end": pause.requested_end_date,
        "effective_start": pause.effective_start_date,
        "effective_end": pause.effective_end_date,
        "status": pause.status,
        "counted_slots": pause.counted_slots,
    }


def pause_totals(ctx: ReportContext) -> dict[str, Any]:
    qs = pause_queryset(ctx)
    pause_ids = list(qs.values_list("pause_id", flat=True))
    counted = MessPauseMealSlot.objects.filter(
        pause_id__in=pause_ids, qualifies_for_activation=True
    ).count()
    return {"pause_count": len(pause_ids), "counted_slots": counted}


def pause_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    groups = (
        pause_queryset(ctx)
        .values("status")
        .annotate(pause_count=Count("pause_id"))
        .order_by("status")
    )
    return [
        {"label": group["status"], "pause_count": group["pause_count"] or 0}
        for group in groups
    ]


# ---------------------------------------------------------------------------
# 5. Feedback
# ---------------------------------------------------------------------------


def feedback_queryset(ctx: ReportContext):
    qs = Feedback.objects.select_related(
        "student__user", "student__hostel", "mess"
    )
    qs = annotate_feedback_month(qs)
    qs = qs.annotate(
        month_index=F("calendar_year") * Value(12) + F("calendar_month")
    ).filter(
        month_index__gte=_month_index(ctx.date_from),
        month_index__lte=_month_index(ctx.date_to),
    )
    qs = _apply_mess_scope(qs, ctx)
    qs = _apply_student_filter(qs, ctx)

    if ctx.role == ROLE_CLERK:
        hostel_id = ctx.scope_hostel_id
        if hostel_id is None:
            return qs.none()
        qs = qs.filter(feedback_assignment_exists(hostel_id=hostel_id))
    elif ctx.hostel_id is not None:
        qs = qs.filter(feedback_assignment_exists(hostel_id=ctx.hostel_id))

    return qs.annotate(
        report_hostel_name=coalesce_hostel_name(feedback_hostel_subquery(names=True))
    ).order_by("calendar_year", "calendar_month", "student__roll_number")


def feedback_row(feedback: Feedback) -> dict[str, Any]:
    return {
        "student": feedback.student.user.full_name,
        "mess": feedback.mess.name,
        "month": f"{feedback.calendar_year}-{feedback.calendar_month:02d}",
        "food_quality_rating": feedback.food_quality_rating,
        "taste_rating": feedback.taste_rating,
        "comments": feedback.comments,
    }


def feedback_totals(ctx: ReportContext) -> dict[str, Any]:
    aggregate = feedback_queryset(ctx).aggregate(
        response_count=Count("feedback_id"),
        average_quality=Sum("food_quality_rating"),
        average_taste=Sum("taste_rating"),
    )
    count = aggregate["response_count"] or 0
    return {
        "response_count": count,
        "average_quality": (
            _decimal(aggregate["average_quality"]) / count if count else Decimal("0")
        ).quantize(Decimal("0.01")),
        "average_taste": (
            _decimal(aggregate["average_taste"]) / count if count else Decimal("0")
        ).quantize(Decimal("0.01")),
    }


def feedback_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    groups = (
        feedback_queryset(ctx)
        .values("mess__name")
        .annotate(
            response_count=Count("feedback_id"),
            quality_total=Sum("food_quality_rating"),
            taste_total=Sum("taste_rating"),
        )
        .order_by("mess__name")
    )
    result = []
    for group in groups:
        count = group["response_count"] or 0
        result.append(
            {
                "label": group["mess__name"],
                "response_count": count,
                "average_quality": (
                    _decimal(group["quality_total"]) / count if count else Decimal("0")
                ).quantize(Decimal("0.01")),
                "average_taste": (
                    _decimal(group["taste_total"]) / count if count else Decimal("0")
                ).quantize(Decimal("0.01")),
            }
        )
    return result


# ---------------------------------------------------------------------------
# 6. Student balance
# ---------------------------------------------------------------------------


def _balance_base_queryset(ctx: ReportContext):
    qs = BalanceAccount.objects.select_related(
        "student__user", "student__hostel", "semester"
    )

    if ctx.role == ROLE_MANAGER:
        return qs.none()

    if ctx.role == ROLE_CLERK:
        hostel_id = ctx.scope_hostel_id
        if hostel_id is None:
            return qs.none()
        qs = qs.filter(
            assignment_overlap_exists(
                date_from=ctx.date_from,
                date_to=ctx.date_to,
                hostel_id=hostel_id,
            )
        )
    elif ctx.hostel_id is not None:
        qs = qs.filter(
            assignment_overlap_exists(
                date_from=ctx.date_from,
                date_to=ctx.date_to,
                hostel_id=ctx.hostel_id,
            )
        )

    return _apply_student_filter(qs, ctx)


def balance_queryset(ctx: ReportContext):
    qs = _balance_base_queryset(ctx)

    in_range = Q(
        ledger_entries__effective_date__gte=ctx.date_from,
        ledger_entries__effective_date__lte=ctx.date_to,
    )
    credits_filter = in_range & Q(
        ledger_entries__entry_type__in=["CREDIT", "BILL_REVERSAL"]
    )
    charges_filter = in_range & Q(ledger_entries__entry_type="BILL_CHARGE")
    as_of_filter = Q(ledger_entries__effective_date__lte=ctx.date_to)

    return qs.annotate(
        report_opening=F("opening_balance"),
        report_credits=Coalesce(
            Sum("ledger_entries__amount", filter=credits_filter),
            Value(Decimal("0")),
            output_field=MONEY_FIELD,
        ),
        report_charges=Coalesce(
            Sum("ledger_entries__amount", filter=charges_filter),
            Value(Decimal("0")),
            output_field=MONEY_FIELD,
        ),
        report_current=Coalesce(
            Sum("ledger_entries__amount", filter=as_of_filter),
            Value(Decimal("0")),
            output_field=MONEY_FIELD,
        ),
    ).order_by("student__roll_number", "semester__start_date", "balance_account_id")


def balance_row(account: BalanceAccount) -> dict[str, Any]:
    return {
        "student": account.student.user.full_name,
        "roll_number": account.student.roll_number,
        "semester": account.semester.code,
        "opening": account.opening_balance,
        "credits": account.report_credits,
        "charges": abs(account.report_charges),
        "current_balance": account.report_current,
    }


def balance_totals(ctx: ReportContext) -> dict[str, Any]:
    qs = _balance_base_queryset(ctx)
    account_ids = qs.values("balance_account_id")
    totals = qs.aggregate(
        account_count=Count("balance_account_id"),
        opening=Sum("opening_balance"),
    )
    credits = BalanceLedgerEntry.objects.filter(
        balance_account_id__in=account_ids,
        entry_type__in=["CREDIT", "BILL_REVERSAL"],
        effective_date__gte=ctx.date_from,
        effective_date__lte=ctx.date_to,
    ).aggregate(total=Sum("amount"))["total"]
    charges = BalanceLedgerEntry.objects.filter(
        balance_account_id__in=account_ids,
        entry_type="BILL_CHARGE",
        effective_date__gte=ctx.date_from,
        effective_date__lte=ctx.date_to,
    ).aggregate(total=Sum("amount"))["total"]
    current = BalanceLedgerEntry.objects.filter(
        balance_account_id__in=account_ids,
        effective_date__lte=ctx.date_to,
    ).aggregate(total=Sum("amount"))["total"]
    return {
        "account_count": totals["account_count"] or 0,
        "opening": _decimal(totals["opening"]),
        "credits": _decimal(credits),
        "charges": abs(_decimal(charges)),
        "current_balance": _decimal(current),
    }


def balance_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    return []


# ---------------------------------------------------------------------------
# 7. Hostel comparison (Super Admin only)
# ---------------------------------------------------------------------------


def _hostel_student_counts(ctx: ReportContext) -> dict[int, int]:
    rows = (
        StudentMessAssignment.objects.filter(
            assignment_overlaps_range_q(
                date_from=ctx.date_from, date_to=ctx.date_to
            )
        )
        .values("hostel_id")
        .annotate(students=Count("student_id", distinct=True))
    )
    return {row["hostel_id"]: row["students"] for row in rows}


def _hostel_meal_totals(ctx: ReportContext) -> dict[int, dict[str, Any]]:
    rows = (
        get_effective_meal_consumptions(
            start_date=ctx.date_from, end_date=ctx.date_to
        )
        .annotate(
            report_hostel_id=coalesce_hostel_id(
                assignment_hostel_on_date_subquery("meal_date", names=False)
            )
        )
        .values("report_hostel_id")
        .annotate(
            meals=Count("meal_consumption_id"),
            meal_amount=Sum("price_at_transaction"),
        )
    )
    return {
        row["report_hostel_id"]: {
            "meals": row["meals"] or 0,
            "meal_amount": _decimal(row["meal_amount"]),
        }
        for row in rows
    }


def _hostel_extra_totals(ctx: ReportContext) -> dict[int, dict[str, Any]]:
    rows = (
        ExtraTransaction.objects.filter(sync_status__in=ACCEPTED_EXTRA_STATUSES)
        .annotate(report_date=TruncDate("transaction_timestamp", tzinfo=IST_ZONE))
        .filter(report_date__gte=ctx.date_from, report_date__lte=ctx.date_to)
        .values("hostel_id")
        .annotate(
            extra_count=Count("extra_transaction_id"),
            extra_amount=Sum("total_amount"),
        )
    )
    return {
        row["hostel_id"]: {
            "extra_count": row["extra_count"] or 0,
            "extra_amount": _decimal(row["extra_amount"]),
        }
        for row in rows
    }


def _hostel_billing_totals(ctx: ReportContext) -> dict[int, dict[str, Any]]:
    rows = (
        Bill.objects.filter(
            billing_period__period_start__lte=ctx.date_to,
            billing_period__period_end__gte=ctx.date_from,
        )
        .annotate(
            report_hostel_id=coalesce_hostel_id(
                assignment_hostel_for_period_subquery(
                    start_field="billing_period__period_start",
                    end_field="billing_period__period_end",
                    names=False,
                )
            )
        )
        .values("report_hostel_id")
        .annotate(billed_total=Sum("final_amount"))
    )
    return {
        row["report_hostel_id"]: {"billed_total": _decimal(row["billed_total"])}
        for row in rows
    }


def _hostel_feedback_totals(ctx: ReportContext) -> dict[int, dict[str, Any]]:
    qs = annotate_feedback_month(Feedback.objects.all())
    qs = qs.annotate(
        month_index=F("calendar_year") * Value(12) + F("calendar_month")
    ).filter(
        month_index__gte=_month_index(ctx.date_from),
        month_index__lte=_month_index(ctx.date_to),
    )
    rows = (
        qs.annotate(
            report_hostel_id=coalesce_hostel_id(feedback_hostel_subquery(names=False))
        )
        .values("report_hostel_id")
        .annotate(
            feedback_count=Count("feedback_id"),
            quality_total=Sum("food_quality_rating"),
            taste_total=Sum("taste_rating"),
        )
    )
    result = {}
    for row in rows:
        count = row["feedback_count"] or 0
        result[row["report_hostel_id"]] = {
            "feedback_count": count,
            "quality_total": _decimal(row["quality_total"]),
            "taste_total": _decimal(row["taste_total"]),
        }
    return result


def hostel_comparison_rows(ctx: ReportContext) -> list[dict[str, Any]]:
    students = _hostel_student_counts(ctx)
    meals = _hostel_meal_totals(ctx)
    extras = _hostel_extra_totals(ctx)
    billing = _hostel_billing_totals(ctx)
    feedback = _hostel_feedback_totals(ctx)

    rows = []
    for hostel in Hostel.objects.all().order_by("code"):
        hostel_id = hostel.hostel_id
        meal_data = meals.get(hostel_id, {})
        extra_data = extras.get(hostel_id, {})
        feedback_data = feedback.get(hostel_id, {})
        feedback_count = feedback_data.get("feedback_count", 0)
        rows.append(
            {
                "hostel": hostel.name,
                "students": students.get(hostel_id, 0),
                "meals": meal_data.get("meals", 0),
                "meal_amount": meal_data.get("meal_amount", Decimal("0")),
                "extras_amount": extra_data.get("extra_amount", Decimal("0")),
                "billed_total": billing.get(hostel_id, {}).get(
                    "billed_total", Decimal("0")
                ),
                "average_quality": (
                    feedback_data.get("quality_total", Decimal("0")) / feedback_count
                    if feedback_count
                    else Decimal("0")
                ).quantize(Decimal("0.01")),
                "average_taste": (
                    feedback_data.get("taste_total", Decimal("0")) / feedback_count
                    if feedback_count
                    else Decimal("0")
                ).quantize(Decimal("0.01")),
                "_quality_total": feedback_data.get("quality_total", Decimal("0")),
                "_taste_total": feedback_data.get("taste_total", Decimal("0")),
                "_feedback_count": feedback_count,
            }
        )
    return rows


def hostel_comparison_totals(ctx: ReportContext, rows=None) -> dict[str, Any]:
    rows = rows if rows is not None else hostel_comparison_rows(ctx)
    quality_total = sum((row["_quality_total"] for row in rows), Decimal("0"))
    taste_total = sum((row["_taste_total"] for row in rows), Decimal("0"))
    feedback_count = sum(row["_feedback_count"] for row in rows)
    return {
        "hostel_count": len(rows),
        "students": sum(row["students"] for row in rows),
        "meals": sum(row["meals"] for row in rows),
        "meal_amount": sum((row["meal_amount"] for row in rows), Decimal("0")),
        "extras_amount": sum((row["extras_amount"] for row in rows), Decimal("0")),
        "billed_total": sum((row["billed_total"] for row in rows), Decimal("0")),
        "average_quality": (
            quality_total / feedback_count if feedback_count else Decimal("0")
        ).quantize(Decimal("0.01")),
        "average_taste": (
            taste_total / feedback_count if feedback_count else Decimal("0")
        ).quantize(Decimal("0.01")),
    }


def hostel_comparison_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    return []


# ---------------------------------------------------------------------------
# 8. Mess comparison (Super Admin only)
# ---------------------------------------------------------------------------


def _mess_student_counts(ctx: ReportContext) -> dict[int, int]:
    rows = (
        StudentMessAssignment.objects.filter(
            assignment_overlaps_range_q(
                date_from=ctx.date_from, date_to=ctx.date_to
            )
        )
        .values("mess_id")
        .annotate(students=Count("student_id", distinct=True))
    )
    return {row["mess_id"]: row["students"] for row in rows}


def _mess_meal_totals(ctx: ReportContext) -> dict[int, dict[str, Any]]:
    rows = (
        get_effective_meal_consumptions(
            start_date=ctx.date_from, end_date=ctx.date_to
        )
        .values("mess_id")
        .annotate(
            meals=Count("meal_consumption_id"),
            meal_amount=Sum("price_at_transaction"),
        )
    )
    return {
        row["mess_id"]: {
            "meals": row["meals"] or 0,
            "meal_amount": _decimal(row["meal_amount"]),
        }
        for row in rows
    }


def _mess_extra_totals(ctx: ReportContext) -> dict[int, dict[str, Any]]:
    rows = (
        ExtraTransaction.objects.filter(sync_status__in=ACCEPTED_EXTRA_STATUSES)
        .annotate(report_date=TruncDate("transaction_timestamp", tzinfo=IST_ZONE))
        .filter(report_date__gte=ctx.date_from, report_date__lte=ctx.date_to)
        .values("mess_id")
        .annotate(
            extra_count=Count("extra_transaction_id"),
            extra_amount=Sum("total_amount"),
        )
    )
    return {
        row["mess_id"]: {
            "extra_count": row["extra_count"] or 0,
            "extra_amount": _decimal(row["extra_amount"]),
        }
        for row in rows
    }


def _mess_billing_totals(ctx: ReportContext) -> dict[int, dict[str, Any]]:
    rows = (
        Bill.objects.filter(
            billing_period__period_start__lte=ctx.date_to,
            billing_period__period_end__gte=ctx.date_from,
        )
        .values("mess_id")
        .annotate(billed_total=Sum("final_amount"))
    )
    return {
        row["mess_id"]: {"billed_total": _decimal(row["billed_total"])}
        for row in rows
    }


def _mess_feedback_totals(ctx: ReportContext) -> dict[int, dict[str, Any]]:
    qs = Feedback.objects.all()
    rows = (
        qs.annotate(month_index=F("calendar_year") * Value(12) + F("calendar_month"))
        .filter(
            month_index__gte=_month_index(ctx.date_from),
            month_index__lte=_month_index(ctx.date_to),
        )
        .values("mess_id")
        .annotate(
            feedback_count=Count("feedback_id"),
            quality_total=Sum("food_quality_rating"),
            taste_total=Sum("taste_rating"),
        )
    )
    result = {}
    for row in rows:
        count = row["feedback_count"] or 0
        result[row["mess_id"]] = {
            "feedback_count": count,
            "quality_total": _decimal(row["quality_total"]),
            "taste_total": _decimal(row["taste_total"]),
        }
    return result


def mess_comparison_rows(ctx: ReportContext) -> list[dict[str, Any]]:
    students = _mess_student_counts(ctx)
    meals = _mess_meal_totals(ctx)
    extras = _mess_extra_totals(ctx)
    billing = _mess_billing_totals(ctx)
    feedback = _mess_feedback_totals(ctx)

    rows = []
    for mess in Mess.objects.all().order_by("code"):
        mess_id = mess.mess_id
        meal_data = meals.get(mess_id, {})
        extra_data = extras.get(mess_id, {})
        feedback_data = feedback.get(mess_id, {})
        feedback_count = feedback_data.get("feedback_count", 0)
        rows.append(
            {
                "mess": mess.name,
                "students": students.get(mess_id, 0),
                "meals": meal_data.get("meals", 0),
                "meal_amount": meal_data.get("meal_amount", Decimal("0")),
                "extras_amount": extra_data.get("extra_amount", Decimal("0")),
                "billed_total": billing.get(mess_id, {}).get(
                    "billed_total", Decimal("0")
                ),
                "average_quality": (
                    feedback_data.get("quality_total", Decimal("0")) / feedback_count
                    if feedback_count
                    else Decimal("0")
                ).quantize(Decimal("0.01")),
                "average_taste": (
                    feedback_data.get("taste_total", Decimal("0")) / feedback_count
                    if feedback_count
                    else Decimal("0")
                ).quantize(Decimal("0.01")),
                "_quality_total": feedback_data.get("quality_total", Decimal("0")),
                "_taste_total": feedback_data.get("taste_total", Decimal("0")),
                "_feedback_count": feedback_count,
            }
        )
    return rows


def mess_comparison_totals(ctx: ReportContext, rows=None) -> dict[str, Any]:
    rows = rows if rows is not None else mess_comparison_rows(ctx)
    quality_total = sum((row["_quality_total"] for row in rows), Decimal("0"))
    taste_total = sum((row["_taste_total"] for row in rows), Decimal("0"))
    feedback_count = sum(row["_feedback_count"] for row in rows)
    return {
        "mess_count": len(rows),
        "students": sum(row["students"] for row in rows),
        "meals": sum(row["meals"] for row in rows),
        "meal_amount": sum((row["meal_amount"] for row in rows), Decimal("0")),
        "extras_amount": sum((row["extras_amount"] for row in rows), Decimal("0")),
        "billed_total": sum((row["billed_total"] for row in rows), Decimal("0")),
        "average_quality": (
            quality_total / feedback_count if feedback_count else Decimal("0")
        ).quantize(Decimal("0.01")),
        "average_taste": (
            taste_total / feedback_count if feedback_count else Decimal("0")
        ).quantize(Decimal("0.01")),
    }


def mess_comparison_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    return []


# ---------------------------------------------------------------------------
# 9. Cross-hostel statistics (Super Admin only)
# ---------------------------------------------------------------------------


def cross_hostel_rows(ctx: ReportContext) -> list[dict[str, Any]]:
    meal_rows = (
        get_effective_meal_consumptions(
            start_date=ctx.date_from, end_date=ctx.date_to
        )
        .annotate(
            report_hostel_id=coalesce_hostel_id(
                assignment_hostel_on_date_subquery("meal_date", names=False)
            )
        )
        .values("report_hostel_id", "mess_id")
        .annotate(
            meal_count=Count("meal_consumption_id"),
            meal_amount=Sum("price_at_transaction"),
        )
    )
    extra_rows = (
        ExtraTransaction.objects.filter(sync_status__in=ACCEPTED_EXTRA_STATUSES)
        .annotate(report_date=TruncDate("transaction_timestamp", tzinfo=IST_ZONE))
        .filter(report_date__gte=ctx.date_from, report_date__lte=ctx.date_to)
        .values("hostel_id", "mess_id")
        .annotate(
            extra_count=Count("extra_transaction_id"),
            extra_amount=Sum("total_amount"),
        )
    )

    hostel_names = dict(Hostel.objects.values_list("hostel_id", "name"))
    mess_names = dict(Mess.objects.values_list("mess_id", "name"))

    combined: dict[tuple[int, int], dict[str, Any]] = {}
    for row in meal_rows:
        key = (row["report_hostel_id"], row["mess_id"])
        entry = combined.setdefault(
            key,
            {
                "hostel": hostel_names.get(key[0], ""),
                "mess": mess_names.get(key[1], ""),
                "meal_count": 0,
                "meal_amount": Decimal("0"),
                "extra_count": 0,
                "extra_amount": Decimal("0"),
            },
        )
        entry["meal_count"] = row["meal_count"] or 0
        entry["meal_amount"] = _decimal(row["meal_amount"])

    for row in extra_rows:
        key = (row["hostel_id"], row["mess_id"])
        entry = combined.setdefault(
            key,
            {
                "hostel": hostel_names.get(key[0], ""),
                "mess": mess_names.get(key[1], ""),
                "meal_count": 0,
                "meal_amount": Decimal("0"),
                "extra_count": 0,
                "extra_amount": Decimal("0"),
            },
        )
        entry["extra_count"] = row["extra_count"] or 0
        entry["extra_amount"] = _decimal(row["extra_amount"])

    rows = []
    for entry in combined.values():
        entry["total_amount"] = entry["meal_amount"] + entry["extra_amount"]
        rows.append(entry)
    return sorted(rows, key=lambda row: (row["hostel"], row["mess"]))


def cross_hostel_totals(ctx: ReportContext, rows=None) -> dict[str, Any]:
    rows = rows if rows is not None else cross_hostel_rows(ctx)
    return {
        "row_count": len(rows),
        "meal_count": sum(row["meal_count"] for row in rows),
        "meal_amount": sum((row["meal_amount"] for row in rows), Decimal("0")),
        "extra_count": sum(row["extra_count"] for row in rows),
        "extra_amount": sum((row["extra_amount"] for row in rows), Decimal("0")),
        "total_amount": sum((row["total_amount"] for row in rows), Decimal("0")),
    }


def cross_hostel_groups(ctx: ReportContext) -> list[dict[str, Any]]:
    return []
