"""
Test suite for Phase 6: QR protocol, student secrets, and test vectors.
Implements test checkpoints defined in ImplementationGuide Phase 6:
- Vector suite green in Python (RFC 4231 & docs/test-vectors/qr-v1.json).
- Database inspection: secret column contains ciphertext, changing key list still decrypts.
- Permissions: Student can fetch own secret; Clerk, Manager, Super Admin get 403.
- Rotation: exactly one ACTIVE row and one RETIRED row; audit row contains no secret.
- Log capture: creating, fetching, and rotating a secret outputs no secret material.
- Backfill command: idempotent secret provisioning.
- Verification abstraction: BaseAttendanceVerifier and QRHMACVerifier.
"""
import base64
import json
import logging
import os
import struct
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.core.clock import clock
from apps.hostel.models import Hostel, Student, StudentMessAssignment
from apps.hostel.services import create_student
from apps.identity.models import DeviceRegistration, Role, StudentSecret, User, UserRole
from apps.identity.services.token_service import generate_access_token
from apps.mess.models import Mess
from apps.qr.crypto import (
    DecryptionError,
    SecretEncryptionService,
    compute_code,
    compute_code_for_time,
    compute_counter,
    compute_hmac,
    counter_to_bytes,
    generate_payload,
    parse_payload,
    truncate_mac,
    verify_qr_payload,
)
from apps.qr.services import (
    get_active_student_secret,
    provision_student_secret,
    rotate_student_secret,
)
from apps.qr.verification import (
    BaseAttendanceVerifier,
    QRHMACVerifier,
    VerificationMethod,
    VerificationResult,
    VerificationStatus,
)
from apps.sync.models import ChangeCursor


