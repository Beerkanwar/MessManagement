"""
Selectors for synchronization delta changes and status queries
[SPEC SDD §67, §68; DBDD §11; ImplementationGuide Phase 8].

The download side is deliberately read-only and authorization-aware: every
selector below is scoped to the Manager's mess and only returns data the
Manager is allowed to cache.
"""
from datetime import date, timedelta
from typing import Any

from django.db.models import Q

from apps.attendance.models import ExtraTransaction, MealConsumption
from apps.config.models import ApplicationVersionPolicy
from apps.config.services import get_int_setting, get_str_setting
from apps.core.clock import clock
from apps.hostel.models import Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, StudentSecret
from apps.mess.models import (
    ExtraItem,
    ExtraPrice,
    MealOccurrence,
    MealRate,
    MealType,
    Mess,
    MessManagerAssignment,
)
from apps.pause.models import MessPause
from apps.pause.services import is_slot_paused
from apps.sync.models import ChangeCursor, SyncBatch, SyncConflict, SyncTransaction

# Bootstrap paging keeps a sync response around 500 students [Phase 8, build 6].
DEFAULT_STUDENT_PAGE_SIZE = 500


def get_current_cursor(aggregate_type: str) -> int:
    """Returns the current monotonic version cursor for the given aggregate key."""
    cursor_obj = ChangeCursor.objects.filter(aggregate_type=aggregate_type).first()
    return cursor_obj.current_version if cursor_obj else 0


def get_overlap_minutes() -> int:
    """Overlap window for late commits [Phase 8, build 6]."""
    return max(0, get_int_setting("sync.overlap_minutes", 2))


def calculate_authorization_state(
    device: DeviceRegistration,
    normal_hours: int | None = None,
    grace_hours: int | None = None,
) -> str:
    """
    Computes Manager authorization state [SPEC SDD §25, §129; D14]:
    ACTIVE / OFFLINE_GRACE / SYNC_REQUIRED / REVOKE_PENDING_SYNC / REVOKED.

    Offline windows are read from settings so the Manager app never hard-codes
    them [SPEC SRS §41].
    """
    if device.session_status == "REVOKED":
        return "REVOKED"
    if device.session_status == "REVOKE_PENDING_SYNC":
        return "REVOKE_PENDING_SYNC"

    if normal_hours is None:
        normal_hours = get_int_setting("offline.normal_hours", 24)
    if grace_hours is None:
        grace_hours = get_int_setting("offline.grace_hours", 24)

    now = clock.now()
    last_sync = device.last_active_at or device.registered_at
    if not last_sync:
        return "ACTIVE"

    elapsed = now - last_sync
    if elapsed <= timedelta(hours=normal_hours):
        return "ACTIVE"
    if elapsed <= timedelta(hours=normal_hours + grace_hours):
        return "OFFLINE_GRACE"
    return "SYNC_REQUIRED"


def get_offline_windows() -> dict[str, int]:
    """Return the configured offline normal and grace windows [SRS §41]."""
    return {
        "normal_hours": get_int_setting("offline.normal_hours", 24),
        "grace_hours": get_int_setting("offline.grace_hours", 24),
    }


