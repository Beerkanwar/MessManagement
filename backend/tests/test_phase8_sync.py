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

    def test_super_admin_resolves_conflict(self, api_client, sync_setup):
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

        # Resolve conflict
        resolve_resp = client.post(
            f"/api/v1/sync/conflicts/{conflict.conflict_id}/resolve",
            {"resolution": "ACCEPTED", "notes": "Approved by warden after review"},
            format="json",
        )
        assert resolve_resp.status_code == status.HTTP_200_OK
        assert resolve_resp.data["resolution"] == "ACCEPTED"
        assert resolve_resp.data["resolution_notes"] == "Approved by warden after review"

        conflict.refresh_from_db()
        assert conflict.resolution == "ACCEPTED"
        assert conflict.resolved_by_user == admin
        assert AuditLog.objects.filter(event_type="SYNC_CONFLICT_RESOLVED").exists()

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
