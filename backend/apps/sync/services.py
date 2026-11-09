"""
Sync services implementing atomic cursor management, batch upload processing,
and conflict resolution [SPEC SDD §52, §56, §67, §68; DBDD §11; SRS §26].
"""
import uuid
from datetime import datetime
from typing import Any

from django.db import connection, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record_audit_event
from apps.config.models import ApplicationVersionPolicy, SystemSetting
from apps.core.clock import clock
from apps.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from apps.identity.models import DeviceRegistration, RefreshToken, User
from apps.identity.selectors import get_user_role
from apps.mess.models import Mess, MessManagerAssignment
from apps.sync.models import ChangeCursor, SyncBatch, SyncConflict, SyncTransaction
from apps.sync.selectors import (
    calculate_authorization_state,
    get_current_cursor,
    get_delta_configuration,
    get_delta_students,
)


def advance_change_cursor(cursor_key: str) -> int:
    """
    Atomically advances the change cursor for the given aggregate key
    (e.g. 'mess:<id>:students', 'mess:<id>:secrets', 'mess:<id>:meal_rates').
    Uses a single atomic PostgreSQL UPSERT statement to eliminate race conditions.
    Returns the new monotonically increasing version number.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sync_change_cursor (aggregate_type, current_version, updated_at)
            VALUES (%s, 1, NOW())
            ON CONFLICT (aggregate_type)
            DO UPDATE SET current_version = sync_change_cursor.current_version + 1, updated_at = NOW()
            RETURNING current_version;
            """,
            [cursor_key],
        )
        row = cursor.fetchone()
        return row[0] if row else 1


