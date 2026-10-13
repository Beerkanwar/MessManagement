"""
Tests for optimistic concurrency control helper [SPEC DBDD §18.3].
Verifies version checking and atomic update behavior.
"""
from types import SimpleNamespace
import pytest
from apps.core.concurrency import check_optimistic_lock, execute_versioned_update
from apps.core.exceptions import ConflictError
from apps.identity.models import User


def test_check_optimistic_lock_success():
    """Version match succeeds silently."""
    instance = SimpleNamespace(version=3)
    check_optimistic_lock(instance, submitted_version=3)


def test_check_optimistic_lock_conflict():
    """Version mismatch raises ConflictError (409)."""
    instance = SimpleNamespace(version=3)
    with pytest.raises(ConflictError) as exc_info:
        check_optimistic_lock(instance, submitted_version=2)
    assert exc_info.value.code == "VERSION_CONFLICT"
    assert exc_info.value.status_code == 409


def test_check_optimistic_lock_missing_version():
    """Missing version parameter raises ConflictError (409)."""
    instance = SimpleNamespace(version=1)
    with pytest.raises(ConflictError) as exc_info:
        check_optimistic_lock(instance, submitted_version=None)
    assert exc_info.value.code == "VERSION_CONFLICT"


@pytest.mark.django_db
def test_execute_versioned_update_success_and_conflict():
    """Tests atomic versioned update and concurrency conflict on User model."""
    user = User.objects.create_user(
        email="concurrency@college.edu",
        password="TestPassword123!",
        full_name="Concurrency User",
    )
    assert user.version == 1

    # Successful update bumping version from 1 to 2
    updated = execute_versioned_update(
        User.objects.filter(user_id=user.user_id),
        submitted_version=1,
        full_name="Updated Name",
    )
    assert updated == 1

    user.refresh_from_db()
    assert user.version == 2
    assert user.full_name == "Updated Name"

    # Conflicting update with stale version (version 1) raises ConflictError
    with pytest.raises(ConflictError):
        execute_versioned_update(
            User.objects.filter(user_id=user.user_id),
            submitted_version=1,
            full_name="Stale Name",
        )
