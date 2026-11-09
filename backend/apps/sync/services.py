"""
Sync services implementing the Phase 8 upload/download contract
[SPEC SDD §52, §56, §67, §68; DBDD §11; SRS §26, §27, §41;
ImplementationGuide Phase 8].

Responsibilities:
- Gatekeeping (token device binding, Manager role/mess, version policy, batch limit,
  per-device throttle) with ``SYNC_FAILURE`` audits.
- Idempotent batch envelope keyed by the client's batch id; completed batches replay
  their stored per-item results and an IN_PROGRESS batch resumes where it stopped.
- Per-transaction savepoints and ``RETRYABLE_ERROR`` for unexpected failures.
- Conflict persistence, ``SYNC_CONFLICT`` audits and DEC-17 resolution.
- Opaque change-version cursor, overlap window, paged bootstrap download,
  data minimization, authorization state and D14 revocation finalization.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone as dt_timezone
import uuid
from typing import Any

import structlog
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import Throttled

from apps.attendance.constants import (
    WAIVE_ASSIGNMENT,
    WAIVE_MEAL_CANCELLED,
    WAIVE_SCOPE,
)
from apps.audit.services import record_audit_event
from apps.config.models import ApplicationVersionPolicy
from apps.config.services import get_int_setting
from apps.core.clock import clock
from apps.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from apps.identity.models import DeviceRegistration, RefreshToken, User
from apps.identity.selectors import get_user_role
from apps.mess.models import MessManagerAssignment
from apps.sync.models import SyncBatch, SyncConflict, SyncTransaction
from apps.sync.selectors import (
    calculate_authorization_state,
    get_attendance_changes,
    get_delta_configuration,
    get_offline_windows,
    get_resolved_results,
    get_student_delta,
)

logger = structlog.get_logger(__name__)

ENTITY_MEAL = "MEAL_CONSUMPTION"
ENTITY_EXTRA = "EXTRA_TRANSACTION"
_MEAL_ALIASES = {"MEAL", "MEAL_CONSUMPTION"}
_EXTRA_ALIASES = {"EXTRA", "EXTRA_TRANSACTION"}

# Domain result code -> persisted conflict type [Phase 8, build 5].
CONFLICT_TYPE_BY_CODE = {
    "ASSIGNMENT_MISMATCH": "ASSIGNMENT_CHANGED",
    "NO_ASSIGNMENT_ON_DATE": "ASSIGNMENT_CHANGED",
    "MEAL_CANCELLED": "MEAL_CANCELLED",
    "BILLING_PERIOD_LOCKED": "LOCKED_PERIOD_EXTRA",
    "MESS_SCOPE_MISMATCH": "UNAUTHORIZED_SCOPE",
}

# Only the check that caused the conflict is waived on ACCEPTED [DEC-17].
WAIVER_BY_CONFLICT_TYPE = {
    "ASSIGNMENT_CHANGED": {WAIVE_ASSIGNMENT},
    "MEAL_CANCELLED": {WAIVE_MEAL_CANCELLED},
    "UNAUTHORIZED_SCOPE": {WAIVE_SCOPE},
}

LOCKED_CONFLICT_TYPES = {
    "LOCKED_PERIOD_EXTRA",
    # Legacy persisted rows used the raw result code as their type.
    "BILLING_PERIOD_LOCKED",
}


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------

def _next_change_version() -> int:
    """Reserve one value from the shared change-version sequence."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('change_version_seq')")
        row = cursor.fetchone()
        return int(row[0])


