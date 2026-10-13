"""
Offline synchronization tracking models matching SPEC DBDD §11.
Implements:
- SyncBatch (groups transactions in an upload, batch_id unique)
- SyncTransaction (per-transaction idempotency, transaction_id unique)
- SyncConflict (persists conflicts for admin review)
- ChangeCursor (monotonic server aggregate version marker for delta downloads)
"""
from django.conf import settings
from django.db import models


class SyncBatch(models.Model):
    """
    Offline synchronization batch header [SPEC DBDD §11].
    Groups multiple transaction uploads (up to 500 per batch [DEC-11, D11]).
    """
    STATUS_CHOICES = [
        ("IN_PROGRESS", "In Progress"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    sync_batch_id = models.AutoField(primary_key=True)
    batch_id = models.UUIDField(
        unique=True, help_text="Client-generated unique batch GUID"
    )
    device_registration = models.ForeignKey(
        "identity.DeviceRegistration", on_delete=models.PROTECT, related_name="sync_batches"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sync_batches"
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="IN_PROGRESS")
    client_cursor = models.BigIntegerField(default=0)
    server_cursor_before = models.BigIntegerField(default=0)
    server_cursor_after = models.BigIntegerField(default=0)
    transaction_count = models.IntegerField(default=0)
    sent_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sync_sync_batch"
        verbose_name = "Sync Batch"
        verbose_name_plural = "Sync Batches"

    def __str__(self):
        return f"Batch {self.batch_id} ({self.status}, {self.transaction_count} txns)"


class SyncTransaction(models.Model):
    """
    Per-transaction sync outcome and idempotency tracking [SPEC DBDD §11, Invariant 5].
    TransactionId is unique across the entire system.
    """
    ENTITY_TYPE_CHOICES = [
        ("MEAL", "Meal"),
        ("EXTRA", "Extra"),
    ]
    PROCESSING_STATUS_CHOICES = [
        ("SYNCHRONIZED", "Synchronized"),
        ("IDEMPOTENT_SUCCESS", "Idempotent Success"),
        ("DUPLICATE", "Duplicate"),
        ("REJECTED", "Rejected"),
        ("CONFLICT", "Conflict"),
    ]

    sync_transaction_id = models.AutoField(primary_key=True)
    transaction_id = models.UUIDField(
        unique=True,
        help_text="Unique operational transaction identifier [Invariant 5, DBDD §11.2]"
    )
    sync_batch = models.ForeignKey(
        SyncBatch, on_delete=models.PROTECT, related_name="transactions"
    )
    entity_type = models.CharField(max_length=50, choices=ENTITY_TYPE_CHOICES)
    entity_id = models.CharField(max_length=50, blank=True, default="")
    client_created_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    processing_status = models.CharField(
        max_length=30, choices=PROCESSING_STATUS_CHOICES
    )
    result_code = models.CharField(max_length=50, blank=True, default="")
    result_message = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "sync_sync_transaction"
        verbose_name = "Sync Transaction"
        verbose_name_plural = "Sync Transactions"
        indexes = [
            models.Index(fields=["sync_batch"], name="idx_sync_txn_batch"),
            models.Index(fields=["processing_status"], name="idx_sync_txn_proc_status"),
            models.Index(fields=["transaction_id"], name="idx_sync_txn_txn_id"),
        ]

    def __str__(self):
        return f"Txn {self.transaction_id} ({self.processing_status})"


class SyncConflict(models.Model):
    """
    Operational conflict persistence for administrative resolution [SPEC DBDD §11].
    Persists conflicts rather than silently discarding them.
    """
    RESOLUTION_CHOICES = [
        ("ACCEPTED", "Accepted"),
        ("REJECTED", "Rejected"),
    ]

    conflict_id = models.AutoField(primary_key=True)
    sync_transaction = models.ForeignKey(
        SyncTransaction, on_delete=models.PROTECT, related_name="conflicts"
    )
    conflict_type = models.CharField(max_length=50)
    conflict_reason = models.TextField()
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="resolved_conflicts"
    )
    resolution = models.CharField(
        max_length=20, choices=RESOLUTION_CHOICES, blank=True, default=""
    )
    resolution_notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "sync_sync_conflict"
        verbose_name = "Sync Conflict"
        verbose_name_plural = "Sync Conflicts"

    def __str__(self):
        return f"Conflict on Txn {self.sync_transaction_id}: {self.conflict_type}"


class ChangeCursor(models.Model):
    """
    Monotonic aggregate version marker for delta downloads [SPEC DBDD §11].
    """
    cursor_id = models.AutoField(primary_key=True)
    aggregate_type = models.CharField(
        max_length=100, unique=True,
        help_text="Aggregate name (e.g. STUDENT, MEAL_RATE, EXTRA_PRICE)"
    )
    current_version = models.BigIntegerField(
        default=1, help_text="Monotonically increasing version counter"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sync_change_cursor"
        verbose_name = "Change Cursor"
        verbose_name_plural = "Change Cursors"

    def __str__(self):
        return f"{self.aggregate_type}: v{self.current_version}"
