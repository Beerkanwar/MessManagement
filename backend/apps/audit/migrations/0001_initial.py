"""
Initial migration for audit app: AuditLog [SPEC DBDD §12].
Enforces:
- Three indexed access paths per DBDD §15.2
- Insert-only trigger guard [Invariant 12, DBDD-AC-33]
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_btree_gist"),
        ("identity", "0002_phase2_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("audit_id", models.AutoField(primary_key=True, serialize=False)),
                ("event_type", models.CharField(help_text="Audit event code (e.g. LOGIN_SUCCESS, DEVICE_REVOKED, ATTENDANCE_CORRECTED)", max_length=100)),
                ("entity_type", models.CharField(help_text="Target entity model name (e.g. User, Student, Bill, MealConsumption)", max_length=100)),
                ("entity_id", models.CharField(blank=True, default="", help_text="Primary key or identifier of target entity", max_length=100)),
                ("occurred_at", models.DateTimeField(help_text="When the event occurred (UTC)")),
                ("reason", models.TextField(blank=True, default="", help_text="Business justification where required (e.g. unlock, correction)")),
                ("correlation_id", models.CharField(blank=True, default="", help_text="Trace or request correlation ID", max_length=255)),
                ("old_values_json", models.JSONField(blank=True, help_text="Pre-mutation snapshot of relevant fields (sanitized)", null=True)),
                ("new_values_json", models.JSONField(blank=True, help_text="Post-mutation snapshot of relevant fields (sanitized)", null=True)),
                ("metadata_json", models.JSONField(blank=True, help_text="Additional sanitized context (IP, user agent, etc.)", null=True)),
                ("actor_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="audit_logs", to=settings.AUTH_USER_MODEL)),
                ("device_registration", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="audit_logs", to="identity.deviceregistration")),
            ],
            options={
                "verbose_name": "Audit Log",
                "verbose_name_plural": "Audit Logs",
                "db_table": "audit_audit_log",
                "ordering": ["-occurred_at"],
            },
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["entity_type", "entity_id"], name="idx_audit_entity"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["actor_user", "-occurred_at"], name="idx_audit_actor_time"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["event_type", "-occurred_at"], name="idx_audit_event_time"),
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION trg_prevent_update_or_delete_audit_log()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Table audit_audit_log is insert-only. UPDATE and DELETE operations are forbidden.';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_guard_audit_log
            BEFORE UPDATE OR DELETE ON audit_audit_log
            FOR EACH ROW
            EXECUTE FUNCTION trg_prevent_update_or_delete_audit_log();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_guard_audit_log ON audit_audit_log;
            DROP FUNCTION IF EXISTS trg_prevent_update_or_delete_audit_log();
            """,
        ),
    ]
