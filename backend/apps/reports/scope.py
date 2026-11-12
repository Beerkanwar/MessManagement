"""
Report scoping primitives [ImplementationGuide Phase 12, SPEC DBDD §4.1, §20].

Reports must never move history when a student transfers between hostels or
messes.  Consequently every historical report resolves hostel/mess context
from the ``StudentMessAssignment`` that covered the row's own date, instead of
reading the student's current ``hostel`` field.  Assignment intervals are
half-open: ``[effective_from, effective_to)``.

The helpers in this module only build querysets/expressions; they do not
perform HTTP validation (see ``services.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.db.models import (
    Case,
    CharField,
    DateField,
    F,
    Func,
    IntegerField,
    Q,
    Value,
    When,
)
from django.db.models.expressions import Exists, OuterRef, Subquery
from django.db.models.functions import Coalesce

from apps.hostel.models import StudentMessAssignment
from apps.identity.models import User
from apps.identity.selectors import (
    get_clerk_hostel,
    get_manager_mess,
    get_user_role,
)

# PENDING_VERIFICATION/REJECTED assignments never represented real occupation;
# ACTIVE and ENDED rows together form the student's historical timeline.
REPORTABLE_ASSIGNMENT_STATUSES = ("ACTIVE", "ENDED")

ROLE_STUDENT = "STUDENT"
ROLE_MANAGER = "MESS_MANAGER"
ROLE_CLERK = "HOSTEL_CLERK"
ROLE_SUPER_ADMIN = "SUPER_ADMIN"


@dataclass(frozen=True)
class ReportContext:
    """Validated parameters shared by every report implementation."""

    user: User
    role: str
    date_from: date
    date_to: date
    hostel_id: int | None = None
    mess_id: int | None = None
    student_id: int | None = None
    meal_type: str | int | None = None
    extra_item_id: int | None = None
    applied_filters: dict[str, Any] = field(default_factory=dict)

    @property
    def scope_hostel_id(self) -> int | None:
        if self.role == ROLE_CLERK:
            hostel = get_clerk_hostel(self.user)
            return hostel.hostel_id if hostel else None
        return self.hostel_id

    @property
    def scope_mess_id(self) -> int | None:
        if self.role == ROLE_MANAGER:
            mess = get_manager_mess(self.user)
            return mess.mess_id if mess else None
        return self.mess_id


def resolve_role(user: User) -> str | None:
    """Returns the effective report role, honouring Django superusers."""
    if getattr(user, "is_superuser", False):
        return ROLE_SUPER_ADMIN
    return get_user_role(user)


def assignment_overlaps_range_q(
    *,
    date_from: date,
    date_to: date,
    hostel_id: int | None = None,
    mess_id: int | None = None,
) -> Q:
    """Q object matching assignments that overlap an inclusive date range."""
    query = Q(
        status__in=REPORTABLE_ASSIGNMENT_STATUSES,
        effective_from__lte=date_to,
    ) & (Q(effective_to__isnull=True) | Q(effective_to__gt=date_from))
    if hostel_id is not None:
        query &= Q(hostel_id=hostel_id)
    if mess_id is not None:
        query &= Q(mess_id=mess_id)
    return query


def assignment_overlap_exists(
    *,
    student_outer_ref: str = "student_id",
    date_from: date,
    date_to: date,
    hostel_id: int | None = None,
    mess_id: int | None = None,
) -> Exists:
    """EXISTS() subquery: does the row's student have an overlapping assignment?"""
    query = assignment_overlaps_range_q(
        date_from=date_from, date_to=date_to, hostel_id=hostel_id, mess_id=mess_id
    )
    return Exists(
        StudentMessAssignment.objects.filter(
            query, student_id=OuterRef(student_outer_ref)
        )
    )


def assignment_on_date_exists(*, hostel_id: int, date_field: str) -> Exists:
    """
    EXISTS() subquery: was the row's student assigned to ``hostel_id`` on the
    date held by ``date_field`` (e.g. ``meal_date``)?
    """
    return Exists(
        StudentMessAssignment.objects.filter(
            student_id=OuterRef("student_id"),
            hostel_id=hostel_id,
            status__in=REPORTABLE_ASSIGNMENT_STATUSES,
            effective_from__lte=OuterRef(date_field),
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=OuterRef(date_field))
        )
    )


def assignment_overlaps_period_exists(
    *, hostel_id: int, start_field: str, end_field: str
) -> Exists:
    """
    EXISTS() subquery: did the row's student have an assignment to the hostel
    that overlaps the row's own inclusive [start_field, end_field] period?
    """
    return Exists(
        StudentMessAssignment.objects.filter(
            student_id=OuterRef("student_id"),
            hostel_id=hostel_id,
            status__in=REPORTABLE_ASSIGNMENT_STATUSES,
            effective_from__lte=OuterRef(end_field),
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=OuterRef(start_field))
        )
    )


