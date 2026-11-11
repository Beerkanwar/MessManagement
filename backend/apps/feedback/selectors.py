"""
Read selectors for the feedback endpoint group
[SPEC DBDD §10, SRS §23, SDD §49, ImplementationGuide Phase 11].

Feedback is associated with the student's mess at submission time; the server
derives the mess from the student's ACTIVE assignment and the year/month from
the IST clock. The client never supplies either.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from django.db.models import Q

from apps.core.clock import clock
from apps.core.exceptions import NotFoundError
from apps.feedback.models import Feedback
from apps.hostel.models import Student, StudentMessAssignment
from apps.identity.models import User


def get_student_for_user(user: User) -> Student:
    student = Student.objects.select_related("hostel").filter(user=user).first()
    if not student:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="No student profile is associated with this account.",
        )
    return student


def get_active_assignment(
    student: Student, on_date: date | None = None
) -> StudentMessAssignment | None:
    """The student's ACTIVE assignment covering the requested IST date."""
    as_of = on_date or clock.today()
    return (
        StudentMessAssignment.objects.filter(
            student=student,
            status="ACTIVE",
            effective_from__lte=as_of,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=as_of))
        .select_related("hostel", "mess")
        .order_by("-effective_from", "-assignment_id")
        .first()
    )


def get_feedback_for_month(
    student: Student, calendar_year: int, calendar_month: int
) -> Feedback | None:
    return (
        Feedback.objects.select_related("mess", "student")
        .filter(
            student=student,
            calendar_year=calendar_year,
            calendar_month=calendar_month,
        )
        .first()
    )


def get_current_feedback_context(user: User) -> dict[str, Any]:
    """
    Tells the app whether this month's response exists and shows it read-only.
    The current month comes from the IST clock, never from the client [DEC-01].
    """
    student = get_student_for_user(user)
    today = clock.today()
    feedback = get_feedback_for_month(student, today.year, today.month)
    return {
        "student_id": student.student_id,
        "calendar_year": today.year,
        "calendar_month": today.month,
        "submitted": feedback is not None,
        "feedback": feedback,
    }
