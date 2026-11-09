"""
Views for offline synchronization endpoint group [SPEC SDD §64, §67, §68; DBDD §11].
Provides:
- POST /api/v1/sync/upload (and /api/v1/upload): Batch transaction sync for Mess Managers.
- GET /api/v1/sync/batches: List sync batch history (Manager: own device, admin: all).
- GET /api/v1/sync/transactions: List sync transactions for the admin screen.
- GET /api/v1/sync/conflicts: List sync conflicts.
- GET /api/v1/sync/conflicts/<conflict_id>: Read one conflict.
- POST /api/v1/sync/conflicts/<conflict_id>/resolve: Admin resolution of a conflict.
- GET /api/v1/sync/devices/last-sync: Per-device last sync timestamps.
"""
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import NotFoundError
from apps.identity.authentication import DeviceBindingJWTAuthentication
from apps.identity.selectors import get_user_role
from apps.sync.selectors import (
    get_device_last_sync,
    get_sync_batches,
    get_sync_conflict,
    get_sync_conflicts,
    get_sync_transactions,
)
from apps.sync.serializers import (
    SyncConflictSerializer,
    SyncUploadRequestSerializer,
    SyncUploadResponseSerializer,
)
from apps.sync.services import process_sync_batch, resolve_sync_conflict


def _has_admin_role(user) -> bool:
    return get_user_role(user) == "SUPER_ADMIN"