@pytest.fixture(autouse=True)
def setup_roles(db):
    """Ensure baseline application roles exist."""
    for role_name in ["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]:
        Role.objects.get_or_create(name=role_name, defaults={"description": f"{role_name} role"})


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def super_admin_user(db):
    user = User.objects.create(
        email="admin_qr@college.edu",
        normalized_email="admin_qr@college.edu",
        full_name="Super Admin QR",
        status="ACTIVE",
    )
    role = Role.objects.get(name="SUPER_ADMIN")
    UserRole.objects.create(user=user, role=role)
    return user


@pytest.fixture
def clerk_user(db):
    user = User.objects.create(
        email="clerk_qr@college.edu",
        normalized_email="clerk_qr@college.edu",
        full_name="Hostel Clerk QR",
        status="ACTIVE",
    )
    role = Role.objects.get(name="HOSTEL_CLERK")
    UserRole.objects.create(user=user, role=role)
    return user


@pytest.fixture
def manager_user(db):
    user = User.objects.create(
        email="manager_qr@college.edu",
        normalized_email="manager_qr@college.edu",
        full_name="Mess Manager QR",
        status="ACTIVE",
    )
    role = Role.objects.get(name="MESS_MANAGER")
    UserRole.objects.create(user=user, role=role)
    return user


@pytest.fixture
def sample_hostel(db):
    return Hostel.objects.create(code="BH-1", name="Boys Hostel 1", status="ACTIVE")


@pytest.fixture
def sample_mess(db):
    return Mess.objects.create(code="MESS-1", name="Central Mess 1", status="ACTIVE")


@pytest.fixture
def student_data(db, sample_hostel, sample_mess):
    user = User.objects.create(
        email="student_qr@college.edu",
        normalized_email="student_qr@college.edu",
        full_name="Student QR User",
        status="ACTIVE",
    )
    role = Role.objects.get(name="STUDENT")
    UserRole.objects.create(user=user, role=role)

    student = Student.objects.create(
        user=user,
        roll_number="23103030",
        hostel=sample_hostel,
        status="ACTIVE",
    )
    StudentMessAssignment.objects.create(
        student=student,
        mess=sample_mess,
        hostel=sample_hostel,
        status="ACTIVE",
        effective_from=clock.today(),
    )
    return user, student


def auth_client(client, user, role_name):
    """Helper to authenticate DRF client with active device binding."""
    device = DeviceRegistration.objects.filter(user=user, session_status="ACTIVE").first()
    if not device:
        device = DeviceRegistration.objects.create(
            user=user,
            device_id=f"dev-qr-{user.user_id}",
            platform="WEB",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
    token = generate_access_token(user, role_name, device)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# ==============================================================================
# 1. Cryptographic Test Vectors & RFC 4231 Verification
# ==============================================================================

@pytest.mark.django_db
class TestCryptographicVectors:
    """Verifies RFC 4231 and docs/test-vectors/qr-v1.json awkward case test vectors."""

    def test_rfc4231_suite_from_json(self):
        """Validates all 7 public RFC 4231 HMAC-SHA256 test cases."""
        vector_file = Path(settings.BASE_DIR).parent / "docs" / "test-vectors" / "qr-v1.json"
        assert vector_file.exists(), f"Test vector file missing: {vector_file}"

        with open(vector_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        rfc_cases = data.get("rfc4231_vectors", [])
        assert len(rfc_cases) == 7, "Must contain exactly 7 RFC 4231 test cases"

        for case in rfc_cases:
            key_bytes = bytes.fromhex(case["key_hex"])
            data_bytes = bytes.fromhex(case["data_hex"])
            expected = case["digest_hex"]
            digest = compute_hmac(key_bytes, data_bytes).hex()
            assert digest == expected, f"RFC 4231 case {case['case']} mismatch: {digest} != {expected}"

    def test_awkward_case_vectors_from_json(self):
        """
        Validates all awkward cases:
        - unix time 0
        - step boundaries (t=29, t=30)
        - offset 0
        - offset 15
        - top bit (MSB) set before clearing
        - six-digit code with leading zeros
        - counter near 32-bit boundary (2^32 - 1 and 2^32)
        """
        vector_file = Path(settings.BASE_DIR).parent / "docs" / "test-vectors" / "qr-v1.json"
        with open(vector_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        vectors = data.get("awkward_case_vectors", [])
        assert len(vectors) >= 7, "Awkward case vector suite must contain all edge cases"

        for v in vectors:
            secret = bytes.fromhex(v["secret"])
            t = v["unix_time"]
            step = v["step"]

            # 1. Counter calculation
            c = compute_counter(t, step)
            assert c == v["counter"], f"Counter mismatch at t={t}: {c} != {v['counter']}"

            # 2. Counter bytes encoding (8-byte big-endian)
            c_bytes = counter_to_bytes(c)
            assert c_bytes.hex() == v["counter_bytes"], f"Counter bytes mismatch at t={t}"

            # 3. HMAC-SHA256
            mac = compute_hmac(secret, c_bytes)
            assert mac.hex() == v["hmac"], f"HMAC mismatch at t={t}"

            # 4. Truncation and offset
            offset, truncated, top_bit = truncate_mac(mac)
            assert offset == v["offset"], f"Offset mismatch at t={t}: {offset} != {v['offset']}"
            assert top_bit == v["top_bit_was_set"], f"Top bit mismatch at t={t}"
            assert truncated == v["truncated"], f"Truncated int mismatch at t={t}"

            # 5. 6-digit code left-padded with zeros
            code = compute_code(secret, c)
            assert code == v["code"], f"Code mismatch at t={t}: {code} != {v['code']}"

    def test_verification_vectors_from_json(self):
        """Validates acceptance window (c, c-1, c+1) and rejection of (c±2, malformed)."""
        vector_file = Path(settings.BASE_DIR).parent / "docs" / "test-vectors" / "qr-v1.json"
        with open(vector_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        secret = bytes.fromhex(data["awkward_case_vectors"][0]["secret"])
        verifier = QRHMACVerifier(secret_bytes=secret)

        for case in data.get("verification_vectors", []):
            res = verifier.verify(
                payload=case["payload"],
                context={"unix_time": case["trusted_time"], "window": case["window"]},
            )
            assert res.is_valid == case["expected_valid"], (
                f"Verification validity failed for '{case['description']}': "
                f"got {res.is_valid}, expected {case['expected_valid']}"
            )
            if case["expected_valid"]:
                assert res.counter == case["expected_counter"], (
                    f"Counter mismatch for '{case['description']}': "
                    f"got {res.counter}, expected {case['expected_counter']}"
                )


# ==============================================================================
# 2. Database Encryption At Rest & Key Rotation
# ==============================================================================

@pytest.mark.django_db
class TestEncryptionAtRest:
    """Verifies that secrets are stored as authenticated ciphertext and key rotation works."""

    def test_secret_stored_as_ciphertext_only(self, student_data):
        user, student = student_data
        student_secret = provision_student_secret(student)

        # Inspect database record
        raw_db_secret = bytes(student_secret.encrypted_secret)
        assert len(raw_db_secret) >= 29, "Ciphertext must contain key_id (1B) + nonce (12B) + tag (16B)"

        # Plain secret must NOT exist anywhere in database row
        plain_secret = SecretEncryptionService.decrypt_secret(raw_db_secret)
        assert plain_secret not in raw_db_secret, "Plain secret must never appear inside ciphertext column"

        # Model __str__ representation must exclude secrets and ciphertexts
        model_str = str(student_secret)
        assert "Secret v1" in model_str
        assert plain_secret.hex() not in model_str
        assert raw_db_secret.hex() not in model_str

    def test_encryption_key_rotation(self, student_data):
        user, student = student_data
        key1 = b"PRIMARY_KEY_FOR_TEST_32_BYTES_!"
        key2 = b"ROTATED_KEY_FOR_TEST_32_BYTES_!"

        # Step 1: Encrypt with Key 1
        with override_settings(SECRET_ENCRYPTION_KEYS={1: key1}):
            plain = b"SECRET_DATA_TO_ENCRYPT_32_BYTES!"
            ciphertext_k1 = SecretEncryptionService.encrypt_secret(plain)
            assert ciphertext_k1[0] == 1  # Key ID 1 prefix
            assert SecretEncryptionService.decrypt_secret(ciphertext_k1) == plain

        # Step 2: Add Key 2 as primary key (first in dict)
        with override_settings(SECRET_ENCRYPTION_KEYS={2: key2, 1: key1}):
            # Old record encrypted with Key 1 STILL decrypts cleanly
            assert SecretEncryptionService.decrypt_secret(ciphertext_k1) == plain

            # New record encrypts with Key 2
            ciphertext_k2 = SecretEncryptionService.encrypt_secret(plain)
            assert ciphertext_k2[0] == 2  # Key ID 2 prefix
            assert SecretEncryptionService.decrypt_secret(ciphertext_k2) == plain

        # Step 3: Removing Key 1 makes ciphertext_k1 fail with DecryptionError
        with override_settings(SECRET_ENCRYPTION_KEYS={2: key2}):
            with pytest.raises(DecryptionError, match="No decryption key available"):
                SecretEncryptionService.decrypt_secret(ciphertext_k1)


# ==============================================================================
# 3. Student Secret API Endpoint & Role Scoping
# ==============================================================================

@pytest.mark.django_db
class TestStudentSecretEndpoint:
    """Verifies GET /api/v1/qr/secret and GET /api/v1/students/me/secret."""

    def test_student_can_fetch_own_secret(self, api_client, student_data):
        user, student = student_data
        auth_client(api_client, user, "STUDENT")

        # Call GET /api/v1/qr/secret
        resp = api_client.get("/api/v1/qr/secret")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"

        assert "secret_version" in resp.data
        assert "secret" in resp.data
        assert "effective_from" in resp.data

        # Decode base64 secret and verify it matches decrypted database secret
        decoded_bytes = base64.b64decode(resp.data["secret"])
        assert len(decoded_bytes) == 32
        _, plain_bytes = get_active_student_secret(student)
        assert decoded_bytes == plain_bytes

        # Verify Cache-Control header [SPEC SDD §21]
        assert "no-store" in resp.headers.get("Cache-Control", "")

        # Also test alias endpoint /api/v1/students/me/secret
        alias_resp = api_client.get("/api/v1/students/me/secret")
        assert alias_resp.status_code == 200
        assert alias_resp.data["secret"] == resp.data["secret"]

    def test_non_student_roles_receive_403(self, api_client, clerk_user, manager_user, super_admin_user):
        """Clerk, Manager, and Super Admin must get 403 on the student secret endpoint."""
        # 1. Hostel Clerk
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")
        resp = api_client.get("/api/v1/qr/secret")
        assert resp.status_code == 403

        # 2. Mess Manager
        auth_client(api_client, manager_user, "MESS_MANAGER")
        resp = api_client.get("/api/v1/qr/secret")
        assert resp.status_code == 403

        # 3. Super Admin
        auth_client(api_client, super_admin_user, "SUPER_ADMIN")
        resp = api_client.get("/api/v1/qr/secret")
        assert resp.status_code == 403

    def test_unauthenticated_request_receives_401(self, api_client):
        resp = api_client.get("/api/v1/qr/secret")
        assert resp.status_code == 401


# ==============================================================================
# 4. Secret Rotation & Audit Logging (DEC-13)
# ==============================================================================

@pytest.mark.django_db
class TestSecretRotation:
    """Verifies atomic secret rotation, audit trail, and mess change cursor advance."""

    def test_super_admin_rotates_student_secret(self, api_client, super_admin_user, student_data, sample_mess):
        user, student = student_data
        provision_student_secret(student)

        # Baseline: version 1 is ACTIVE
        v1 = StudentSecret.objects.get(student=student, status="ACTIVE")
        assert v1.secret_version == 1

        auth_client(api_client, super_admin_user, "SUPER_ADMIN")
        resp = api_client.post(
            "/api/v1/qr/rotate",
            data={
                "student_id": student.student_id,
                "reason": "Off-hours routine secret rotation per DEC-13",
            },
            format="json",
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
        assert resp.data["affected_count"] == 1

        # Check DB rows: exactly one RETIRED row and one ACTIVE row
        secrets = StudentSecret.objects.filter(student=student).order_by("secret_version")
        assert secrets.count() == 2

        old_secret = secrets[0]
        new_secret = secrets[1]

        assert old_secret.status == "RETIRED"
        assert old_secret.secret_version == 1
        assert old_secret.effective_to is not None
        assert old_secret.rotated_by == super_admin_user
        assert old_secret.rotated_at is not None

        assert new_secret.status == "ACTIVE"
        assert new_secret.secret_version == 2
        assert new_secret.effective_to is None

        # Verify audit trail
        audit = AuditLog.objects.filter(event_type="SECRET_ROTATED", entity_id=str(student.student_id)).first()
        assert audit is not None
        assert audit.actor_user == super_admin_user
        assert audit.reason == "Off-hours routine secret rotation per DEC-13"
        assert audit.old_values_json == {"version": 1}
        assert audit.new_values_json == {"version": 2}

        # Verify audit payload contains NO secret or ciphertext
        audit_dump = json.dumps(audit.new_values_json) + json.dumps(audit.old_values_json)
        assert "secret" not in audit_dump.lower()
        assert "key" not in audit_dump.lower()

        # Verify change cursor advanced for the student's active mess
        cursor = ChangeCursor.objects.filter(aggregate_type=f"mess:{sample_mess.mess_id}:secrets").first()
        assert cursor is not None
        assert cursor.current_version >= 1

    def test_rotate_without_reason_rejected(self, api_client, super_admin_user, student_data):
        user, student = student_data
        auth_client(api_client, super_admin_user, "SUPER_ADMIN")

        resp = api_client.post(
            "/api/v1/qr/rotate",
            data={"student_id": student.student_id, "reason": ""},
            format="json",
        )
        assert resp.status_code == 400

    def test_non_super_admin_cannot_rotate(self, api_client, clerk_user, manager_user, student_data):
        user, student = student_data
        for role, test_user in [("HOSTEL_CLERK", clerk_user), ("MESS_MANAGER", manager_user)]:
            auth_client(api_client, test_user, role)
            resp = api_client.post(
                "/api/v1/qr/rotate",
                data={"student_id": student.student_id, "reason": "Unauthorized rotation attempt"},
                format="json",
            )
            assert resp.status_code == 403


# ==============================================================================
# 5. Log Sanitization Checkpoint
# ==============================================================================

@pytest.mark.django_db
class TestLogSanitization:
    """Verifies that no secret material is leaked in logs during creation, fetch, and rotation."""

    def test_logs_contain_no_secret_material(self, api_client, super_admin_user, student_data, caplog):
        user, student = student_data
        caplog.set_level(logging.DEBUG)

        # 1. Provision secret
        student_secret = provision_student_secret(student)
        _, plain_bytes = get_active_student_secret(student)
        base64_secret = base64.b64encode(plain_bytes).decode("ascii")

        # 2. Student fetches secret via API
        auth_client(api_client, user, "STUDENT")
        resp = api_client.get("/api/v1/qr/secret")
        assert resp.status_code == 200

        # 3. Super admin rotates secret
        auth_client(api_client, super_admin_user, "SUPER_ADMIN")
        api_client.post(
            "/api/v1/qr/rotate",
            data={"student_id": student.student_id, "reason": "Sanitization verification"},
            format="json",
        )

        # Verify all captured log records
        for record in caplog.records:
            log_text = record.getMessage()
            assert base64_secret not in log_text, "Base64 secret found in logs!"
            assert plain_bytes.hex() not in log_text, "Hex secret found in logs!"


# ==============================================================================
# 6. Backfill Command & Automatic Provisioning
# ==============================================================================

@pytest.mark.django_db
class TestProvisioningAndBackfill:
    """Verifies backfill management command and automatic student secret provisioning."""

    def test_backfill_management_command(self, sample_hostel, sample_mess):
        # Create 3 students manually without secrets
        students = []
        for i in range(1, 4):
            u = User.objects.create(
                email=f"backfill_{i}@college.edu",
                normalized_email=f"backfill_{i}@college.edu",
                full_name=f"Backfill Student {i}",
                status="ACTIVE",
            )
            s = Student.objects.create(
                user=u,
                roll_number=f"2310309{i}",
                hostel=sample_hostel,
                status="ACTIVE",
            )
            students.append(s)

        assert StudentSecret.objects.count() == 0

        # Run backfill command
        call_command("backfill_student_secrets")

        # Every student now has an ACTIVE secret
        assert StudentSecret.objects.filter(status="ACTIVE").count() == 3

        # Running backfill command again is idempotent (no new secrets created)
        call_command("backfill_student_secrets")
        assert StudentSecret.objects.filter(status="ACTIVE").count() == 3

    def test_automatic_provisioning_on_student_create(self, super_admin_user, sample_hostel, sample_mess):
        result = create_student(
            email="auto_provision@college.edu",
            full_name="Auto Provisioned",
            roll_number="23103088",
            hostel_code=sample_hostel.code,
            mess_code=sample_mess.code,
            actor=super_admin_user,
        )
        student_id = result["student_id"]
        secret = StudentSecret.objects.filter(student_id=student_id, status="ACTIVE").first()
        assert secret is not None
        assert secret.secret_version == 1
        assert len(bytes(secret.encrypted_secret)) >= 29


# ==============================================================================
# 7. Verification Abstraction Layer
# ==============================================================================

@pytest.mark.django_db
class TestVerificationAbstraction:
    """Verifies BaseAttendanceVerifier and QRHMACVerifier extensibility interface."""

    def test_qr_hmac_verifier_interface(self):
        secret = b"VERIFICATION_SECRET_32_BYTES_!!"
        verifier = QRHMACVerifier(secret_bytes=secret)

        assert isinstance(verifier, BaseAttendanceVerifier)
        assert verifier.method_name == VerificationMethod.QR_HMAC_SHA256.value

        t = 1700000000
        code = compute_code_for_time(secret, t)
        payload = f"23103030|{code}"

        # 1. Success case
        res = verifier.verify(payload, context={"unix_time": t})
        assert isinstance(res, VerificationResult)
        assert res.is_valid is True
        assert res.method == "QR_HMAC_SHA256"
        assert res.status == VerificationStatus.SUCCESS.value
        assert res.roll_number == "23103030"
        assert res.counter == t // 30

        # 2. Window mismatch
        res_expired = verifier.verify(payload, context={"unix_time": t + 90})
        assert res_expired.is_valid is False
        assert res_expired.status == VerificationStatus.REJECTED.value

        # 3. Malformed payload
        res_malformed = verifier.verify("invalid_payload", context={"unix_time": t})
        assert res_malformed.is_valid is False
        assert res_malformed.status == VerificationStatus.MALFORMED_PAYLOAD.value
