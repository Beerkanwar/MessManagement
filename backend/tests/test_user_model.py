"""
Tests for custom User model [SPEC DBDD §3, ImplementationGuide Phase 1].
Confirms AUTH_USER_MODEL configuration, table naming conventions,
email normalization, and password hashing before initial migrations.
"""
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from apps.identity.models import User


def test_auth_user_model_setting():
    """Confirms AUTH_USER_MODEL is correctly configured to identity.User."""
    assert settings.AUTH_USER_MODEL == "identity.User"
    assert get_user_model() is User


@pytest.mark.django_db
def test_create_user_with_dbdd_conventions():
    """
    Verifies that identity.User follows all DBDD §3 specifications:
    - Surrogate key: user_id (AutoField)
    - Normalized email: trimmed and lowercased
    - Table name: identity_user
    - Status default: ACTIVE
    - Concurrency version: 1
    """
    user = User.objects.create_user(
        email="  Test.Student@College.EDU  ",
        password="ValidPassword123#",
        full_name="Test Student",
        phone_number="+919876543210",
    )

    assert user.user_id is not None
    assert user.pk == user.user_id
    assert user.email == "Test.Student@college.edu"
    assert user.normalized_email == "test.student@college.edu"
    assert user.status == "ACTIVE"
    assert user.is_active is True
    assert user.version == 1
    assert user.created_at is not None
    assert user.updated_at is not None
    assert user._meta.db_table == "identity_user"

    # Password validation
    assert user.check_password("ValidPassword123#") is True
    assert user.check_password("WrongPassword") is False
    assert user.password != "ValidPassword123#"


@pytest.mark.django_db
def test_user_last_login_mapping():
    """Confirms last_login maps to last_login_at attribute and column."""
    from apps.core.clock import clock

    user = User.objects.create_user(
        email="login.test@college.edu",
        password="SecurePassword123!",
        full_name="Login Test",
    )
    now = clock.now()
    user.last_login = now
    user.save()

    refreshed = User.objects.get(user_id=user.user_id)
    assert refreshed.last_login is not None
    assert refreshed.last_login_at == refreshed.last_login
