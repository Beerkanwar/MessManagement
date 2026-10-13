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