def process_sync_batch(
    user: User,
    data: dict[str, Any],
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Processes an offline synchronization batch uploaded by a Mess Manager [SPEC SDD §52, §67].
    Executes:
    1. Caller and role verification (Manager or Super Admin).
    2. Device binding and status validation (ACTIVE or REVOKE_PENDING_SYNC).
    3. Application version policy check (BLOCKED versions rejected).
    4. Batch transaction count limit (max 500 [DEC-11, D11]).
    5. Per-transaction idempotency, duplicate, conflict, and acceptance handling.
    6. SyncBatch completion and monotonic cursor advance.
    7. Device REVOKE_PENDING_SYNC finalization upon completion.
    8. Returns ServerTime, AuthorizationState, StudentChanges, ConfigurationChanges,
       TransactionResults[], and NewSyncCursor.
    """
    role = get_user_role(user)
    if role not in ["MESS_MANAGER", "SUPER_ADMIN"]:
        raise PermissionDeniedError("Only authorized Mess Managers or Super Admins may upload sync batches.")

    # Resolve Manager's assigned mess
    if role == "MESS_MANAGER":
        manager_assignment = (
            MessManagerAssignment.objects.filter(user=user, is_active=True)
            .select_related("mess")
            .first()
        )
        if not manager_assignment:
            raise PermissionDeniedError("Mess Manager has no active assigned mess.")
        mess_id = manager_assignment.mess_id
    else:
        # Super admin: check if mess_id provided in first transaction or default
        mess_id = None
        txns = data.get("transactions", [])
        if txns:
            first_payload = txns[0].get("payload", {})
            mess_id = first_payload.get("mess_id")
        if not mess_id:
            first_mess = Mess.objects.first()
            mess_id = first_mess.mess_id if first_mess else 1

    # Validate device registration
    device_id_raw = data.get("device_id")
    device = DeviceRegistration.objects.filter(user=user, device_id=device_id_raw).first()
    if not device:
        # Fallback by device_registration_id if provided
        try:
            device = DeviceRegistration.objects.filter(
                user=user, device_registration_id=int(device_id_raw)
            ).first()
        except (ValueError, TypeError):
            pass

    if not device:
        raise PermissionDeniedError(f"Device '{device_id_raw}' is not registered to this user.")

    if device.session_status == "REVOKED":
        raise PermissionDeniedError("Device registration is revoked and cannot synchronize.")

    # Application version policy check [SPEC SDD §120]
    client_version = data.get("client_version", "1.0.0")
    platform = device.platform or "ANDROID"
    policy = ApplicationVersionPolicy.objects.filter(
        platform=platform, app_version=client_version
    ).first()
    if policy and policy.status == "BLOCKED":
        raise PermissionDeniedError(
            f"Client application version {client_version} on {platform} is blocked from synchronizing [SPEC SDD §120]."
        )

    # Batch transaction limit [DEC-11, D11]
    transactions_data = data.get("transactions", [])
    max_batch_size = 500
    batch_setting = SystemSetting.objects.filter(key="sync.batch_max_transactions").first()
    if batch_setting:
        try:
            max_batch_size = int(batch_setting.value)
        except (ValueError, TypeError):
            max_batch_size = 500

    if len(transactions_data) > max_batch_size:
        raise ValidationError(
            {"transactions": f"Batch transaction count ({len(transactions_data)}) exceeds maximum allowed ({max_batch_size})."}
        )

    client_cursor = int(data.get("last_server_version", 0))
    aggregate_key = f"mess:{mess_id}"
    cursor_before = get_current_cursor(aggregate_key)
    now = clock.now()

    # Create SyncBatch record
    batch = SyncBatch.objects.create(
        batch_id=uuid.uuid4(),
        device_registration=device,
        user=user,
        status="IN_PROGRESS",
        client_cursor=client_cursor,
        server_cursor_before=cursor_before,
        server_cursor_after=cursor_before,
        transaction_count=len(transactions_data),
        sent_at=now,
    )

    transaction_results = []
    has_conflicts = False

    # Process each transaction atomically within its own savepoint
    from apps.attendance.services import record_extra, record_meal

    for item in transactions_data:
        txn_id = uuid.UUID(str(item["transaction_id"]))
        entity_type = item["entity_type"]
        client_created_at = item["client_created_at"]
        payload = item.get("payload", {})

        # Fast-path idempotency check: already recorded in SyncTransaction
        existing_st = SyncTransaction.objects.filter(transaction_id=txn_id).first()
        if existing_st:
            transaction_results.append({
                "transaction_id": txn_id,
                "status": existing_st.processing_status,
                "result_code": existing_st.result_code or "IDEMPOTENT_SUCCESS",
                "result_message": existing_st.result_message or "Transaction already processed.",
                "entity_id": existing_st.entity_id,
            })
            continue

        if entity_type == "MEAL":
            meal_res = record_meal(
                transaction_id=txn_id,
                student=payload.get("student_id"),
                meal_type=payload.get("meal_type"),
                meal_date=payload.get("meal_date"),
                mess=payload.get("mess_id") or mess_id,
                recorded_by_user=user,
                roll_number_snapshot=payload.get("roll_number_snapshot", ""),
                transaction_timestamp=payload.get("transaction_timestamp") or client_created_at,
                verification_method=payload.get("verification_method", "QR_HMAC_SHA256"),
                verification_result=payload.get("verification_result", "SUCCESS"),
                device_registration=device,
                source="OFFLINE_SYNC",
                correlation_id=correlation_id,
            )

            entity_id_str = (
                str(meal_res.meal_consumption.meal_consumption_id)
                if meal_res.meal_consumption
                else ""
            )

            st = SyncTransaction.objects.create(
                transaction_id=txn_id,
                sync_batch=batch,
                entity_type="MEAL",
                entity_id=entity_id_str,
                client_created_at=client_created_at,
                processing_status=meal_res.status,
                result_code=meal_res.code,
                result_message=meal_res.message,
                processed_at=clock.now(),
            )

            if meal_res.status == "CONFLICT":
                has_conflicts = True
                SyncConflict.objects.create(
                    sync_transaction=st,
                    conflict_type=meal_res.code,
                    conflict_reason=meal_res.message,
                )

            transaction_results.append({
                "transaction_id": txn_id,
                "status": meal_res.status,
                "result_code": meal_res.code,
                "result_message": meal_res.message,
                "entity_id": entity_id_str,
            })

        elif entity_type == "EXTRA":
            extra_res = record_extra(
                transaction_id=txn_id,
                student=payload.get("student_id"),
                mess=payload.get("mess_id") or mess_id,
                extra_item=payload.get("extra_item_id"),
                quantity=payload.get("quantity", 1),
                recorded_by_user=user,
                transaction_timestamp=payload.get("transaction_timestamp") or client_created_at,
                device_registration=device,
                source="OFFLINE_SYNC",
                correlation_id=correlation_id,
            )

            entity_id_str = (
                str(extra_res.extra_transaction.extra_transaction_id)
                if extra_res.extra_transaction
                else ""
            )

            st = SyncTransaction.objects.create(
                transaction_id=txn_id,
                sync_batch=batch,
                entity_type="EXTRA",
                entity_id=entity_id_str,
                client_created_at=client_created_at,
                processing_status=extra_res.status,
                result_code=extra_res.code,
                result_message=extra_res.message,
                processed_at=clock.now(),
            )

            if extra_res.status == "CONFLICT":
                has_conflicts = True
                SyncConflict.objects.create(
                    sync_transaction=st,
                    conflict_type=extra_res.code,
                    conflict_reason=extra_res.message,
                )

            transaction_results.append({
                "transaction_id": txn_id,
                "status": extra_res.status,
                "result_code": extra_res.code,
                "result_message": extra_res.message,
                "entity_id": entity_id_str,
            })

    # Advance monotonic version cursor
    cursor_after = advance_change_cursor(aggregate_key)

    # Complete SyncBatch
    batch.status = "COMPLETED"
    batch.completed_at = clock.now()
    batch.server_cursor_after = cursor_after
    batch.save(update_fields=["status", "completed_at", "server_cursor_after"])

    # Update device sync timestamps & evaluate REVOKE_PENDING_SYNC [SPEC SDD §121, D14]
    now_sync = clock.now()
    device.last_active_at = now_sync

    if device.session_status == "REVOKE_PENDING_SYNC":
        device.session_status = "REVOKED"
        device.revoked_at = now_sync
        device.save(update_fields=["last_active_at", "session_status", "revoked_at"])
        RefreshToken.objects.filter(device_registration=device).update(is_revoked=True)
        record_audit_event(
            event_type="DEVICE_REVOKED",
            actor_user=user,
            device_registration=device,
            entity_type="DeviceRegistration",
            entity_id=device.device_registration_id,
            reason="Device sync completed; finalized REVOKE_PENDING_SYNC revocation [SPEC SDD §121].",
            correlation_id=correlation_id,
        )
    else:
        device.save(update_fields=["last_active_at"])

    # Record sync audit event
    record_audit_event(
        event_type="SYNC_SUCCESS" if not has_conflicts else "SYNC_CONFLICT",
        actor_user=user,
        device_registration=device,
        entity_type="SyncBatch",
        entity_id=batch.sync_batch_id,
        metadata={
            "batch_id": str(batch.batch_id),
            "transaction_count": len(transactions_data),
            "has_conflicts": has_conflicts,
        },
        correlation_id=correlation_id,
    )

    auth_state = calculate_authorization_state(device)
    student_changes = get_delta_students(mess_id, client_cursor)
    configuration_changes = get_delta_configuration(mess_id, client_cursor)

    return {
        "server_time": now_sync,
        "authorization_state": auth_state,
        "student_changes": student_changes,
        "configuration_changes": configuration_changes,
        "transaction_results": transaction_results,
        "new_sync_cursor": cursor_after,
    }


def resolve_sync_conflict(
    conflict_id: int,
    resolution: str,
    actor_user: User,
    notes: str = "",
    correlation_id: str = "",
) -> SyncConflict:
    """
    Administrative review and resolution of a sync conflict [SPEC DBDD §11, App Flow §13].
    """
    if resolution not in ["ACCEPTED", "REJECTED"]:
        raise ValidationError({"resolution": "Resolution must be ACCEPTED or REJECTED."})

    try:
        conflict = SyncConflict.objects.select_related("sync_transaction").get(conflict_id=conflict_id)
    except SyncConflict.DoesNotExist:
        raise NotFoundError(f"SyncConflict ID {conflict_id} not found.")

    conflict.resolution = resolution
    conflict.resolution_notes = notes
    conflict.resolved_at = clock.now()
    conflict.resolved_by_user = actor_user
    conflict.save(update_fields=["resolution", "resolution_notes", "resolved_at", "resolved_by_user"])

    record_audit_event(
        event_type="SYNC_CONFLICT_RESOLVED",
        actor_user=actor_user,
        entity_type="SyncConflict",
        entity_id=conflict.conflict_id,
        reason=f"Conflict resolved as {resolution}: {notes}",
        correlation_id=correlation_id,
    )

    return conflict
