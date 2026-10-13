"""
Abstract base models for timestamps and optimistic concurrency versioning.
Enforces DBDD §18.3 and Phase 1 naming conventions.
"""
from django.db import models


class TimeStampedModel(models.Model):
    """
    Abstract base model providing self-updating created_at and updated_at fields.
    """
    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")

    class Meta:
        abstract = True


class VersionedModel(TimeStampedModel):
    """
    Abstract base model providing an optimistic concurrency version column.
    Every mutable admin/config model carries version bigint [DBDD §18.3].
    """
    version = models.BigIntegerField(
        default=1,
        help_text="Optimistic concurrency control version counter"
    )

    class Meta:
        abstract = True


class InsertOnlyModel(models.Model):
    """
    Abstract base model for append-only/immutable tables [SPEC DBDD §16.1].
    Refuses update and delete at the ORM level.
    Database-level triggers provide a second guard (added via RunSQL migrations).
    Tables: AuditLog, BalanceLedgerEntry, BillAdjustment, AttendanceCorrection,
    StudentVerification, Feedback.
    """
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when row was created (UTC)"
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise ValueError(
                f"{self.__class__.__name__} is insert-only and cannot be updated."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            f"{self.__class__.__name__} is insert-only and cannot be deleted."
        )
