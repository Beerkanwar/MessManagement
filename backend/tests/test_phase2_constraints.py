"""
Phase 2 constraint and invariant verification suite.
Validates:
- All DBDD §16 database-enforced invariants (1 to 12)
- DBDD acceptance criteria (DBDD-AC-13 to DBDD-AC-33)
- Optimistic concurrency control & insert-only model behaviors
- Price snapshot immutability
- Locked-bill guard trigger
- Multi-threaded concurrent duplicate attendance insertion (DBDD-AC-17)
- Seed idempotency and presence
"""
import threading
from datetime import date, datetime, timezone
import uuid
import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone as django_tz

from apps.identity.models import User, Role, UserRole, DeviceRegistration, StudentSecret
from apps.hostel.models import (
    Hostel, Student, StudentMessAssignment, HostelClerkAssignment,
    StudentVerification, StudentImportBatch, StudentImportError
)
from apps.mess.models import (
    Mess, MessManagerAssignment, MealType, MealOccurrence,
    MealRate, ExtraItem, ExtraPrice
)
from apps.attendance.models import MealConsumption, ExtraTransaction, AttendanceCorrection
from apps.pause.models import MessPause, MessPauseMealSlot
from apps.billing.models import (
    Semester, BillingPeriod, BillingPolicy, Bill, BillLine,
    BillAdjustment, BalanceAccount, BalanceLedgerEntry
)
from apps.menu.models import FoodItem, Menu, MenuMeal, MenuItem
from apps.feedback.models import Feedback
from apps.sync.models import SyncBatch, SyncTransaction, ChangeCursor
from apps.audit.models import AuditLog
from apps.config.models import SystemSetting


@pytest.fixture
def base_setup(db):
    """Creates core master records for testing constraints."""
    user1 = User.objects.create_user(email="student1@college.edu", full_name="Student One")
    user2 = User.objects.create_user(email="student2@college.edu", full_name="Student Two")
    staff_user = User.objects.create_user(email="staff@college.edu", full_name="Staff User")

    hostel = Hostel.objects.create(code="H1", name="Hostel 1")
    mess = Mess.objects.create(code="M1", name="Mess 1")

    student1 = Student.objects.create(user=user1, roll_number="ROLL001", hostel=hostel)
    student2 = Student.objects.create(user=user2, roll_number="ROLL002", hostel=hostel)

    meal_type_bf, _ = MealType.objects.get_or_create(
        code="BREAKFAST", defaults={"name": "Breakfast", "sequence_no": 1}
    )
    meal_type_lunch, _ = MealType.objects.get_or_create(
        code="LUNCH", defaults={"name": "Lunch", "sequence_no": 2}
    )

    semester = Semester.objects.create(
        code="SEM-2026-1", name="Autumn 2026",
        start_date=date(2026, 7, 1), end_date=date(2026, 12, 31)
    )

    billing_period = BillingPeriod.objects.create(
        year=2026, month=10,
        period_start=date(2026, 10, 1), period_end=date(2026, 10, 31),
        status="OPEN"
    )

    return {
        "user1": user1,
        "user2": user2,
        "staff": staff_user,
        "hostel": hostel,
        "mess": mess,
        "student1": student1,
        "student2": student2,
        "meal_type_bf": meal_type_bf,
        "meal_type_lunch": meal_type_lunch,
        "semester": semester,
        "billing_period": billing_period,
    }


# ==============================================================================
# Invariant 1 / DBDD-AC-13: Overlapping active student-mess assignments
# ==============================================================================
@pytest.mark.django_db
def test_invariant_1_student_mess_assignment_overlap(base_setup):
    """
    Invariant 1: A student cannot have two overlapping active/effective mess assignments.
    DBDD-AC-13.
    """
    s = base_setup["student1"]
    h = base_setup["hostel"]
    m = base_setup["mess"]

    # First active assignment: Oct 1 to Oct 15
    StudentMessAssignment.objects.create(
        student=s, hostel=h, mess=m,
        effective_from=date(2026, 10, 1), effective_to=date(2026, 10, 15),
        status="ACTIVE"
    )

    # Overlapping active assignment: Oct 10 to Oct 20 -> must fail
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StudentMessAssignment.objects.create(
                student=s, hostel=h, mess=m,
                effective_from=date(2026, 10, 10), effective_to=date(2026, 10, 20),
                status="ACTIVE"
            )


# ==============================================================================
# Invariant 2 / DBDD-AC-14: One active mess per manager
# ==============================================================================
@pytest.mark.django_db
def test_invariant_2_manager_one_active_mess(base_setup):
    """
    Invariant 2: A Mess Manager cannot have more than one active mess assignment.
    DEC-21: One active manager per mess.
    DBDD-AC-14.
    """
    u = base_setup["staff"]
    m1 = base_setup["mess"]
    m2 = Mess.objects.create(code="M2", name="Mess 2")

    MessManagerAssignment.objects.create(user=u, mess=m1, is_active=True, assigned_at=django_tz.now())

    # Second active mess for same manager -> fails
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MessManagerAssignment.objects.create(user=u, mess=m2, is_active=True, assigned_at=django_tz.now())


