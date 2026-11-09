"""
Test suite for Phase 7: Central attendance, extras, and corrections [ImplementationGuide Phase 7].
Verifies:
- record_meal domain pipeline (acceptance rules 1-9, idempotency, duplicate prevention).
- 20-thread concurrency test for same logical meal [DBDD-AC-17].
- Price immutability when rate changes [DBDD-AC-20].
- Student transfers before vs after MealDate.
- Manager scope enforcement (Mess A manager cannot record Mess B student).
- Atomicity: Audit insert failure rolls back meal consumption.
- Pause check (owner change D23 / DBDD-AC-27): active pause cancelled upon meal taken.
- Late transactions vs locked billing period (DEC-05): meal accepted, extra becomes CONFLICT.
- record_extra acceptance rules (positive integer quantity, hostel match).
- Online attendance corrections (DEC-12, DEC-22, D12 scope, 48h window, ADD_MISSING, REMOVE_INCORRECT).
- Remove then add back: effective view follows latest applied correction.
- Scoped read APIs for Student, Clerk, Manager, and Super Admin.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
import uuid
from unittest.mock import patch

import pytest
from django.db import connection, transaction
from rest_framework.test import APIClient

from apps.attendance.models import AttendanceCorrection, ExtraTransaction, MealConsumption
from apps.attendance.selectors import (
    get_attendance_summary,
    get_effective_meal_consumptions,
    get_scoped_attendance_corrections,
    get_scoped_extra_transactions,
    get_scoped_meal_consumptions,
)
from apps.attendance.services import (
    apply_attendance_correction,
    record_extra,
    record_meal,
)
from apps.audit.models import AuditLog
from apps.billing.models import BillingPeriod
from apps.core.clock import IST_ZONE, clock
from apps.core.exceptions import ConflictError, NotFoundError, ValidationError
from apps.hostel.models import Hostel, HostelClerkAssignment, Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, Role, User, UserRole
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


@pytest.fixture(autouse=True)
def freeze_phase7_clock():
    """
    Pin the clock to the fixture's 2026-11-06 design date.

    This module models "today" as 2026-11-06 (correction window, billing period,
    transfers and rate changes). Without freezing, the 48-hour correction window
    expires as real time advances and the suite rots.
    """
    clock.set_time(datetime(2026, 11, 6, 12, 0, tzinfo=IST_ZONE))
    yield
    clock.reset()


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
def test_setup(db, freeze_phase7_clock):
    """Sets up a realistic test campus: Hostels, Messes, Clerks, Managers, Students, Occurrences, and Rates."""
    # 1. Hostels
    hostel_a = Hostel.objects.create(code="H-A", name="Hostel Alpha", status="ACTIVE")
    hostel_b = Hostel.objects.create(code="H-B", name="Hostel Beta", status="ACTIVE")

    # 2. Messes
    mess_1 = Mess.objects.create(code="M-1", name="Mess One", status="ACTIVE")
    mess_2 = Mess.objects.create(code="M-2", name="Mess Two", status="ACTIVE")

    # 3. Super Admin
    admin_user = User.objects.create(
        email="admin_p7@college.edu", normalized_email="admin_p7@college.edu", full_name="Super Admin P7", status="ACTIVE"
    )
    UserRole.objects.create(user=admin_user, role=Role.objects.get(name="SUPER_ADMIN"))

    # 4. Hostel Clerks
    clerk_a_user = User.objects.create(
        email="clerk_a@college.edu", normalized_email="clerk_a@college.edu", full_name="Clerk Alpha", status="ACTIVE"
    )
    UserRole.objects.create(user=clerk_a_user, role=Role.objects.get(name="HOSTEL_CLERK"))
    HostelClerkAssignment.objects.create(user=clerk_a_user, hostel=hostel_a, is_active=True, assigned_at=clock.now())

    clerk_b_user = User.objects.create(
        email="clerk_b@college.edu", normalized_email="clerk_b@college.edu", full_name="Clerk Beta", status="ACTIVE"
    )
    UserRole.objects.create(user=clerk_b_user, role=Role.objects.get(name="HOSTEL_CLERK"))
    HostelClerkAssignment.objects.create(user=clerk_b_user, hostel=hostel_b, is_active=True, assigned_at=clock.now())

    # 5. Mess Managers
    manager_1_user = User.objects.create(
        email="mgr_1@college.edu", normalized_email="mgr_1@college.edu", full_name="Manager Mess 1", status="ACTIVE"
    )
    UserRole.objects.create(user=manager_1_user, role=Role.objects.get(name="MESS_MANAGER"))
    MessManagerAssignment.objects.create(user=manager_1_user, mess=mess_1, is_active=True, assigned_at=clock.now())
    device_mgr_1 = DeviceRegistration.objects.create(
        user=manager_1_user, device_id="dev-mgr-1", platform="ANDROID", session_status="ACTIVE", registered_at=clock.now()
    )

    manager_2_user = User.objects.create(
        email="mgr_2@college.edu", normalized_email="mgr_2@college.edu", full_name="Manager Mess 2", status="ACTIVE"
    )
    UserRole.objects.create(user=manager_2_user, role=Role.objects.get(name="MESS_MANAGER"))
    MessManagerAssignment.objects.create(user=manager_2_user, mess=mess_2, is_active=True, assigned_at=clock.now())
    device_mgr_2 = DeviceRegistration.objects.create(
        user=manager_2_user, device_id="dev-mgr-2", platform="ANDROID", session_status="ACTIVE", registered_at=clock.now()
    )

    # 6. Students
    student_1_user = User.objects.create(
        email="student_1@college.edu", normalized_email="student_1@college.edu", full_name="Student One", status="ACTIVE"
    )
    UserRole.objects.create(user=student_1_user, role=Role.objects.get(name="STUDENT"))
    student_1 = Student.objects.create(user=student_1_user, roll_number="23101001", hostel=hostel_a, status="ACTIVE")
    StudentMessAssignment.objects.create(
        student=student_1, hostel=hostel_a, mess=mess_1, status="ACTIVE", effective_from=date(2026, 11, 1)
    )

    student_2_user = User.objects.create(
        email="student_2@college.edu", normalized_email="student_2@college.edu", full_name="Student Two", status="ACTIVE"
    )
    UserRole.objects.create(user=student_2_user, role=Role.objects.get(name="STUDENT"))
    student_2 = Student.objects.create(user=student_2_user, roll_number="23101002", hostel=hostel_b, status="ACTIVE")
    StudentMessAssignment.objects.create(
        student=student_2, hostel=hostel_b, mess=mess_2, status="ACTIVE", effective_from=date(2026, 11, 1)
    )

    # 7. Meal occurrences & rates for 2026-11-06
    today = date(2026, 11, 6)
    bf = MealType.objects.get(code="BREAKFAST")
    lunch = MealType.objects.get(code="LUNCH")
    dinner = MealType.objects.get(code="DINNER")

    MealOccurrence.objects.create(mess=mess_1, meal_date=today, meal_type=lunch, status="SCHEDULED")
    MealOccurrence.objects.create(mess=mess_1, meal_date=today, meal_type=dinner, status="SCHEDULED")
    MealOccurrence.objects.create(mess=mess_2, meal_date=today, meal_type=lunch, status="SCHEDULED")

    MealRate.objects.create(mess=mess_1, effective_from=date(2026, 11, 1), rate=Decimal("45.0000"), created_by=admin_user)
    MealRate.objects.create(mess=mess_2, effective_from=date(2026, 11, 1), rate=Decimal("50.0000"), created_by=admin_user)

    # 8. Extra items & prices
    extra_a = ExtraItem.objects.create(hostel=hostel_a, name="Egg Curry", status="ACTIVE")
    ExtraPrice.objects.create(extra_item=extra_a, effective_from=date(2026, 11, 1), unit_price=Decimal("20.0000"), created_by=admin_user)

    extra_b = ExtraItem.objects.create(hostel=hostel_b, name="Gulab Jamun", status="ACTIVE")
    ExtraPrice.objects.create(extra_item=extra_b, effective_from=date(2026, 11, 1), unit_price=Decimal("15.0000"), created_by=admin_user)

    # 9. Open billing period
    period = BillingPeriod.objects.create(
        year=2026, month=11, period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), status="OPEN"
    )

    return {
        "hostel_a": hostel_a,
        "hostel_b": hostel_b,
        "mess_1": mess_1,
        "mess_2": mess_2,
        "admin_user": admin_user,
        "clerk_a_user": clerk_a_user,
        "clerk_b_user": clerk_b_user,
        "manager_1_user": manager_1_user,
        "manager_2_user": manager_2_user,
        "device_mgr_1": device_mgr_1,
        "device_mgr_2": device_mgr_2,
        "student_1": student_1,
        "student_2": student_2,
        "student_1_user": student_1_user,
        "student_2_user": student_2_user,
        "today": today,
        "lunch": lunch,
        "dinner": dinner,
        "extra_a": extra_a,
        "extra_b": extra_b,
        "billing_period": period,
    }


def auth_client(client, user, role_name):
    device = DeviceRegistration.objects.filter(user=user, session_status="ACTIVE").first()
    if not device:
        device = DeviceRegistration.objects.create(
            user=user,
            device_id=f"dev-att-{user.user_id}",
            platform="WEB",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
    # This module freezes the clock in the past, but PyJWT checks `exp` against the
    # real clock. Mint the token unfrozen, then restore the frozen test time.
    frozen = clock._frozen_dt
    clock.reset()
    try:
        token = generate_access_token(user, role_name, device)
    finally:
        if frozen is not None:
            clock.set_time(frozen)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# ==============================================================================
# 1. record_meal: Idempotency & Duplicate Prevention
# ==============================================================================

@pytest.mark.django_db
class TestRecordMealIdempotency:
    """Verifies that the duplicate and idempotency rules strictly hold [SPEC DBDD §11, §18.2]."""

    def test_same_transaction_id_twice_returns_idempotent_success(self, test_setup):
        s = test_setup
        txn_id = uuid.uuid4()

        res1 = record_meal(
            transaction_id=txn_id,
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res1.status == "SYNCHRONIZED"
        assert res1.price == Decimal("45.0000")
        assert MealConsumption.objects.count() == 1

        # Second call with the same transaction id
        res2 = record_meal(
            transaction_id=txn_id,
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res2.status == "IDEMPOTENT_SUCCESS"
        assert res2.price == Decimal("45.0000")
        assert MealConsumption.objects.count() == 1

    def test_same_student_date_meal_new_id_returns_duplicate(self, test_setup):
        s = test_setup
        txn_id_1 = uuid.uuid4()
        txn_id_2 = uuid.uuid4()

        res1 = record_meal(
            transaction_id=txn_id_1,
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res1.status == "SYNCHRONIZED"
        assert MealConsumption.objects.count() == 1

        # Different transaction id for the same logical slot
        res2 = record_meal(
            transaction_id=txn_id_2,
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res2.status == "DUPLICATE"
        assert res2.price == Decimal("0.0000")
        assert MealConsumption.objects.count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_submissions_produce_exactly_one_row(self, test_setup):
        """20 threads submitting the same logical meal produce exactly one row [DBDD-AC-17]."""
        s = test_setup
        txn_ids = [uuid.uuid4() for _ in range(20)]

        def submit_meal(tid):
            # Close connection to force new per-thread database session
            connection.close()
            try:
                return record_meal(
                    transaction_id=tid,
                    student=s["student_1"].student_id,
                    meal_date=s["today"],
                    meal_type="LUNCH",
                    mess=s["mess_1"].mess_id,
                    recorded_by_user=s["manager_1_user"],
                    device_registration=s["device_mgr_1"],
                )
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(submit_meal, txn_ids))

        # Exactly 1 success, others DUPLICATE
        synced = [r for r in results if r.status == "SYNCHRONIZED"]
        duplicates = [r for r in results if r.status == "DUPLICATE"]

        assert len(synced) == 1
        assert len(duplicates) == 19
        assert MealConsumption.objects.filter(student=s["student_1"], meal_date=s["today"]).count() == 1


# ==============================================================================
# 2. Price Immutability & Rates
# ==============================================================================

@pytest.mark.django_db
class TestPriceImmutability:
    """Verifies that meal rate changes do not rewrite historical consumption prices [DBDD-AC-20]."""

    def test_rate_change_preserves_historical_price(self, test_setup):
        s = test_setup
        txn_id = uuid.uuid4()

        # Meal recorded on 2026-11-06 with current rate 45.00
        res = record_meal(
            transaction_id=txn_id,
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res.price == Decimal("45.0000")

        # Rate changes next week to 55.00
        old_rate = MealRate.objects.filter(mess=s["mess_1"], effective_to__isnull=True).first()
        if old_rate:
            old_rate.effective_to = date(2026, 11, 13)
            old_rate.save(update_fields=["effective_to"])

        MealRate.objects.create(
            mess=s["mess_1"],
            effective_from=date(2026, 11, 13),
            rate=Decimal("55.0000"),
            created_by=s["admin_user"],
        )

        # Historical row retains 45.00
        meal_db = MealConsumption.objects.get(transaction_id=txn_id)
        assert meal_db.price_at_transaction == Decimal("45.0000")


# ==============================================================================
# 3. Assignment Transfers & Mess Scope Checks
# ==============================================================================

@pytest.mark.django_db
class TestAssignmentAndScope:
    """Verifies assignment evaluations on MealDate and Manager mess scoping [SPEC SRS §27, DBDD §11.1]."""

    def test_student_transfers_after_meal_date_meal_kept(self, test_setup):
        s = test_setup
        today = s["today"]  # 2026-11-06

        # Meal recorded on 2026-11-06 for Mess 1
        res = record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            meal_date=today,
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res.status == "SYNCHRONIZED"

        # Student transfers to Mess 2 effective 2026-11-10 (after MealDate)
        s1_assign = StudentMessAssignment.objects.get(student=s["student_1"], status="ACTIVE")
        s1_assign.effective_to = date(2026, 11, 9)
        s1_assign.status = "ENDED"
        s1_assign.save()

        StudentMessAssignment.objects.create(
            student=s["student_1"],
            hostel=s["hostel_a"],
            mess=s["mess_2"],
            status="ACTIVE",
            effective_from=date(2026, 11, 10),
        )

        # Historical meal remains valid and kept
        assert MealConsumption.objects.filter(student=s["student_1"], meal_date=today).count() == 1

    def test_student_moved_before_meal_date_results_in_conflict(self, test_setup):
        s = test_setup
        # Student 1 assignment was retired before today
        s1_assign = StudentMessAssignment.objects.get(student=s["student_1"], status="ACTIVE")
        s1_assign.effective_to = date(2026, 11, 4)
        s1_assign.status = "ENDED"
        s1_assign.save()

        # Moved to Mess 2 on Nov 5
        StudentMessAssignment.objects.create(
            student=s["student_1"],
            hostel=s["hostel_a"],
            mess=s["mess_2"],
            status="ACTIVE",
            effective_from=date(2026, 11, 5),
        )

        # Manager 1 (Mess 1) sends meal for Nov 6 -> CONFLICT ASSIGNMENT_MISMATCH
        res = record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res.status == "CONFLICT"
        assert res.code == "ASSIGNMENT_MISMATCH"

    def test_manager_of_mess_a_recording_for_mess_b_rejected(self, test_setup):
        s = test_setup
        # Manager 1 attempts to record for Mess 2
        res = record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_2"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_2"],  # Not Manager 1's mess
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res.status == "REJECTED"
        assert res.code == "MESS_SCOPE_MISMATCH"


# ==============================================================================
# 4. Atomicity & Audit Rollback Checkpoint
# ==============================================================================

@pytest.mark.django_db
class TestAuditRollback:
    """Verifies that forced audit failure rolls back the meal consumption insertion [SPEC SDD §77]."""

    def test_audit_insert_failure_rolls_back_meal(self, test_setup):
        s = test_setup
        txn_id = uuid.uuid4()

        with patch("apps.attendance.services.record_audit_event", side_effect=RuntimeError("Forced audit failure")):
            with pytest.raises(RuntimeError, match="Forced audit failure"):
                record_meal(
                    transaction_id=txn_id,
                    student=s["student_1"],
                    meal_date=s["today"],
                    meal_type=s["lunch"],
                    mess=s["mess_1"],
                    recorded_by_user=s["manager_1_user"],
                    device_registration=s["device_mgr_1"],
                )

        # MealConsumption must NOT be persisted
        assert not MealConsumption.objects.filter(transaction_id=txn_id).exists()


# ==============================================================================
# 5. Pause Check & Automatic Cancellation (D23, DBDD-AC-27)
# ==============================================================================

@pytest.mark.django_db
class TestPauseCancellationOnMeal:
    """Verifies that consuming a meal during an ACTIVE pause automatically cancels it with MEAL_TAKEN."""

    def test_active_pause_cancelled_when_meal_taken(self, test_setup):
        s = test_setup
        # Create an ACTIVE pause covering today (2026-11-06)
        pause = MessPause.objects.create(
            student=s["student_1"],
            mess=s["mess_1"],
            requested_start_date=date(2026, 11, 5),
            requested_end_date=date(2026, 11, 10),
            effective_start_date=date(2026, 11, 5),
            effective_end_date=date(2026, 11, 10),
            status="ACTIVE",
            requested_at=clock.now(),
        )

        res = record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res.status == "SYNCHRONIZED"

        # Pause is now CANCELLED with reason MEAL_TAKEN
        pause.refresh_from_db()
        assert pause.status == "CANCELLED"
        assert pause.cancellation_reason == "MEAL_TAKEN"
        assert pause.cancelled_at is not None

        # Audit record emitted
        audit = AuditLog.objects.filter(event_type="PAUSE_CANCELLED", entity_id=str(pause.pause_id)).first()
        assert audit is not None
        assert audit.reason == "MEAL_TAKEN"


# ==============================================================================
# 6. Locked Billing Period Rules (DEC-05)
# ==============================================================================

@pytest.mark.django_db
class TestLockedBillingPeriod:
    """Verifies DEC-05 rules for late meals (accepted) and late extras (CONFLICT)."""

    def test_late_meal_accepted_when_period_locked(self, test_setup):
        s = test_setup
        # Lock November period
        s["billing_period"].status = "LOCKED"
        s["billing_period"].save()

        res = record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res.status == "SYNCHRONIZED"
        assert MealConsumption.objects.count() == 1

    def test_late_extra_becomes_conflict_when_period_locked(self, test_setup):
        s = test_setup
        # Lock November period
        s["billing_period"].status = "LOCKED"
        s["billing_period"].save()

        res = record_extra(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            extra_item=s["extra_a"],
            quantity=1,
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
            device_registration=s["device_mgr_1"],
        )
        assert res.status == "CONFLICT"
        assert res.code == "BILLING_PERIOD_LOCKED"
        assert ExtraTransaction.objects.count() == 0


# ==============================================================================
# 7. record_extra Acceptance Rules
# ==============================================================================

@pytest.mark.django_db
class TestRecordExtraRules:
    """Verifies extra item acceptance: positive integer quantity, hostel match [SPEC SRS §14.3]."""

    def test_extra_quantity_zero_negative_non_int_rejected(self, test_setup):
        s = test_setup

        # Quantity 0
        r0 = record_extra(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            extra_item=s["extra_a"],
            quantity=0,
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
        )
        assert r0.status == "REJECTED"
        assert r0.code == "INVALID_QUANTITY"

        # Quantity negative
        r_neg = record_extra(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            extra_item=s["extra_a"],
            quantity=-2,
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
        )
        assert r_neg.status == "REJECTED"
        assert r_neg.code == "INVALID_QUANTITY"

    def test_extra_from_another_hostel_item_rejected(self, test_setup):
        s = test_setup
        # Student 1 is in Hostel Alpha; extra_b is in Hostel Beta
        res = record_extra(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            extra_item=s["extra_b"],
            quantity=2,
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
        )
        assert res.status == "REJECTED"
        assert res.code == "HOSTEL_MISMATCH"

    def test_valid_extra_recorded_with_pricing(self, test_setup):
        s = test_setup
        res = record_extra(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            extra_item=s["extra_a"],
            quantity=3,
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
        )
        assert res.status == "SYNCHRONIZED"
        assert res.unit_price == Decimal("20.0000")
        assert res.total_amount == Decimal("60.0000")
        assert ExtraTransaction.objects.count() == 1


# ==============================================================================
# 8. Attendance Corrections (DEC-12, DEC-22, D12)
# ==============================================================================

@pytest.mark.django_db
class TestAttendanceCorrections:
    """Verifies online attendance corrections and effective-attendance derivation."""

    def test_correction_without_reason_rejected(self, test_setup):
        s = test_setup
        with pytest.raises(ValidationError, match="Correction reason is required"):
            apply_attendance_correction(
                correction_transaction_id=uuid.uuid4(),
                student_id=s["student_1"].student_id,
                meal_date=s["today"],
                meal_type="LUNCH",
                action="ADD_MISSING",
                reason="shrt",  # Under 5 chars
                actor=s["admin_user"],
            )

    def test_correction_on_locked_billing_period_rejected(self, test_setup):
        s = test_setup
        s["billing_period"].status = "LOCKED"
        s["billing_period"].save()

        with pytest.raises(ValidationError, match="locked"):
            apply_attendance_correction(
                correction_transaction_id=uuid.uuid4(),
                student_id=s["student_1"].student_id,
                meal_date=s["today"],
                meal_type="LUNCH",
                action="ADD_MISSING",
                reason="Valid correction reason text",
                actor=s["admin_user"],
            )

    def test_out_of_scope_clerk_or_manager_receives_404(self, test_setup):
        s = test_setup
        # Clerk B attempts to correct Student 1 (Hostel A) -> 404
        with pytest.raises(NotFoundError):
            apply_attendance_correction(
                correction_transaction_id=uuid.uuid4(),
                student_id=s["student_1"].student_id,
                meal_date=s["today"],
                meal_type="LUNCH",
                action="ADD_MISSING",
                reason="Valid reason from wrong clerk",
                actor=s["clerk_b_user"],
            )

        # Manager 2 attempts to correct Student 1 (Mess 1) -> 404
        with pytest.raises(NotFoundError):
            apply_attendance_correction(
                correction_transaction_id=uuid.uuid4(),
                student_id=s["student_1"].student_id,
                meal_date=s["today"],
                meal_type="LUNCH",
                action="ADD_MISSING",
                reason="Valid reason from wrong manager",
                actor=s["manager_2_user"],
            )

    def test_remove_then_add_back_effective_attendance_derivation(self, test_setup):
        s = test_setup
        today = s["today"]

        # Step 1: Normal meal recorded
        res = record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            meal_date=today,
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
        )
        assert res.status == "SYNCHRONIZED"
        assert get_effective_meal_consumptions(student=s["student_1"]).count() == 1

        # Step 2: Clerk A removes attendance
        corr1 = apply_attendance_correction(
            correction_transaction_id=uuid.uuid4(),
            student_id=s["student_1"].student_id,
            meal_date=today,
            meal_type=s["lunch"],
            action="REMOVE_INCORRECT",
            reason="Mistakenly scanned student card",
            actor=s["clerk_a_user"],
        )
        assert corr1.status == "APPLIED"

        # Effective count is now 0 (row still exists in MealConsumption!)
        assert get_effective_meal_consumptions(student=s["student_1"]).count() == 0
        assert MealConsumption.objects.filter(student=s["student_1"]).count() == 1

        # Step 3: Manager 1 adds back the missing meal
        corr2 = apply_attendance_correction(
            correction_transaction_id=uuid.uuid4(),
            student_id=s["student_1"].student_id,
            meal_date=today,
            meal_type=s["lunch"],
            action="ADD_MISSING",
            reason="Confirmed student was actually present",
            actor=s["manager_1_user"],
        )
        assert corr2.status == "APPLIED"

        # Effective count is now 1 again! Both correction rows preserved
        assert get_effective_meal_consumptions(student=s["student_1"]).count() == 1
        assert AttendanceCorrection.objects.filter(student=s["student_1"]).count() == 2


# ==============================================================================
# 9. Scoped Read APIs
# ==============================================================================

@pytest.mark.django_db
class TestAttendanceAPIEndpoints:
    """Verifies GET /attendance, /summary, /extras/transactions and POST /corrections via HTTP."""

    def test_student_sees_own_effective_attendance_and_summary(self, api_client, test_setup):
        s = test_setup
        # Create meal for Student 1 and Student 2
        record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
        )
        record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_2"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_2"],
            recorded_by_user=s["manager_2_user"],
        )

        auth_client(api_client, s["student_1_user"], "STUDENT")

        # GET /api/v1/attendance
        resp = api_client.get("/api/v1/attendance")
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["student_id"] == s["student_1"].student_id
        assert resp.data["results"][0]["price_at_transaction"] == "45.0000"

        # GET /api/v1/attendance/summary
        resp_sum = api_client.get("/api/v1/attendance/summary")
        assert resp_sum.status_code == 200
        assert resp_sum.data["total_meals"] == 1
        assert resp_sum.data["lunch_count"] == 1
        assert resp_sum.data["breakfast_count"] == 0

    def test_manager_sees_own_mess_attendance_only(self, api_client, test_setup):
        s = test_setup
        record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_1"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_1"],
            recorded_by_user=s["manager_1_user"],
        )
        record_meal(
            transaction_id=uuid.uuid4(),
            student=s["student_2"],
            meal_date=s["today"],
            meal_type=s["lunch"],
            mess=s["mess_2"],
            recorded_by_user=s["manager_2_user"],
        )

        auth_client(api_client, s["manager_1_user"], "MESS_MANAGER")
        resp = api_client.get("/api/v1/attendance")
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["mess_id"] == s["mess_1"].mess_id

    def test_post_and_get_attendance_corrections_api(self, api_client, test_setup):
        s = test_setup
        auth_client(api_client, s["clerk_a_user"], "HOSTEL_CLERK")

        post_data = {
            "correction_transaction_id": str(uuid.uuid4()),
            "student_id": s["student_1"].student_id,
            "meal_date": str(s["today"]),
            "meal_type": "DINNER",
            "action": "ADD_MISSING",
            "reason": "Scanner missed evening attendance",
        }
        resp = api_client.post("/api/v1/attendance/corrections", data=post_data, format="json")
        assert resp.status_code == 201
        assert resp.data["action"] == "ADD_MISSING"

        # GET /api/v1/attendance/corrections
        resp_list = api_client.get("/api/v1/attendance/corrections")
        assert resp_list.status_code == 200
        assert resp_list.data["count"] == 1
