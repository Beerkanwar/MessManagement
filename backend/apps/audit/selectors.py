"""
Read selectors for the append-only audit log [ImplementationGuide Phase 13].

The audit read API filters over the DBDD §15.2 access paths and pages with a
keyset cursor on ``(occurred_at DESC, audit_id DESC)`` so deep pages do not
degrade like OFFSET paging.
"""
from __future__ import annotations

import base64
import binascii
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.clock import IST_ZONE, clock
from apps.core.exceptions import ValidationError

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


def _ist_day_start(day: date) -> datetime:
    """Return midnight IST for ``day`` as an aware UTC-compatible datetime."""
    return datetime.combine(day, time.min, tzinfo=IST_ZONE)


def _ist_day_end_exclusive(day: date) -> datetime:
    """Return the first instant after ``day`` in IST."""
    return _ist_day_start(day + timedelta(days=1))


def encode_cursor(occurred_at: datetime, audit_id: int) -> str:
    """Encode the keyset position as an opaque URL-safe token."""
    raw = f"{occurred_at.isoformat()}|{audit_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode a cursor token, raising the standard validation error if invalid."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        occurred_at_raw, audit_id_raw = raw.rsplit("|", 1)
        occurred_at = datetime.fromisoformat(occurred_at_raw)
        audit_id = int(audit_id_raw)
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Invalid audit cursor token.",
        )
    if timezone.is_naive(occurred_at):
        occurred_at = timezone.make_aware(occurred_at, IST_ZONE)
    return occurred_at, audit_id


def parse_date_param(value: str, name: str) -> date:
    """Parse a YYYY-MM-DD query parameter with a stable error envelope."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"'{name}' must be an ISO date (YYYY-MM-DD).",
        )


def parse_page_size(value: str | None) -> int:
    """Parse and bound the caller's page size."""
    if value in (None, ""):
        return DEFAULT_PAGE_SIZE
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="'limit' must be an integer.",
        )
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"'limit' must be between 1 and {MAX_PAGE_SIZE}.",
        )
    return limit


def list_audit_events(
    *,
    actor_id: int | None = None,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    correlation_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[AuditLog], str | None, bool, int]:
    """
    Return ``(rows, next_cursor, has_more)`` for the filtered audit log.

    Ordering is newest-first. A row at the cursor position is excluded, so the
    next page never repeats an event even when several share the same instant.
    """
    queryset = AuditLog.objects.select_related("actor_user", "device_registration")

    if actor_id is not None:
        queryset = queryset.filter(actor_user_id=actor_id)
    if event_type:
        queryset = queryset.filter(event_type=event_type)
    if entity_type:
        queryset = queryset.filter(entity_type=entity_type)
    if entity_id:
        queryset = queryset.filter(entity_id=str(entity_id))
    if correlation_id:
        queryset = queryset.filter(correlation_id=correlation_id)

    if date_from and date_to and date_from > date_to:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="'from' must be on or before 'to'.",
        )
    if date_from:
        queryset = queryset.filter(occurred_at__gte=_ist_day_start(date_from))
    if date_to:
        queryset = queryset.filter(occurred_at__lt=_ist_day_end_exclusive(date_to))

    total = queryset.count()

    if cursor:
        cursor_time, cursor_id = decode_cursor(cursor)
        queryset = queryset.filter(
            Q(occurred_at__lt=cursor_time)
            | Q(occurred_at=cursor_time, audit_id__lt=cursor_id)
        )

    rows = list(queryset.order_by("-occurred_at", "-audit_id")[: limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        encode_cursor(rows[-1].occurred_at, rows[-1].audit_id)
        if has_more and rows
        else None
    )
    return rows, next_cursor, has_more, total


def audit_events_queryset():
    """Reusable queryset for callers that need their own filtering."""
    return AuditLog.objects.select_related("actor_user", "device_registration")


def current_ist_date() -> date:
    """Expose the injectable clock's IST date for view defaults/tests."""
    return clock.today()