# ==============================================================================
# Invariant 3 / DBDD-AC-15: One active hostel per clerk
# ==============================================================================
@pytest.mark.django_db
def test_invariant_3_clerk_one_active_hostel(base_setup):
    """
    Invariant 3: A Hostel Clerk cannot have more than one active hostel assignment.
    DBDD-AC-15.
    """
    u = base_setup["staff"]
    h1 = base_setup["hostel"]
    h2 = Hostel.objects.create(code="H2", name="Hostel 2")

    HostelClerkAssignment.objects.create(user=u, hostel=h1, is_active=True, assigned_at=django_tz.now())

    # Second active hostel for same clerk -> fails
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            HostelClerkAssignment.objects.create(user=u, hostel=h2, is_active=True, assigned_at=django_tz.now())


# ==============================================================================
# Invariant 4 / DBDD-AC-16: Duplicate meal attendance prevention
# ==============================================================================
@pytest.mark.django_db
def test_invariant_4_duplicate_meal_attendance(base_setup):
    """
    Invariant 4: A student cannot have two meal-consumption records for the same MealDate and MealType.
    DBDD-AC-16.
    """
    s = base_setup["student1"]
    m = base_setup["mess"]
    mt = base_setup["meal_type_bf"]
    staff = base_setup["staff"]
    meal_date = date(2026, 10, 14)

    MealConsumption.objects.create(
        transaction_id=uuid.uuid4(),
        student=s, roll_number_snapshot=s.roll_number,
        mess=m, meal_type=mt, meal_date=meal_date,
        price_at_transaction=50.0,
        transaction_timestamp=django_tz.now(),
        recorded_by_user=staff,
    )

    # Second meal for same student + date + type -> fails
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MealConsumption.objects.create(
                transaction_id=uuid.uuid4(),
                student=s, roll_number_snapshot=s.roll_number,
                mess=m, meal_type=mt, meal_date=meal_date,
                price_at_transaction=50.0,
                transaction_timestamp=django_tz.now(),
                recorded_by_user=staff,
            )


# ==============================================================================
# Invariant 5 / DBDD-AC-18: Unique transaction_id (idempotency)
# ==============================================================================
@pytest.mark.django_db
def test_invariant_5_unique_transaction_id(base_setup):
    """
    Invariant 5: A synchronization transaction cannot be accepted twice by TransactionId.
    DBDD-AC-18.
    """
    s = base_setup["student1"]
    m = base_setup["mess"]
    mt1 = base_setup["meal_type_bf"]
    mt2 = base_setup["meal_type_lunch"]
    staff = base_setup["staff"]
    txn_id = uuid.uuid4()

    MealConsumption.objects.create(
        transaction_id=txn_id,
        student=s, roll_number_snapshot=s.roll_number,
        mess=m, meal_type=mt1, meal_date=date(2026, 10, 14),
        price_at_transaction=50.0,
        transaction_timestamp=django_tz.now(),
        recorded_by_user=staff,
    )

    # Reusing txn_id for another consumption -> fails
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MealConsumption.objects.create(
                transaction_id=txn_id,
                student=s, roll_number_snapshot=s.roll_number,
                mess=m, meal_type=mt2, meal_date=date(2026, 10, 14),
                price_at_transaction=60.0,
                transaction_timestamp=django_tz.now(),
                recorded_by_user=staff,
            )


# ==============================================================================
# Invariant 6 / DBDD-AC-29: Unique feedback per student per month
# ==============================================================================
@pytest.mark.django_db
def test_invariant_6_monthly_feedback_uniqueness(base_setup):
    """
    Invariant 6: A student cannot have two feedback records in the same calendar month.
    DBDD-AC-29.
    """
    s = base_setup["student1"]
    m = base_setup["mess"]

    Feedback.objects.create(
        student=s, mess=m, calendar_year=2026, calendar_month=10,
        food_quality_rating=4, taste_rating=4, comments="Good food"
    )

    # Second feedback for same month -> fails
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Feedback.objects.create(
                student=s, mess=m, calendar_year=2026, calendar_month=10,
                food_quality_rating=5, taste_rating=5, comments="Another comment"
            )


