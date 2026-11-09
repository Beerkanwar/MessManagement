"""
Mess pause domain services implementing SPEC DBDD §7, DEC-06, DEC-23 and D23.

Business rules:
- A pause is automatically approved and becomes effective only after the next three
  qualifying scheduled meal slots pass. Breakfast, Lunch and Dinner qualify;
  Evening Snacks are walked over but never count [DBDD §7, DEC-06].
- The requested end date is never altered. The effective start date is the date of
  the first qualifying slot after the third counted slot [DBDD-AC-27].
- At most one SCHEDULED or ACTIVE pause exists per student (database partial unique).
- A meal taken during an ACTIVE pause cancels the rest of the pause from that meal;
  earlier slots remain paused and the meal is recorded and billed normally [D23].
- The server is authoritative for pause state. Managers receive it through sync.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from typing import Any, Iterable, Sequence

from django.db import IntegrityError, transaction
from django.db.models import F, Q

from apps.audit.services import record_audit_event
from apps.config.services import get_time_setting
from apps.core.clock import IST_ZONE, clock
from apps.core.exceptions import ConflictError, NotFoundError, ValidationError
from apps.hostel.models import Student, StudentMessAssignment
from apps.identity.models import User
from apps.mess.models import MealOccurrence, MealType, Mess
from apps.pause.models import MessPause, MessPauseMealSlot

# Qualifying meal type codes for pause activation [DEC-06]
QUALIFYING_MEAL_CODES = {"BREAKFAST", "LUNCH", "DINNER"}

# Number of qualifying slots required before pause activation [DEC-06]
ACTIVATION_SLOT_COUNT = 3

# Pause cancellation reasons owned by the domain
CANCEL_REASON_MEAL_TAKEN = "MEAL_TAKEN"
CANCEL_REASON_STUDENT = "CANCELLED_BY_STUDENT"


@dataclass(frozen=True)
class SlotInput:
    """A scheduled meal slot reduced to the data the activation counter needs."""

    meal_date: date
    meal_type_code: str
    sequence_no: int
    end_at: datetime

    @property
    def qualifies(self) -> bool:
        return self.meal_type_code in QUALIFYING_MEAL_CODES


@dataclass(frozen=True)
class ActivationPlan:
    """Deterministic result of walking the meal calendar for a pause request."""

    counted_slots: tuple[SlotInput, ...]
    skipped_slots: tuple[SlotInput, ...]
    recorded_slots: tuple[SlotInput, ...]
    activation_meal_date: date
    effective_start_date: date


def _iso(value) -> str | None:
    """Render a date/datetime as ISO text for API-facing dictionaries."""
    return value.isoformat() if value is not None else None


def _as_utc(value: datetime) -> datetime:
    """Normalise a datetime to an aware UTC value (naive input is assumed UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(dt_timezone.utc)


def _start_of_day_ist(day: date) -> datetime:
    """Return IST midnight for a calendar date, expressed in UTC."""
    return datetime.combine(day, time.min).replace(tzinfo=IST_ZONE).astimezone(dt_timezone.utc)


def occurrence_end_at(occurrence: MealOccurrence) -> datetime:
    """
    Resolve a meal occurrence's service end time from SystemSetting (IST) [DEC-06].
    The value is returned as an aware UTC datetime so it can be compared with clock.now().
    """
    setting_key = f"meal.{occurrence.meal_type.code}.end_time"
    end_time = get_time_setting(setting_key)
    if end_time is None:
        raise ValidationError(
            code="MEAL_END_TIME_NOT_CONFIGURED",
            message=f"Meal end time '{setting_key}' is not configured.",
        )
    local_end = datetime.combine(occurrence.meal_date, end_time).replace(tzinfo=IST_ZONE)
    return local_end.astimezone(dt_timezone.utc)


def build_activation_plan(
    slots: Sequence[SlotInput],
    threshold: datetime,
) -> ActivationPlan:
    """
    Pure slot-counting function (no database access, no writes) [DEC-06].

    It walks scheduled slots in (MealDate, MealType sequence) order starting at the
    first slot whose end time is strictly after ``threshold``. Evening Snacks are
    recorded as skipped slots; Breakfast, Lunch and Dinner are counted until three
    have been seen. The effective start date is the next qualifying slot after the
    third counted slot.
    """
    threshold = _as_utc(threshold)
    ordered = sorted(slots, key=lambda slot: (slot.meal_date, slot.sequence_no))

    recorded: list[SlotInput] = []
    counted: list[SlotInput] = []
    skipped: list[SlotInput] = []
    activation_meal_date: date | None = None
    effective_start_date: date | None = None

    for slot in ordered:
        if slot.end_at <= threshold:
            continue

        if len(counted) < ACTIVATION_SLOT_COUNT:
            recorded.append(slot)
            if slot.qualifies:
                counted.append(slot)
            else:
                skipped.append(slot)

            if len(counted) == ACTIVATION_SLOT_COUNT:
                activation_meal_date = slot.meal_date
            continue

        # Three qualifying slots have been counted; the next core meal starts the pause.
        if slot.qualifies:
            effective_start_date = slot.meal_date
            break

    if len(counted) < ACTIVATION_SLOT_COUNT:
        raise ValidationError(
            code="INSUFFICIENT_QUALIFYING_SLOTS",
            message=(
                "At least three qualifying Breakfast, Lunch or Dinner occurrences "
                "must remain ahead of the requested start date."
            ),
        )

    if effective_start_date is None:
        raise ValidationError(
            code="INSUFFICIENT_QUALIFYING_SLOTS",
            message=(
                "At least four qualifying Breakfast, Lunch or Dinner occurrences "
                "must remain ahead (three to count and one to start the pause)."
            ),
        )

    assert activation_meal_date is not None
    return ActivationPlan(
        counted_slots=tuple(counted),
        skipped_slots=tuple(skipped),
        recorded_slots=tuple(recorded),
        activation_meal_date=activation_meal_date,
        effective_start_date=effective_start_date,
    )


def _load_slots(
    mess: Mess,
    start_date: date,
) -> list[tuple[SlotInput, MealOccurrence]]:
    """Load scheduled occurrences for a mess from ``start_date`` onwards."""
    occurrences = (
        MealOccurrence.objects.filter(
            mess=mess,
            status="SCHEDULED",
            meal_date__gte=start_date,
        )
        .select_related("meal_type")
        .order_by("meal_date", "meal_type__sequence_no")
    )
    pairs: list[tuple[SlotInput, MealOccurrence]] = []
    for occurrence in occurrences:
        pairs.append(
            (
                SlotInput(
                    meal_date=occurrence.meal_date,
                    meal_type_code=occurrence.meal_type.code,
                    sequence_no=occurrence.meal_type.sequence_no,
                    end_at=occurrence_end_at(occurrence),
                ),
                occurrence,
            )
        )
    return pairs


def _plan_with_occurrences(
    *,
    mess: Mess,
    request_time: datetime,
    requested_start_date: date,
) -> tuple[ActivationPlan, dict[tuple[date, str], MealOccurrence]]:
    """Load the calendar and compute the activation plan plus occurrence lookup."""
    threshold = max(_as_utc(request_time), _start_of_day_ist(requested_start_date))
    pairs = _load_slots(mess, requested_start_date)
    plan = build_activation_plan([slot for slot, _ in pairs], threshold)
    occurrence_map = {
        (occurrence.meal_date, occurrence.meal_type.code): occurrence
        for _, occurrence in pairs
    }
    return plan, occurrence_map


def get_activation_plan(
    *,
    mess: Mess,
    request_time: datetime,
    requested_start_date: date,
) -> ActivationPlan:
    """Public wrapper returning the deterministic activation plan for a request."""
    plan, _ = _plan_with_occurrences(
        mess=mess,
        request_time=request_time,
        requested_start_date=requested_start_date,
    )
    return plan


def _get_active_mess_for_student(student: Student, on_date: date) -> Mess | None:
    """Return the student's active mess assignment on the given date, if any."""
    assignment = (
        StudentMessAssignment.objects.filter(
            student=student,
            effective_from__lte=on_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .filter(status="ACTIVE")
        .select_related("mess")
        .order_by("-effective_from")
        .first()
    )
    return assignment.mess if assignment else None


def _touch_student_sync(pause: MessPause) -> None:
    """
    Advance the change markers Managers poll so a pause state change is downloaded.
    The sync delta selector compares StudentMessAssignment.version, so bump it and
    advance the mess student cursor.
    """
    StudentMessAssignment.objects.filter(
        student_id=pause.student_id,
        mess_id=pause.mess_id,
    ).update(version=F("version") + 1)

    # Imported lazily to avoid a module-level cycle through sync selectors.
    from apps.sync.services import advance_change_cursor

    advance_change_cursor(f"mess:{pause.mess_id}:students")


def _save_pause(pause: MessPause, fields: Sequence[str]) -> None:
    """Persist selected fields and advance the optimistic-concurrency version."""
    pause.version = (pause.version or 0) + 1
    update_fields = list(dict.fromkeys([*fields, "version", "updated_at"]))
    pause.save(update_fields=update_fields)


@transaction.atomic
def request_pause(
    *,
    student: Student,
    mess: Mess,
    requested_start_date: date,
    requested_end_date: date,
    actor: User,
    correlation_id: str = "",
) -> MessPause:
    """
    Create a new mess pause request in SCHEDULED status [SPEC DBDD §7].

    Validations:
    - The start date is not in the past and the end date is not before the start.
    - The student has an ACTIVE assignment to the requested mess on the start date.
    - No other SCHEDULED or ACTIVE pause exists (database partial unique backs this).
    - At least four qualifying occurrences exist ahead.
    - The requested end date is on or after the computed effective start date.
    """
    if requested_start_date < clock.today():
        raise ValidationError(
            code="PAUSE_START_IN_PAST",
            message="Requested start date cannot be in the past.",
        )

    if requested_end_date < requested_start_date:
        raise ValidationError(
            code="INVALID_DATE_RANGE",
            message="Requested end date must be on or after requested start date.",
        )

    active_mess = _get_active_mess_for_student(student, requested_start_date)
    if not active_mess or active_mess.mess_id != mess.mess_id:
        raise ValidationError(
            code="NO_ACTIVE_ASSIGNMENT",
            message="Student has no active mess assignment to this mess on the requested start date.",
        )

    if MessPause.objects.filter(
        student=student,
        status__in=["SCHEDULED", "ACTIVE"],
    ).exists():
        raise ConflictError(
            code="DUPLICATE_PAUSE",
            message=(
                "Student already has a scheduled or active pause. "
                "Only one SCHEDULED or ACTIVE pause is allowed per student."
            ),
        )

    plan, occurrence_map = _plan_with_occurrences(
        mess=mess,
        request_time=clock.now(),
        requested_start_date=requested_start_date,
    )

    if requested_end_date < plan.effective_start_date:
        raise ValidationError(
            code="PAUSE_END_BEFORE_EFFECTIVE_START",
            message=(
                "Requested end date falls before the effective start date "
                f"({plan.effective_start_date.isoformat()}) produced by the three-slot "
                "activation delay. Choose a later end date."
            ),
        )

    try:
        pause = MessPause.objects.create(
            student=student,
            mess=mess,
            requested_start_date=requested_start_date,
            requested_end_date=requested_end_date,
            effective_start_date=plan.effective_start_date,
            effective_end_date=requested_end_date,
            activation_meal_date=plan.activation_meal_date,
            status="SCHEDULED",
            requested_at=clock.now(),
            cancellation_reason="",
        )
    except IntegrityError as exc:
        raise ConflictError(
            code="DUPLICATE_PAUSE",
            message="Student already has a scheduled or active pause.",
        ) from exc

    for sequence, slot in enumerate(plan.recorded_slots, start=1):
        occurrence = occurrence_map[(slot.meal_date, slot.meal_type_code)]
        MessPauseMealSlot.objects.create(
            pause=pause,
            meal_occurrence=occurrence,
            slot_sequence=sequence,
            qualifies_for_activation=slot.qualifies,
            slot_date=slot.meal_date,
            consumed_for_activation=False,
        )

    record_audit_event(
        event_type="PAUSE_SUBMITTED",
        actor_user=actor,
        entity_type="MessPause",
        entity_id=pause.pause_id,
        new_values={
            "student_id": student.student_id,
            "mess_id": mess.mess_id,
            "requested_start_date": str(requested_start_date),
            "requested_end_date": str(requested_end_date),
            "effective_start_date": str(plan.effective_start_date),
            "activation_meal_date": str(plan.activation_meal_date),
            "status": "SCHEDULED",
        },
        correlation_id=correlation_id,
    )

    _touch_student_sync(pause)
    return pause


@transaction.atomic
def cancel_pause(
    *,
    pause: MessPause,
    actor: User,
    reason: str = "",
    correlation_id: str = "",
) -> MessPause:
    """
    Cancel a SCHEDULED or ACTIVE mess pause [SPEC DBDD §7, DEC-23].

    The requested end date is immutable. The effective end date becomes the
    cancellation date. For an ACTIVE pause, only slots on that date that had already
    ended at the cancellation instant remain paused (see is_slot_paused).
    """
    if pause.status in ["CANCELLED", "COMPLETED"]:
        raise ConflictError(
            code="PAUSE_ALREADY_TERMINATED",
            message=f"Pause is already {pause.status.lower()} and cannot be cancelled.",
        )

    old_status = pause.status
    cancellation_reason = reason or CANCEL_REASON_STUDENT
    pause.status = "CANCELLED"
    pause.cancelled_at = clock.now()
    pause.cancellation_reason = cancellation_reason
    pause.effective_end_date = clock.today()

    _save_pause(
        pause,
        ["status", "cancelled_at", "cancellation_reason", "effective_end_date"],
    )

    record_audit_event(
        event_type="PAUSE_CANCELLED",
        actor_user=actor,
        entity_type="MessPause",
        entity_id=pause.pause_id,
        reason=cancellation_reason,
        old_values={"status": old_status},
        new_values={
            "status": "CANCELLED",
            "cancellation_reason": cancellation_reason,
            "effective_end_date": str(pause.effective_end_date),
        },
        correlation_id=correlation_id,
    )

    _touch_student_sync(pause)
    return pause


def _find_next_qualifying_occurrence(
    mess: Mess,
    *,
    after_date: date,
    after_sequence: int,
    exclude_ids: Iterable[int] = (),
) -> MealOccurrence | None:
    """Return the next SCHEDULED qualifying occurrence strictly after a slot."""
    queryset = (
        MealOccurrence.objects.filter(
            mess=mess,
            status="SCHEDULED",
            meal_type__code__in=QUALIFYING_MEAL_CODES,
            meal_date__gte=after_date,
        )
        .select_related("meal_type")
        .order_by("meal_date", "meal_type__sequence_no")
    )
    excluded = set(exclude_ids)
    if excluded:
        queryset = queryset.exclude(meal_occurrence_id__in=excluded)

    for occurrence in queryset:
        if (occurrence.meal_date, occurrence.meal_type.sequence_no) > (
            after_date,
            after_sequence,
        ):
            return occurrence
    return None


def _recompute_activation_dates(pause: MessPause) -> bool:
    """Recompute planned activation and effective start from the current slot rows."""
    rows = list(
        MessPauseMealSlot.objects.filter(
            pause=pause,
            qualifies_for_activation=True,
        )
        .select_related("meal_occurrence__meal_type")
        .order_by("slot_sequence")
    )
    if len(rows) < ACTIVATION_SLOT_COUNT:
        return False

    third = rows[ACTIVATION_SLOT_COUNT - 1]
    next_occurrence = _find_next_qualifying_occurrence(
        pause.mess,
        after_date=third.meal_occurrence.meal_date,
        after_sequence=third.meal_occurrence.meal_type.sequence_no,
        exclude_ids=[row.meal_occurrence_id for row in rows],
    )

    changed = False
    if pause.activation_meal_date != third.slot_date:
        pause.activation_meal_date = third.slot_date
        changed = True
    if next_occurrence and pause.effective_start_date != next_occurrence.meal_date:
        pause.effective_start_date = next_occurrence.meal_date
        changed = True
    return changed


def _replace_cancelled_counted_slots(pause: MessPause, now: datetime) -> bool:
    """
    Replace a counted occurrence cancelled before it could count with the next
    qualifying slot [DEC-06]. The cancelled row is retained for traceability with
    its qualifying flag cleared.

    ``now`` is accepted for symmetry with slot consumption, but an unconsumed
    cancelled row is always replaced: the scheduled job runs every 15 minutes, so a
    row still waiting here was cancelled while the pause was waiting.
    """
    changed = False
    processed: set[int] = set()

    while True:
        row = (
            MessPauseMealSlot.objects.filter(
                pause=pause,
                qualifies_for_activation=True,
                consumed_for_activation=False,
                meal_occurrence__status="CANCELLED",
            )
            .exclude(pause_slot_id__in=processed)
            .select_related("meal_occurrence__meal_type")
            .order_by("slot_sequence")
            .first()
        )
        if row is None:
            break

        processed.add(row.pause_slot_id)
        row.qualifies_for_activation = False
        row.save(update_fields=["qualifies_for_activation"])
        changed = True

        last_row = (
            MessPauseMealSlot.objects.filter(pause=pause)
            .select_related("meal_occurrence__meal_type")
            .order_by("-slot_sequence")
            .first()
        )
        if last_row is None:
            break

        used_ids = list(
            MessPauseMealSlot.objects.filter(pause=pause).values_list(
                "meal_occurrence_id", flat=True
            )
        )
        replacement = _find_next_qualifying_occurrence(
            pause.mess,
            after_date=last_row.meal_occurrence.meal_date,
            after_sequence=last_row.meal_occurrence.meal_type.sequence_no,
            exclude_ids=used_ids,
        )
        if replacement is None:
            continue

        MessPauseMealSlot.objects.create(
            pause=pause,
            meal_occurrence=replacement,
            slot_sequence=last_row.slot_sequence + 1,
            qualifies_for_activation=True,
            slot_date=replacement.meal_date,
            consumed_for_activation=False,
        )
        changed = True

    if changed:
        _recompute_activation_dates(pause)
    return changed


def _mark_slots_consumed(pause: MessPause, now: datetime) -> bool:
    """Mark every scheduled slot whose end time has passed as consumed."""
    changed = False
    rows = (
        MessPauseMealSlot.objects.filter(pause=pause, consumed_for_activation=False)
        .select_related("meal_occurrence__meal_type")
        .order_by("slot_sequence")
    )
    for row in rows:
        occurrence = row.meal_occurrence
        if occurrence_end_at(occurrence) > now:
            continue
        row.consumed_for_activation = True
        row.save(update_fields=["consumed_for_activation"])
        changed = True
    return changed


def _activate_if_ready(pause: MessPause, correlation_id: str = "") -> bool:
    """Transition SCHEDULED to ACTIVE once three qualifying slots have passed."""
    if pause.status != "SCHEDULED":
        return False

    qualifying_consumed = list(
        MessPauseMealSlot.objects.filter(
            pause=pause,
            qualifies_for_activation=True,
            consumed_for_activation=True,
        )
        .select_related("meal_occurrence__meal_type")
        .order_by("slot_sequence")
    )
    if len(qualifying_consumed) < ACTIVATION_SLOT_COUNT:
        return False

    third = qualifying_consumed[ACTIVATION_SLOT_COUNT - 1]
    next_occurrence = _find_next_qualifying_occurrence(
        pause.mess,
        after_date=third.meal_occurrence.meal_date,
        after_sequence=third.meal_occurrence.meal_type.sequence_no,
        exclude_ids=[
            row.meal_occurrence_id
            for row in MessPauseMealSlot.objects.filter(pause=pause)
        ],
    )

    pause.status = "ACTIVE"
    pause.activation_meal_date = third.slot_date
    if next_occurrence:
        pause.effective_start_date = next_occurrence.meal_date

    _save_pause(
        pause,
        ["status", "activation_meal_date", "effective_start_date"],
    )

    record_audit_event(
        event_type="PAUSE_ACTIVATED",
        actor_user=None,
        entity_type="MessPause",
        entity_id=pause.pause_id,
        old_values={"status": "SCHEDULED"},
        new_values={
            "status": "ACTIVE",
            "activation_meal_date": str(pause.activation_meal_date),
            "effective_start_date": str(pause.effective_start_date),
        },
        correlation_id=correlation_id,
    )

    _touch_student_sync(pause)
    return True


def _complete_if_due(pause: MessPause, now: datetime) -> bool:
    """Transition ACTIVE to COMPLETED after the effective end date has passed."""
    if pause.status != "ACTIVE":
        return False

    end_date = pause.effective_end_date or pause.requested_end_date
    if end_date is None or end_date >= clock.today():
        return False

    pause.status = "COMPLETED"
    pause.completed_at = now
    _save_pause(pause, ["status", "completed_at"])

    record_audit_event(
        event_type="PAUSE_COMPLETED",
        actor_user=None,
        entity_type="MessPause",
        entity_id=pause.pause_id,
        old_values={"status": "ACTIVE"},
        new_values={
            "status": "COMPLETED",
            "effective_end_date": str(end_date),
        },
    )

    _touch_student_sync(pause)
    return True


def advance_pause(pause: MessPause, now: datetime | None = None) -> bool:
    """
    Advance one pause through its lifecycle in the caller's transaction.
    Idempotent: running it again with no elapsed slot changes nothing.
    """
    now = now or clock.now()
    changed = False

    if pause.status == "SCHEDULED":
        replaced = _replace_cancelled_counted_slots(pause, now)
        consumed = _mark_slots_consumed(pause, now)
        changed = replaced or consumed

        if changed and pause.status == "SCHEDULED":
            _save_pause(pause, ["activation_meal_date", "effective_start_date"])

        if _activate_if_ready(pause):
            changed = True

    if pause.status == "ACTIVE" and _complete_if_due(pause, now):
        changed = True

    return changed


def advance_pauses(now: datetime | None = None) -> dict[str, int]:
    """
    Process every SCHEDULED and ACTIVE pause, each in its own transaction,
    under a row lock so overlapping job runs cannot double-transition a pause.
    """
    now = now or clock.now()
    counts = {
        "processed": 0,
        "changed": 0,
        "activated": 0,
        "completed": 0,
    }

    pause_ids = list(
        MessPause.objects.filter(status__in=["SCHEDULED", "ACTIVE"]).values_list(
            "pause_id", flat=True
        )
    )

    for pause_id in pause_ids:
        with transaction.atomic():
            pause = (
                MessPause.objects.select_for_update()
                .select_related("mess")
                .filter(pause_id=pause_id)
                .first()
            )
            if pause is None:
                continue

            previous_status = pause.status
            counts["processed"] += 1

            if advance_pause(pause, now):
                counts["changed"] += 1

            # A long time jump can activate and complete in the same run, so count
            # activation from the starting status rather than the final one.
            if previous_status == "SCHEDULED" and pause.status in (
                "ACTIVE",
                "COMPLETED",
            ):
                counts["activated"] += 1
            if pause.status == "COMPLETED" and previous_status != "COMPLETED":
                counts["completed"] += 1

    return counts


def activate_pause_after_three_slots(
    pause: MessPause,
    correlation_id: str = "",
) -> bool:
    """
    Evaluate a SCHEDULED pause for activation without marking slots consumed.
    Retained as the explicit domain operation used by tests and callers that have
    already advanced slot consumption.
    """
    return _activate_if_ready(pause, correlation_id=correlation_id)


def mark_meal_slot_consumed(meal_occurrence: MealOccurrence) -> None:
    """
    Mark one finished occurrence as consumed and advance any waiting pauses.
    The scheduled ``advance_pauses`` job performs this in bulk; this helper exists
    for callers that process occurrences individually.
    """
    if meal_occurrence.meal_type.code not in QUALIFYING_MEAL_CODES:
        return
    if occurrence_end_at(meal_occurrence) > clock.now():
        return

    slots = (
        MessPauseMealSlot.objects.filter(
            meal_occurrence=meal_occurrence,
            consumed_for_activation=False,
        )
        .select_related("pause")
        .order_by("slot_sequence")
    )
    for slot in slots:
        slot.consumed_for_activation = True
        slot.save(update_fields=["consumed_for_activation"])
        if slot.pause.status == "SCHEDULED":
            advance_pause(slot.pause)


def _pause_range(pause: MessPause) -> tuple[date, date]:
    """Return the effective (start, end) dates for a pause."""
    start = pause.effective_start_date or pause.requested_start_date
    end = pause.effective_end_date or pause.requested_end_date
    return start, end


def is_slot_paused(student: Student, occurrence: MealOccurrence) -> bool:
    """
    Shared predicate for billing, sync and reports [DEC-23].

    A slot is paused when the student had an effective pause covering its date.
    For a pause cancelled manually during ACTIVE, only slots that had already ended
    at the cancellation instant remain paused. For a meal that cancelled the pause
    (D23), the meal's own slot and every later slot are normal while earlier slots
    on the same date stay paused.
    """
    if occurrence.meal_type.code not in QUALIFYING_MEAL_CODES:
        return False

    slot_end = occurrence_end_at(occurrence)
    pauses = MessPause.objects.filter(
        student=student,
        mess_id=occurrence.mess_id,
        status__in=["ACTIVE", "COMPLETED", "CANCELLED"],
    ).order_by("-requested_at")

    for pause in pauses:
        start, end = _pause_range(pause)
        if start is None or end is None:
            continue
        if not (start <= occurrence.meal_date <= end):
            continue

        if pause.status in ("ACTIVE", "COMPLETED"):
            return True

        # A CANCELLED pause only applies if it had already become effective.
        if pause.cancelled_at is None:
            continue
        if pause.cancelled_at < _start_of_day_ist(start):
            continue

        if pause.cancellation_reason == CANCEL_REASON_MEAL_TAKEN:
            if slot_end < pause.cancelled_at:
                return True
        elif slot_end <= pause.cancelled_at:
            return True

    return False


def cancel_active_pause_on_meal(
    *,
    student: Student,
    occurrence: MealOccurrence,
    actor: User | None,
    transaction_id: Any = "",
    correlation_id: str = "",
) -> MessPause | None:
    """
    Owner change D23: a meal taken during an ACTIVE pause cancels the rest of the
    pause from that meal. Earlier slots on the same date remain paused and the meal
    itself is recorded and billed normally.

    The cutoff is the meal slot's end time, combined with the strict comparison in
    is_slot_paused, so the meal's own slot is normal while earlier slots are not.
    """
    active_pause = (
        MessPause.objects.select_for_update()
        .filter(
            student=student,
            mess_id=occurrence.mess_id,
            status="ACTIVE",
        )
        .order_by("-requested_at")
        .first()
    )
    if active_pause is None:
        return None

    start, end = _pause_range(active_pause)
    if start is None or end is None:
        return None
    if not (start <= occurrence.meal_date <= end):
        return None

    active_pause.status = "CANCELLED"
    active_pause.cancelled_at = occurrence_end_at(occurrence)
    active_pause.cancellation_reason = CANCEL_REASON_MEAL_TAKEN
    active_pause.effective_end_date = occurrence.meal_date
    _save_pause(
        active_pause,
        [
            "status",
            "cancelled_at",
            "cancellation_reason",
            "effective_end_date",
        ],
    )

    record_audit_event(
        event_type="PAUSE_CANCELLED",
        actor_user=actor,
        entity_type="MessPause",
        entity_id=active_pause.pause_id,
        reason=CANCEL_REASON_MEAL_TAKEN,
        old_values={"status": "ACTIVE"},
        new_values={
            "status": "CANCELLED",
            "cancellation_reason": CANCEL_REASON_MEAL_TAKEN,
            "effective_end_date": str(active_pause.effective_end_date),
            "meal_date": str(occurrence.meal_date),
            "meal_type": occurrence.meal_type.code,
        },
        metadata={"transaction_id": str(transaction_id)} if transaction_id else None,
        correlation_id=correlation_id,
    )

    _touch_student_sync(active_pause)
    return active_pause


def get_active_pause(student: Student) -> MessPause | None:
    """Return the student's currently ACTIVE pause, if any [SPEC DBDD §7]."""
    return (
        MessPause.objects.filter(student=student, status="ACTIVE")
        .select_related("mess")
        .first()
    )


def get_current_pause(student: Student) -> MessPause | None:
    """Return the student's SCHEDULED or ACTIVE pause, if any."""
    return (
        MessPause.objects.filter(
            student=student,
            status__in=["SCHEDULED", "ACTIVE"],
        )
        .select_related("mess")
        .order_by("-requested_at")
        .first()
    )


def get_pause_state(student: Student) -> dict[str, Any]:
    """
    Return the current pause state for a student [SPEC DBDD §7].

    Includes status, effective dates, activation date and qualifying slot progress.
    """
    pause = get_current_pause(student)
    if not pause:
        return {"has_pause": False, "status": "NONE"}

    slots = list(
        MessPauseMealSlot.objects.filter(pause=pause)
        .select_related("meal_occurrence__meal_type")
        .order_by("slot_sequence")
    )
    qualifying = [slot for slot in slots if slot.qualifies_for_activation]
    qualifying_consumed = [
        slot for slot in qualifying if slot.consumed_for_activation
    ]

    return {
        "has_pause": True,
        "pause_id": pause.pause_id,
        "status": pause.status,
        "mess_id": pause.mess_id,
        "mess_code": pause.mess.code,
        "requested_start_date": _iso(pause.requested_start_date),
        "requested_end_date": _iso(pause.requested_end_date),
        "effective_start_date": _iso(pause.effective_start_date),
        "effective_end_date": _iso(pause.effective_end_date),
        "activation_meal_date": _iso(pause.activation_meal_date),
        "requested_at": _iso(pause.requested_at),
        "qualifying_slots_total": len(qualifying),
        "qualifying_slots_consumed": len(qualifying_consumed),
        "slots_remaining": max(
            0, ACTIVATION_SLOT_COUNT - len(qualifying_consumed)
        ),
        "meal_slots": [
            {
                "pause_slot_id": slot.pause_slot_id,
                "slot_sequence": slot.slot_sequence,
                "meal_date": slot.slot_date,
                "meal_type_code": slot.meal_occurrence.meal_type.code,
                "qualifies_for_activation": slot.qualifies_for_activation,
                "consumed_for_activation": slot.consumed_for_activation,
            }
            for slot in slots
        ],
    }


def get_pauses_for_student(student: Student, limit: int = 50):
    """Return all pauses for a student, ordered by most recent first [SPEC DBDD §7]."""
    return (
        MessPause.objects.filter(student=student)
        .select_related("mess")
        .order_by("-requested_at")[:limit]
    )


def get_pauses_for_mess(mess: Mess, limit: int = 50):
    """Return all pauses for a mess, ordered by most recent first (reports)."""
    return (
        MessPause.objects.filter(mess=mess)
        .select_related("student")
        .order_by("-requested_at")[:limit]
    )
