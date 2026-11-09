"""
Serializers for offline synchronization batch uploads and conflicts [SPEC SDD §67, §68; DBDD §11].
"""
from rest_framework import serializers

from apps.sync.models import SyncBatch, SyncConflict, SyncTransaction


class SyncTransactionItemSerializer(serializers.Serializer):
    """Represents a single offline transaction item submitted in a sync batch."""
    transaction_id = serializers.UUIDField(required=True)
    entity_type = serializers.ChoiceField(
        choices=[
            "MEAL_CONSUMPTION",
            "EXTRA_TRANSACTION",
            # Legacy codes retained so already-installed clients keep working.
            "MEAL",
            "EXTRA",
        ],
        required=True,
    )
    client_created_at = serializers.DateTimeField(required=True)
    payload = serializers.DictField(required=True)


class SyncUploadRequestSerializer(serializers.Serializer):
    """
    Request schema for POST /api/v1/sync/upload [SPEC SDD §67].
    Includes BatchId, DeviceId, ClientVersion, LastServerVersion,
    TrustedTimeMetadata, PendingTransactionCount and Transactions[].
    """
    batch_id = serializers.UUIDField(
        required=False,
        help_text="Client-generated batch GUID; replaying it is safe [Phase 8].",
    )
    device_id = serializers.CharField(max_length=255, required=True)
    client_version = serializers.CharField(max_length=50, required=False, default="1.0.0")
    last_server_version = serializers.IntegerField(required=False, default=0, min_value=0)
    page_token = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Last student id of the previous bootstrap page [Phase 8].",
    )
    trusted_time_metadata = serializers.DictField(required=False, default=dict)
    pending_transaction_count = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
        help_text="Transactions still queued on the device after this batch [D14].",
    )
    transactions = serializers.ListField(
        child=SyncTransactionItemSerializer(),
        required=False,
        default=list,
    )


class TransactionResultItemSerializer(serializers.Serializer):
    """Per-transaction processing outcome in sync response [SPEC DBDD §11.1]."""
    transaction_id = serializers.UUIDField()
    status = serializers.ChoiceField(
        choices=[
            "SYNCHRONIZED",
            "IDEMPOTENT_SUCCESS",
            "DUPLICATE",
            "CONFLICT",
            "REJECTED",
            "RETRYABLE_ERROR",
        ]
    )
    result_code = serializers.CharField(allow_blank=True, default="")
    result_message = serializers.CharField(allow_blank=True, default="")
    entity_id = serializers.CharField(allow_blank=True, default="")


class SyncUploadResponseSerializer(serializers.Serializer):
    """
    Response schema for POST /api/v1/sync/upload [SPEC SDD §67].
    Returns ServerTime, AuthorizationState, OfflineWindows, TransactionResults[],
    StudentChanges, ConfigurationChanges, AttendanceChanges, ResolvedResults,
    NewSyncCursor, CursorIssuedAt and HasMore.
    """
    batch_id = serializers.UUIDField(required=False)
    server_time = serializers.DateTimeField()
    authorization_state = serializers.CharField()
    offline_windows = serializers.DictField(required=False)
    student_changes = serializers.ListField(child=serializers.DictField())
    student_removals = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    configuration_changes = serializers.DictField()
    attendance_changes = serializers.DictField(required=False)
    resolved_results = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    transaction_results = serializers.ListField(child=TransactionResultItemSerializer())
    new_sync_cursor = serializers.IntegerField()
    cursor_issued_at = serializers.DateTimeField(required=False)
    has_more = serializers.BooleanField(required=False, default=False)
    next_page_token = serializers.IntegerField(required=False, allow_null=True)


class SyncConflictSerializer(serializers.ModelSerializer):
    transaction_id = serializers.UUIDField(source="sync_transaction.transaction_id", read_only=True)
    entity_type = serializers.CharField(source="sync_transaction.entity_type", read_only=True)

    class Meta:
        model = SyncConflict
        fields = [
            "conflict_id",
            "sync_transaction_id",
            "transaction_id",
            "entity_type",
            "conflict_type",
            "conflict_reason",
            "detected_at",
            "resolved_at",
            "resolved_by_user_id",
            "resolution",
            "resolution_notes",
        ]
