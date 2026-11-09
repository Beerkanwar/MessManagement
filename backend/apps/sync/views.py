"""
Views for offline synchronization endpoint group [SPEC SDD §64, §67, §68; DBDD §11].
Provides:
- POST /api/v1/sync/upload (and /api/v1/upload): Batch transaction sync for Mess Managers.
- GET /api/v1/sync/batches: List sync batch history.
- GET /api/v1/sync/conflicts: List sync conflicts.
- POST /api/v1/sync/conflicts/<conflict_id>/resolve: Admin resolution of a conflict.
"""
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardPageNumberPagination
from apps.identity.authentication import DeviceBindingJWTAuthentication
from apps.identity.selectors import get_user_role
from apps.sync.selectors import get_sync_batches, get_sync_conflicts
from apps.sync.serializers import (
    SyncConflictSerializer,
    SyncUploadRequestSerializer,
    SyncUploadResponseSerializer,
)
from apps.sync.services import process_sync_batch, resolve_sync_conflict


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
    )
    return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Sync Batches",
    description="Lists recent synchronization batch records [SPEC DBDD §11].",
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

    batches = get_sync_batches(limit=50)
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
    role = get_user_role(request.user)
    if role != "SUPER_ADMIN":
        return Response({"detail": "Only Super Admins may view sync conflicts."}, status=status.HTTP_403_FORBIDDEN)

    resolved_param = request.query_params.get("resolved")
    resolved = None
    if resolved_param is not None:
        resolved = resolved_param.lower() in ["true", "1", "yes"]

    conflicts = get_sync_conflicts(resolved=resolved)
    serializer = SyncConflictSerializer(conflicts, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


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
    role = get_user_role(request.user)
    if role != "SUPER_ADMIN":
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