@extend_schema(
    summary="Manager Batch Upload",
    description=(
        "Synchronizes offline transactions uploaded by Mess Managers [SPEC SDD §67, §68]. "
        "Processes batched meal and extra transactions with per-transaction idempotency, "
        "enforces 500-item limits, duplicate prevention, and returns delta updates."
    ),
    tags=["sync"],
    request=SyncUploadRequestSerializer,
    responses={
        200: SyncUploadResponseSerializer,
        400: OpenApiResponse(description="Validation error or batch size exceeded"),
        403: OpenApiResponse(description="Unauthorized mess or blocked version"),
    },
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def sync_upload_view(request):
    """Handles offline batch upload for Mess Managers [SPEC SDD §67]."""
    serializer = SyncUploadRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    correlation_id = getattr(request, "correlation_id", "")
    result = process_sync_batch(
        user=request.user,
        data=serializer.validated_data,
        correlation_id=correlation_id,
        device=getattr(request, "device", None),
    )
    return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Sync Batches",
    description=(
        "Lists recent synchronization batch records [SPEC DBDD §11]. Managers see "
        "their own device; Super Admins see every device [Phase 8, build 10]."
    ),
    tags=["sync"],
    responses={200: OpenApiResponse(description="List of sync batches")},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def sync_batches_list_view(request):
    """Returns recent sync batches."""
    role = get_user_role(request.user)
    if role not in ["SUPER_ADMIN", "MESS_MANAGER"]:
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    device = None
    if role == "MESS_MANAGER":
        device = getattr(request, "device", None)
        if device is None:
            return Response(
                {"detail": "A registered device is required."},
                status=status.HTTP_403_FORBIDDEN,
            )

    batches = get_sync_batches(device=device, limit=50)
    data = [
        {
            "sync_batch_id": b.sync_batch_id,
            "batch_id": str(b.batch_id),
            "device_id": b.device_registration.device_id,
            "user_id": b.user_id,
            "status": b.status,
            "transaction_count": b.transaction_count,
            "client_cursor": b.client_cursor,
            "server_cursor_before": b.server_cursor_before,
            "server_cursor_after": b.server_cursor_after,
            "sent_at": b.sent_at,
            "completed_at": b.completed_at,
        }
        for b in batches
    ]
    return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Sync Transactions",
    description=(
        "Lists recent synchronization transactions for the admin Synchronization "
        "screen [Phase 8, build 10]."
    ),
    tags=["sync"],
    parameters=[
        OpenApiParameter("batch_id", str, description="Filter by client batch id"),
        OpenApiParameter("transaction_id", str, description="Filter by transaction id"),
    ],
    responses={200: OpenApiResponse(description="List of sync transactions")},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def sync_transactions_list_view(request):
    """Returns recent sync transactions for administrators."""
    if not _has_admin_role(request.user):
        return Response(
            {"detail": "Only Super Admins may view sync transactions."},
            status=status.HTTP_403_FORBIDDEN,
        )

    transactions = get_sync_transactions(
        batch_id=request.query_params.get("batch_id") or None,
        transaction_id=request.query_params.get("transaction_id") or None,
        limit=50,
    )
    data = [
        {
            "sync_transaction_id": t.sync_transaction_id,
            "transaction_id": str(t.transaction_id),
            "batch_id": str(t.sync_batch.batch_id),
            "device_id": t.sync_batch.device_registration.device_id,
            "entity_type": t.entity_type,
            "entity_id": t.entity_id,
            "processing_status": t.processing_status,
            "result_code": t.result_code,
            "result_message": t.result_message,
            "client_created_at": t.client_created_at,
            "received_at": t.received_at,
            "processed_at": t.processed_at,
        }
        for t in transactions
    ]
    return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Sync Conflicts",
    description="Lists offline synchronization conflicts requiring administrative review [SPEC DBDD §11, App Flow §13].",
    tags=["sync"],
    parameters=[
        OpenApiParameter("resolved", bool, description="Filter by resolution status (true/false)"),
    ],
    responses={200: SyncConflictSerializer(many=True)},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def sync_conflicts_list_view(request):
    """Returns sync conflicts."""
    if not _has_admin_role(request.user):
        return Response({"detail": "Only Super Admins may view sync conflicts."}, status=status.HTTP_403_FORBIDDEN)

    resolved_param = request.query_params.get("resolved")
    resolved = None
    if resolved_param is not None:
        resolved = resolved_param.lower() in ["true", "1", "yes"]

    conflicts = get_sync_conflicts(resolved=resolved)
    serializer = SyncConflictSerializer(conflicts, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    summary="Read Sync Conflict",
    description="Reads one synchronization conflict for administrative review [DEC-17].",
    tags=["sync"],
    responses={200: SyncConflictSerializer, 404: OpenApiResponse(description="Conflict not found")},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def sync_conflict_detail_view(request, conflict_id: int):
    """Returns one sync conflict."""
    if not _has_admin_role(request.user):
        return Response(
            {"detail": "Only Super Admins may view sync conflicts."},
            status=status.HTTP_403_FORBIDDEN,
        )

    conflict = get_sync_conflict(conflict_id)
    if conflict is None:
        raise NotFoundError(f"SyncConflict ID {conflict_id} not found.")
    return Response(
        SyncConflictSerializer(conflict).data, status=status.HTTP_200_OK
    )


@extend_schema(
    summary="Resolve Sync Conflict",
    description="Super Admin resolves a synchronization conflict (ACCEPTED or REJECTED) [SPEC DBDD §11, App Flow §13].",
    tags=["sync"],
    request=None,
    responses={200: SyncConflictSerializer},
)
@api_view(["POST"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def sync_conflict_resolve_view(request, conflict_id: int):
    """Resolves an existing sync conflict."""
    if not _has_admin_role(request.user):
        return Response({"detail": "Only Super Admins may resolve sync conflicts."}, status=status.HTTP_403_FORBIDDEN)

    resolution = request.data.get("resolution", "").strip().upper()
    notes = request.data.get("notes", "").strip()
    correlation_id = getattr(request, "correlation_id", "")

    conflict = resolve_sync_conflict(
        conflict_id=conflict_id,
        resolution=resolution,
        actor_user=request.user,
        notes=notes,
        correlation_id=correlation_id,
    )
    serializer = SyncConflictSerializer(conflict)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    summary="Per-Device Last Sync",
    description=(
        "Lists per-device last sync timestamps for the Devices screen "
        "[Phase 8, build 10]."
    ),
    tags=["sync"],
    parameters=[
        OpenApiParameter("mess_id", int, description="Filter to devices of one mess"),
    ],
    responses={200: OpenApiResponse(description="List of devices with last sync time")},
)
@api_view(["GET"])
@authentication_classes([DeviceBindingJWTAuthentication])
@permission_classes([IsAuthenticated])
def sync_devices_last_sync_view(request):
    """Returns per-device last sync timestamps for administrators."""
    if not _has_admin_role(request.user):
        return Response(
            {"detail": "Only Super Admins may view device sync status."},
            status=status.HTTP_403_FORBIDDEN,
        )

    mess_id = request.query_params.get("mess_id")
    try:
        mess_id = int(mess_id) if mess_id not in (None, "") else None
    except (TypeError, ValueError):
        return Response(
            {"detail": "mess_id must be an integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    devices = get_device_last_sync(mess_id=mess_id)
    data = [
        {
            "device_registration_id": d.device_registration_id,
            "device_id": d.device_id,
            "user_id": d.user_id,
            "platform": d.platform,
            "session_status": d.session_status,
            "registered_at": d.registered_at,
            "last_active_at": d.last_active_at,
        }
        for d in devices
    ]
    return Response(data, status=status.HTTP_200_OK)
