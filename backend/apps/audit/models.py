"""
Audit logging models matching SPEC DBDD §12.
Implements:
- AuditLog (append-only [Invariant 12], sensitive value redaction, 3 indexed access paths [DBDD §15.2])
"""
from django.conf import settings
from django.db import models
from apps.core.models import InsertOnlyModel


class AuditLog(InsertOnlyModel):
    """
    Central tamper-evident audit log [SPEC DBDD §12, Invariant 12, DBDD-AC-33].
    Append-only: No UPDATE or DELETE permitted (InsertOnlyModel + database trigger guard).
    Sensitive values (passwords, OTPs, JWTs, StudentSecretKeys, QR payloads) are never recorded [SPEC SDD §63].
    Three access paths indexed per DBDD §15.2.
    """
    audit_id = models.AutoField(primary_key=True)
    event_type = models.CharField(
        max_length=100,
        help_text="Audit event code (e.g. LOGIN_SUCCESS, DEVICE_REVOKED, ATTENDANCE_CORRECTED)"
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="audit_logs"
    )
    device_registration = models.ForeignKey(
        "identity.DeviceRegistration", on_delete=models.PROTECT,
        null=True, blank=True, related_name="audit_logs"
    )
    entity_type = models.CharField(
        max_length=100,
        help_text="Target entity model name (e.g. User, Student, Bill, MealConsumption)"
    )
    entity_id = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Primary key or identifier of target entity"
    )
    occurred_at = models.DateTimeField(
        help_text="When the event occurred (UTC)"
    )
    reason = models.TextField(
        blank=True, default="",
        help_text="Business justification where required (e.g. unlock, correction)"
    )
    correlation_id = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Trace or request correlation ID"
    )
    old_values_json = models.JSONField(
        null=True, blank=True,
        help_text="Pre-mutation snapshot of relevant fields (sanitized)"
    )
    new_values_json = models.JSONField(
        null=True, blank=True,
        help_text="Post-mutation snapshot of relevant fields (sanitized)"
    )
    metadata_json = models.JSONField(
        null=True, blank=True,
        help_text="Additional sanitized context (IP, user agent, etc.)"
    )

    class Meta:
        db_table = "audit_audit_log"
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-occurred_at"]
        indexes = [
            # Access path 1: Entity inspection
            models.Index(fields=["entity_type", "entity_id"], name="idx_audit_entity"),
            # Access path 2: Actor timeline
            models.Index(fields=["actor_user", "-occurred_at"], name="idx_audit_actor_time"),
            # Access path 3: Event type timeline
            models.Index(fields=["event_type", "-occurred_at"], name="idx_audit_event_time"),
        ]

    def __str__(self):
        return f"{self.event_type} on {self.entity_type} {self.entity_id} at {self.occurred_at}"
