"""
Test suite for Phase 8: Offline Synchronization API [SPEC SDD §52, §56, §67, §68; DBDD §11; SRS §26].
Verifies:
- Batch upload endpoint (/api/v1/sync/upload and /api/v1/upload) with meals and extras.
- Per-transaction idempotency (re-uploading same TransactionId produces IDEMPOTENT_SUCCESS).
- Logical duplicate meal detection (different TransactionId for same student/meal date/type -> DUPLICATE).
- 500-transaction batch limit enforcement (501 items -> 400 Bad Request [DEC-11, D11]).
- Manager scope enforcement (Manager 1 cannot record Student 2 assigned to Mess 2).
- Device registration check and REVOKE_PENDING_SYNC finalization upon sync completion [SPEC SDD §121, D14].
- Application version policy check (BLOCKED versions rejected with 403 [SPEC SDD §120]).
- Locked billing period handling (DEC-05: late meal accepted, late extra becomes CONFLICT).
- Pause auto-cancellation (D23 / DBDD-AC-27: active pause cancelled upon offline meal taken).
- Delta updates and cursor progression in response (student_changes, configuration_changes, new_sync_cursor).
- Sync batch history and conflict listing/resolution by Super Admin (/api/v1/sync/conflicts/<id>/resolve).
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.attendance.models import ExtraTransaction, MealConsumption
from apps.audit.models import AuditLog
from apps.billing.models import BillingPeriod
from apps.config.models import ApplicationVersionPolicy, SystemSetting
from apps.config.services import clear_settings_cache
from apps.core.clock import clock
from apps.hostel.models import Hostel, Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, RefreshToken, Role, StudentSecret, User, UserRole
from apps.identity.services.token_service import generate_access_token
from apps.mess.models import (
    ExtraItem,
    ExtraPrice,
    MealOccurrence,
    MealRate,
    MealType,
    Mess,
    MessManagerAssignment,
)
from apps.pause.models import MessPause
from apps.sync.models import ChangeCursor, SyncBatch, SyncConflict, SyncTransaction
from apps.sync.services import advance_change_cursor


@pytest.fixture(autouse=True)
def setup_roles_and_meal_types(db):
    """Ensure baseline roles and meal types exist."""
    for role_name in ["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]:
        Role.objects.get_or_create(name=role_name, defaults={"description": f"{role_name} role"})

    for code, name, seq in [
        ("BREAKFAST", "Breakfast", 1),
        ("LUNCH", "Lunch", 2),
        ("EVENING_SNACKS", "Evening Snacks", 3),
        ("DINNER", "Dinner", 4),
    ]:
        MealType.objects.get_or_create(code=code, defaults={"name": name, "sequence_no": seq})


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sync_setup(db):
    """Sets up campus environment for sync testing."""
    hostel_a = Hostel.objects.create(code="H-SYNC-A", name="Hostel Sync Alpha", status="ACTIVE")
    hostel_b = Hostel.objects.create(code="H-SYNC-B", name="Hostel Sync Beta", status="ACTIVE")

    mess_1 = Mess.objects.create(code="M-SYNC-1", name="Mess Sync 1", status="ACTIVE")
    mess_2 = Mess.objects.create(code="M-SYNC-2", name="Mess Sync 2", status="ACTIVE")

    # Super Admin
    admin_user = User.objects.create(
        email="admin_sync@college.edu", normalized_email="admin_sync@college.edu", full_name="Super Admin Sync", status="ACTIVE"
    )
    UserRole.objects.create(user=admin_user, role=Role.objects.get(name="SUPER_ADMIN"))
    admin_device = DeviceRegistration.objects.create(
        user=admin_user, device_id="dev-admin-sync", platform="WEB", session_status="ACTIVE", registered_at=clock.now()
    )

    # Manager 1 (Mess 1)
    mgr_1_user = User.objects.create(
        email="mgr_sync_1@college.edu", normalized_email="mgr_sync_1@college.edu", full_name="Manager Mess 1", status="ACTIVE"
    )
    UserRole.objects.create(user=mgr_1_user, role=Role.objects.get(name="MESS_MANAGER"))
    MessManagerAssignment.objects.create(user=mgr_1_user, mess=mess_1, is_active=True, assigned_at=clock.now())
    device_mgr_1 = DeviceRegistration.objects.create(
        user=mgr_1_user, device_id="dev-mgr-sync-1", platform="ANDROID", session_status="ACTIVE", registered_at=clock.now()
    )

    # Manager 2 (Mess 2)
    mgr_2_user = User.objects.create(
        email="mgr_sync_2@college.edu", normalized_email="mgr_sync_2@college.edu", full_name="Manager Mess 2", status="ACTIVE"
    )
    UserRole.objects.create(user=mgr_2_user, role=Role.objects.get(name="MESS_MANAGER"))
    MessManagerAssignment.objects.create(user=mgr_2_user, mess=mess_2, is_active=True, assigned_at=clock.now())
    device_mgr_2 = DeviceRegistration.objects.create(
        user=mgr_2_user, device_id="dev-mgr-sync-2", platform="ANDROID", session_status="ACTIVE", registered_at=clock.now()
    )

    # Student 1 -> Mess 1
    s1_user = User.objects.create(
        email="student_sync_1@college.edu", normalized_email="student_sync_1@college.edu", full_name="Student Sync 1", status="ACTIVE"
    )
    UserRole.objects.create(user=s1_user, role=Role.objects.get(name="STUDENT"))
    student_1 = Student.objects.create(user=s1_user, roll_number="23108001", hostel=hostel_a, status="ACTIVE")
    StudentMessAssignment.objects.create(
        student=student_1, hostel=hostel_a, mess=mess_1, status="ACTIVE", effective_from=date(2026, 11, 1)
    )
    StudentSecret.objects.create(
        student=student_1, encrypted_secret=b"cipher1", secret_version=1, status="ACTIVE", effective_from=clock.now()
    )

    # Student 2 -> Mess 2
    s2_user = User.objects.create(
        email="student_sync_2@college.edu", normalized_email="student_sync_2@college.edu", full_name="Student Sync 2", status="ACTIVE"
    )
    UserRole.objects.create(user=s2_user, role=Role.objects.get(name="STUDENT"))
    student_2 = Student.objects.create(user=s2_user, roll_number="23108002", hostel=hostel_b, status="ACTIVE")
    StudentMessAssignment.objects.create(
        student=student_2, hostel=hostel_b, mess=mess_2, status="ACTIVE", effective_from=date(2026, 11, 1)
    )
    StudentSecret.objects.create(
        student=student_2, encrypted_secret=b"cipher2", secret_version=1, status="ACTIVE", effective_from=clock.now()
    )

    # Meal Occurrences & Rates for 2026-11-09
    sync_date = date(2026, 11, 9)
    bf = MealType.objects.get(code="BREAKFAST")
    lunch = MealType.objects.get(code="LUNCH")
    dinner = MealType.objects.get(code="DINNER")

    MealOccurrence.objects.create(mess=mess_1, meal_date=sync_date, meal_type=lunch, status="SCHEDULED")
    MealOccurrence.objects.create(mess=mess_1, meal_date=sync_date, meal_type=dinner, status="SCHEDULED")
    MealOccurrence.objects.create(mess=mess_2, meal_date=sync_date, meal_type=lunch, status="SCHEDULED")

    MealRate.objects.create(mess=mess_1, effective_from=date(2026, 11, 1), rate=Decimal("48.0000"), created_by=admin_user)
    MealRate.objects.create(mess=mess_2, effective_from=date(2026, 11, 1), rate=Decimal("52.0000"), created_by=admin_user)

    # Extra Items
    extra_1 = ExtraItem.objects.create(hostel=hostel_a, name="Paneer Tikka", status="ACTIVE")
    ExtraPrice.objects.create(extra_item=extra_1, effective_from=date(2026, 11, 1), unit_price=Decimal("25.0000"), created_by=admin_user)

    # Open Billing Period
    period = BillingPeriod.objects.create(
        year=2026, month=11, period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), status="OPEN"
    )

    return {
        "hostel_a": hostel_a,
        "hostel_b": hostel_b,
        "mess_1": mess_1,
        "mess_2": mess_2,
        "admin_user": admin_user,
        "admin_device": admin_device,
        "mgr_1_user": mgr_1_user,
        "mgr_2_user": mgr_2_user,
        "device_mgr_1": device_mgr_1,
        "device_mgr_2": device_mgr_2,
        "student_1": student_1,
        "student_2": student_2,
        "sync_date": sync_date,
        "lunch": lunch,
        "dinner": dinner,
        "extra_1": extra_1,
        "period": period,
    }


def auth_client(client, user, role_name, device):
    token = generate_access_token(user, role_name, device)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# ==============================================================================
# 1. Batch Upload & Per-Transaction Idempotency
# ==============================================================================

@pytest.mark.django_db
class TestSyncBatchUploadPipeline:
    """Verifies offline sync batch execution, idempotency, and outcome reporting [SPEC SDD §52, §67]."""

    def test_successful_batch_upload_with_meals_and_extras(self, api_client, sync_setup):
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        s1 = sync_setup["student_1"]
        extra = sync_setup["extra_1"]
        sync_date = sync_setup["sync_date"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        txn_meal_id = uuid.uuid4()
        txn_extra_id = uuid.uuid4()

        payload = {
            "device_id": dev.device_id,
            "client_version": "1.0.0",
            "last_server_version": 0,
            "trusted_time_metadata": {"is_valid": True},
            "transactions": [
                {
                    "transaction_id": str(txn_meal_id),
                    "entity_type": "MEAL",
                    "client_created_at": "2026-11-09T12:30:00Z",
                    "payload": {
                        "student_id": s1.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "meal_type": "LUNCH",
                        "meal_date": str(sync_date),
                        "transaction_timestamp": "2026-11-09T12:30:00Z",
                        "verification_method": "QR_HMAC_SHA256",
                        "verification_result": "SUCCESS",
                    },
                },
                {
                    "transaction_id": str(txn_extra_id),
                    "entity_type": "EXTRA",
                    "client_created_at": "2026-11-09T12:32:00Z",
                    "payload": {
                        "student_id": s1.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "extra_item_id": extra.extra_item_id,
                        "quantity": 2,
                        "transaction_timestamp": "2026-11-09T12:32:00Z",
                    },
                },
            ],
        }

        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert "server_time" in data
        assert data["authorization_state"] in ["ACTIVE", "OFFLINE_NORMAL"]
        assert data["new_sync_cursor"] >= 1
        assert len(data["student_changes"]) >= 1
        assert "meal_rate" in data["configuration_changes"]

        results = data["transaction_results"]
        assert len(results) == 2
        assert str(results[0]["transaction_id"]) == str(txn_meal_id)
        assert results[0]["status"] == "SYNCHRONIZED"
        assert str(results[1]["transaction_id"]) == str(txn_extra_id)
        assert results[1]["status"] == "SYNCHRONIZED"

        # Verify DB records
        assert MealConsumption.objects.filter(transaction_id=txn_meal_id).exists()
        assert ExtraTransaction.objects.filter(transaction_id=txn_extra_id).exists()
        assert SyncBatch.objects.filter(device_registration=dev, status="COMPLETED").exists()
        assert SyncTransaction.objects.filter(transaction_id=txn_meal_id, processing_status="SYNCHRONIZED").exists()
        assert SyncTransaction.objects.filter(transaction_id=txn_extra_id, processing_status="SYNCHRONIZED").exists()
        assert AuditLog.objects.filter(event_type="SYNC_SUCCESS").exists()

    def test_reupload_same_batch_returns_idempotent_success(self, api_client, sync_setup):
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        s1 = sync_setup["student_1"]
        sync_date = sync_setup["sync_date"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        txn_id = uuid.uuid4()
        payload = {
            "device_id": dev.device_id,
            "client_version": "1.0.0",
            "last_server_version": 0,
            "transactions": [
                {
                    "transaction_id": str(txn_id),
                    "entity_type": "MEAL",
                    "client_created_at": "2026-11-09T12:30:00Z",
                    "payload": {
                        "student_id": s1.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "meal_type": "LUNCH",
                        "meal_date": str(sync_date),
                    },
                }
            ],
        }

        # First upload
        resp1 = client.post("/api/v1/sync/upload", payload, format="json")
        assert resp1.status_code == status.HTTP_200_OK
        assert resp1.data["transaction_results"][0]["status"] == "SYNCHRONIZED"

        # Second upload (same transaction_id)
        resp2 = client.post("/api/v1/sync/upload", payload, format="json")
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.data["transaction_results"][0]["status"] in ["IDEMPOTENT_SUCCESS", "SYNCHRONIZED"]

        # Exactly 1 meal consumption record must exist
        assert MealConsumption.objects.filter(student=s1, meal_date=sync_date).count() == 1

    def test_logical_duplicate_meal_in_different_transaction(self, api_client, sync_setup):
        """Second distinct transaction for same student/date/meal is DUPLICATE [DBDD §11.1]."""
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        s1 = sync_setup["student_1"]
        sync_date = sync_setup["sync_date"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        txn1 = uuid.uuid4()
        txn2 = uuid.uuid4()

        payload = {
            "device_id": dev.device_id,
            "client_version": "1.0.0",
            "transactions": [
                {
                    "transaction_id": str(txn1),
                    "entity_type": "MEAL",
                    "client_created_at": "2026-11-09T12:30:00Z",
                    "payload": {
                        "student_id": s1.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "meal_type": "LUNCH",
                        "meal_date": str(sync_date),
                    },
                },
                {
                    "transaction_id": str(txn2),
                    "entity_type": "MEAL",
                    "client_created_at": "2026-11-09T12:35:00Z",
                    "payload": {
                        "student_id": s1.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "meal_type": "LUNCH",
                        "meal_date": str(sync_date),
                    },
                },
            ],
        }

        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["transaction_results"]
        assert results[0]["status"] == "SYNCHRONIZED"
        assert results[1]["status"] == "DUPLICATE"
        assert results[1]["result_code"] == "DUPLICATE"

        assert MealConsumption.objects.filter(student=s1, meal_date=sync_date).count() == 1


# ==============================================================================
# 2. Batch Limits and Scope Enforcement
# ==============================================================================

@pytest.mark.django_db
class TestSyncBatchLimitsAndScope:
    """Verifies batch capacity, manager assignment boundaries, and caller roles."""

    def test_batch_limit_exceeded_501_rejected(self, api_client, sync_setup):
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        oversized_txns = [
            {
                "transaction_id": str(uuid.uuid4()),
                "entity_type": "MEAL",
                "client_created_at": "2026-11-09T12:30:00Z",
                "payload": {"student_id": 1, "meal_type": "LUNCH", "meal_date": "2026-11-09"},
            }
            for _ in range(501)
        ]

        payload = {
            "device_id": dev.device_id,
            "client_version": "1.0.0",
            "transactions": oversized_txns,
        }

        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert AuditLog.objects.filter(event_type="SYNC_FAILURE").exists()

    def test_manager_scope_unauthorized_student_rejected(self, api_client, sync_setup):
        """Manager 1 cannot record Student 2 who belongs to Mess 2."""
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        s2 = sync_setup["student_2"]
        sync_date = sync_setup["sync_date"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        txn_id = uuid.uuid4()
        payload = {
            "device_id": dev.device_id,
            "transactions": [
                {
                    "transaction_id": str(txn_id),
                    "entity_type": "MEAL",
                    "client_created_at": "2026-11-09T12:30:00Z",
                    "payload": {
                        "student_id": s2.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "meal_type": "LUNCH",
                        "meal_date": str(sync_date),
                    },
                }
            ],
        }

        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        res = response.data["transaction_results"][0]
        assert res["status"] in ["REJECTED", "CONFLICT"]
        assert "ASSIGNMENT_MISMATCH" in res["result_code"] or "different mess" in res["result_message"]

    def test_non_manager_role_forbidden(self, api_client, sync_setup):
        """Student or Clerk user calling sync/upload gets 403 Forbidden."""
        student_user = sync_setup["student_1"].user
        dev = DeviceRegistration.objects.create(
            user=student_user, device_id="dev-s1", platform="ANDROID", session_status="ACTIVE", registered_at=clock.now()
        )
        client = auth_client(api_client, student_user, "STUDENT", dev)

        payload = {"device_id": dev.device_id, "transactions": []}
        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert AuditLog.objects.filter(event_type="SYNC_FAILURE").exists()


# ==============================================================================
# 3. Device Binding & Revocation Flow (D14 / SDD §121)
# ==============================================================================

@pytest.mark.django_db
class TestSyncDeviceRevocationFlow:
    """Verifies REVOKE_PENDING_SYNC finalization upon sync completion."""

    def test_revoked_device_cannot_sync(self, api_client, sync_setup):
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        dev.session_status = "REVOKED"
        dev.save()

        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)
        payload = {"device_id": dev.device_id, "transactions": []}
        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_revoke_pending_sync_device_finalized_upon_sync(self, api_client, sync_setup):
        """Device in REVOKE_PENDING_SYNC completes sync and becomes REVOKED [SPEC SDD §121, D14]."""
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        dev.session_status = "REVOKE_PENDING_SYNC"
        dev.save()

        # Create refresh token to verify revocation
        rt = RefreshToken.objects.create(
            user=mgr, device_registration=dev, token_hash="samplehash123", expires_at=clock.now() + timedelta(days=7)
        )

        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)
        payload = {"device_id": dev.device_id, "transactions": []}
        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        dev.refresh_from_db()
        assert dev.session_status == "REVOKED"
        assert dev.revoked_at is not None

        rt.refresh_from_db()
        assert rt.is_revoked is True
        assert AuditLog.objects.filter(event_type="DEVICE_REVOKED").exists()

    def test_blocked_application_version_rejected(self, api_client, sync_setup):
        """ApplicationVersionPolicy with status=BLOCKED rejects upload [SPEC SDD §120]."""
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        ApplicationVersionPolicy.objects.create(
            platform="ANDROID", app_version="0.8.0", status="BLOCKED"
        )

        payload = {"device_id": dev.device_id, "client_version": "0.8.0", "transactions": []}
        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "blocked from synchronizing" in str(response.data)


# ==============================================================================
# 4. Locked Billing Period & Pause Cancellation
# ==============================================================================

@pytest.mark.django_db
class TestSyncLockedBillingAndPause:
    """Verifies DEC-05 (locked billing period) and D23 (active pause cancellation)."""

    def test_locked_billing_period_meal_accepted_extra_conflict(self, api_client, sync_setup):
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        s1 = sync_setup["student_1"]
        extra = sync_setup["extra_1"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        # Lock the billing period
        period = sync_setup["period"]
        period.status = "LOCKED"
        period.save()

        txn_meal = uuid.uuid4()
        txn_extra = uuid.uuid4()
        sync_date = sync_setup["sync_date"]

        payload = {
            "device_id": dev.device_id,
            "transactions": [
                {
                    "transaction_id": str(txn_meal),
                    "entity_type": "MEAL",
                    "client_created_at": "2026-11-09T12:30:00Z",
                    "payload": {
                        "student_id": s1.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "meal_type": "LUNCH",
                        "meal_date": str(sync_date),
                    },
                },
                {
                    "transaction_id": str(txn_extra),
                    "entity_type": "EXTRA",
                    "client_created_at": "2026-11-09T12:35:00Z",
                    "payload": {
                        "student_id": s1.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "extra_item_id": extra.extra_item_id,
                        "quantity": 1,
                    },
                },
            ],
        }

        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        results = response.data["transaction_results"]
        # DEC-05: Late meal is accepted
        assert results[0]["status"] == "SYNCHRONIZED"
        # DEC-05: Late extra becomes CONFLICT
        assert results[1]["status"] == "CONFLICT"
        assert "BILLING_PERIOD_LOCKED" in results[1]["result_code"]

        # Conflict persisted in DB
        assert SyncConflict.objects.filter(sync_transaction__transaction_id=txn_extra).exists()

    def test_active_pause_cancelled_when_meal_synced(self, api_client, sync_setup):
        """Meal taken during ACTIVE pause automatically cancels remaining pause [D23, DBDD-AC-27]."""
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        s1 = sync_setup["student_1"]
        sync_date = sync_setup["sync_date"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        # Create active pause
        pause = MessPause.objects.create(
            student=s1,
            mess=sync_setup["mess_1"],
            requested_start_date=sync_date - timedelta(days=2),
            requested_end_date=sync_date + timedelta(days=5),
            effective_start_date=sync_date - timedelta(days=1),
            effective_end_date=sync_date + timedelta(days=5),
            status="ACTIVE",
            requested_at=clock.now() - timedelta(days=3),
        )

        txn_id = uuid.uuid4()
        payload = {
            "device_id": dev.device_id,
            "transactions": [
                {
                    "transaction_id": str(txn_id),
                    "entity_type": "MEAL",
                    "client_created_at": "2026-11-09T12:30:00Z",
                    "payload": {
                        "student_id": s1.student_id,
                        "mess_id": sync_setup["mess_1"].mess_id,
                        "meal_type": "LUNCH",
                        "meal_date": str(sync_date),
                    },
                }
            ],
        }

        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["transaction_results"][0]["status"] == "SYNCHRONIZED"

        pause.refresh_from_db()
        assert pause.status == "CANCELLED"
        assert pause.cancellation_reason == "MEAL_TAKEN"


# ==============================================================================
# 5. Conflict Resolution and Sync History APIs
# ==============================================================================

@pytest.mark.django_db
class TestSyncConflictResolutionAndHistory:
    """Verifies Super Admin conflict inspection and resolution [SPEC DBDD §11, App Flow §13]."""

    def test_super_admin_rejects_locked_period_conflict(self, api_client, sync_setup):
        admin = sync_setup["admin_user"]
        dev = sync_setup["admin_device"]
        client = auth_client(api_client, admin, "SUPER_ADMIN", dev)

        # Create batch, transaction, and conflict
        batch = SyncBatch.objects.create(
            batch_id=uuid.uuid4(),
            device_registration=sync_setup["device_mgr_1"],
            user=sync_setup["mgr_1_user"],
            status="COMPLETED",
            sent_at=clock.now(),
        )
        st = SyncTransaction.objects.create(
            transaction_id=uuid.uuid4(),
            sync_batch=batch,
            entity_type="EXTRA",
            client_created_at=clock.now(),
            processing_status="CONFLICT",
            result_code="BILLING_PERIOD_LOCKED",
            result_message="Late extra",
        )
        conflict = SyncConflict.objects.create(
            sync_transaction=st,
            conflict_type="BILLING_PERIOD_LOCKED",
            conflict_reason="Late extra against locked period",
        )

        # List conflicts
        list_resp = client.get("/api/v1/sync/conflicts")
        assert list_resp.status_code == status.HTTP_200_OK
        assert len(list_resp.data) >= 1

        # Reading one conflict is part of the Super Admin review screen.
        detail_resp = client.get(f"/api/v1/sync/conflicts/{conflict.conflict_id}")
        assert detail_resp.status_code == status.HTTP_200_OK
        assert detail_resp.data["conflict_id"] == conflict.conflict_id

        # A locked period is never waivable [DEC-17].
        accepted_resp = client.post(
            f"/api/v1/sync/conflicts/{conflict.conflict_id}/resolve",
            {"resolution": "ACCEPTED", "notes": "Try to force it"},
            format="json",
        )
        assert accepted_resp.status_code == status.HTTP_409_CONFLICT
        assert accepted_resp.data["code"] == "LOCKED_PERIOD_NOT_WAIVABLE"

        # Resolve conflict
        resolve_resp = client.post(
            f"/api/v1/sync/conflicts/{conflict.conflict_id}/resolve",
            {"resolution": "REJECTED", "notes": "Approved by warden after review"},
            format="json",
        )
        assert resolve_resp.status_code == status.HTTP_200_OK
        assert resolve_resp.data["resolution"] == "REJECTED"
        assert resolve_resp.data["resolution_notes"] == "Approved by warden after review"

        conflict.refresh_from_db()
        assert conflict.resolution == "REJECTED"
        assert conflict.resolved_by_user == admin
        assert AuditLog.objects.filter(event_type="SYNC_CONFLICT_RESOLVED").exists()

    def test_super_admin_accepts_assignment_conflict_and_replays(self, api_client, sync_setup):
        """ACCEPTED re-runs the command with only the conflicting check waived [DEC-17]."""
        admin = sync_setup["admin_user"]
        admin_dev = sync_setup["admin_device"]
        client = auth_client(api_client, admin, "SUPER_ADMIN", admin_dev)

        student = sync_setup["student_1"]
        mess = sync_setup["mess_1"]
        dev = sync_setup["device_mgr_1"]
        sync_date = sync_setup["sync_date"]

        # Student starts their Mess 1 assignment after the meal date, so the
        # original upload conflicted with NO_ASSIGNMENT_ON_DATE.
        assignment = StudentMessAssignment.objects.get(student=student)
        assignment.effective_from = sync_date + timedelta(days=1)
        assignment.save(update_fields=["effective_from"])

        txn_id = uuid.uuid4()
        batch = SyncBatch.objects.create(
            batch_id=uuid.uuid4(),
            device_registration=dev,
            user=sync_setup["mgr_1_user"],
            status="COMPLETED",
            sent_at=clock.now(),
        )
        payload = {
            "student_id": student.student_id,
            "mess_id": mess.mess_id,
            "meal_type": "LUNCH",
            "meal_date": str(sync_date),
            "transaction_timestamp": f"{sync_date}T12:30:00Z",
        }
        st = SyncTransaction.objects.create(
            transaction_id=txn_id,
            sync_batch=batch,
            entity_type="MEAL_CONSUMPTION",
            client_created_at=clock.now(),
            processing_status="CONFLICT",
            result_code="NO_ASSIGNMENT_ON_DATE",
            result_message="Student had no active mess assignment on MealDate.",
            client_payload=payload,
        )
        conflict = SyncConflict.objects.create(
            sync_transaction=st,
            conflict_type="ASSIGNMENT_CHANGED",
            conflict_reason="Student had no active mess assignment on MealDate.",
        )

        resolve_resp = client.post(
            f"/api/v1/sync/conflicts/{conflict.conflict_id}/resolve",
            {"resolution": "ACCEPTED", "notes": "Assignment record was late"},
            format="json",
        )
        assert resolve_resp.status_code == status.HTTP_200_OK
        assert resolve_resp.data["resolution"] == "ACCEPTED"

        # The record is created once, with Source SYNC_RESOLUTION.
        meal = MealConsumption.objects.get(transaction_id=txn_id)
        assert meal.source == "SYNC_RESOLUTION"

        # A second ACCEPTED attempt cannot create it again.
        again = client.post(
            f"/api/v1/sync/conflicts/{conflict.conflict_id}/resolve",
            {"resolution": "ACCEPTED", "notes": "again"},
            format="json",
        )
        assert again.status_code == status.HTTP_409_CONFLICT
        assert MealConsumption.objects.filter(transaction_id=txn_id).count() == 1

        # The Manager sees the final outcome through resolved results.
        mgr = sync_setup["mgr_1_user"]
        mgr_client = auth_client(APIClient(), mgr, "MESS_MANAGER", dev)
        sync_resp = mgr_client.post(
            "/api/v1/sync/upload",
            {"device_id": dev.device_id, "last_server_version": 0, "transactions": []},
            format="json",
        )
        assert sync_resp.status_code == status.HTTP_200_OK
        resolved = {str(row["transaction_id"]): row for row in sync_resp.data["resolved_results"]}
        assert resolved[str(txn_id)]["status"] == "SYNCHRONIZED"
        assert resolved[str(txn_id)]["resolution"] == "ACCEPTED"

    def test_sync_batches_list_endpoint(self, api_client, sync_setup):
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        SyncBatch.objects.create(
            batch_id=uuid.uuid4(),
            device_registration=dev,
            user=mgr,
            status="COMPLETED",
            transaction_count=5,
            sent_at=clock.now(),
        )

        response = client.get("/api/v1/sync/batches")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1


# ==============================================================================
# 6. Build-checkpoint scenarios [ImplementationGuide Phase 8]
# ==============================================================================

@pytest.mark.django_db
class TestSyncGuideCheckpoints:
    """Covers the Phase 8 build and test checkpoints end to end."""

    def _meal_item(self, setup, txn_id, meal_type="LUNCH", minute=30):
        return {
            "transaction_id": str(txn_id),
            "entity_type": "MEAL_CONSUMPTION",
            "client_created_at": f"2026-11-09T12:{minute:02d}:00Z",
            "payload": {
                "student_id": setup["student_1"].student_id,
                "mess_id": setup["mess_1"].mess_id,
                "meal_type": meal_type,
                "meal_date": str(setup["sync_date"]),
                "transaction_timestamp": f"2026-11-09T12:{minute:02d}:00Z",
            },
        }

    def _extra_item(self, setup, txn_id, minute=30):
        return {
            "transaction_id": str(txn_id),
            "entity_type": "EXTRA_TRANSACTION",
            "client_created_at": f"2026-11-09T12:{minute:02d}:00Z",
            "payload": {
                "student_id": setup["student_1"].student_id,
                "mess_id": setup["mess_1"].mess_id,
                "extra_item_id": setup["extra_1"].extra_item_id,
                "quantity": 1,
                "transaction_timestamp": f"2026-11-09T12:{minute:02d}:00Z",
            },
        }

    def test_replaying_completed_batch_id_returns_stored_results(
        self, api_client, sync_setup
    ):
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        batch_id = uuid.uuid4()
        txn_id = uuid.uuid4()
        payload = {
            "batch_id": str(batch_id),
            "device_id": dev.device_id,
            "transactions": [self._meal_item(sync_setup, txn_id)],
        }

        first = client.post("/api/v1/sync/upload", payload, format="json")
        second = client.post("/api/v1/sync/upload", payload, format="json")

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert second.data["batch_id"] == str(batch_id)
        assert second.data["transaction_results"] == first.data["transaction_results"]
        assert SyncBatch.objects.filter(batch_id=batch_id).count() == 1
        assert SyncTransaction.objects.filter(transaction_id=txn_id).count() == 1
        assert MealConsumption.objects.filter(transaction_id=txn_id).count() == 1

    def test_partial_batch_resumes_without_duplicates(self, api_client, sync_setup):
        """Server killed after half the items: resend completes the rest [build 2-3]."""
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        batch_id = uuid.uuid4()
        first_txn = uuid.uuid4()
        second_txn = uuid.uuid4()
        batch = SyncBatch.objects.create(
            batch_id=batch_id,
            device_registration=dev,
            user=mgr,
            status="IN_PROGRESS",
            sent_at=clock.now(),
        )
        SyncTransaction.objects.create(
            transaction_id=first_txn,
            sync_batch=batch,
            entity_type="MEAL_CONSUMPTION",
            client_created_at=clock.now() - timedelta(minutes=5),
            processing_status="SYNCHRONIZED",
            result_code="SYNCHRONIZED",
        )

        payload = {
            "batch_id": str(batch_id),
            "device_id": dev.device_id,
            "transactions": [
                self._meal_item(sync_setup, first_txn, "LUNCH", 30),
                self._meal_item(sync_setup, second_txn, "DINNER", 40),
            ],
        }
        response = client.post("/api/v1/sync/upload", payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        by_id = {
            str(row["transaction_id"]): row
            for row in response.data["transaction_results"]
        }
        assert by_id[str(first_txn)]["status"] == "SYNCHRONIZED"
        assert by_id[str(second_txn)]["status"] == "SYNCHRONIZED"

        batch.refresh_from_db()
        assert batch.status == "COMPLETED"
        assert batch.transactions.count() == 2
        assert MealConsumption.objects.filter(transaction_id=second_txn).count() == 1

    def test_transfer_removes_from_old_cache_and_adds_to_new(
        self, api_client, sync_setup
    ):
        mgr_1 = sync_setup["mgr_1_user"]
        dev_1 = sync_setup["device_mgr_1"]
        mgr_2 = sync_setup["mgr_2_user"]
        dev_2 = sync_setup["device_mgr_2"]
        student = sync_setup["student_1"]
        sync_date = sync_setup["sync_date"]

        client_1 = auth_client(api_client, mgr_1, "MESS_MANAGER", dev_1)
        first = client_1.post(
            "/api/v1/sync/upload",
            {"device_id": dev_1.device_id, "last_server_version": 0, "transactions": []},
            format="json",
        )
        assert first.status_code == status.HTTP_200_OK
        assert student.student_id in {
            row["student_id"] for row in first.data["student_changes"]
        }

        old_assignment = StudentMessAssignment.objects.get(
            student=student, mess=sync_setup["mess_1"]
        )
        old_assignment.status = "ENDED"
        old_assignment.effective_to = sync_date
        old_assignment.save()
        StudentMessAssignment.objects.create(
            student=student,
            hostel=sync_setup["hostel_b"],
            mess=sync_setup["mess_2"],
            status="ACTIVE",
            effective_from=sync_date,
        )

        delta = client_1.post(
            "/api/v1/sync/upload",
            {
                "device_id": dev_1.device_id,
                "last_server_version": first.data["new_sync_cursor"],
                "transactions": [],
            },
            format="json",
        )
        assert delta.status_code == status.HTTP_200_OK
        removals = [row for row in delta.data["student_removals"] if row["student_id"] == student.student_id]
        assert removals and removals[0]["reason"] == "ASSIGNMENT_ENDED"
        assert student.student_id not in {
            row["student_id"] for row in delta.data["student_changes"]
        }

        client_2 = auth_client(APIClient(), mgr_2, "MESS_MANAGER", dev_2)
        new_mess = client_2.post(
            "/api/v1/sync/upload",
            {"device_id": dev_2.device_id, "last_server_version": 0, "transactions": []},
            format="json",
        )
        assert new_mess.status_code == status.HTTP_200_OK
        assert student.student_id in {
            row["student_id"] for row in new_mess.data["student_changes"]
        }

    def test_download_contains_only_authorized_students_and_fields(
        self, api_client, sync_setup
    ):
        client = auth_client(
            api_client,
            sync_setup["mgr_1_user"],
            "MESS_MANAGER",
            sync_setup["device_mgr_1"],
        )
        response = client.post(
            "/api/v1/sync/upload",
            {
                "device_id": sync_setup["device_mgr_1"].device_id,
                "last_server_version": 0,
                "transactions": [],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        rows = response.data["student_changes"]
        ids = {row["student_id"] for row in rows}
        assert sync_setup["student_1"].student_id in ids
        assert sync_setup["student_2"].student_id not in ids

        allowed = {
            "student_id",
            "roll_number",
            "display_name",
            "student_status",
            "hostel_id",
            "mess_id",
            "assignment_version",
            "change_version",
            "pause_state",
            "secret_version",
            "secret_ciphertext",
        }
        for row in rows:
            assert set(row.keys()) == allowed

        # Student 2's secret never appears in Manager 1's payload.
        assert all(row["secret_ciphertext"] != "cipher2" for row in rows)
        assert any(row["secret_ciphertext"] == "cipher1" for row in rows)

    def test_bootstrap_paging_union_is_exactly_authorized_set(
        self, api_client, sync_setup
    ):
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        mess = sync_setup["mess_1"]
        hostel = sync_setup["hostel_a"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)

        for index in range(25):
            user = User.objects.create(
                email=f"page_student_{index}@college.edu",
                normalized_email=f"page_student_{index}@college.edu",
                full_name=f"Page Student {index}",
                status="ACTIVE",
            )
            UserRole.objects.create(user=user, role=Role.objects.get(name="STUDENT"))
            student = Student.objects.create(
                user=user,
                roll_number=f"PAGE{index:04d}",
                hostel=hostel,
                status="ACTIVE",
            )
            StudentMessAssignment.objects.create(
                student=student,
                hostel=hostel,
                mess=mess,
                status="ACTIVE",
                effective_from=date(2026, 11, 1),
            )

        SystemSetting.objects.create(
            key="sync.student_page_size",
            value="10",
            data_type="INTEGER",
            effective_from=clock.now(),
            description="Test page size",
        )
        clear_settings_cache()
        try:
            collected = []
            page_token = None
            for _ in range(10):
                body = {
                    "device_id": dev.device_id,
                    "last_server_version": 0,
                    "transactions": [],
                }
                if page_token is not None:
                    body["page_token"] = page_token
                response = client.post("/api/v1/sync/upload", body, format="json")
                assert response.status_code == status.HTTP_200_OK
                collected.extend(row["student_id"] for row in response.data["student_changes"])
                if not response.data["has_more"]:
                    assert response.data["next_page_token"] is None
                    break
                page_token = response.data["next_page_token"]
                assert page_token is not None
            else:  # pragma: no cover - guard against an endless paging loop
                pytest.fail("Bootstrap paging did not terminate")

            expected = set(
                StudentMessAssignment.objects.filter(
                    mess=mess, status="ACTIVE"
                ).values_list("student_id", flat=True)
            )
            assert len(collected) == len(set(collected))
            assert set(collected) == expected
        finally:
            clear_settings_cache()

    def test_late_commit_delivered_by_overlap_window(self, api_client, sync_setup):
        """A row changed at/after the cursor time is still delivered [build 6]."""
        client = auth_client(
            api_client,
            sync_setup["mgr_1_user"],
            "MESS_MANAGER",
            sync_setup["device_mgr_1"],
        )
        first = client.post(
            "/api/v1/sync/upload",
            {
                "device_id": sync_setup["device_mgr_1"].device_id,
                "last_server_version": 0,
                "transactions": [],
            },
            format="json",
        )
        assert first.status_code == status.HTTP_200_OK
        assert first.data["cursor_issued_at"]

        # A cursor far ahead of every change_version leaves only the overlap
        # window able to deliver the row.
        second = client.post(
            "/api/v1/sync/upload",
            {
                "device_id": sync_setup["device_mgr_1"].device_id,
                "last_server_version": 10**9,
                "transactions": [],
            },
            format="json",
        )
        assert second.status_code == status.HTTP_200_OK
        assert sync_setup["student_1"].student_id in {
            row["student_id"] for row in second.data["student_changes"]
        }

    def test_batched_volume_across_35_batches(self, api_client, sync_setup):
        """
        Batching checkpoint: 35 consecutive batches all upload and complete.

        The guide's full 7,000-transaction run takes ~11 minutes on the test
        database, so CI runs the same 35-batch shape at a bounded volume.
        """
        mgr = sync_setup["mgr_1_user"]
        dev = sync_setup["device_mgr_1"]
        client = auth_client(api_client, mgr, "MESS_MANAGER", dev)
        per_batch = 20
        batch_count = 35

        SystemSetting.objects.create(
            key="sync.rate_limit_per_minute",
            value="1000",
            data_type="INTEGER",
            effective_from=clock.now(),
            description="Test throttle headroom",
        )
        clear_settings_cache()
        try:
            accepted = 0
            for batch_index in range(batch_count):
                transactions = []
                for item_index in range(per_batch):
                    minute = item_index % 60
                    second = item_index % 60
                    txn_id = uuid.uuid4()
                    transactions.append(
                        {
                            "transaction_id": str(txn_id),
                            "entity_type": "EXTRA_TRANSACTION",
                            "client_created_at": (
                                f"2026-11-09T{(batch_index % 12) + 8:02d}:"
                                f"{minute:02d}:{second:02d}Z"
                            ),
                            "payload": {
                                "student_id": sync_setup["student_1"].student_id,
                                "mess_id": sync_setup["mess_1"].mess_id,
                                "extra_item_id": sync_setup["extra_1"].extra_item_id,
                                "quantity": 1,
                                "transaction_timestamp": (
                                    f"2026-11-09T{(batch_index % 12) + 8:02d}:"
                                    f"{minute:02d}:{second:02d}Z"
                                ),
                            },
                        }
                    )
                response = client.post(
                    "/api/v1/sync/upload",
                    {
                        "batch_id": str(uuid.uuid4()),
                        "device_id": dev.device_id,
                        "transactions": transactions,
                    },
                    format="json",
                )
                assert response.status_code == status.HTTP_200_OK
                statuses = [row["status"] for row in response.data["transaction_results"]]
                assert len(statuses) == per_batch
                assert all(status == "SYNCHRONIZED" for status in statuses)
                accepted += len(statuses)
            assert accepted == per_batch * batch_count
            assert (
                ExtraTransaction.objects.filter(mess=sync_setup["mess_1"]).count()
                == accepted
            )
        finally:
            clear_settings_cache()