def assignment_hostel_on_date_subquery(date_field: str, *, names: bool = False):
    """
    Correlated subquery resolving the hostel governing ``date_field``.

    Returns the most recently started assignment covering the date.  Callers
    typically wrap this in ``Coalesce(..., F("student__hostel_id"))`` so a
    missing assignment still yields a useful fallback.
    """
    value_field = "hostel__name" if names else "hostel_id"
    return Subquery(
        StudentMessAssignment.objects.filter(
            student_id=OuterRef("student_id"),
            status__in=REPORTABLE_ASSIGNMENT_STATUSES,
            effective_from__lte=OuterRef(date_field),
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=OuterRef(date_field)))
        .order_by("-effective_from", "-assignment_id")
        .values(value_field)[:1]
    )


def assignment_hostel_for_period_subquery(
    *, start_field: str, end_field: str, names: bool = False
):
    """
    Correlated subquery resolving the hostel for a billing/reporting period.

    A bill belongs to the assignment whose interval overlaps the billing
    period; the latest-starting overlapping row wins when a transfer straddles
    a period boundary.
    """
    value_field = "hostel__name" if names else "hostel_id"
    return Subquery(
        StudentMessAssignment.objects.filter(
            student_id=OuterRef("student_id"),
            status__in=REPORTABLE_ASSIGNMENT_STATUSES,
            effective_from__lte=OuterRef(end_field),
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=OuterRef(start_field)))
        .order_by("-effective_from", "-assignment_id")
        .values(value_field)[:1]
    )


def feedback_month_start_expression():
    """
    Postgres ``make_date(calendar_year, calendar_month, 1)`` expression.

    Feedback is stored as (year, month) integers; the expression converts it to
    a date without a Python round-trip so scope filters stay SQL-side.
    """
    return Func(
        F("calendar_year"),
        F("calendar_month"),
        Value(1),
        function="make_date",
        output_field=DateField(),
    )


def feedback_next_month_start_expression():
    """Postgres expression for the first day of the month after a feedback row."""
    next_year = F("calendar_year") + Case(
        When(calendar_month=12, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )
    next_month = Case(
        When(calendar_month=12, then=Value(1)),
        default=F("calendar_month") + Value(1),
        output_field=IntegerField(),
    )
    return Func(
        next_year,
        next_month,
        Value(1),
        function="make_date",
        output_field=DateField(),
    )


def feedback_assignment_exists(*, hostel_id: int) -> Exists:
    """
    EXISTS() scoping feedback to a Clerk's hostel for the feedback's own month.

    The assignment must overlap the calendar month: assignment.start < next
    month start AND (assignment.end is null OR assignment.end > month start).
    """
    return Exists(
        StudentMessAssignment.objects.filter(
            student_id=OuterRef("student_id"),
            hostel_id=hostel_id,
            status__in=REPORTABLE_ASSIGNMENT_STATUSES,
            effective_from__lt=OuterRef("report_month_next"),
        ).filter(
            Q(effective_to__isnull=True)
            | Q(effective_to__gt=OuterRef("report_month_start"))
        )
    )


def feedback_hostel_subquery(*, names: bool = False):
    """Correlated subquery resolving the hostel governing a feedback month."""
    value_field = "hostel__name" if names else "hostel_id"
    return Subquery(
        StudentMessAssignment.objects.filter(
            student_id=OuterRef("student_id"),
            status__in=REPORTABLE_ASSIGNMENT_STATUSES,
            effective_from__lt=OuterRef("report_month_next"),
        )
        .filter(
            Q(effective_to__isnull=True)
            | Q(effective_to__gt=OuterRef("report_month_start"))
        )
        .order_by("-effective_from", "-assignment_id")
        .values(value_field)[:1]
    )


def annotate_feedback_month(queryset):
    """Adds ``report_month_start``/``report_month_next`` aliases to Feedback."""
    return queryset.annotate(
        report_month_start=feedback_month_start_expression(),
        report_month_next=feedback_next_month_start_expression(),
    )


def coalesce_hostel_id(subquery):
    """Subquery with the student's current hostel as a fallback."""
    return Coalesce(subquery, F("student__hostel_id"), output_field=IntegerField())


def coalesce_hostel_name(subquery):
    """Hostel-name subquery with the student's current hostel name as fallback."""
    return Coalesce(
        subquery,
        F("student__hostel__name"),
        output_field=CharField(),
    )
