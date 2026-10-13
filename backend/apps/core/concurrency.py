"""
Optimistic concurrency control helper enforcing SPEC DBDD §18.3.
Raises HTTP 409 Conflict when a stale version or updated_at is submitted.
"""
from typing import Any
from django.db import models
from django.db.models import F
from apps.core.exceptions import ConflictError


def check_optimistic_lock(instance: Any, submitted_version: int | None) -> None:
    """
    Validates whether the submitted version matches the instance version in memory.
    Raises ConflictError (HTTP 409) with code 'VERSION_CONFLICT' if mismatched.
    """
    if submitted_version is None:
        raise ConflictError(
            code="VERSION_CONFLICT",
            message="Version parameter is required for optimistic concurrency verification.",
        )
    if int(instance.version) != int(submitted_version):
        raise ConflictError(
            code="VERSION_CONFLICT",
            message="This record was changed by someone else. Please reload and try again.",
        )


def execute_versioned_update(queryset: models.QuerySet, submitted_version: int, **update_fields: Any) -> int:
    """
    Executes an atomic database update conditioned on the version column.
    Increments version atomically by 1.
    Raises ConflictError (HTTP 409) if the row was updated concurrently or deleted.
    """
    updated_count = queryset.filter(version=submitted_version).update(
        version=F("version") + 1,
        **update_fields
    )
    if updated_count == 0:
        raise ConflictError(
            code="VERSION_CONFLICT",
            message="This record was changed by someone else. Please reload and try again.",
        )
    return updated_count