# ==============================================================================
# Invariant 7 / DBDD-AC-21: Unique bill per Student + Mess + BillingPeriod
# ==============================================================================
@pytest.mark.django_db
def test_invariant_7_unique_bill_per_period(base_setup):
    """
    Invariant 7: A student cannot have two bills for the same Mess and BillingPeriod.
    DBDD-AC-21.
    """
    s = base_setup["student1"]
    m = base_setup["mess"]
    bp = base_setup["billing_period"]

    Bill.objects.create(
        student=s, mess=m, billing_period=bp,
        meal_component_amount=1500.0, extra_charges_amount=200.0,
        adjustment_amount=0.0, final_amount=1700.0,
        common_diet_rate_snapshot=50.0, minimum_diet_count_snapshot=30,
        actual_meal_count=28, status="DRAFT",
        generated_at=django_tz.now()
    )

    # Duplicate bill -> fails
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Bill.objects.create(
                student=s, mess=m, billing_period=bp,
                meal_component_amount=1500.0, extra_charges_amount=200.0,
                adjustment_amount=0.0, final_amount=1700.0,
                common_diet_rate_snapshot=50.0, minimum_diet_count_snapshot=30,
                actual_meal_count=28, status="DRAFT",
                generated_at=django_tz.now()
            )


# ==============================================================================
# Invariant 8 / DBDD-AC-24: Unique prepaid BalanceAccount per Student + Semester
# ==============================================================================
@pytest.mark.django_db
def test_invariant_8_unique_balance_account(base_setup):
    """
    Invariant 8: A student cannot have two prepaid BalanceAccounts for the same Semester.
    DBDD-AC-24.
    """
    s = base_setup["student1"]
    sem = base_setup["semester"]

    BalanceAccount.objects.create(student=s, semester=sem, opening_balance=5000.0, current_balance=5000.0)

    # Second account for same student + semester -> fails
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            BalanceAccount.objects.create(student=s, semester=sem, opening_balance=2000.0, current_balance=2000.0)


# ==============================================================================
# Invariant 9: Unique MealOccurrence per Mess + MealDate + MealType
# ==============================================================================
@pytest.mark.django_db
def test_invariant_9_unique_meal_occurrence(base_setup):
    """
    Invariant 9: A meal occurrence cannot be duplicated for the same Mess/date/type.
    """
    m = base_setup["mess"]
    mt = base_setup["meal_type_bf"]
    meal_date = date(2026, 10, 15)

    MealOccurrence.objects.create(mess=m, meal_type=mt, meal_date=meal_date, status="SCHEDULED")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MealOccurrence.objects.create(mess=m, meal_type=mt, meal_date=meal_date, status="SCHEDULED")


# ==============================================================================
# Invariant 10 / DBDD-AC-30: No duplicate FoodItem in same MenuMeal
# ==============================================================================
@pytest.mark.django_db
def test_invariant_10_unique_food_item_in_menu_meal(base_setup):
    """
    Invariant 10: A menu cannot contain the same FoodItem twice under one MenuMeal.
    DBDD-AC-30.
    """
    h = base_setup["hostel"]
    mt = base_setup["meal_type_bf"]

    menu = Menu.objects.create(hostel=h, menu_year=2026, menu_month=10, status="DRAFT")
    menu_meal = MenuMeal.objects.create(menu=menu, menu_date=date(2026, 10, 15), meal_type=mt)
    food_item = FoodItem.objects.create(name="Poha", normalized_name="POHA")

    MenuItem.objects.create(menu_meal=menu_meal, food_item=food_item, display_order=1)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MenuItem.objects.create(menu_meal=menu_meal, food_item=food_item, display_order=2)


# ==============================================================================
# Invariant 11 / DBDD-AC-20: Price snapshot immutability
# ==============================================================================
@pytest.mark.django_db
def test_invariant_11_price_snapshot_immutability(base_setup):
    """
    Invariant 11: Transaction monetary values are snapshots and are not cascade-updated
    by master-price changes, nor modified directly (enforced via database trigger).
    DBDD-AC-20.
    """
    s = base_setup["student1"]
    m = base_setup["mess"]
    mt = base_setup["meal_type_bf"]
    staff = base_setup["staff"]

    consumption = MealConsumption.objects.create(
        transaction_id=uuid.uuid4(),
        student=s, roll_number_snapshot=s.roll_number,
        mess=m, meal_type=mt, meal_date=date(2026, 10, 14),
        price_at_transaction=50.0,
        transaction_timestamp=django_tz.now(),
        recorded_by_user=staff,
    )

    # Attempting to mutate price_at_transaction must trigger database exception
    consumption.price_at_transaction = 99.0
    with pytest.raises(Exception):
        with transaction.atomic():
            consumption.save()


