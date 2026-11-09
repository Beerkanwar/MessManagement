"""
Selectors for mess pause read queries [SPEC DBDD §7].

Business rules stay in ``apps.pause.services``; these functions exist so views and
later phases (billing, reports) read pause data through the same authorization-aware
surface rather than building ad-hoc queries.
"""
from apps.pause.models import MessPause, MessPauseMealSlot
from apps.pause.services import (
    get_active_pause,
    get_current_pause,
    get_pause_state,
    get_pauses_for_mess,
    get_pauses_for_student,
    is_slot_paused,
)

__all__ = [
    "get_active_pause",
    "get_current_pause",
    "get_pause_by_id",
    "get_pause_state",
    "get_pauses_for_mess",
    "get_pauses_for_student",
    "get_qualifying_slots",
    "get_consumed_slot_count",
    "is_slot_paused",
]


def get_pause_by_id(pause_id: int) -> MessPause | None:
    """Return a pause by its ID [SPEC DBDD §7]."""
    return (
        MessPause.objects.filter(pause_id=pause_id)
        .select_related("student", "mess")
        .first()
    )


def get_qualifying_slots(pause: MessPause):
    """Return all counted activation slots for a pause [DEC-06]."""
    return MessPauseMealSlot.objects.filter(
        pause=pause,
        qualifies_for_activation=True,
    ).order_by("slot_sequence")


def get_consumed_slot_count(pause: MessPause) -> int:
    """Return the count of consumed qualifying slots for a pause [DEC-06]."""
    return MessPauseMealSlot.objects.filter(
        pause=pause,
        qualifies_for_activation=True,
        consumed_for_activation=True,
    ).count()
