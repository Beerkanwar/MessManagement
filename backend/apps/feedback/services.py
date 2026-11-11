"""
Feedback domain services implementing SPEC DBDD §10, SRS §23, SDD §49 and
ImplementationGuide Phase 11.

Rules:
- One immutable response per student per calendar month [Invariant 6,
  DBDD-AC-29]. The database unique constraint is the final guard under double
  taps; the service maps that race to FEEDBACK_ALREADY_SUBMITTED.
- The mess comes from the student's ACTIVE assignment at submission time and the
  year/month from the IST clock; the client sends neither [SRS §29].
- Ratings are whole numbers 1-5; comments are optional inert plain text up to
  1,000 characters.
- There is no update or delete path: model code and a database trigger refuse
  both [SDD §49, Invariant 12].
"""
from __future__ import annotations

from django.db import IntegrityError, transaction

from apps.core.clock import clock
from apps.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from apps.feedback.models import Feedback
from apps.feedback.selectors import get_active_assignment, get_student_for_user
from apps.identity.models import User
from apps.identity.selectors import get_user_role

MAX_COMMENTS_LENGTH = 1000


def _require_student(actor: User) -> None:
    if get_user_role(actor) != "STUDENT":
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Feedback submission is limited to students.",
        )


def _validate_rating(label: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"{label} must be a whole number from 1 to 5.",
        )


@transaction.atomic
def submit_feedback(
    *,
    food_quality_rating: int,
    taste_rating: int,
    comments: str | None = None,
    actor: User,
    correlation_id: str = "",
) -> Feedback:
    """
    Records the student's one feedback response for the current IST month.
    A duplicate is rejected with 409 FEEDBACK_ALREADY_SUBMITTED.
    """
    _require_student(actor)
    _validate_rating("food_quality_rating", food_quality_rating)
    _validate_rating("taste_rating", taste_rating)

    plain_comments = comments or ""
    if len(plain_comments) > MAX_COMMENTS_LENGTH:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Comments cannot exceed {MAX_COMMENTS_LENGTH} characters.",
        )

    student = get_student_for_user(actor)
    assignment = get_active_assignment(student)
    if not assignment:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="No active mess assignment is available for this student.",
        )

    today = clock.today()
    if Feedback.objects.filter(
        student=student,
        calendar_year=today.year,
        calendar_month=today.month,
    ).exists():
        raise ConflictError(
            code="FEEDBACK_ALREADY_SUBMITTED",
            message="Feedback has already been submitted for this calendar month.",
        )

    try:
        with transaction.atomic():
            return Feedback.objects.create(
                student=student,
                mess=assignment.mess,
                calendar_year=today.year,
                calendar_month=today.month,
                food_quality_rating=food_quality_rating,
                taste_rating=taste_rating,
                comments=plain_comments,
            )
    except IntegrityError:
        # The unique constraint is the final guard under concurrent double taps
        # [DBDD-AC-29]. The insert was rolled back; the request is a clean 409.
        raise ConflictError(
            code="FEEDBACK_ALREADY_SUBMITTED",
            message="Feedback has already been submitted for this calendar month.",
        )
