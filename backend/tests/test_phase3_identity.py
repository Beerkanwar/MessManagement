"""
Comprehensive Phase 3 Test Suite: Identity, Authentication, Devices, and Role-Based Access.
Enforces:
- SPEC SDD §11, §11.1, §12, §63, §64, §100, §118, §121
- SPEC DBDD §3, §3.1, §12
- DEC-03, DEC-10, DEC-11, DEC-14, DEC-18, DEC-20
"""
from datetime import date, timedelta
import io
import time
from unittest.mock import patch
import jwt
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import CommandError, call_command
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import record_audit_event, sanitize_audit_payload
from apps.config.models import ApplicationVersionPolicy
from apps.core.clock import clock
from apps.core.error_codes import ErrorCodes
from apps.core.exceptions import NotFoundError
from apps.hostel.models import Hostel, HostelClerkAssignment, Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, PasswordResetToken, RefreshToken, Role, UserRole
from apps.identity.selectors import (
    get_clerk_hostel,
    get_manager_mess,
    get_student_in_scope,
    get_user_assignment_summary,
    get_user_role,
    get_visible_students_queryset,
)
from apps.identity.services.auth_service import login_user
from apps.identity.services.token_service import (
    generate_access_token,
    generate_refresh_token,
    rotate_refresh_token,
)
from apps.mess.models import Mess, MessManagerAssignment

User = get_user_model()


class JsonAPIClient(APIClient):
    """DRF APIClient that defaults to JSON format for requests per JSONParser requirement."""

    def post(self, path, data=None, format="json", **extra):
        return super().post(path, data=data, format=format, **extra)

    def put(self, path, data=None, format="json", **extra):
        return super().put(path, data=data, format=format, **extra)

    def patch(self, path, data=None, format="json", **extra):
        return super().patch(path, data=data, format=format, **extra)


@pytest.fixture
def api_client():
    """Provides a fresh JsonAPIClient."""
    return JsonAPIClient()


@pytest.fixture(autouse=True)
def clear_cache_and_reset_clock():
    """Ensure cache and clock are pristine for each test."""
    cache.clear()
    clock.reset()
    yield
    cache.clear()
    clock.reset()