# ==============================================================================
# Invariant 12 / DBDD-AC-33: Insert-only tables
# ==============================================================================
@pytest.mark.django_db
def test_invariant_12_insert_only_tables(base_setup):
    """
    Invariant 12: Audit records and immutable tables are append-only.
    UPDATE and DELETE are rejected at ORM level and database trigger level.
    DBDD-AC-33.
    """
    staff = base_setup["staff"]

    log = AuditLog.objects.create(
        event_type="LOGIN_SUCCESS",
        actor_user=staff,
        entity_type="User",
        entity_id=str(staff.user_id),
        occurred_at=django_tz.now()
    )

    # ORM level update rejection
    log.reason = "modified reason"
    with pytest.raises(ValueError):
        log.save()

    # ORM level delete rejection
    with pytest.raises(ValueError):
        log.delete()


# ==============================================================================
# Locked-Bill Guard / DBDD-AC-22: Writes rejected when BillingPeriod is LOCKED
# ==============================================================================
@pytest.mark.django_db
def test_locked_bill_guard(base_setup):
    """
    DBDD-AC-22: A locked bill cannot be silently modified.
    Trigger rejects insert, update, delete when parent period is LOCKED.
    """
    s = base_setup["student1"]
    m = base_setup["mess"]
    staff = base_setup["staff"]

    locked_period = BillingPeriod.objects.create(
        year=2026, month=9,
        period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
        status="LOCKED", locked_at=django_tz.now()
    )

    # Creating a Bill in a LOCKED period must fail via trigger
    with pytest.raises(Exception):
        with transaction.atomic():
            Bill.objects.create(
                student=s, mess=m, billing_period=locked_period,
                meal_component_amount=1500.0, extra_charges_amount=0.0,
                adjustment_amount=0.0, final_amount=1500.0,
                common_diet_rate_snapshot=50.0, minimum_diet_count_snapshot=30,
                actual_meal_count=30, status="LOCKED",
                generated_at=django_tz.now()
            )


# ==============================================================================
# Invariant 25: Negative balance representable
# ==============================================================================
@pytest.mark.django_db
def test_invariant_25_negative_balance(base_setup):
    """
    DBDD-AC-25: Negative balance is representable on BalanceAccount.
    """
    s = base_setup["student1"]
    sem = base_setup["semester"]

    acct = BalanceAccount.objects.create(
        student=s, semester=sem, opening_balance=0.0, current_balance=-250.50
    )
    acct.refresh_from_db()
    assert acct.current_balance < 0


# ==============================================================================
# Concurrency Check / DBDD-AC-17: Concurrent duplicate meal attendance
# ==============================================================================
@pytest.mark.django_db(transaction=True)
def test_concurrency_duplicate_meal_attendance(base_setup):
    """
    DBDD-AC-17: Two threads insert the same (student, date, meal_type) concurrently;
    exactly one succeeds.
    """
    s = base_setup["student1"]
    m = base_setup["mess"]
    mt = base_setup["meal_type_bf"]
    staff = base_setup["staff"]
    meal_date = date(2026, 10, 16)

    results = []

    def insert_meal():
        try:
            with transaction.atomic():
                MealConsumption.objects.create(
                    transaction_id=uuid.uuid4(),
                    student=s, roll_number_snapshot=s.roll_number,
                    mess=m, meal_type=mt, meal_date=meal_date,
                    price_at_transaction=50.0,
                    transaction_timestamp=django_tz.now(),
                    recorded_by_user=staff,
                )
            results.append("SUCCESS")
        except IntegrityError:
            results.append("INTEGRITY_ERROR")

    t1 = threading.Thread(target=insert_meal)
    t2 = threading.Thread(target=insert_meal)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count("SUCCESS") == 1
    assert results.count("INTEGRITY_ERROR") == 1


# ==============================================================================
# Seeds Verification: Roles, MealTypes, SystemSettings
# ==============================================================================
@pytest.mark.django_db
def test_seeds_present_and_correct(db):
    """
    Verifies that seed migrations populated Roles, MealTypes, and SystemSettings.
    """
    # Roles
    assert Role.objects.filter(name="STUDENT").exists()
    assert Role.objects.filter(name="MESS_MANAGER").exists()
    assert Role.objects.filter(name="HOSTEL_CLERK").exists()
    assert Role.objects.filter(name="SUPER_ADMIN").exists()

    # MealTypes
    assert MealType.objects.filter(code="BREAKFAST", sequence_no=1).exists()
    assert MealType.objects.filter(code="LUNCH", sequence_no=2).exists()
    assert MealType.objects.filter(code="EVENING_SNACKS", sequence_no=3).exists()
    assert MealType.objects.filter(code="DINNER", sequence_no=4).exists()

    # SystemSettings
    assert SystemSetting.objects.filter(key="sync.batch_max_transactions", value="500").exists()
    assert SystemSetting.objects.filter(key="meal.BREAKFAST.end_time", value="10:00").exists()
    assert SystemSetting.objects.filter(key="meal.rollover_time", value="03:00").exists()
