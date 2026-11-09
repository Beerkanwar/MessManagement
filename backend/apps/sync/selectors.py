"""
Selectors for synchronization delta changes and status queries [SPEC SDD §67, §68; DBDD §11].
"""
from datetime import timedelta
from typing import Any

from django.db.models import Q

from apps.attendance.models import MealConsumption
from apps.config.models import SystemSetting
from apps.core.clock import clock
from apps.hostel.models import Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, StudentSecret
from apps.mess.models import ExtraItem, ExtraPrice, MealRate, MealType
from apps.pause.models import MessPause
from apps.sync.models import ChangeCursor, SyncBatch, SyncConflict


def get_current_cursor(aggregate_type: str) -> int:
    """Returns the current monotonic version cursor for the given aggregate key."""
    cursor_obj = ChangeCursor.objects.filter(aggregate_type=aggregate_type).first()
    return cursor_obj.current_version if cursor_obj else 1


def calculate_authorization_state(
    device: DeviceRegistration,
    normal_hours: int = 24,
    grace_hours: int = 24,
) -> str:
    """
    Computes Manager authorization state [SPEC SDD §25, §129]:
    ACTIVE / OFFLINE_NORMAL / OFFLINE_GRACE / SYNC_REQUIRED / REVOKED.
    """
    if device.session_status == "REVOKED":
        return "REVOKED"

    now = clock.now()
    last_sync = device.last_active_at or device.registered_at
    if not last_sync:
        return "ACTIVE"

    elapsed = now - last_sync
    if elapsed <= timedelta(hours=normal_hours):
        return "ACTIVE"
    elif elapsed <= timedelta(hours=normal_hours + grace_hours):
        return "OFFLINE_GRACE"
    else:
        return "SYNC_REQUIRED"


def get_delta_students(mess_id: int, client_cursor: int = 0) -> list[dict[str, Any]]:
    """
    Returns students authorized for the given mess matching delta criteria [SPEC SDD §16, §27].
    Includes Student Name, Roll Number, Pause State, Secret Version, Assignment Version.
    """
    now = clock.now()
    today = clock.today()

    # Find active assignments for this mess
    assignments = (
        StudentMessAssignment.objects.filter(
            mess_id=mess_id,
            status="ACTIVE",
            effective_from__lte=today,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        .select_related("student", "hostel")
    )

    student_list = []
    for asm in assignments:
        student = asm.student
        # Skip if neither student nor assignment updated since client_cursor (if version filtering applies)
        # However, for baseline reliability, if client_cursor is 0 or version > cursor, include it:
        asm_version = getattr(asm, "version", 1)
        student_version = getattr(student, "version", 1)
        max_ver = max(asm_version, student_version)
        if client_cursor > 0 and max_ver <= client_cursor:
            continue

        # Active pause state
        active_pause = (
            MessPause.objects.filter(
                student=student,
                status__in=["SCHEDULED", "ACTIVE"],
            )
            .order_by("-requested_at")
            .first()
        )
        pause_state = active_pause.status if active_pause else "NONE"

        # Active secret
        active_sec = (
            StudentSecret.objects.filter(student=student, status="ACTIVE")
            .order_by("-secret_version")
            .first()
        )

        student_list.append({
            "student_id": student.student_id,
            "roll_number": student.roll_number,
            "display_name": student.user.full_name,
            "student_status": student.status,
            "hostel_id": asm.hostel_id,
            "mess_id": mess_id,
            "assignment_version": asm_version,
            "pause_state": pause_state,
            "secret_version": active_sec.secret_version if active_sec else 1,
            "secret_ciphertext": active_sec.encrypted_secret.decode("latin-1") if active_sec else "",
        })

    return student_list


def get_delta_configuration(mess_id: int, client_cursor: int = 0) -> dict[str, Any]:
    """
    Returns pricing, extras, and operational settings delta [SPEC SDD §67].
    """
    today = clock.today()

    # Active meal rate for mess
    active_rate = (
        MealRate.objects.filter(
            mess_id=mess_id,
            effective_from__lte=today,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        .order_by("-effective_from")
        .first()
    )

    # Active extras for hostels assigned to this mess
    hostel_ids = list(
        StudentMessAssignment.objects.filter(mess_id=mess_id, status="ACTIVE")
        .values_list("hostel_id", flat=True)
        .distinct()
    )

    extra_items = []
    if hostel_ids:
        items = ExtraItem.objects.filter(hostel_id__in=hostel_ids, status="ACTIVE")
        for item in items:
            price_obj = (
                ExtraPrice.objects.filter(
                    extra_item=item,
                    effective_from__lte=today,
                )
                .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
                .order_by("-effective_from")
                .first()
            )
            extra_items.append({
                "extra_item_id": item.extra_item_id,
                "hostel_id": item.hostel_id,
                "name": item.name,
                "current_price": str(price_obj.unit_price) if price_obj else "0.00",
                "status": item.status,
            })

    # Fixed meal types
    meal_types = list(
        MealType.objects.filter(is_active=True).values("meal_type_id", "code", "name", "sequence_no")
    )

    return {
        "meal_rate": str(active_rate.rate) if active_rate else "0.00",
        "extra_items": extra_items,
        "meal_types": meal_types,
    }


def get_sync_batches(mess_id: int | None = None, limit: int = 50):
    """Returns recent sync batches."""
    qs = SyncBatch.objects.select_related("device_registration", "user").order_by("-created_at")
    return qs[:limit]


def get_sync_conflicts(resolved: bool | None = None, limit: int = 50):
    """Returns sync conflicts filtered by resolution status."""
    qs = SyncConflict.objects.select_related("sync_transaction").order_by("-detected_at")
    if resolved is not None:
        if resolved:
            qs = qs.filter(resolved_at__isnull=False)
        else:
            qs = qs.filter(resolved_at__isnull=True)
    return qs[:limit]