def _active_assignment_queryset(mess_id: int, on_date: date):
    return (
        StudentMessAssignment.objects.filter(
            mess_id=mess_id,
            status="ACTIVE",
            effective_from__lte=on_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .select_related("student__user", "hostel")
    )


def _student_payload(assignment: StudentMessAssignment, mess_id: int) -> dict[str, Any]:
    """Render one LocalStudent-compatible upsert [DBDD §14; SRS §13]."""
    student = assignment.student
    pause = (
        MessPause.objects.filter(
            student=student,
            status__in=["SCHEDULED", "ACTIVE"],
        )
        .order_by("-requested_at")
        .first()
    )
    secret = (
        StudentSecret.objects.filter(student=student, status="ACTIVE")
        .order_by("-secret_version")
        .first()
    )
    secret_ciphertext = ""
    if secret is not None and secret.encrypted_secret is not None:
        raw = secret.encrypted_secret
        secret_ciphertext = (
            bytes(raw).decode("latin-1") if not isinstance(raw, str) else raw
        )

    return {
        "student_id": student.student_id,
        "roll_number": student.roll_number,
        "display_name": student.user.full_name,
        "student_status": student.status,
        "hostel_id": assignment.hostel_id,
        "mess_id": mess_id,
        "assignment_version": getattr(assignment, "version", 1),
        "change_version": max(
            getattr(assignment, "change_version", 0) or 0,
            getattr(student, "change_version", 0) or 0,
        ),
        "pause_state": pause.status if pause else "NONE",
        "secret_version": secret.secret_version if secret else 1,
        "secret_ciphertext": secret_ciphertext,
    }


def _overlap_cutoff(cursor_issued_at=None):
    return (cursor_issued_at or clock.now()) - timedelta(
        minutes=get_overlap_minutes()
    )


def _assignment_removals(mess_id: int, client_cursor: int, overlap_cutoff):
    """
    Assignments of this mess that ended after the client's cursor.

    ``change_version`` catches ordinary endings; the overlap window catches rows
    whose version was obtained before, but committed after, the last cursor.
    """
    query = StudentMessAssignment.objects.filter(mess_id=mess_id).exclude(
        status="ACTIVE"
    )
    if client_cursor > 0:
        query = query.filter(
            Q(change_version__gt=client_cursor)
            | Q(updated_at__gte=overlap_cutoff)
        )
    else:
        query = query.filter(updated_at__gte=overlap_cutoff)
    return list(query.values("student_id", "status"))


def _student_inactive_removals(
    mess_id: int, client_cursor: int, overlap_cutoff
):
    """Students with any assignment to this mess who have been deactivated."""
    student_ids = StudentMessAssignment.objects.filter(mess_id=mess_id).values(
        "student_id"
    )
    query = Student.objects.filter(student_id__in=student_ids, status="INACTIVE")
    if client_cursor > 0:
        query = query.filter(
            Q(change_version__gt=client_cursor)
            | Q(updated_at__gte=overlap_cutoff)
        )
    else:
        query = query.filter(updated_at__gte=overlap_cutoff)
    return list(query.values_list("student_id", flat=True))


def _secret_retired_removals(
    mess_id: int, client_cursor: int, overlap_cutoff
):
    """
    Secrets retired after the client's cursor when the student has no active
    replacement; the Manager must drop the cached secret.
    """
    student_ids = StudentMessAssignment.objects.filter(mess_id=mess_id).values(
        "student_id"
    )
    retained = StudentSecret.objects.filter(
        student_id__in=student_ids,
        status="RETIRED",
    )
    if client_cursor > 0:
        retained = retained.filter(
            Q(change_version__gt=client_cursor)
            | Q(updated_at__gte=overlap_cutoff)
        )
    else:
        retained = retained.filter(updated_at__gte=overlap_cutoff)

    retired_students = set(retained.values_list("student_id", flat=True))
    if not retired_students:
        return []
    active_students = set(
        StudentSecret.objects.filter(
            student_id__in=retired_students, status="ACTIVE"
        ).values_list("student_id", flat=True)
    )
    return list(retired_students - active_students)


def get_student_delta(
    mess_id: int,
    client_cursor: int = 0,
    *,
    cursor_issued_at=None,
    page_token: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    """
    Return authorized student upserts plus removals for this mess [Phase 8, build 6-7].

    ``page_token`` is the last student id of the previous page; it lets a first
    (bootstrap) call walk the roster in bounded pages until ``has_more`` is false.
    Delta calls include rows touched in the overlap window before the cursor time.
    """
    today = clock.today()
    if page_size is None:
        page_size = get_int_setting(
            "sync.student_page_size", DEFAULT_STUDENT_PAGE_SIZE
        )
    overlap_cutoff = _overlap_cutoff(cursor_issued_at)

    assignments = _active_assignment_queryset(mess_id, today).order_by("student_id")
    if page_token:
        assignments = assignments.filter(student_id__gt=page_token)

    # Bootstrap returns the full roster; a delta narrows by change_version or overlap.
    if client_cursor > 0:
        recent_pause_students = MessPause.objects.filter(
            mess_id=mess_id,
            updated_at__gte=overlap_cutoff,
        ).values_list("student_id", flat=True)
        recent_secret_students = StudentSecret.objects.filter(
            student_id__in=StudentMessAssignment.objects.filter(
                mess_id=mess_id
            ).values("student_id"),
            updated_at__gte=overlap_cutoff,
        ).values_list("student_id", flat=True)
        assignments = assignments.filter(
            Q(change_version__gt=client_cursor)
            | Q(student__change_version__gt=client_cursor)
            | Q(updated_at__gte=overlap_cutoff)
            | Q(student__updated_at__gte=overlap_cutoff)
            | Q(student_id__in=recent_pause_students)
            | Q(student_id__in=recent_secret_students)
        )

    page = list(assignments[: page_size + 1])
    has_more = len(page) > page_size
    page = page[:page_size]
    next_page_token = page[-1].student_id if has_more and page else None

    upserts = [_student_payload(assignment, mess_id) for assignment in page]

    removals: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    def _add_removal(student_id: int, reason: str) -> None:
        key = (student_id, reason)
        if key in seen:
            return
        seen.add(key)
        removals.append({"student_id": student_id, "reason": reason})

    for row in _assignment_removals(mess_id, client_cursor, overlap_cutoff):
        reason = (
            "ASSIGNMENT_ENDED"
            if row["status"] == "ENDED"
            else "ASSIGNMENT_INACTIVE"
        )
        _add_removal(row["student_id"], reason)

    for student_id in _student_inactive_removals(
        mess_id, client_cursor, overlap_cutoff
    ):
        _add_removal(student_id, "STUDENT_INACTIVE")

    for student_id in _secret_retired_removals(
        mess_id, client_cursor, overlap_cutoff
    ):
        _add_removal(student_id, "SECRET_RETIRED")

    return {
        "upserts": upserts,
        "removals": removals,
        "has_more": has_more,
        "next_page_token": next_page_token,
    }


def get_delta_students(mess_id: int, client_cursor: int = 0) -> list[dict[str, Any]]:
    """Compatibility wrapper returning student upserts only."""
    return get_student_delta(mess_id, client_cursor)["upserts"]


def get_delta_configuration(mess_id: int, client_cursor: int = 0) -> dict[str, Any]:
    """
    Returns pricing, extras, occurrences, mess and operational settings delta
    [SPEC SDD §67; Phase 8, build 6].
    """
    today = clock.today()

    mess = (
        Mess.objects.filter(mess_id=mess_id)
        .values("mess_id", "code", "name")
        .first()
    )

    active_rate = (
        MealRate.objects.filter(mess_id=mess_id, effective_from__lte=today)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        .order_by("-effective_from")
        .first()
    )

    hostel_ids = list(
        StudentMessAssignment.objects.filter(mess_id=mess_id, status="ACTIVE")
        .values_list("hostel_id", flat=True)
        .distinct()
    )

    extra_items = []
    if hostel_ids:
        for item in ExtraItem.objects.filter(
            hostel_id__in=hostel_ids, status="ACTIVE"
        ):
            price_obj = (
                ExtraPrice.objects.filter(
                    extra_item=item, effective_from__lte=today
                )
                .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
                .order_by("-effective_from")
                .first()
            )
            extra_items.append(
                {
                    "extra_item_id": item.extra_item_id,
                    "hostel_id": item.hostel_id,
                    "name": item.name,
                    "current_price": (
                        str(price_obj.unit_price) if price_obj else "0.00"
                    ),
                    "status": item.status,
                }
            )

    meal_types = list(
        MealType.objects.filter(is_active=True).values(
            "meal_type_id", "code", "name", "sequence_no"
        )
    )

    horizon_days = get_int_setting("meal.occurrence_horizon_days", 35)
    horizon_end = today + timedelta(days=horizon_days)
    occurrences = list(
        MealOccurrence.objects.filter(
            mess_id=mess_id,
            meal_date__gte=today,
            meal_date__lte=horizon_end,
        )
        .select_related("meal_type")
        .order_by("meal_date", "meal_type__sequence_no")
        .values(
            "meal_occurrence_id",
            "meal_date",
            "status",
            "meal_type__code",
            "meal_type__name",
        )
    )

    system_settings = {
        "offline.normal_hours": get_int_setting("offline.normal_hours", 24),
        "offline.grace_hours": get_int_setting("offline.grace_hours", 24),
        "meal.rollover_time": get_str_setting("meal.rollover_time", "03:00"),
        "sync.batch_max_transactions": get_int_setting(
            "sync.batch_max_transactions", 500
        ),
        "meal.BREAKFAST.end_time": get_str_setting(
            "meal.BREAKFAST.end_time", "10:00"
        ),
        "meal.LUNCH.end_time": get_str_setting("meal.LUNCH.end_time", "14:30"),
        "meal.EVENING_SNACKS.end_time": get_str_setting(
            "meal.EVENING_SNACKS.end_time", "18:30"
        ),
        "meal.DINNER.end_time": get_str_setting(
            "meal.DINNER.end_time", "22:00"
        ),
    }

    version_policies = list(
        ApplicationVersionPolicy.objects.all().values(
            "platform", "app_version", "status", "force_update_message"
        )
    )

    return {
        "mess": mess,
        "meal_rate": str(active_rate.rate) if active_rate else "0.00",
        "meal_rates": (
            [
                {
                    "effective_from": str(active_rate.effective_from),
                    "rate": str(active_rate.rate),
                }
            ]
            if active_rate
            else []
        ),
        "extra_items": extra_items,
        "meal_types": meal_types,
        "meal_occurrences": occurrences,
        "system_settings": system_settings,
        "version_policies": version_policies,
    }


def get_attendance_changes(
    mess_id: int,
    client_cursor: int = 0,
    days: int | None = None,
) -> dict[str, Any]:
    """
    Effective meals and extras of the last few days for the consumed set
    [Phase 8 response contract; Phase 9 shared pause predicate].
    """
    if days is None:
        days = get_int_setting("sync.attendance_window_days", 3)

    today = clock.today()
    since = today - timedelta(days=days)

    meals = []
    meal_rows = (
        MealConsumption.objects.filter(mess_id=mess_id, meal_date__gte=since)
        .select_related("student", "meal_type", "meal_occurrence__meal_type")
        .order_by("-meal_date", "-accepted_at")
    )
    for meal in meal_rows:
        occurrence = meal.meal_occurrence
        paused = False
        if occurrence is not None:
            paused = is_slot_paused(meal.student, occurrence)
        meals.append(
            {
                "meal_consumption_id": meal.meal_consumption_id,
                "student_id": meal.student_id,
                "meal_date": meal.meal_date,
                "meal_type": meal.meal_type.code,
                "price_at_transaction": str(meal.price_at_transaction),
                "source": meal.source,
                "sync_status": meal.sync_status,
                "transaction_id": (
                    str(meal.transaction_id) if meal.transaction_id else None
                ),
                "is_paused": paused,
            }
        )

    extras = list(
        ExtraTransaction.objects.filter(
            mess_id=mess_id,
            transaction_timestamp__date__gte=since,
        )
        .select_related("student", "extra_item")
        .order_by("-transaction_timestamp")
        .values(
            "extra_transaction_id",
            "student_id",
            "extra_item_id",
            "quantity",
            "unit_price_at_transaction",
            "total_amount",
            "transaction_timestamp",
            "transaction_id",
        )
    )

    return {"meals": meals, "extras": extras}


def get_resolved_results(device: DeviceRegistration) -> list[dict[str, Any]]:
    """
    Outcomes for transactions that were CONFLICT and have since been resolved
    [DEC-17; Phase 8, build 5]. The Manager applies them on the next sync.
    """
    conflicts = (
        SyncConflict.objects.filter(
            sync_transaction__sync_batch__device_registration=device,
            resolved_at__isnull=False,
        )
        .select_related("sync_transaction")
        .order_by("-resolved_at")[:100]
    )
    results = []
    for conflict in conflicts:
        txn = conflict.sync_transaction
        results.append(
            {
                "transaction_id": str(txn.transaction_id),
                "status": (
                    "SYNCHRONIZED"
                    if conflict.resolution == "ACCEPTED"
                    else "REJECTED"
                ),
                "conflict_type": conflict.conflict_type,
                "resolution": conflict.resolution,
                "resolution_notes": conflict.resolution_notes,
                "resolved_at": conflict.resolved_at,
                "entity_id": txn.entity_id,
            }
        )
    return results


def get_sync_batches(device: DeviceRegistration | None = None, limit: int = 50):
    """Returns recent sync batches, optionally scoped to one device."""
    qs = SyncBatch.objects.select_related(
        "device_registration", "user"
    ).order_by("-created_at")
    if device is not None:
        qs = qs.filter(device_registration=device)
    return qs[:limit]


def get_sync_transaction(transaction_id):
    """Look up one sync transaction by its client transaction id."""
    return (
        SyncTransaction.objects.select_related(
            "sync_batch", "sync_batch__device_registration"
        )
        .filter(transaction_id=transaction_id)
        .first()
    )


def get_sync_transactions(
    batch_id=None,
    transaction_id=None,
    device: DeviceRegistration | None = None,
    limit: int = 50,
):
    """Returns recent sync transactions for the admin Synchronization screen."""
    qs = SyncTransaction.objects.select_related(
        "sync_batch", "sync_batch__device_registration"
    ).order_by("-received_at")
    if batch_id is not None:
        qs = qs.filter(sync_batch__batch_id=batch_id)
    if transaction_id is not None:
        qs = qs.filter(transaction_id=transaction_id)
    if device is not None:
        qs = qs.filter(sync_batch__device_registration=device)
    return qs[:limit]


def get_sync_conflicts(resolved: bool | None = None, limit: int = 50):
    """Returns sync conflicts filtered by resolution status."""
    qs = SyncConflict.objects.select_related(
        "sync_transaction", "sync_transaction__sync_batch"
    ).order_by("-detected_at")
    if resolved is not None:
        if resolved:
            qs = qs.filter(resolved_at__isnull=False)
        else:
            qs = qs.filter(resolved_at__isnull=True)
    return qs[:limit]


def get_sync_conflict(conflict_id: int) -> SyncConflict | None:
    """Return one conflict for the admin detail view."""
    return (
        SyncConflict.objects.select_related(
            "sync_transaction", "sync_transaction__sync_batch"
        )
        .filter(conflict_id=conflict_id)
        .first()
    )


def get_device_last_sync(mess_id: int | None = None):
    """Return per-device last sync timestamps for the Devices screen."""
    qs = DeviceRegistration.objects.select_related("user").order_by(
        "-last_active_at"
    )
    if mess_id is not None:
        user_ids = list(
            MessManagerAssignment.objects.filter(
                mess_id=mess_id, is_active=True
            ).values_list("user_id", flat=True)
        )
        qs = qs.filter(user_id__in=user_ids)
    return qs[:100]
