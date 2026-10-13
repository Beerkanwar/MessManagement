"""
Initial migration for sync app: SyncBatch, SyncTransaction, SyncConflict, ChangeCursor [SPEC DBDD §11].
Enforces:
- Unique batch_id on SyncBatch
- Unique transaction_id on SyncTransaction [Invariant 5]
- Unique aggregate_type on ChangeCursor
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("identity", "0002_phase2_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChangeCursor",
            fields=[
                ("cursor_id", models.AutoField(primary_key=True, serialize=False)),
                ("aggregate_type", models.CharField(help_text="Aggregate name (e.g. STUDENT, MEAL_RATE, EXTRA_PRICE)", max_length=100, unique=True)),
                ("current_version", models.BigIntegerField(default=1, help_text="Monotonically increasing version counter")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Change Cursor",
                "verbose_name_plural": "Change Cursors",
                "db_table": "sync_change_cursor",
            },
        ),
        migrations.CreateModel(
            name="SyncBatch",
            fields=[
                ("sync_batch_id", models.AutoField(primary_key=True, serialize=False)),
                ("batch_id", models.UUIDField(help_text="Client-generated unique batch GUID", unique=True)),
                ("status", models.CharField(choices=[("IN_PROGRESS", "In Progress"), ("COMPLETED", "Completed"), ("FAILED", "Failed")], default="IN_PROGRESS", max_length=30)),
                ("client_cursor", models.BigIntegerField(default=0)),
                ("server_cursor_before", models.BigIntegerField(default=0)),
                ("server_cursor_after", models.BigIntegerField(default=0)),
                ("transaction_count", models.IntegerField(default=0)),
                ("sent_at", models.DateTimeField()),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("device_registration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sync_batches", to="identity.deviceregistration")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sync_batches", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Sync Batch",
                "verbose_name_plural": "Sync Batches",
                "db_table": "sync_sync_batch",
            },
        ),
        migrations.CreateModel(
            name="SyncTransaction",
            fields=[
                ("sync_transaction_id", models.AutoField(primary_key=True, serialize=False)),
                ("transaction_id", models.UUIDField(help_text="Unique operational transaction identifier [Invariant 5, DBDD §11.2]", unique=True)),
                ("entity_type", models.CharField(choices=[("MEAL", "Meal"), ("EXTRA", "Extra")], max_length=50)),
                ("entity_id", models.CharField(blank=True, default="", max_length=50)),
                ("client_created_at", models.DateTimeField()),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processing_status", models.CharField(choices=[("SYNCHRONIZED", "Synchronized"), ("IDEMPOTENT_SUCCESS", "Idempotent Success"), ("DUPLICATE", "Duplicate"), ("REJECTED", "Rejected"), ("CONFLICT", "Conflict")], max_length=30)),
                ("result_code", models.CharField(blank=True, default="", max_length=50)),
                ("result_message", models.TextField(blank=True, default="")),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=255)),
                ("sync_batch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="sync.syncbatch")),
            ],
            options={
                "verbose_name": "Sync Transaction",
                "verbose_name_plural": "Sync Transactions",
                "db_table": "sync_sync_transaction",
            },
        ),
        migrations.CreateModel(
            name="SyncConflict",
            fields=[
                ("conflict_id", models.AutoField(primary_key=True, serialize=False)),
                ("conflict_type", models.CharField(max_length=50)),
                ("conflict_reason", models.TextField()),
                ("detected_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("resolution", models.CharField(blank=True, choices=[("ACCEPTED", "Accepted"), ("REJECTED", "Rejected")], default="", max_length=20)),
                ("resolution_notes", models.TextField(blank=True, default="")),
                ("resolved_by_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="resolved_conflicts", to=settings.AUTH_USER_MODEL)),
                ("sync_transaction", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="conflicts", to="sync.synctransaction")),
            ],
            options={
                "verbose_name": "Sync Conflict",
                "verbose_name_plural": "Sync Conflicts",
                "db_table": "sync_sync_conflict",
            },
        ),
        migrations.AddIndex(
            model_name="synctransaction",
            index=models.Index(fields=["sync_batch"], name="idx_sync_txn_batch"),
        ),
        migrations.AddIndex(
            model_name="synctransaction",
            index=models.Index(fields=["processing_status"], name="idx_sync_txn_proc_status"),
        ),
        migrations.AddIndex(
            model_name="synctransaction",
            index=models.Index(fields=["transaction_id"], name="idx_sync_txn_txn_id"),
        ),
    ]