@pytest.fixture
def identity_roles(db):
    """Seed base roles for testing."""
    roles = {}
    for r in ["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]:
        role_obj, _ = Role.objects.get_or_create(name=r, defaults={"description": f"{r} role"})
        roles[r] = role_obj
    return roles


@pytest.fixture
def setup_users(db, identity_roles):
    """Creates a user for each role with active status and password."""
    users = {}
    pw = "StrongP@ssw0rd123!"

    # Super Admin
    sa = User.objects.create_superuser(
        email="admin@college.edu",
        full_name="Super Admin",
        password=pw,
    )
    UserRole.objects.get_or_create(user=sa, role=identity_roles["SUPER_ADMIN"])
    users["super_admin"] = sa

    # Hostel Clerk
    hc = User.objects.create_user(
        email="clerk@college.edu",
        full_name="Hostel Clerk",
        password=pw,
    )
    UserRole.objects.create(user=hc, role=identity_roles["HOSTEL_CLERK"])
    users["clerk"] = hc

    # Mess Manager
    mm = User.objects.create_user(
        email="manager@college.edu",
        full_name="Mess Manager",
        password=pw,
    )
    UserRole.objects.create(user=mm, role=identity_roles["MESS_MANAGER"])
    users["manager"] = mm

    # Student
    st = User.objects.create_user(
        email="student@college.edu",
        full_name="Student User",
        password=pw,
    )
    UserRole.objects.create(user=st, role=identity_roles["STUDENT"])
    users["student"] = st

    return users


# ==============================================================================
# 1. Token Security & Device Binding Tests (SDD §11.1, §100, §118)
# ==============================================================================


@pytest.mark.django_db
class TestTokenSecurityAndDeviceBinding:
    """Tests access token verification, HMAC tampering, expiration, and active device binding."""

    def test_valid_access_token_authenticates(self, api_client, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-student-1",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        token = generate_access_token(user, "STUDENT", device)

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["user"]["email"] == user.email
        assert data["role"] == "STUDENT"
        assert data["device"]["device_id"] == "dev-student-1"

    def test_unauthenticated_request_fails(self, api_client):
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == ErrorCodes.UNAUTHENTICATED

    def test_malformed_token_fails(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-jwt-token-string")
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == ErrorCodes.INVALID_TOKEN

    def test_expired_access_token_fails(self, api_client, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-expired-1",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        # Advance clock to create token in past
        now = clock.now()
        past_payload = {
            "user_id": user.user_id,
            "role": "STUDENT",
            "device_registration_id": device.device_registration_id,
            "device_id": device.device_id,
            "iss": settings.SIMPLE_JWT.get("ISSUER", "mess-management-auth"),
            "aud": settings.SIMPLE_JWT.get("AUDIENCE", "mess-management-api"),
            "iat": int((now - timedelta(minutes=30)).timestamp()),
            "exp": int((now - timedelta(minutes=15)).timestamp()),
            "jti": "exp-token-1",
        }
        signing_key = settings.SIMPLE_JWT.get("SIGNING_KEY")
        expired_token = jwt.encode(past_payload, signing_key, algorithm="HS256")

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_token}")
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == ErrorCodes.TOKEN_EXPIRED

    def test_tampered_access_token_fails(self, api_client, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-tamper-1",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        valid_token = generate_access_token(user, "STUDENT", device)
        # Sign with wrong key
        tampered_token = jwt.encode(
            jwt.decode(valid_token, options={"verify_signature": False}),
            "wrong-secret-key-at-least-32-chars-long!",
            algorithm="HS256",
        )

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tampered_token}")
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == ErrorCodes.INVALID_TOKEN

    def test_wrong_issuer_fails(self, api_client, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-iss-1",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        now = clock.now()
        payload = {
            "user_id": user.user_id,
            "role": "STUDENT",
            "device_registration_id": device.device_registration_id,
            "device_id": device.device_id,
            "iss": "untrusted-evil-issuer",
            "aud": settings.SIMPLE_JWT.get("AUDIENCE", "mess-management-api"),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "jti": "iss-1",
        }
        token = jwt.encode(payload, settings.SIMPLE_JWT.get("SIGNING_KEY"), algorithm="HS256")

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == ErrorCodes.INVALID_TOKEN

    def test_wrong_audience_fails(self, api_client, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-aud-1",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        now = clock.now()
        payload = {
            "user_id": user.user_id,
            "role": "STUDENT",
            "device_registration_id": device.device_registration_id,
            "device_id": device.device_id,
            "iss": settings.SIMPLE_JWT.get("ISSUER", "mess-management-auth"),
            "aud": "wrong-external-api",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "jti": "aud-1",
        }
        token = jwt.encode(payload, settings.SIMPLE_JWT.get("SIGNING_KEY"), algorithm="HS256")

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == ErrorCodes.INVALID_TOKEN

    def test_revoked_device_refuses_immediately(self, api_client, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-revoked-1",
            platform="ANDROID",
            session_status="REVOKED",
            revoke_reason="ADMIN_ACTION",
            registered_at=clock.now(),
        )
        token = generate_access_token(user, "STUDENT", device)

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == ErrorCodes.DEVICE_REVOKED

    def test_inactive_user_refuses_immediately(self, api_client, setup_users):
        user = setup_users["student"]
        user.status = "INACTIVE"
        user.save()
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-user-inact-1",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        token = generate_access_token(user, "STUDENT", device)

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == ErrorCodes.UNAUTHENTICATED


# ==============================================================================
# 2. Single Active Device & Session Replacement (DBDD §3, SDD §11)
# ==============================================================================


@pytest.mark.django_db(transaction=True)
class TestSingleActiveDeviceLifecycle:
    """Tests atomic replacement of prior active devices, logout, and self-revocation."""

    def test_login_replaces_old_device_and_revokes_tokens(self, api_client, setup_users):
        user = setup_users["student"]
        pw = "StrongP@ssw0rd123!"

        # 1. First login on Phone 1
        res1 = api_client.post(
            "/api/v1/auth/login",
            {
                "email": user.email,
                "password": pw,
                "device_id": "phone-1",
                "platform": "ANDROID",
            },
        )
        assert res1.status_code == status.HTTP_200_OK
        data1 = res1.json()
        token1 = data1["tokens"]["access"]
        refresh1 = data1["tokens"]["refresh"]
        dev_id1 = data1["device"]["device_registration_id"]

        # Phone 1 is active
        dev1 = DeviceRegistration.objects.get(device_registration_id=dev_id1)
        assert dev1.session_status == "ACTIVE"

        # 2. Second login on Phone 2
        res2 = api_client.post(
            "/api/v1/auth/login",
            {
                "email": user.email,
                "password": pw,
                "device_id": "phone-2",
                "platform": "ANDROID",
            },
        )
        assert res2.status_code == status.HTTP_200_OK
        data2 = res2.json()
        token2 = data2["tokens"]["access"]

        # Phone 1 is now REPLACED
        dev1.refresh_from_db()
        assert dev1.session_status == "REPLACED"
        assert dev1.revoke_reason == "NEW_DEVICE_LOGIN"

        # Phone 1 access token rejected immediately
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token1}")
        res_old = api_client.get("/api/v1/auth/me")
        assert res_old.status_code == status.HTTP_401_UNAUTHORIZED
        assert res_old.json()["code"] == ErrorCodes.DEVICE_REVOKED

        # Phone 1 refresh token rejected immediately
        res_refresh_old = api_client.post("/api/v1/auth/refresh", {"refresh": refresh1})
        assert res_refresh_old.status_code == status.HTTP_401_UNAUTHORIZED

        # Phone 2 access token works
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token2}")
        res_new = api_client.get("/api/v1/auth/me")
        assert res_new.status_code == status.HTTP_200_OK

        # Verify audit logs
        assert AuditLog.objects.filter(event_type="LOGIN_SUCCESS", entity_id=str(user.user_id)).count() == 2
        assert AuditLog.objects.filter(
            event_type="DEVICE_REVOKED",
            entity_id=str(dev_id1),
            reason="NEW_DEVICE_LOGIN",
        ).exists()

    def test_self_revoke_current_device(self, api_client, setup_users):
        user = setup_users["student"]
        login_res = api_client.post(
            "/api/v1/auth/login",
            {
                "email": user.email,
                "password": "StrongP@ssw0rd123!",
                "device_id": "phone-self-revoke",
                "platform": "ANDROID",
            },
        )
        token = login_res.json()["tokens"]["access"]
        dev_id = login_res.json()["device"]["device_registration_id"]

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        revoke_res = api_client.post("/api/v1/devices/revoke")
        assert revoke_res.status_code == status.HTTP_200_OK

        # Device is now REVOKED
        dev = DeviceRegistration.objects.get(device_registration_id=dev_id)
        assert dev.session_status == "REVOKED"

        # Subsequent requests fail immediately
        me_res = api_client.get("/api/v1/auth/me")
        assert me_res.status_code == status.HTTP_401_UNAUTHORIZED
        assert me_res.json()["code"] == ErrorCodes.DEVICE_REVOKED

    def test_user_logout_view(self, api_client, setup_users):
        user = setup_users["clerk"]
        login_res = api_client.post(
            "/api/v1/auth/login",
            {
                "email": user.email,
                "password": "StrongP@ssw0rd123!",
                "device_id": "browser-clerk-1",
                "platform": "WEB",
            },
        )
        token = login_res.json()["tokens"]["access"]
        refresh = login_res.json()["tokens"]["refresh"]
        dev_id = login_res.json()["device"]["device_registration_id"]

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        logout_res = api_client.post("/api/v1/auth/logout")
        assert logout_res.status_code == status.HTTP_200_OK

        dev = DeviceRegistration.objects.get(device_registration_id=dev_id)
        assert dev.session_status == "LOGGED_OUT"
        assert dev.revoke_reason == "LOGOUT"

        # Refresh token is revoked
        ref_res = api_client.post("/api/v1/auth/refresh", {"refresh": refresh})
        assert ref_res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_device_metadata_update(self, api_client, setup_users):
        user = setup_users["student"]
        login_res = api_client.post(
            "/api/v1/auth/login",
            {
                "email": user.email,
                "password": "StrongP@ssw0rd123!",
                "device_id": "phone-meta-1",
                "platform": "ANDROID",
                "app_version": "1.0.0",
            },
        )
        token = login_res.json()["tokens"]["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        update_res = api_client.post(
            "/api/v1/devices/register",
            {"app_version": "1.1.0", "device_name": "Pixel 8 Pro"},
        )
        assert update_res.status_code == status.HTTP_200_OK
        data = update_res.json()
        assert data["app_version"] == "1.1.0"
        assert data["device_name"] == "Pixel 8 Pro"


# ==============================================================================
# 3. Refresh Token Rotation, Replay, and Grace Window (DBDD §3, REC)
# ==============================================================================


@pytest.mark.django_db(transaction=True)
class TestRefreshTokenLifecycle:
    """Tests rotation, replaced_by chaining, 30s grace window, and theft detection."""

    def test_normal_refresh_rotation(self, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-ref-rot",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        raw_refresh, token_rec = generate_refresh_token(user, device, "ANDROID")

        result = rotate_refresh_token(raw_refresh)
        assert "access" in result
        assert "refresh" in result
        assert result["refresh"] != raw_refresh

        # Check successor pointer
        token_rec.refresh_from_db()
        assert token_rec.replaced_by is not None
        assert token_rec.replaced_by.user == user

    def test_refresh_replay_within_30s_grace_window_succeeds(self, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-ref-grace",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        raw_refresh, token_rec = generate_refresh_token(user, device, "ANDROID")

        # First rotation
        res1 = rotate_refresh_token(raw_refresh)

        # Immediate retry with the original token within 30s (dropped packet scenario)
        res2 = rotate_refresh_token(raw_refresh)
        assert "access" in res2
        assert "refresh" in res2

        # Device remains ACTIVE
        device.refresh_from_db()
        assert device.session_status == "ACTIVE"

    def test_refresh_replay_outside_30s_grace_window_detects_theft_and_revokes(self, setup_users):
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-theft",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        raw_refresh, token_rec = generate_refresh_token(user, device, "ANDROID")

        # First rotation
        res1 = rotate_refresh_token(raw_refresh)
        token_rec.refresh_from_db()

        # Advance clock by 35 seconds to simulate replay outside grace window
        future_time = token_rec.replaced_by.created_at + timedelta(seconds=35)
        with patch.object(clock, "now", return_value=future_time):
            with pytest.raises(Exception) as excinfo:
                rotate_refresh_token(raw_refresh)

        # Exception detail must signal token reuse
        assert "token_reuse_detected" in str(excinfo.value).lower()

        # Device session must be revoked immediately
        device.refresh_from_db()
        assert device.session_status == "REVOKED"
        assert device.revoke_reason == "TOKEN_REUSE_DETECTED"

        # All refresh tokens for this device must be marked revoked
        assert not RefreshToken.objects.filter(device_registration=device, is_revoked=False).exists()

        # Audit events must be recorded
        assert AuditLog.objects.filter(
            event_type="TOKEN_REUSE_DETECTED",
            entity_id=str(device.device_registration_id),
        ).exists()
        assert AuditLog.objects.filter(
            event_type="DEVICE_REVOKED",
            entity_id=str(device.device_registration_id),
            reason="TOKEN_REUSE_DETECTED",
        ).exists()

    def test_two_concurrent_refreshes_both_succeed(self, setup_users):
        """Simulates rapid concurrent refresh requests from client retry."""
        user = setup_users["student"]
        device = DeviceRegistration.objects.create(
            user=user,
            device_id="dev-concurrent-ref",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        raw_refresh, _ = generate_refresh_token(user, device, "ANDROID")

        # First rotation
        res1 = rotate_refresh_token(raw_refresh)
        # Second immediate rotation
        res2 = rotate_refresh_token(raw_refresh)

        assert res1["access"]
        assert res2["access"]
        device.refresh_from_db()
        assert device.session_status == "ACTIVE"


# ==============================================================================
# 4. Surface Authorization, Throttling & Timing Parity (DEC-10, DEC-11)
# ==============================================================================


@pytest.mark.django_db
class TestSurfaceAndLoginSecurity:
    """Tests surface-specific access barriers, login failure throttling, and timing parity."""

    def test_surface_access_rules(self, api_client, setup_users):
        pw = "StrongP@ssw0rd123!"

        # Student on WEB -> 403 WRONG_CLIENT
        res_st_web = api_client.post(
            "/api/v1/auth/login",
            {"email": setup_users["student"].email, "password": pw, "device_id": "d1", "platform": "WEB"},
        )
        assert res_st_web.status_code == status.HTTP_403_FORBIDDEN
        assert res_st_web.json()["code"] == ErrorCodes.WRONG_CLIENT

        # Manager on WEB -> 403 WRONG_CLIENT
        res_mm_web = api_client.post(
            "/api/v1/auth/login",
            {"email": setup_users["manager"].email, "password": pw, "device_id": "d2", "platform": "WEB"},
        )
        assert res_mm_web.status_code == status.HTTP_403_FORBIDDEN
        assert res_mm_web.json()["code"] == ErrorCodes.WRONG_CLIENT

        # Clerk on ANDROID -> 403 WRONG_CLIENT
        res_cl_mob = api_client.post(
            "/api/v1/auth/login",
            {"email": setup_users["clerk"].email, "password": pw, "device_id": "d3", "platform": "ANDROID"},
        )
        assert res_cl_mob.status_code == status.HTTP_403_FORBIDDEN
        assert res_cl_mob.json()["code"] == ErrorCodes.WRONG_CLIENT

        # Super Admin on IOS -> 403 WRONG_CLIENT
        res_sa_mob = api_client.post(
            "/api/v1/auth/login",
            {"email": setup_users["super_admin"].email, "password": pw, "device_id": "d4", "platform": "IOS"},
        )
        assert res_sa_mob.status_code == status.HTTP_403_FORBIDDEN
        assert res_sa_mob.json()["code"] == ErrorCodes.WRONG_CLIENT

        # Permitted combinations:
        assert api_client.post(
            "/api/v1/auth/login",
            {"email": setup_users["student"].email, "password": pw, "device_id": "d5", "platform": "ANDROID"},
        ).status_code == status.HTTP_200_OK

        assert api_client.post(
            "/api/v1/auth/login",
            {"email": setup_users["manager"].email, "password": pw, "device_id": "d6", "platform": "IOS"},
        ).status_code == status.HTTP_200_OK

        assert api_client.post(
            "/api/v1/auth/login",
            {"email": setup_users["clerk"].email, "password": pw, "device_id": "d7", "platform": "WEB"},
        ).status_code == status.HTTP_200_OK

        assert api_client.post(
            "/api/v1/auth/login",
            {"email": setup_users["super_admin"].email, "password": pw, "device_id": "d8", "platform": "WEB"},
        ).status_code == status.HTTP_200_OK

    def test_login_throttling_after_5_failures(self, api_client, setup_users):
        email = setup_users["student"].email
        # Attempt 5 failed logins
        for i in range(5):
            res = api_client.post(
                "/api/v1/auth/login",
                {"email": email, "password": "WrongPassword!", "device_id": "dev-throt", "platform": "ANDROID"},
            )
            print("DEBUG RES:", res.status_code, res.json())
            assert res.status_code == status.HTTP_401_UNAUTHORIZED

        # 6th attempt must be blocked by rate limit
        res_blocked = api_client.post(
            "/api/v1/auth/login",
            {"email": email, "password": "WrongPassword!", "device_id": "dev-throt", "platform": "ANDROID"},
        )
        assert res_blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert res_blocked.json()["code"] == ErrorCodes.RATE_LIMIT_EXCEEDED

    def test_password_stored_with_argon2id(self):
        from config.settings import base as base_settings
        assert "django.contrib.auth.hashers.Argon2PasswordHasher" in base_settings.PASSWORD_HASHERS
        assert base_settings.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"
        # Test actual Argon2id hashing
        h = make_password("SecretPassword123!", hasher="argon2")
        assert h.startswith("argon2")

    def test_unknown_email_vs_wrong_password_timing_parity(self, api_client, setup_users):
        """Verifies timing parity: both known email with wrong pw and unknown email execute dummy hash."""
        known_email = setup_users["student"].email
        unknown_email = "nonexistent.student.9999@college.edu"

        # Warm-up call
        api_client.post(
            "/api/v1/auth/login",
            {"email": known_email, "password": "WrongPassword1!", "device_id": "t1", "platform": "ANDROID"},
        )

        t0 = time.perf_counter()
        api_client.post(
            "/api/v1/auth/login",
            {"email": known_email, "password": "WrongPassword2!", "device_id": "t2", "platform": "ANDROID"},
        )
        known_duration = time.perf_counter() - t0

        t1 = time.perf_counter()
        api_client.post(
            "/api/v1/auth/login",
            {"email": unknown_email, "password": "WrongPassword2!", "device_id": "t3", "platform": "ANDROID"},
        )
        unknown_duration = time.perf_counter() - t1

        # Both durations should be roughly within a reasonable factor
        ratio = max(known_duration, unknown_duration) / max(min(known_duration, unknown_duration), 0.001)
        assert ratio < 8.0, f"Timing disparity too high: known={known_duration:.4f}s, unknown={unknown_duration:.4f}s"


# ==============================================================================
# 5. Password Reset, OTP Lifecycle & Change Password (SRS §5, SDD §12, DEC-11)
# ==============================================================================


@pytest.mark.django_db(transaction=True)
class TestPasswordResetAndOtp:
    """Tests 6-digit OTP dispatch, attempt lockout, single-use, session revocation, and change password."""

    def test_forgot_password_always_answers_202(self, api_client, setup_users):
        # Known user
        res1 = api_client.post("/api/v1/auth/forgot-password", {"email": setup_users["student"].email})
        assert res1.status_code == status.HTTP_202_ACCEPTED
        assert len(mail.outbox) == 1
        assert "Your 6-digit verification code" in mail.outbox[0].body

        # Unknown user
        res2 = api_client.post("/api/v1/auth/forgot-password", {"email": "ghost@college.edu"})
        assert res2.status_code == status.HTTP_202_ACCEPTED
        assert len(mail.outbox) == 1  # No additional email dispatched

    def test_otp_brute_force_lockout_at_5_attempts(self, api_client, setup_users):
        email = setup_users["student"].email
        api_client.post("/api/v1/auth/forgot-password", {"email": email})

        # Submit 5 incorrect OTPs
        for i in range(5):
            res = api_client.post("/api/v1/auth/verify-otp", {"email": email, "otp": "000000"})
            assert res.status_code == status.HTTP_400_BAD_REQUEST

        # 6th attempt fails with OTP_ATTEMPTS_EXCEEDED
        res6 = api_client.post("/api/v1/auth/verify-otp", {"email": email, "otp": "000000"})
        assert res6.status_code == status.HTTP_400_BAD_REQUEST
        assert "OTP_ATTEMPTS_EXCEEDED" in res6.json()["code"]

    def test_otp_expiry_after_10_minutes(self, api_client, setup_users):
        email = setup_users["student"].email
        api_client.post("/api/v1/auth/forgot-password", {"email": email})

        # Advance time by 11 minutes
        future = clock.now() + timedelta(minutes=11)
        with patch.object(clock, "now", return_value=future):
            res = api_client.post("/api/v1/auth/verify-otp", {"email": email, "otp": "123456"})
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            assert "OTP_EXPIRED" in res.json()["code"]

    def test_reset_password_success_revokes_all_sessions_and_tokens(self, api_client, setup_users):
        user = setup_users["student"]
        email = user.email

        # Establish an active session first
        login_res = api_client.post(
            "/api/v1/auth/login",
            {"email": email, "password": "StrongP@ssw0rd123!", "device_id": "active-dev", "platform": "ANDROID"},
        )
        old_access_token = login_res.json()["tokens"]["access"]
        old_dev_id = login_res.json()["device"]["device_registration_id"]

        # Request reset
        api_client.post("/api/v1/auth/forgot-password", {"email": email})
        email_body = mail.outbox[-1].body
        # Parse 6-digit code from email body
        import re

        match = re.search(r"\b(\d{6})\b", email_body)
        assert match is not None
        otp = match.group(1)

        # Verify OTP
        v_res = api_client.post("/api/v1/auth/verify-otp", {"email": email, "otp": otp})
        assert v_res.status_code == status.HTTP_200_OK

        # Reset Password
        new_pw = "NewSup3rStrongP@ssw0rd!"
        r_res = api_client.post(
            "/api/v1/auth/reset-password",
            {"email": email, "otp": otp, "new_password": new_pw},
        )
        assert r_res.status_code == status.HTTP_200_OK

        # Old device session is revoked
        old_dev = DeviceRegistration.objects.get(device_registration_id=old_dev_id)
        assert old_dev.session_status == "REVOKED"
        assert old_dev.revoke_reason == "PASSWORD_RESET"

        # Old access token rejected
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access_token}")
        assert api_client.get("/api/v1/auth/me").status_code == status.HTTP_401_UNAUTHORIZED

        # Login with new password succeeds
        api_client.credentials()  # clear auth
        new_login = api_client.post(
            "/api/v1/auth/login",
            {"email": email, "password": new_pw, "device_id": "new-dev", "platform": "ANDROID"},
        )
        assert new_login.status_code == status.HTTP_200_OK

        # Attempting to reuse the OTP fails
        reuse_res = api_client.post(
            "/api/v1/auth/reset-password",
            {"email": email, "otp": otp, "new_password": "AnotherNewPassword123!"},
        )
        assert reuse_res.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_view(self, api_client, setup_users):
        user = setup_users["student"]
        login_res = api_client.post(
            "/api/v1/auth/login",
            {"email": user.email, "password": "StrongP@ssw0rd123!", "device_id": "chg-pw-dev", "platform": "ANDROID"},
        )
        token = login_res.json()["tokens"]["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Wrong current password
        bad_res = api_client.post(
            "/api/v1/auth/change-password",
            {"current_password": "WrongPassword123!", "new_password": "NewStrongPassword123!"},
        )
        assert bad_res.status_code == status.HTTP_400_BAD_REQUEST

        # Correct change
        good_res = api_client.post(
            "/api/v1/auth/change-password",
            {"current_password": "StrongP@ssw0rd123!", "new_password": "NewStrongPassword123!"},
        )
        assert good_res.status_code == status.HTTP_200_OK
        assert AuditLog.objects.filter(
            event_type="PASSWORD_RESET",
            entity_id=str(user.user_id),
            reason="PASSWORD_CHANGED",
        ).exists()


# ==============================================================================
# 6. Scope Selectors and Object Isolation (DBDD §3.1, REC)
# ==============================================================================


@pytest.mark.django_db
class TestScopeSelectorsAndIsolation:
    """Tests student scope isolation per role: Super Admin, Clerk, Manager, Student."""

    @pytest.fixture
    def hostel_and_mess_setup(self, db, setup_users):
        h1 = Hostel.objects.create(code="H1", name="Hostel 1")
        h2 = Hostel.objects.create(code="H2", name="Hostel 2")
        m1 = Mess.objects.create(code="M1", name="Mess 1")
        m2 = Mess.objects.create(code="M2", name="Mess 2")

        # Assign Clerk to Hostel 1
        HostelClerkAssignment.objects.create(
            user=setup_users["clerk"],
            hostel=h1,
            assigned_at=clock.now(),
            is_active=True,
        )

        # Assign Manager to Mess 1
        MessManagerAssignment.objects.create(
            user=setup_users["manager"],
            mess=m1,
            assigned_at=clock.now(),
            is_active=True,
        )

        # Student 1: in Hostel 1, assigned to Mess 1
        student1 = Student.objects.create(user=setup_users["student"], roll_number="ST001", hostel=h1)
        StudentMessAssignment.objects.create(
            student=student1,
            mess=m1,
            hostel=h1,
            status="ACTIVE",
            effective_from=date(2026, 1, 1),
        )

        # Student 2: in Hostel 2, assigned to Mess 2
        u2 = User.objects.create_user(email="student2@college.edu", full_name="Student Two")
        Role.objects.get_or_create(name="STUDENT")
        UserRole.objects.create(user=u2, role=Role.objects.get(name="STUDENT"))
        student2 = Student.objects.create(user=u2, roll_number="ST002", hostel=h2)
        StudentMessAssignment.objects.create(
            student=student2,
            mess=m2,
            hostel=h2,
            status="ACTIVE",
            effective_from=date(2026, 1, 1),
        )

        return {
            "h1": h1, "h2": h2,
            "m1": m1, "m2": m2,
            "student1": student1,
            "student2": student2,
        }

    def test_student_scope_isolation(self, setup_users, hostel_and_mess_setup):
        student_user = setup_users["student"]
        st1 = hostel_and_mess_setup["student1"]
        st2 = hostel_and_mess_setup["student2"]

        # Student sees only themselves
        qs = get_visible_students_queryset(student_user)
        assert list(qs) == [st1]

        # Student requesting another student raises NotFoundError (404)
        with pytest.raises(NotFoundError) as excinfo:
            get_student_in_scope(student_user, st2.student_id)
        assert excinfo.value.code == ErrorCodes.OBJECT_NOT_FOUND

    def test_clerk_scope_isolation(self, setup_users, hostel_and_mess_setup):
        clerk_user = setup_users["clerk"]
        st1 = hostel_and_mess_setup["student1"]
        st2 = hostel_and_mess_setup["student2"]

        # Clerk assigned to H1 sees student1 but not student2
        qs = get_visible_students_queryset(clerk_user)
        assert st1 in qs
        assert st2 not in qs

        # Clerk requesting student2 raises NotFoundError (404)
        with pytest.raises(NotFoundError) as excinfo:
            get_student_in_scope(clerk_user, st2.student_id)
        assert excinfo.value.code == ErrorCodes.OBJECT_NOT_FOUND

    def test_manager_scope_isolation(self, setup_users, hostel_and_mess_setup):
        manager_user = setup_users["manager"]
        st1 = hostel_and_mess_setup["student1"]
        st2 = hostel_and_mess_setup["student2"]

        # Manager assigned to M1 sees student1 on active date
        target_date = date(2026, 6, 1)
        qs = get_visible_students_queryset(manager_user, target_date=target_date)
        assert st1 in qs
        assert st2 not in qs

        # Manager requesting student2 raises NotFoundError (404)
        with pytest.raises(NotFoundError) as excinfo:
            get_student_in_scope(manager_user, st2.student_id, target_date=target_date)
        assert excinfo.value.code == ErrorCodes.OBJECT_NOT_FOUND

    def test_super_admin_sees_all_students(self, setup_users, hostel_and_mess_setup):
        admin_user = setup_users["super_admin"]
        st1 = hostel_and_mess_setup["student1"]
        st2 = hostel_and_mess_setup["student2"]

        qs = get_visible_students_queryset(admin_user)
        assert st1 in qs
        assert st2 in qs


# ==============================================================================
# 7. Owner Change D14 & Admin Device Revocation (DEC-14, SDD §121)
# ==============================================================================


@pytest.mark.django_db(transaction=True)
class TestDeviceRevocationAndD14:
    """Tests D14 manager unsynced transactions check and Super Admin device revocation."""

    def test_manager_login_blocked_when_old_device_has_unsynced_txns(self, api_client, setup_users):
        manager = setup_users["manager"]

        # 1. Login on Manager Phone 1
        res1 = api_client.post(
            "/api/v1/auth/login",
            {"email": manager.email, "password": "StrongP@ssw0rd123!", "device_id": "mgr-phone-1", "platform": "ANDROID"},
        )
        assert res1.status_code == status.HTTP_200_OK
        dev_id1 = res1.json()["device"]["device_registration_id"]

        # 2. Simulate unsynced transactions on Phone 1
        dev1 = DeviceRegistration.objects.get(device_registration_id=dev_id1)
        cache.set(f"device_pending_sync:{dev_id1}", 5)

        # 3. Manager attempts login on Manager Phone 2
        res2 = api_client.post(
            "/api/v1/auth/login",
            {"email": manager.email, "password": "StrongP@ssw0rd123!", "device_id": "mgr-phone-2", "platform": "ANDROID"},
        )
        assert res2.status_code == status.HTTP_409_CONFLICT
        assert res2.json()["code"] == ErrorCodes.DEVICE_REVOKE_PENDING_SYNC

        # Phone 1 is marked REVOKE_PENDING_SYNC
        dev1.refresh_from_db()
        assert dev1.session_status == "REVOKE_PENDING_SYNC"

    def test_admin_revoke_device_requires_reason_and_super_admin(self, api_client, setup_users):
        student = setup_users["student"]
        admin = setup_users["super_admin"]
        clerk = setup_users["clerk"]

        dev = DeviceRegistration.objects.create(
            user=student,
            device_id="st-dev-to-revoke",
            platform="ANDROID",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )

        # 1. Non-admin caller gets 403
        clerk_dev = DeviceRegistration.objects.create(
            user=clerk, device_id="c-dev", platform="WEB", session_status="ACTIVE", registered_at=clock.now()
        )
        clerk_token = generate_access_token(clerk, "HOSTEL_CLERK", clerk_dev)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {clerk_token}")
        res_forbidden = api_client.post(
            f"/api/v1/admin/devices/{dev.device_registration_id}/revoke",
            {"reason": "Security violation"},
        )
        assert res_forbidden.status_code == status.HTTP_403_FORBIDDEN

        # 2. Admin caller missing reason gets 400
        admin_dev = DeviceRegistration.objects.create(
            user=admin, device_id="admin-dev", platform="WEB", session_status="ACTIVE", registered_at=clock.now()
        )
        admin_token = generate_access_token(admin, "SUPER_ADMIN", admin_dev)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")

        res_no_reason = api_client.post(f"/api/v1/admin/devices/{dev.device_registration_id}/revoke", {})
        assert res_no_reason.status_code == status.HTTP_400_BAD_REQUEST

        # 3. Admin caller with valid reason revokes successfully
        res_ok = api_client.post(
            f"/api/v1/admin/devices/{dev.device_registration_id}/revoke",
            {"reason": "Device reported lost by student"},
        )
        assert res_ok.status_code == status.HTTP_200_OK

        dev.refresh_from_db()
        assert dev.session_status == "REVOKED"
        assert dev.revoke_reason == "Device reported lost by student"


# ==============================================================================
# 8. Application Version Policy Enforcement (DEC-18)
# ==============================================================================


@pytest.mark.django_db
class TestAppVersionPolicy:
    """Tests mobile application version enforcement (SUPPORTED, DEPRECATED, BLOCKED)."""

    def test_blocked_app_version_returns_403(self, api_client, setup_users):
        # Create BLOCKED version policy
        ApplicationVersionPolicy.objects.create(
            platform="ANDROID",
            app_version="1.0.0",
            status="BLOCKED",
            force_update_message="Please update to version 2.0.0 from the Play Store.",
        )

        from rest_framework.test import APIRequestFactory
        from apps.identity.permissions import EnforceAppVersion
        from rest_framework.exceptions import PermissionDenied

        factory = APIRequestFactory()
        req = factory.get("/api/v1/sync/pull", HTTP_X_APP_VERSION="1.0.0", HTTP_X_PLATFORM="ANDROID")
        perm = EnforceAppVersion()
        with pytest.raises(PermissionDenied) as exc:
            perm.has_permission(req, None)
        assert "APP_VERSION_BLOCKED" in str(exc.value)


# ==============================================================================
# 9. Audit Service Sensitive Data Filtering & Log Redaction (SPEC SDD §63, §103)
# ==============================================================================


@pytest.mark.django_db
class TestAuditSanitizationAndLogging:
    """Verifies sensitive credential fields are rejected from audit events per SPEC SDD §63."""

    def test_audit_payload_sensitive_key_rejection(self):
        sensitive_payload = {
            "password": "SecretPassword123!",
            "safe_field": "Normal value",
        }
        with pytest.raises(DjangoValidationError) as exc:
            sanitize_audit_payload(sensitive_payload)
        assert "prohibited sensitive key" in str(exc.value).lower()

    def test_audit_service_truncates_oversized_values(self):
        oversized = {"big_text": "x" * 5000}
        with pytest.raises(DjangoValidationError) as exc:
            sanitize_audit_payload(oversized)
        assert "exceeds maximum allowed length" in str(exc.value).lower()


# ==============================================================================
# 10. Super Admin Bootstrap Command (ImplementationGuide Phase 3)
# ==============================================================================


@pytest.mark.django_db
class TestBootstrapSuperAdminCommand:
    """Tests interactive superadmin bootstrap command and existing-account refusal."""

    def test_bootstrap_superadmin_creates_account(self):
        inputs = [
            "first.superadmin@college.edu",  # email
            "First Super Admin",            # name
        ]

        with patch("builtins.input", side_effect=inputs):
            with patch("getpass.getpass", side_effect=["SuperAdminPass123!", "SuperAdminPass123!"]):
                out = io.StringIO()
                call_command("bootstrap_superadmin", stdout=out)

        sa = User.objects.get(normalized_email="first.superadmin@college.edu")
        assert sa.is_superuser is True
        assert get_user_role(sa) == "SUPER_ADMIN"
        assert AuditLog.objects.filter(event_type="USER_CREATED", entity_id=str(sa.user_id)).exists()

    def test_bootstrap_refuses_when_superadmin_already_exists(self, setup_users):
        # setup_users already contains a super_admin
        with pytest.raises(CommandError) as exc:
            call_command("bootstrap_superadmin")
        assert "already exists" in str(exc.value).lower()
