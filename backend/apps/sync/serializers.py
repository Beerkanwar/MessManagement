"""
Serializers for offline synchronization batch uploads and conflicts [SPEC SDD §67, §68; DBDD §11].
"""
from rest_framework import serializers

from apps.sync.models import SyncBatch, SyncConflict, SyncTransaction


class SyncTransactionItemSerializer(serializers.Serializer):
    """Represents a single offline transaction item submitted in a sync batch."""
    transaction_id = serializers.UUIDField(required=True)
    entity_type = serializers.ChoiceField(choices=["MEAL", "EXTRA"], required=True)
    client_created_at = serializers.DateTimeField(required=True)
    payload = serializers.DictField(required=True)


class SyncUploadRequestSerializer(serializers.Serializer):
    """
    Request schema for POST /api/v1/sync/upload [SPEC SDD §67].
    Includes DeviceId, ClientVersion, LastServerVersion, TrustedTimeMetadata, and Transactions[].
    """
    device_id = serializers.CharField(max_length=255, required=True)
    client_version = serializers.CharField(max_length=50, required=False, default="1.0.0")
    last_server_version = serializers.IntegerField(required=False, default=0, min_value=0)
    trusted_time_metadata = serializers.DictField(required=False, default=dict)
    transactions = serializers.ListField(
        child=SyncTransactionItemSerializer(),
        required=False,
        default=list,
    )


class TransactionResultItemSerializer(serializers.Serializer):
    """Per-transaction processing outcome in sync response [SPEC DBDD §11.1]."""
    transaction_id = serializers.UUIDField()
    status = serializers.ChoiceField(
        choices=["SYNCHRONIZED", "IDEMPOTENT_SUCCESS", "DUPLICATE", "CONFLICT", "REJECTED"]
    )
    result_code = serializers.CharField(allow_blank=True, default="")
    result_message = serializers.CharField(allow_blank=True, default="")
    entity_id = serializers.CharField(allow_blank=True, default="")


class SyncUploadResponseSerializer(serializers.Serializer):
    """
    Response schema for POST /api/v1/sync/upload [SPEC SDD §67].
    Returns ServerTime, AuthorizationState, StudentChanges, ConfigurationChanges,
    TransactionResults[], and NewSyncCursor.
    """
    server_time = serializers.DateTimeField()
    authorization_state = serializers.CharField()
    student_changes = serializers.ListField(child=serializers.DictField())
    configuration_changes = serializers.DictField()
    transaction_results = serializers.ListField(child=TransactionResultItemSerializer())
    new_sync_cursor = serializers.IntegerField()


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