def advance_change_cursor(cursor_key: str) -> int:
    """
    Atomically reserve a change version and raise the aggregate's cursor to it.

    ``ChangeCursor`` stores the highest version issued per aggregate; the value
    returned never regresses even if two writers reserve concurrently.
    """
    version = _next_change_version()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sync_change_cursor (aggregate_type, current_version, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (aggregate_type)
            DO UPDATE SET
                current_version = GREATEST(
                    sync_change_cursor.current_version,
                    EXCLUDED.current_version
                ),
                updated_at = NOW()
            RETURNING current_version;
            """,
            [cursor_key, version],
        )
        row = cursor.fetchone()
        return int(row[0]) if row else version


def issue_change_cursor(mess_id: int) -> int:
    """Issue the opaque cursor returned to a Manager for this mess [Phase 8]."""
    return advance_change_cursor(f"mess:{mess_id}")


# ---------------------------------------------------------------------------
# Gatekeeping [Phase 8, build 1]
# ---------------------------------------------------------------------------

def _audit_sync_failure(
    *,
    user: User | None,
    device: DeviceRegistration | None,
    reason: str,
    correlation_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    safe_metadata = {
        "stage": "sync_upload",
        **(metadata or {}),
    }
    record_audit_event(
        event_type="SYNC_FAILURE",
        actor_user=user,
        device_registration=device,
        entity_type="SyncBatch",
        entity_id="",
        reason=reason,
        metadata=safe_metadata,
        correlation_id=correlation_id,
    )


def _audit_failure_and_raise(
    *,
    exc: Exception,
    user: User | None,
    device: DeviceRegistration | None,
    reason: str,
    correlation_id: str,
    metadata: dict[str, Any] | None = None,
):
    _audit_sync_failure(
        user=user,
        device=device,
        reason=reason,
        correlation_id=correlation_id,
        metadata=metadata,
    )
    raise exc


def _resolve_device(
    user: User, data: dict[str, Any], device: DeviceRegistration | None
) -> DeviceRegistration | None:
    if device is not None:
        return device
    body_device_id = str(data.get("device_id") or "")
    return DeviceRegistration.objects.filter(
        user=user, device_id=body_device_id
    ).first()


def _check_throttle(
    device: DeviceRegistration,
    user: User,
    correlation_id: str,
) -> None:
    """Per-device sync call limit, default six per minute [Phase 8, build 10]."""
    limit = max(1, get_int_setting("sync.rate_limit_per_minute", 6))
    window = int(clock.now().timestamp() // 60)
    key = f"sync:throttle:{device.device_registration_id}:{window}"
    current = cache.get(key, 0)
    if current >= limit:
        _audit_failure_and_raise(
            exc=Throttled(
                wait=60, detail="Sync call limit exceeded for this device."
            ),
            user=user,
            device=device,
            reason="Sync call limit exceeded for this device.",
            correlation_id=correlation_id,
            metadata={"limit_per_minute": limit},
        )
    cache.set(key, current + 1, timeout=120)


def _gatekeep(
    *,
    user: User,
    data: dict[str, Any],
    device: DeviceRegistration,
    correlation_id: str,
) -> tuple[int, MessManagerAssignment]:
    """
    Validate every precondition before doing any sync work.

    Returns the Manager's active mess id and assignment.
    """
    body_device_id = str(data.get("device_id") or "")
    if device is None or device.device_id != body_device_id:
        _audit_failure_and_raise(
            exc=PermissionDeniedError(
                "The authenticated device does not match the request device id.",
                code="DEVICE_MISMATCH",
            ),
            user=user,
            device=device,
            reason="Request device id does not match the authenticated device.",
            correlation_id=correlation_id,
        )

    if device.session_status not in ("ACTIVE", "REVOKE_PENDING_SYNC"):
        _audit_failure_and_raise(
            exc=PermissionDeniedError(
                "Device registration is not allowed to synchronize.",
                code="DEVICE_NOT_ACTIVE",
            ),
            user=user,
            device=device,
            reason=f"Device session is {device.session_status}.",
            correlation_id=correlation_id,
        )

    role = get_user_role(user)
    if role != "MESS_MANAGER":
        _audit_failure_and_raise(
            exc=PermissionDeniedError(
                "Only Mess Managers may upload sync batches.",
                code="UNAUTHORIZED_ROLE",
            ),
            user=user,
            device=device,
            reason="Caller is not a Mess Manager.",
            correlation_id=correlation_id,
        )

    assignment = (
        MessManagerAssignment.objects.filter(user=user, is_active=True)
        .select_related("mess")
        .first()
    )
    if assignment is None:
        _audit_failure_and_raise(
            exc=PermissionDeniedError(
                "Mess Manager has no active assigned mess.",
                code="NO_ACTIVE_MESS_ASSIGNMENT",
            ),
            user=user,
            device=device,
            reason="Mess Manager has no active assignment.",
            correlation_id=correlation_id,
        )

    client_version = data.get("client_version") or "1.0.0"
    platform = device.platform or "ANDROID"
    policy = ApplicationVersionPolicy.objects.filter(
        platform=platform, app_version=client_version
    ).first()
    if policy and policy.status == "BLOCKED":
        _audit_failure_and_raise(
            exc=PermissionDeniedError(
                f"Client application version {client_version} on {platform} is "
                "blocked from synchronizing.",
                code="APP_VERSION_BLOCKED",
            ),
            user=user,
            device=device,
            reason="Client application version is blocked.",
            correlation_id=correlation_id,
            metadata={"platform": platform, "client_version": client_version},
        )

    max_batch_size = max(
        1, get_int_setting("sync.batch_max_transactions", 500)
    )
    transactions_data = data.get("transactions") or []
    if len(transactions_data) > max_batch_size:
        _audit_failure_and_raise(
            exc=ValidationError(
                f"Batch transaction count ({len(transactions_data)}) exceeds "
                f"the maximum allowed ({max_batch_size}).",
                code="BATCH_LIMIT_EXCEEDED",
            ),
            user=user,
            device=device,
            reason="Sync batch exceeds the configured transaction limit.",
            correlation_id=correlation_id,
            metadata={
                "transaction_count": len(transactions_data),
                "max_batch_size": max_batch_size,
            },
        )

    _check_throttle(device, user, correlation_id)
    return assignment.mess_id, assignment


# ---------------------------------------------------------------------------
# Per-transaction processing [Phase 8, build 3-4]
# ---------------------------------------------------------------------------

def _coerce_uuid(value) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _coerce_datetime(value, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            result = fallback or clock.now()
    if result.tzinfo is None:
        result = result.replace(tzinfo=dt_timezone.utc)
    return result


def _sort_key(item: dict[str, Any]):
    return _coerce_datetime(item.get("client_created_at"))


def _result(
    transaction_id,
    status: str,
    code: str = "",
    message: str = "",
    entity_id: str = "",
) -> dict[str, Any]:
    return {
        "transaction_id": transaction_id,
        "status": status,
        "result_code": code,
        "result_message": message,
        "entity_id": entity_id,
    }


def _result_from_transaction(st: SyncTransaction) -> dict[str, Any]:
    return _result(
        st.transaction_id,
        st.processing_status,
        st.result_code or "",
        st.result_message or "",
        st.entity_id or "",
    )


def _normalise_entity_type(raw: Any) -> str | None:
    value = str(raw or "").upper()
    if value in _MEAL_ALIASES:
        return ENTITY_MEAL
    if value in _EXTRA_ALIASES:
        return ENTITY_EXTRA
    return None


def _payload_mess_id(payload: dict[str, Any], default_mess_id: int) -> int | None:
    raw = payload.get("mess_id")
    if raw in (None, ""):
        return default_mess_id
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _apply_meal(
    *,
    user: User,
    device: DeviceRegistration,
    mess_id: int,
    payload: dict[str, Any],
    transaction_id: uuid.UUID,
    client_created_at: datetime,
    correlation_id: str,
    waive_checks: set[str] | None = None,
    source: str = "QR",
):
    # Imported lazily: attendance.services -> mess.services -> sync.services
    # would otherwise form an import cycle at module load time.
    from apps.attendance.services import record_meal

    return record_meal(
        transaction_id=transaction_id,
        student=payload.get("student_id"),
        meal_type=payload.get("meal_type"),
        meal_date=payload.get("meal_date"),
        mess=mess_id,
        recorded_by_user=user,
        roll_number_snapshot=payload.get("roll_number_snapshot", ""),
        transaction_timestamp=payload.get("transaction_timestamp")
        or client_created_at,
        verification_method=payload.get(
            "verification_method", "QR_HMAC_SHA256"
        ),
        verification_result=payload.get("verification_result", "SUCCESS"),
        device_registration=device,
        source=source,
        correlation_id=correlation_id,
        waive_checks=waive_checks,
    )


def _apply_extra(
    *,
    user: User,
    device: DeviceRegistration,
    mess_id: int,
    payload: dict[str, Any],
    transaction_id: uuid.UUID,
    client_created_at: datetime,
    correlation_id: str,
    waive_checks: set[str] | None = None,
    source: str = "SCAN_CONFIRMATION",
):
    # Imported lazily: attendance.services -> mess.services -> sync.services
    # would otherwise form an import cycle at module load time.
    from apps.attendance.services import record_extra

    return record_extra(
        transaction_id=transaction_id,
        student=payload.get("student_id"),
        mess=mess_id,
        extra_item=payload.get("extra_item_id"),
        quantity=payload.get("quantity", 1),
        recorded_by_user=user,
        transaction_timestamp=payload.get("transaction_timestamp")
        or client_created_at,
        device_registration=device,
        source=source,
        correlation_id=correlation_id,
        waive_checks=waive_checks,
    )


def _apply_transaction(
    *,
    user: User,
    device: DeviceRegistration,
    mess_id: int,
    entity_type: str,
    payload: dict[str, Any],
    transaction_id: uuid.UUID,
    client_created_at: datetime,
    correlation_id: str,
    waive_checks: set[str] | None = None,
    source: str = "QR",
):
    """Run the Phase 7 command for one normalized transaction."""
    payload_mess_id = _payload_mess_id(payload, mess_id)
    if payload_mess_id is None or payload_mess_id != mess_id:
        # Manager reassigned while offline: old-mess work is a scope conflict.
        return _result(
            transaction_id,
            "CONFLICT",
            "MESS_SCOPE_MISMATCH",
            "Transaction mess is not the Manager's current mess [SRS §27].",
        )

    if entity_type == ENTITY_MEAL:
        return _apply_meal(
            user=user,
            device=device,
            mess_id=mess_id,
            payload=payload,
            transaction_id=transaction_id,
            client_created_at=client_created_at,
            correlation_id=correlation_id,
            waive_checks=waive_checks,
            source=source,
        )

    return _apply_extra(
        user=user,
        device=device,
        mess_id=mess_id,
        payload=payload,
        transaction_id=transaction_id,
        client_created_at=client_created_at,
        correlation_id=correlation_id,
        waive_checks=waive_checks,
        source=(
            "SYNC_RESOLUTION" if source == "SYNC_RESOLUTION" else "SCAN_CONFIRMATION"
        ),
    )


def _persist_outcome(
    *,
    batch: SyncBatch,
    transaction_id: uuid.UUID,
    entity_type: str,
    entity_id: str,
    client_created_at: datetime,
    status: str,
    code: str,
    message: str,
    payload: dict[str, Any],
    user: User,
    device: DeviceRegistration,
    correlation_id: str,
) -> SyncTransaction:
    st = SyncTransaction.objects.create(
        transaction_id=transaction_id,
        sync_batch=batch,
        entity_type=entity_type,
        entity_id=entity_id or "",
        client_created_at=client_created_at,
        processing_status=status,
        result_code=code or "",
        result_message=message or "",
        processed_at=clock.now(),
        idempotency_key=str(transaction_id),
        client_payload=payload,
    )

    if status == "CONFLICT":
        conflict_type = CONFLICT_TYPE_BY_CODE.get(code, code or "SYNC_CONFLICT")
        SyncConflict.objects.create(
            sync_transaction=st,
            conflict_type=conflict_type,
            conflict_reason=message or "",
        )
        record_audit_event(
            event_type="SYNC_CONFLICT",
            actor_user=user,
            device_registration=device,
            entity_type="SyncTransaction",
            entity_id=st.sync_transaction_id,
            reason=message or conflict_type,
            metadata={
                "transaction_id": str(transaction_id),
                "conflict_type": conflict_type,
                "entity_type": entity_type,
            },
            correlation_id=correlation_id,
        )
    return st


def _process_item(
    *,
    user: User,
    device: DeviceRegistration,
    mess_id: int,
    batch: SyncBatch,
    item: dict[str, Any],
    correlation_id: str,
) -> dict[str, Any]:
    """
    Process one transaction in its own savepoint.

    One bad transaction never fails the batch; an unexpected exception becomes
    RETRYABLE_ERROR, is logged with the trace id, and is not stored as final.
    """
    transaction_id = _coerce_uuid(item.get("transaction_id"))
    if transaction_id is None:
        return _result(
            item.get("transaction_id"),
            "REJECTED",
            "INVALID_TRANSACTION_ID",
            "Transaction id must be a UUID.",
        )

    entity_type = _normalise_entity_type(item.get("entity_type"))
    if entity_type is None:
        return _result(
            transaction_id,
            "REJECTED",
            "INVALID_ENTITY_TYPE",
            "Entity type must be MEAL_CONSUMPTION or EXTRA_TRANSACTION.",
        )

    client_created_at = _coerce_datetime(item.get("client_created_at"))
    payload = item.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        with transaction.atomic():
            existing = SyncTransaction.objects.filter(
                transaction_id=transaction_id
            ).first()
            if existing is not None:
                return _result_from_transaction(existing)

            result = _apply_transaction(
                user=user,
                device=device,
                mess_id=mess_id,
                entity_type=entity_type,
                payload=payload,
                transaction_id=transaction_id,
                client_created_at=client_created_at,
                correlation_id=correlation_id,
            )

            if isinstance(result, dict):
                # Scope pre-check produced a result without calling a command.
                status = result["status"]
                code = result["result_code"]
                message = result["result_message"]
                entity_id = result["entity_id"]
            else:
                status = result.status
                code = result.code
                message = result.message
                entity = (
                    result.meal_consumption
                    if entity_type == ENTITY_MEAL
                    else result.extra_transaction
                )
                entity_id = ""
                if entity is not None:
                    entity_id = str(
                        entity.meal_consumption_id
                        if entity_type == ENTITY_MEAL
                        else entity.extra_transaction_id
                    )

            _persist_outcome(
                batch=batch,
                transaction_id=transaction_id,
                entity_type=entity_type,
                entity_id=entity_id,
                client_created_at=client_created_at,
                status=status,
                code=code,
                message=message,
                payload=payload,
                user=user,
                device=device,
                correlation_id=correlation_id,
            )
            return _result(
                transaction_id, status, code or "", message or "", entity_id
            )
    except IntegrityError:
        # Concurrent duplicate: another request stored this transaction first.
        existing = SyncTransaction.objects.filter(
            transaction_id=transaction_id
        ).first()
        if existing is not None:
            return _result_from_transaction(existing)
        return _result(
            transaction_id,
            "RETRYABLE_ERROR",
            "RETRYABLE_ERROR",
            "Temporary concurrency error; retry this transaction.",
        )
    except Exception as exc:  # noqa: BLE001 - boundary records retryable failure
        logger.error(
            "sync_transaction_failed",
            transaction_id=str(transaction_id),
            correlation_id=correlation_id,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return _result(
            transaction_id,
            "RETRYABLE_ERROR",
            "RETRYABLE_ERROR",
            "Temporary server error; retry this transaction.",
        )


# ---------------------------------------------------------------------------
# Batch orchestration [Phase 8, build 2]
# ---------------------------------------------------------------------------

def _clock_skew_seconds(
    trusted_time_metadata: dict[str, Any] | None, server_time: datetime
) -> float | None:
    """Clock skew between the Manager's claimed trusted time and the server."""
    if not isinstance(trusted_time_metadata, dict):
        return None
    anchor = (
        trusted_time_metadata.get("anchor_server_time")
        or trusted_time_metadata.get("anchorServerTime")
        or trusted_time_metadata.get("server_time")
    )
    elapsed = (
        trusted_time_metadata.get("elapsed_seconds")
        if "elapsed_seconds" in trusted_time_metadata
        else trusted_time_metadata.get("elapsedSeconds")
    )
    if anchor is None or elapsed is None:
        return None
    try:
        anchor_dt = _coerce_datetime(anchor)
        claimed = anchor_dt + timedelta(seconds=float(elapsed))
        return round((claimed - server_time).total_seconds(), 3)
    except (TypeError, ValueError):
        return None


def _finalize_device(
    *,
    device: DeviceRegistration,
    user: User,
    pending_transaction_count: int,
    results: list[dict[str, Any]],
    correlation_id: str,
) -> None:
    now = clock.now()
    device.last_active_at = now

    all_have_outcomes = all(
        result["status"] != "RETRYABLE_ERROR" for result in results
    )
    if (
        device.session_status == "REVOKE_PENDING_SYNC"
        and pending_transaction_count == 0
        and all_have_outcomes
    ):
        device.session_status = "REVOKED"
        device.revoked_at = now
        device.save(
            update_fields=["last_active_at", "session_status", "revoked_at"]
        )
        RefreshToken.objects.filter(device_registration=device).update(
            is_revoked=True
        )
        record_audit_event(
            event_type="DEVICE_REVOKED",
            actor_user=user,
            device_registration=device,
            entity_type="DeviceRegistration",
            entity_id=device.device_registration_id,
            reason=(
                "Device sync completed; finalized REVOKE_PENDING_SYNC "
                "revocation [D14, SPEC SDD §121]."
            ),
            correlation_id=correlation_id,
        )
    else:
        device.save(update_fields=["last_active_at"])


def _build_response(
    *,
    batch: SyncBatch,
    user: User,
    device: DeviceRegistration,
    mess_id: int,
    client_cursor: int,
    page_token: int | None,
    pending_transaction_count: int,
    results: list[dict[str, Any]],
    trusted_time_metadata: dict[str, Any] | None,
    correlation_id: str,
    cursor_issued_at: datetime,
    new_cursor: int,
) -> dict[str, Any]:
    _finalize_device(
        device=device,
        user=user,
        pending_transaction_count=pending_transaction_count,
        results=results,
        correlation_id=correlation_id,
    )

    tallies = Counter(result["status"] for result in results)
    # Server time is read as late as possible before serialization [build 9].
    server_time = clock.now()
    clock_skew = _clock_skew_seconds(trusted_time_metadata, server_time)

    record_audit_event(
        event_type="SYNC_SUCCESS",
        actor_user=user,
        device_registration=device,
        entity_type="SyncBatch",
        entity_id=batch.sync_batch_id,
        reason="Sync batch processed.",
        metadata={
            "batch_id": str(batch.batch_id),
            "transaction_count": len(results),
            "outcome_counts": dict(tallies),
            "has_conflicts": bool(tallies.get("CONFLICT")),
            "retryable_errors": int(tallies.get("RETRYABLE_ERROR", 0)),
            "pending_transaction_count": pending_transaction_count,
            "clock_skew_seconds": clock_skew,
        },
        correlation_id=correlation_id,
    )

    student_delta = get_student_delta(
        mess_id,
        client_cursor,
        cursor_issued_at=cursor_issued_at,
        page_token=page_token,
    )

    return {
        "batch_id": str(batch.batch_id),
        "server_time": server_time,
        "authorization_state": calculate_authorization_state(device),
        "offline_windows": get_offline_windows(),
        "transaction_results": results,
        "student_changes": student_delta["upserts"],
        "student_removals": student_delta["removals"],
        "configuration_changes": get_delta_configuration(mess_id, client_cursor),
        "attendance_changes": get_attendance_changes(mess_id, client_cursor),
        "resolved_results": get_resolved_results(device),
        "new_sync_cursor": new_cursor,
        "cursor_issued_at": cursor_issued_at,
        "has_more": student_delta["has_more"],
        "next_page_token": student_delta["next_page_token"],
    }


def process_sync_batch(
    user: User,
    data: dict[str, Any],
    correlation_id: str = "",
    device: DeviceRegistration | None = None,
) -> dict[str, Any]:
    """
    Process an offline synchronization batch uploaded by a Mess Manager
    [SPEC SDD §52, §67; ImplementationGuide Phase 8].
    """
    resolved_device = _resolve_device(user, data, device)
    if resolved_device is None or not isinstance(
        resolved_device, DeviceRegistration
    ):
        _audit_sync_failure(
            user=user,
            device=None,
            reason="Device is not registered to this user.",
            correlation_id=correlation_id,
        )
        raise PermissionDeniedError(
            "Device is not registered to this user.", code="DEVICE_NOT_FOUND"
        )

    mess_id, _assignment = _gatekeep(
        user=user,
        data=data,
        device=resolved_device,
        correlation_id=correlation_id,
    )

    transactions_data = list(data.get("transactions") or [])
    client_cursor = int(data.get("last_server_version") or 0)
    page_token = data.get("page_token") or None
    if page_token is not None:
        try:
            page_token = int(page_token)
        except (TypeError, ValueError):
            page_token = None
    pending_transaction_count = int(
        data.get("pending_transaction_count") or 0
    )
    trusted_time_metadata = data.get("trusted_time_metadata") or {}

    batch_id = _coerce_uuid(data.get("batch_id")) or uuid.uuid4()

    existing_batch = SyncBatch.objects.filter(batch_id=batch_id).first()
    if existing_batch is not None:
        if (
            existing_batch.device_registration_id
            != resolved_device.device_registration_id
        ):
            _audit_failure_and_raise(
                exc=PermissionDeniedError(
                    "Batch id belongs to a different device.",
                    code="BATCH_DEVICE_MISMATCH",
                ),
                user=user,
                device=resolved_device,
                reason="Batch id belongs to a different device.",
                correlation_id=correlation_id,
                metadata={"batch_id": str(batch_id)},
            )

        if existing_batch.status == "COMPLETED":
            # Replaying a completed batch is harmless: return the stored
            # per-item results again plus a fresh download [build 2].
            results = [
                _result_from_transaction(st)
                for st in existing_batch.transactions.order_by(
                    "client_created_at", "sync_transaction_id"
                )
            ]
            cursor_issued_at = clock.now()
            new_cursor = issue_change_cursor(mess_id)
            return _build_response(
                batch=existing_batch,
                user=user,
                device=resolved_device,
                mess_id=mess_id,
                client_cursor=client_cursor,
                page_token=page_token,
                pending_transaction_count=pending_transaction_count,
                results=results,
                trusted_time_metadata=trusted_time_metadata,
                correlation_id=correlation_id,
                cursor_issued_at=cursor_issued_at,
                new_cursor=new_cursor,
            )

        # Server died mid-batch: resume by skipping already stored outcomes.
        batch = existing_batch
    else:
        try:
            batch = SyncBatch.objects.create(
                batch_id=batch_id,
                device_registration=resolved_device,
                user=user,
                status="IN_PROGRESS",
                client_cursor=client_cursor,
                server_cursor_before=client_cursor,
                server_cursor_after=client_cursor,
                transaction_count=len(transactions_data),
                sent_at=clock.now(),
            )
        except IntegrityError:
            # A concurrent request inserted the same batch id first. Continue
            # with its row; per-item lookups make the replay idempotent.
            batch = SyncBatch.objects.get(batch_id=batch_id)

    results: list[dict[str, Any]] = []
    for item in sorted(transactions_data, key=_sort_key):
        results.append(
            _process_item(
                user=user,
                device=resolved_device,
                mess_id=mess_id,
                batch=batch,
                item=item,
                correlation_id=correlation_id,
            )
        )

    cursor_issued_at = clock.now()
    cursor_after = issue_change_cursor(mess_id)
    batch.status = "COMPLETED"
    batch.completed_at = clock.now()
    batch.server_cursor_after = cursor_after
    batch.transaction_count = len(transactions_data)
    batch.save(
        update_fields=[
            "status",
            "completed_at",
            "server_cursor_after",
            "transaction_count",
        ]
    )

    return _build_response(
        batch=batch,
        user=user,
        device=resolved_device,
        mess_id=mess_id,
        client_cursor=client_cursor,
        page_token=page_token,
        pending_transaction_count=pending_transaction_count,
        results=results,
        trusted_time_metadata=trusted_time_metadata,
        correlation_id=correlation_id,
        cursor_issued_at=cursor_issued_at,
        new_cursor=cursor_after,
    )


# ---------------------------------------------------------------------------
# Conflict resolution [DEC-17; Phase 8, build 5]
# ---------------------------------------------------------------------------

def _replay_conflict(
    *,
    conflict: SyncConflict,
    actor_user: User,
    correlation_id: str,
) -> dict[str, Any]:
    """Re-run the original command with only the conflicting check waived."""
    st = conflict.sync_transaction
    if conflict.conflict_type in LOCKED_CONFLICT_TYPES:
        raise ConflictError(
            "A locked billing period is never waived; reject this conflict instead.",
            code="LOCKED_PERIOD_NOT_WAIVABLE",
        )

    payload = st.client_payload or {}
    entity_type = _normalise_entity_type(st.entity_type)
    if entity_type is None or not isinstance(payload, dict) or not payload:
        raise ConflictError(
            "The original transaction payload is unavailable; reject this conflict.",
            code="CONFLICT_PAYLOAD_MISSING",
        )

    device = st.sync_batch.device_registration
    current_mess_id = (
        st.sync_batch.user.mess_manager_assignments.filter(is_active=True)
        .values_list("mess_id", flat=True)
        .first()
    )
    # A scope conflict must be replayed against the original mess; the scope
    # check is the one check waived for this conflict type.
    payload_mess_id = _payload_mess_id(payload, current_mess_id)
    mess_id = payload_mess_id or current_mess_id
    if mess_id is None:
        raise ConflictError(
            "The Manager has no active mess; reject this conflict.",
            code="NO_ACTIVE_MESS_ASSIGNMENT",
        )

    waive_checks = WAIVER_BY_CONFLICT_TYPE.get(conflict.conflict_type, set())
    result = _apply_transaction(
        user=actor_user,
        device=device,
        mess_id=int(mess_id),
        entity_type=entity_type,
        payload=payload,
        transaction_id=st.transaction_id,
        client_created_at=st.client_created_at,
        correlation_id=correlation_id,
        waive_checks=waive_checks,
        source="SYNC_RESOLUTION",
    )

    if isinstance(result, dict):
        status = result["status"]
        code = result["result_code"]
        message = result["result_message"]
        entity_id = result["entity_id"]
    else:
        status = result.status
        code = result.code
        message = result.message
        entity = (
            result.meal_consumption
            if entity_type == ENTITY_MEAL
            else result.extra_transaction
        )
        entity_id = ""
        if entity is not None:
            entity_id = str(
                entity.meal_consumption_id
                if entity_type == ENTITY_MEAL
                else entity.extra_transaction_id
            )

    if status in ("CONFLICT", "REJECTED", "RETRYABLE_ERROR"):
        raise ConflictError(
            f"Conflict could not be accepted: {code or status} - {message or ''}".strip(),
            code=code or status,
        )
    return {
        "status": status,
        "code": code,
        "message": message,
        "entity_id": entity_id,
    }


def resolve_sync_conflict(
    conflict_id: int,
    resolution: str,
    actor_user: User,
    notes: str = "",
    correlation_id: str = "",
) -> SyncConflict:
    """
    Administrative review and resolution of a sync conflict
    [SPEC DBDD §11, App Flow §13; DEC-17].

    ACCEPTED re-runs the command with only the conflicting check waived and
    Source SYNC_RESOLUTION; REJECTED closes it. Both require notes and audit.
    """
    resolution = (resolution or "").strip().upper()
    notes = (notes or "").strip()
    if resolution not in ["ACCEPTED", "REJECTED"]:
        raise ValidationError(
            "Resolution must be ACCEPTED or REJECTED.",
            code="INVALID_RESOLUTION",
        )
    if not notes:
        raise ValidationError(
            "Resolution notes are required.",
            code="RESOLUTION_NOTES_REQUIRED",
        )

    with transaction.atomic():
        conflict = (
            SyncConflict.objects.select_for_update()
            .select_related("sync_transaction", "sync_transaction__sync_batch")
            .filter(conflict_id=conflict_id)
            .first()
        )
        if conflict is None:
            raise NotFoundError(f"SyncConflict ID {conflict_id} not found.")
        if conflict.resolved_at is not None:
            raise ConflictError(
                "This conflict has already been resolved.",
                code="CONFLICT_ALREADY_RESOLVED",
            )

        st = conflict.sync_transaction
        if resolution == "ACCEPTED":
            outcome = _replay_conflict(
                conflict=conflict,
                actor_user=actor_user,
                correlation_id=correlation_id,
            )
            st.processing_status = outcome["status"]
            st.result_code = outcome["code"] or "SYNC_RESOLUTION"
            st.result_message = outcome["message"] or "Accepted by resolution."
            st.entity_id = outcome["entity_id"] or st.entity_id
            st.processed_at = clock.now()
            st.save(
                update_fields=[
                    "processing_status",
                    "result_code",
                    "result_message",
                    "entity_id",
                    "processed_at",
                ]
            )

        conflict.resolution = resolution
        conflict.resolution_notes = notes[:2000]
        conflict.resolved_at = clock.now()
        conflict.resolved_by_user = actor_user
        conflict.save(
            update_fields=[
                "resolution",
                "resolution_notes",
                "resolved_at",
                "resolved_by_user",
            ]
        )

        record_audit_event(
            event_type="SYNC_CONFLICT_RESOLVED",
            actor_user=actor_user,
            entity_type="SyncConflict",
            entity_id=conflict.conflict_id,
            reason=f"Conflict resolved as {resolution}: {notes}"[:500],
            metadata={
                "transaction_id": str(st.transaction_id),
                "conflict_type": conflict.conflict_type,
                "resolution": resolution,
            },
            correlation_id=correlation_id,
        )

    return conflict
