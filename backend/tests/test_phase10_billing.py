"""
Phase 10 test suite: billing and the prepaid balance ledger
[SPEC DBDD §8, ImplementationGuide Phase 10, owner change C01, DEC-04, DEC-24].

Coverage:
- The amended DBDD §19 example under C01, with MealCount below, equal to and
  above the billed minimum, plus an independent recomputation of every bill.
- First-day rate/policy snapshots across a mid-month rate change.
- Pause deduction (DEC-04b) and mid-month transfer proration (DEC-24).
- Extras on IST period boundaries and snacks billed as extras.
- Idempotent regeneration; positive-only fees and fines.
- Locked-bill immutability through the ORM and raw SQL [DBDD-AC-22].
- Audited unlock [DBDD-AC-23] and the lock/unlock/relock ledger invariant.
- One balance account per student and semester [DBDD-AC-24].
- Negative balances never blocking a synced meal [DBDD-AC-25].
- Two simultaneous lock calls producing exactly one lock.
- The 300-student, two-mess end-to-end exit gate.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo
import threading
import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections, transaction
from django.db.utils import DatabaseError
from rest_framework import status
from rest_framework.test import APIClient

from apps.attendance.models import ExtraTransaction, MealConsumption
from apps.attendance.services import record_meal
from apps.audit.models import AuditLog
from apps.billing import services as billing
from apps.billing.models import (
    BalanceAccount,
    BalanceLedgerEntry,
    Bill,
    BillAdjustment,
    BillingPeriod,
    BillingPolicy,
    Semester,
)
from apps.billing.selectors import bill_totals, get_balance_account
from apps.core.clock import clock
from apps.core.exceptions import ConflictError, ValidationError
from apps.hostel.models import Hostel, HostelClerkAssignment, Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, Role, User, UserRole
from apps.identity.services.token_service import generate_access_token
from apps.mess.models import ExtraItem, MealOccurrence, MealRate, MealType, Mess, MessManagerAssignment
from apps.pause.models import MessPause

IST = ZoneInfo("Asia/Kolkata")
QUALIFYING_CODES = ("BREAKFAST", "LUNCH", "DINNER")
ALL_CODES = ("BREAKFAST", "EVENING_SNACKS", "LUNCH", "DINNER")
PERIOD_START = date(2026, 11, 1)
PERIOD_END = date(2026, 11, 30)
MONEY = Decimal("0.0001")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ist_dt(day: date, clock_time: time = time(0, 0)) -> datetime:
    """Build an aware Asia/Kolkata datetime."""
    return datetime.combine(day, clock_time).replace(tzinfo=IST)


def make_user(email: str, full_name: str, role_name: str) -> User:
    user = User.objects.create(
        email=email,
        normalized_email=email,
        full_name=full_name,
        status="ACTIVE",
    )
    UserRole.objects.create(user=user, role=Role.objects.get(name=role_name))
    return user


def make_student(
    *,
    email: str,
    roll_number: str,
    hostel: Hostel,
    role_name: str = "STUDENT",
    full_name: str | None = None,
) -> tuple[Student, User]:
    user = make_user(email, full_name or roll_number, role_name)
    student = Student.objects.create(
        user=user, roll_number=roll_number, hostel=hostel, status="ACTIVE"
    )
    return student, user


def auth_client(client: APIClient, user: User, role_name: str) -> APIClient:
    """Authenticate a DRF client even while the domain clock is frozen."""
    device = DeviceRegistration.objects.filter(
        user=user, session_status="ACTIVE"
    ).first()
    if not device:
        device = DeviceRegistration.objects.create(
            user=user,
            device_id=f"dev-p10-{user.user_id}",
            platform="WEB",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
    frozen = clock._frozen_dt
    clock.reset()
    try:
        token = generate_access_token(user, role_name, device)
    finally:
        if frozen is not None:
            clock.set_time(frozen)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def create_calendar(
    mess: Mess, start_day: date = PERIOD_START, days: int = 30
) -> None:
    """Create three qualifying slots per day (and no snacks) for a mess."""
    meal_types = {code: MealType.objects.get(code=code) for code in QUALIFYING_CODES}
    rows = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        for code in QUALIFYING_CODES:
            rows.append(
                MealOccurrence(
                    mess=mess,
                    meal_date=day,
                    meal_type=meal_types[code],
                    status="SCHEDULED",
                )
            )
    MealOccurrence.objects.bulk_create(rows)


def create_meals(
    *,
    student: Student,
    mess: Mess,
    count: int,
    recorded_by: User,
    price: Decimal = Decimal("150.0000"),
) -> None:
    """Create ``count`` effective qualifying meal consumptions for a student."""
    if count <= 0:
        return
    meal_types = [MealType.objects.get(code=code) for code in QUALIFYING_CODES]
    rows = []
    created = 0
    day_offset = 0
    while created < count:
        day = PERIOD_START + timedelta(days=day_offset)
        for meal_type in meal_types:
            if created >= count:
                break
            rows.append(
                MealConsumption(
                    transaction_id=uuid.uuid4(),
                    student=student,
                    roll_number_snapshot=student.roll_number,
                    mess=mess,
                    meal_type=meal_type,
                    meal_date=day,
                    price_at_transaction=price,
                    transaction_timestamp=ist_dt(day, time(12, 0)),
                    recorded_by_user=recorded_by,
                    source="QR",
                    sync_status="SYNCHRONIZED",
                    accepted_at=clock.now(),
                )
            )
            created += 1
        day_offset += 1
    MealConsumption.objects.bulk_create(rows)


def create_snack(
    *, student: Student, mess: Mess, day: date, price: Decimal, recorded_by: User
) -> MealConsumption:
    return MealConsumption.objects.create(
        transaction_id=uuid.uuid4(),
        student=student,
        roll_number_snapshot=student.roll_number,
        mess=mess,
        meal_type=MealType.objects.get(code="EVENING_SNACKS"),
        meal_date=day,
        price_at_transaction=price,
        transaction_timestamp=ist_dt(day, time(18, 0)),
        recorded_by_user=recorded_by,
        source="QR",
        sync_status="SYNCHRONIZED",
        accepted_at=clock.now(),
    )


def create_extra(
    *,
    student: Student,
    hostel: Hostel,
    mess: Mess,
    item: ExtraItem,
    quantity: int,
    unit_price: Decimal,
    when: datetime,
    recorded_by: User,
    sync_status: str = "SYNCHRONIZED",
) -> ExtraTransaction:
    return ExtraTransaction.objects.create(
        transaction_id=uuid.uuid4(),
        student=student,
        hostel=hostel,
        mess=mess,
        extra_item=item,
        quantity=quantity,
        unit_price_at_transaction=unit_price,
        total_amount=unit_price * quantity,
        transaction_timestamp=when,
        recorded_by_user=recorded_by,
        source="MANUAL",
        sync_status=sync_status,
        accepted_at=clock.now() if sync_status in {"SYNCHRONIZED", "IDEMPOTENT_SUCCESS"} else None,
    )


def make_active_pause(
    *,
    student: Student,
    mess: Mess,
    start: date,
    end: date,
) -> MessPause:
    return MessPause.objects.create(
        student=student,
        mess=mess,
        requested_start_date=start,
        requested_end_date=end,
        effective_start_date=start,
        effective_end_date=end,
        activation_meal_date=start - timedelta(days=1),
        status="ACTIVE",
        requested_at=clock.now(),
    )


def independent_totals(period: BillingPeriod) -> dict[str, Decimal]:
    """
    Recompute the period's money from source rows without using the billing
    service helpers. This is the "independent spreadsheet" used by the tests.
    """
    total_billed = Decimal("0")
    total_extras = Decimal("0")
    total_adjustments = Decimal("0")
    start = datetime.combine(period.period_start, time.min, tzinfo=IST)
    end = datetime.combine(period.period_end + timedelta(days=1), time.min, tzinfo=IST)

    for bill in Bill.objects.filter(billing_period=period):
        rate = bill.common_diet_rate_snapshot
        meal_component = (
            Decimal(max(bill.minimum_diet_count_snapshot, bill.actual_meal_count)) * rate
        )
        extras = (
            ExtraTransaction.objects.filter(
                student_id=bill.student_id,
                mess_id=bill.mess_id,
                transaction_timestamp__gte=start,
                transaction_timestamp__lt=end,
            )
            .exclude(sync_status__in=["REJECTED", "CONFLICT", "DUPLICATE"])
            .aggregate(total=billing.Sum("total_amount"))["total"]
            or Decimal("0")
        )
        snack_rows = MealConsumption.objects.filter(
            student_id=bill.student_id,
            mess_id=bill.mess_id,
            meal_date__gte=period.period_start,
            meal_date__lte=period.period_end,
            meal_type__code__in=["EVENING_SNACKS", "SNACKS"],
        )
        extras += sum(
            (row.price_at_transaction for row in snack_rows), Decimal("0")
        )
        adjustments = (
            BillAdjustment.objects.filter(bill_id=bill.bill_id).aggregate(
                total=billing.Sum("amount")
            )["total"]
            or Decimal("0")
        )

        assert bill.meal_component_amount == meal_component.quantize(MONEY)
        assert bill.extra_charges_amount == Decimal(extras).quantize(MONEY)
        assert bill.adjustment_amount == Decimal(adjustments).quantize(MONEY)
        assert bill.final_amount == (
            bill.meal_component_amount
            + bill.extra_charges_amount
            + bill.adjustment_amount
        )

        total_billed += bill.final_amount
        total_extras += bill.extra_charges_amount
        total_adjustments += bill.adjustment_amount

    return {
        "total_billed": total_billed.quantize(MONEY),
        "total_extras": total_extras.quantize(MONEY),
        "total_adjustments": total_adjustments.quantize(MONEY),
    }


def assert_balances_match_ledger() -> None:
    for account in BalanceAccount.objects.all():
        ledger_sum = (
            BalanceLedgerEntry.objects.filter(balance_account=account).aggregate(
                total=billing.Sum("amount")
            )["total"]
            or Decimal("0")
        )
        assert Decimal(ledger_sum).quantize(MONEY) == account.current_balance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def freeze_phase10_clock():
    """Pin the clock after the billing month so fixtures are deterministic."""
    clock.set_time(ist_dt(date(2026, 12, 1), time(9, 0)))
    yield
    clock.reset()


@pytest.fixture(autouse=True)
def setup_roles_and_meal_types(db):
    for role_name in ["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]:
        Role.objects.get_or_create(
            name=role_name, defaults={"description": f"{role_name} role"}
        )
    for code, name, seq in [
        ("BREAKFAST", "Breakfast", 1),
        ("LUNCH", "Lunch", 2),
        ("EVENING_SNACKS", "Evening Snacks", 3),
        ("DINNER", "Dinner", 4),
    ]:
        MealType.objects.get_or_create(
            code=code, defaults={"name": name, "sequence_no": seq}
        )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def billing_setup(db):
    hostel_a = Hostel.objects.create(code="H-P10-A", name="Hostel P10 A", status="ACTIVE")
    hostel_b = Hostel.objects.create(code="H-P10-B", name="Hostel P10 B", status="ACTIVE")
    mess_a = Mess.objects.create(code="M-P10-A", name="Mess P10 A", status="ACTIVE")
    mess_b = Mess.objects.create(code="M-P10-B", name="Mess P10 B", status="ACTIVE")

    admin = make_user("admin_p10@college.edu", "Admin P10", "SUPER_ADMIN")
    clerk_user = make_user("clerk_p10@college.edu", "Clerk P10", "HOSTEL_CLERK")
    HostelClerkAssignment.objects.create(
        user=clerk_user, hostel=hostel_a, is_active=True, assigned_at=clock.now()
    )
    manager_user = make_user("manager_p10@college.edu", "Manager P10", "MESS_MANAGER")
    MessManagerAssignment.objects.create(
        user=manager_user, mess=mess_a, is_active=True, assigned_at=clock.now()
    )
    manager_device = DeviceRegistration.objects.create(
        user=manager_user,
        device_id="dev-manager-p10",
        platform="ANDROID",
        session_status="ACTIVE",
        registered_at=clock.now(),
    )

    semester = Semester.objects.create(
        code="AUTUMN-2026",
        name="Autumn Semester 2026",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 12, 31),
        status="ACTIVE",
    )

    BillingPolicy.objects.create(
        mess=mess_a,
        minimum_diet_count=30,
        effective_from=PERIOD_START,
        policy_version=1,
        created_by=admin,
    )
    BillingPolicy.objects.create(
        mess=mess_b,
        minimum_diet_count=30,
        effective_from=PERIOD_START,
        policy_version=1,
        created_by=admin,
    )

    # Mid-month rate change: the bill must keep the first-day rate.
    MealRate.objects.create(
        mess=mess_a,
        effective_from=PERIOD_START,
        effective_to=date(2026, 11, 15),
        rate=Decimal("150.0000"),
        created_by=admin,
    )
    MealRate.objects.create(
        mess=mess_a,
        effective_from=date(2026, 11, 15),
        rate=Decimal("200.0000"),
        created_by=admin,
    )
    MealRate.objects.create(
        mess=mess_b,
        effective_from=PERIOD_START,
        rate=Decimal("150.0000"),
        created_by=admin,
    )

    create_calendar(mess_a)
    create_calendar(mess_b)

    c01_student, c01_user = make_student(
        email="c01_p10@college.edu", roll_number="23110001", hostel=hostel_a
    )
    equal_student, _ = make_student(
        email="equal_p10@college.edu", roll_number="23110002", hostel=hostel_a
    )
    above_student, _ = make_student(
        email="above_p10@college.edu", roll_number="23110003", hostel=hostel_a
    )
    plain_student, plain_user = make_student(
        email="plain_p10@college.edu", roll_number="23110004", hostel=hostel_a
    )
    paused_student, _ = make_student(
        email="paused_p10@college.edu", roll_number="23110005", hostel=hostel_a
    )
    transfer_student, _ = make_student(
        email="transfer_p10@college.edu", roll_number="23110006", hostel=hostel_b
    )
    boundary_student, _ = make_student(
        email="boundary_p10@college.edu", roll_number="23110007", hostel=hostel_b
    )

    for student in [c01_student, equal_student, above_student, plain_student, paused_student]:
        StudentMessAssignment.objects.create(
            student=student,
            hostel=hostel_a,
            mess=mess_a,
            status="ACTIVE",
            effective_from=PERIOD_START,
        )
    # DEC-24 transfer: first half at mess A, second half at mess B.
    StudentMessAssignment.objects.create(
        student=transfer_student,
        hostel=hostel_a,
        mess=mess_a,
        status="ENDED",
        effective_from=PERIOD_START,
        effective_to=date(2026, 11, 16),
    )
    StudentMessAssignment.objects.create(
        student=transfer_student,
        hostel=hostel_b,
        mess=mess_b,
        status="ACTIVE",
        effective_from=date(2026, 11, 16),
    )
    StudentMessAssignment.objects.create(
        student=boundary_student,
        hostel=hostel_b,
        mess=mess_b,
        status="ACTIVE",
        effective_from=PERIOD_START,
    )

    create_meals(student=c01_student, mess=mess_a, count=26, recorded_by=admin)
    create_meals(student=equal_student, mess=mess_a, count=30, recorded_by=admin)
    create_meals(student=above_student, mess=mess_a, count=34, recorded_by=admin)

    extra_item = ExtraItem.objects.create(
        hostel=hostel_a,
        name="Egg Curry",
        normalized_name="EGG CURRY",
        status="ACTIVE",
    )
    create_extra(
        student=c01_student,
        hostel=hostel_a,
        mess=mess_a,
        item=extra_item,
        quantity=66,
        unit_price=Decimal("20.0000"),
        when=ist_dt(date(2026, 11, 10), time(12, 0)),
        recorded_by=admin,
    )

    period = BillingPeriod.objects.create(
        year=2026,
        month=11,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        status="OPEN",
    )

    return {
        "hostel_a": hostel_a,
        "hostel_b": hostel_b,
        "mess_a": mess_a,
        "mess_b": mess_b,
        "admin": admin,
        "clerk_user": clerk_user,
        "manager_user": manager_user,
        "manager_device": manager_device,
        "semester": semester,
        "period": period,
        "c01_student": c01_student,
        "c01_user": c01_user,
        "equal_student": equal_student,
        "above_student": above_student,
        "plain_student": plain_student,
        "plain_user": plain_user,
        "paused_student": paused_student,
        "transfer_student": transfer_student,
        "boundary_student": boundary_student,
        "extra_item": extra_item,
    }


def generate(setup: dict[str, Any]) -> dict[str, Any]:
    return billing.generate_bills(
        billing_period_id=setup["period"].billing_period_id,
        actor=setup["admin"],
    )


def run_to_locked(setup: dict[str, Any]) -> BillingPeriod:
    generate(setup)
    billing.review_period(
        billing_period_id=setup["period"].billing_period_id, actor=setup["admin"]
    )
    billing.lock_period(
        billing_period_id=setup["period"].billing_period_id, actor=setup["admin"]
    )
    setup["period"].refresh_from_db()
    return setup["period"]


# ---------------------------------------------------------------------------
# C01 formula
# ---------------------------------------------------------------------------


class TestC01Formula:
    def test_c01_example_below_minimum(self, billing_setup):
        """Policy 30, meals 26 -> MAX is 30; extras and fees are additions only."""
        s = billing_setup
        generate(s)
        bill = Bill.objects.get(student=s["c01_student"], billing_period=s["period"])

        assert bill.minimum_diet_count_snapshot == 30
        assert bill.actual_meal_count == 26
        assert bill.common_diet_rate_snapshot == Decimal("150.0000")
        assert bill.meal_component_amount == Decimal("4500.0000")
        assert bill.extra_charges_amount == Decimal("1320.0000")

        billing.add_bill_adjustment(
            bill_id=bill.bill_id,
            amount=Decimal("1000.0000"),
            adjustment_type="FEE",
            reason="Library fee",
            actor=s["admin"],
        )
        billing.add_bill_adjustment(
            bill_id=bill.bill_id,
            amount=Decimal("100.0000"),
            adjustment_type="FINE",
            reason="Late return",
            actor=s["admin"],
        )
        bill.refresh_from_db()
        assert bill.adjustment_amount == Decimal("1100.0000")
        assert bill.final_amount == Decimal("6920.0000")  # 4500 + 1320 + 1100

        # Regeneration preserves every adjustment and rebuilds the same totals.
        generate(s)
        bill.refresh_from_db()
        assert bill.meal_component_amount == Decimal("4500.0000")
        assert bill.extra_charges_amount == Decimal("1320.0000")
        assert bill.adjustment_amount == Decimal("1100.0000")
        assert bill.final_amount == Decimal("6920.0000")

    def test_meal_count_equal_to_minimum(self, billing_setup):
        s = billing_setup
        generate(s)
        bill = Bill.objects.get(student=s["equal_student"], billing_period=s["period"])
        assert bill.actual_meal_count == 30
        assert bill.minimum_diet_count_snapshot == 30
        assert bill.meal_component_amount == Decimal("4500.0000")
        assert bill.final_amount == Decimal("4500.0000")

    def test_meal_count_above_minimum(self, billing_setup):
        s = billing_setup
        generate(s)
        bill = Bill.objects.get(student=s["above_student"], billing_period=s["period"])
        assert bill.actual_meal_count == 34
        assert bill.minimum_diet_count_snapshot == 30
        assert bill.meal_component_amount == Decimal("5100.0000")  # 34 x 150
        assert bill.final_amount == Decimal("5100.0000")

    def test_every_generated_bill_matches_independent_formula(self, billing_setup):
        """Property-style check: recompute every bill from source rows."""
        s = billing_setup
        # Add a snack and a boundary extra so the property covers both extras paths.
        create_snack(
            student=s["boundary_student"],
            mess=s["mess_b"],
            day=date(2026, 11, 5),
            price=Decimal("25.0000"),
            recorded_by=s["admin"],
        )
        create_extra(
            student=s["boundary_student"],
            hostel=s["hostel_b"],
            mess=s["mess_b"],
            item=s["extra_item"],
            quantity=3,
            unit_price=Decimal("10.0000"),
            when=ist_dt(date(2026, 11, 6), time(13, 0)),
            recorded_by=s["admin"],
        )
        generate(s)

        bills = Bill.objects.filter(billing_period=s["period"])
        assert bills.count() == 8  # 7 students, the transfer student has two bills
        expected = independent_totals(s["period"])
        actual = bill_totals(s["period"])
        assert actual["total_billed"] == expected["total_billed"]
        assert actual["total_extras"] == expected["total_extras"]
        assert actual["total_adjustments"] == expected["total_adjustments"]
        assert actual["bill_count"] == bills.count()
        assert actual["student_count"] == 7

    def test_mid_month_rate_change_uses_first_day_rate(self, billing_setup):
        s = billing_setup
        generate(s)
        bill = Bill.objects.get(student=s["plain_student"], billing_period=s["period"])
        assert bill.common_diet_rate_snapshot == Decimal("150.0000")
        assert bill.meal_component_amount == Decimal("4500.0000")  # not 30 x 200


# ---------------------------------------------------------------------------
# Pause and transfer proration
# ---------------------------------------------------------------------------


class TestPauseAndProration:
    def test_pause_reduces_billed_minimum(self, billing_setup):
        s = billing_setup
        make_active_pause(
            student=s["paused_student"],
            mess=s["mess_a"],
            start=date(2026, 11, 10),
            end=date(2026, 11, 14),
        )
        generate(s)
        bill = Bill.objects.get(student=s["paused_student"], billing_period=s["period"])
        assert bill.minimum_diet_count_snapshot == 15  # 30 - (5 days x 3 slots)
        assert bill.actual_meal_count == 0
        assert bill.meal_component_amount == Decimal("2250.0000")

    def test_pause_cannot_push_billed_minimum_below_zero(self, billing_setup):
        s = billing_setup
        make_active_pause(
            student=s["paused_student"],
            mess=s["mess_a"],
            start=PERIOD_START,
            end=PERIOD_END,
        )
        generate(s)
        bill = Bill.objects.get(student=s["paused_student"], billing_period=s["period"])
        assert bill.minimum_diet_count_snapshot == 0
        assert bill.meal_component_amount == Decimal("0.0000")

    def test_mid_month_transfer_prorates_both_messes(self, billing_setup):
        s = billing_setup
        generate(s)
        first = Bill.objects.get(
            student=s["transfer_student"],
            mess=s["mess_a"],
            billing_period=s["period"],
        )
        second = Bill.objects.get(
            student=s["transfer_student"],
            mess=s["mess_b"],
            billing_period=s["period"],
        )
        assert first.minimum_diet_count_snapshot == 15  # 45 of 90 slots
        assert second.minimum_diet_count_snapshot == 15
        assert first.meal_component_amount == Decimal("2250.0000")
        assert second.meal_component_amount == Decimal("2250.0000")
        assert (
            first.minimum_diet_count_snapshot + second.minimum_diet_count_snapshot
        ) == 30


# ---------------------------------------------------------------------------
# Extras, snacks and regeneration
# ---------------------------------------------------------------------------


class TestExtrasAndRegeneration:
    def test_extras_use_ist_period_boundaries(self, billing_setup):
        s = billing_setup
        # Inside: first day 00:15 IST and last day 23:30 IST.
        create_extra(
            student=s["boundary_student"],
            hostel=s["hostel_b"],
            mess=s["mess_b"],
            item=s["extra_item"],
            quantity=1,
            unit_price=Decimal("5.0000"),
            when=ist_dt(date(2026, 11, 1), time(0, 15)),
            recorded_by=s["admin"],
        )
        create_extra(
            student=s["boundary_student"],
            hostel=s["hostel_b"],
            mess=s["mess_b"],
            item=s["extra_item"],
            quantity=1,
            unit_price=Decimal("11.0000"),
            when=ist_dt(date(2026, 11, 30), time(23, 30)),
            recorded_by=s["admin"],
        )
        # Outside: last day of October and first day of December in IST.
        create_extra(
            student=s["boundary_student"],
            hostel=s["hostel_b"],
            mess=s["mess_b"],
            item=s["extra_item"],
            quantity=1,
            unit_price=Decimal("7.0000"),
            when=ist_dt(date(2026, 10, 31), time(23, 45)),
            recorded_by=s["admin"],
        )
        create_extra(
            student=s["boundary_student"],
            hostel=s["hostel_b"],
            mess=s["mess_b"],
            item=s["extra_item"],
            quantity=1,
            unit_price=Decimal("13.0000"),
            when=ist_dt(date(2026, 12, 1), time(0, 30)),
            recorded_by=s["admin"],
        )
        # A rejected row inside the period never reaches the bill.
        create_extra(
            student=s["boundary_student"],
            hostel=s["hostel_b"],
            mess=s["mess_b"],
            item=s["extra_item"],
            quantity=1,
            unit_price=Decimal("17.0000"),
            when=ist_dt(date(2026, 11, 15), time(12, 0)),
            recorded_by=s["admin"],
            sync_status="REJECTED",
        )

        generate(s)
        bill = Bill.objects.get(
            student=s["boundary_student"],
            mess=s["mess_b"],
            billing_period=s["period"],
        )
        assert bill.extra_charges_amount == Decimal("16.0000")

    def test_snacks_are_extras_and_never_count_as_meals(self, billing_setup):
        s = billing_setup
        create_snack(
            student=s["plain_student"],
            mess=s["mess_a"],
            day=date(2026, 11, 12),
            price=Decimal("30.0000"),
            recorded_by=s["admin"],
        )
        generate(s)
        bill = Bill.objects.get(student=s["plain_student"], billing_period=s["period"])
        assert bill.actual_meal_count == 0
        assert bill.extra_charges_amount == Decimal("30.0000")
        assert bill.meal_component_amount == Decimal("4500.0000")

    def test_regenerate_twice_is_idempotent(self, billing_setup):
        s = billing_setup
        generate(s)
        first_bill = Bill.objects.get(
            student=s["plain_student"], billing_period=s["period"]
        )
        first_lines = sorted(
            first_bill.lines.values_list(
                "line_type", "calculation_order", "quantity", "amount", "source_entity_id"
            )
        )
        first_values = (
            first_bill.meal_component_amount,
            first_bill.extra_charges_amount,
            first_bill.adjustment_amount,
            first_bill.final_amount,
            first_bill.minimum_diet_count_snapshot,
            first_bill.actual_meal_count,
        )
        bill_count = Bill.objects.filter(billing_period=s["period"]).count()

        generate(s)
        s["period"].refresh_from_db()

        second_bill = Bill.objects.get(
            student=s["plain_student"], billing_period=s["period"]
        )
        second_lines = sorted(
            second_bill.lines.values_list(
                "line_type", "calculation_order", "quantity", "amount", "source_entity_id"
            )
        )
        assert Bill.objects.filter(billing_period=s["period"]).count() == bill_count
        assert first_values == (
            second_bill.meal_component_amount,
            second_bill.extra_charges_amount,
            second_bill.adjustment_amount,
            second_bill.final_amount,
            second_bill.minimum_diet_count_snapshot,
            second_bill.actual_meal_count,
        )
        assert first_lines == second_lines
        assert s["period"].status == "BILL_GENERATED"


# ---------------------------------------------------------------------------
# Fees and fines
# ---------------------------------------------------------------------------


class TestFeesAndFines:
    def test_negative_and_zero_amounts_are_rejected(self, billing_setup):
        s = billing_setup
        generate(s)
        bill = Bill.objects.get(student=s["plain_student"], billing_period=s["period"])
        for amount in (Decimal("-1.0000"), Decimal("0.0000")):
            with pytest.raises(ValidationError):
                billing.add_bill_adjustment(
                    bill_id=bill.bill_id,
                    amount=amount,
                    adjustment_type="FEE",
                    reason="Invalid",
                    actor=s["admin"],
                )

    def test_database_rejects_negative_adjustments(self, billing_setup):
        s = billing_setup
        generate(s)
        bill = Bill.objects.get(student=s["plain_student"], billing_period=s["period"])
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                BillAdjustment.objects.create(
                    bill=bill,
                    amount=Decimal("-5.0000"),
                    adjustment_type="FINE",
                    reason="Negative",
                    created_by=s["admin"],
                )

    def test_adjustment_requires_reason_and_positive_amount_at_the_api(self, billing_setup, api_client):
        s = billing_setup
        generate(s)
        bill = Bill.objects.get(student=s["plain_student"], billing_period=s["period"])
        client = auth_client(api_client, s["admin"], "SUPER_ADMIN")

        response = client.post(
            f"/api/v1/billing/bills/{bill.bill_id}/adjustments",
            {"amount": "10.0000", "adjustment_type": "FEE", "reason": ""},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.post(
            f"/api/v1/billing/bills/{bill.bill_id}/adjustments",
            {"amount": "-10.0000", "adjustment_type": "FEE", "reason": "Refund"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Lock immutability and audited unlock
# ---------------------------------------------------------------------------


class TestLockAndUnlock:
    def test_locked_bill_rejects_orm_and_raw_sql_writes(self, billing_setup):
        s = billing_setup
        run_to_locked(s)
        bill = Bill.objects.get(student=s["plain_student"], billing_period=s["period"])

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                bill.final_amount = bill.final_amount + 1
                bill.save()

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                Bill.objects.filter(bill_id=bill.bill_id).update(
                    final_amount=bill.final_amount + 1
                )

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE billing_bill SET final_amount = final_amount + 1 WHERE bill_id = %s",
                        [bill.bill_id],
                    )

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM billing_bill WHERE bill_id = %s", [bill.bill_id]
                    )

        bill.refresh_from_db()
        assert bill.status == "LOCKED"

    def test_unlock_requires_reason(self, billing_setup):
        s = billing_setup
        run_to_locked(s)
        with pytest.raises(ValidationError):
            billing.unlock_period(
                billing_period_id=s["period"].billing_period_id,
                reason="   ",
                actor=s["admin"],
            )

    def test_unlock_reopens_bills_and_audits_full_state(self, billing_setup):
        s = billing_setup
        run_to_locked(s)
        bill_count = Bill.objects.filter(billing_period=s["period"]).count()

        result = billing.unlock_period(
            billing_period_id=s["period"].billing_period_id,
            reason="Corrected late extras",
            actor=s["admin"],
        )

        s["period"].refresh_from_db()
        assert s["period"].status == "REVIEWED"
        assert s["period"].unlock_reason == "Corrected late extras"
        assert s["period"].unlocked_by_id == s["admin"].user_id
        assert s["period"].unlocked_at is not None
        assert result["reversed_bill_count"] == bill_count
        assert Bill.objects.filter(billing_period=s["period"], status="LOCKED").count() == 0

        audit = AuditLog.objects.get(event_type="BILL_UNLOCKED")
        assert audit.actor_user_id == s["admin"].user_id
        assert audit.old_values_json["status"] == "LOCKED"
        assert audit.new_values_json["status"] == "REVIEWED"
        assert audit.new_values_json["reason"] == "Corrected late extras"
        assert audit.reason == "Corrected late extras"
        assert audit.new_values_json["reversed_bill_count"] == bill_count

    def test_lock_unlock_relock_keeps_ledger_balanced(self, billing_setup):
        s = billing_setup
        billing.set_opening_balance(
            student_id=s["c01_student"].student_id,
            semester_id=s["semester"].semester_id,
            amount=Decimal("10000.0000"),
            actor=s["admin"],
        )
        run_to_locked(s)
        bill = Bill.objects.get(student=s["c01_student"], billing_period=s["period"])
        account = get_balance_account(
            s["c01_student"].student_id, s["semester"].semester_id
        )

        assert account.current_balance == Decimal("10000.0000") - bill.final_amount
        assert_balances_match_ledger()
        assert billing.verify_balances()["drifts"] == []

        billing.unlock_period(
            billing_period_id=s["period"].billing_period_id,
            reason="Relock test",
            actor=s["admin"],
        )
        account.refresh_from_db()
        assert account.current_balance == Decimal("10000.0000")
        assert_balances_match_ledger()

        billing.lock_period(
            billing_period_id=s["period"].billing_period_id, actor=s["admin"]
        )
        account.refresh_from_db()
        assert account.current_balance == Decimal("10000.0000") - bill.final_amount
        assert_balances_match_ledger()
        assert billing.verify_balances()["drifts"] == []

        entry_types = list(
            BalanceLedgerEntry.objects.filter(balance_account=account)
            .order_by("ledger_entry_id")
            .values_list("entry_type", flat=True)
        )
        assert entry_types == ["OPENING", "BILL_CHARGE", "BILL_REVERSAL", "BILL_CHARGE"]

    def test_lock_refuses_stale_transactions(self, billing_setup):
        s = billing_setup
        generate(s)
        billing.review_period(
            billing_period_id=s["period"].billing_period_id, actor=s["admin"]
        )
        # A late meal recorded after generation makes the snapshot stale.
        clock.set_time(ist_dt(date(2026, 12, 1), time(10, 0)))
        create_meals(
            student=s["plain_student"],
            mess=s["mess_a"],
            count=1,
            recorded_by=s["admin"],
        )
        with pytest.raises(ConflictError) as excinfo:
            billing.lock_period(
                billing_period_id=s["period"].billing_period_id, actor=s["admin"]
            )
        assert excinfo.value.code == "BILLING_PERIOD_STALE"


# ---------------------------------------------------------------------------
# Balance ledger account rules
# ---------------------------------------------------------------------------


class TestBalanceLedger:
    def test_one_account_per_student_and_semester(self, billing_setup):
        s = billing_setup
        account = billing.set_opening_balance(
            student_id=s["plain_student"].student_id,
            semester_id=s["semester"].semester_id,
            amount=Decimal("500.0000"),
            actor=s["admin"],
        )
        assert account.current_balance == Decimal("500.0000")

        with pytest.raises(ConflictError):
            billing.set_opening_balance(
                student_id=s["plain_student"].student_id,
                semester_id=s["semester"].semester_id,
                amount=Decimal("100.0000"),
                actor=s["admin"],
            )

        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                BalanceAccount.objects.create(
                    student=s["plain_student"],
                    semester=s["semester"],
                    opening_balance=Decimal("0.0000"),
                    current_balance=Decimal("0.0000"),
                )

    def test_authorized_credit_updates_cached_balance(self, billing_setup):
        s = billing_setup
        billing.set_opening_balance(
            student_id=s["plain_student"].student_id,
            semester_id=s["semester"].semester_id,
            amount=Decimal("100.0000"),
            actor=s["admin"],
        )
        account = billing.add_balance_credit(
            student_id=s["plain_student"].student_id,
            semester_id=s["semester"].semester_id,
            amount=Decimal("250.0000"),
            reference="TXN-123",
            reason="Fee system top-up",
            actor=s["admin"],
        )
        assert account.current_balance == Decimal("350.0000")
        assert_balances_match_ledger()

    def test_negative_balance_does_not_block_a_synced_meal(self, billing_setup):
        s = billing_setup
        billing.set_opening_balance(
            student_id=s["plain_student"].student_id,
            semester_id=s["semester"].semester_id,
            amount=Decimal("0.0000"),
            actor=s["admin"],
            reference="FEE-SYSTEM",
        )
        run_to_locked(s)
        bill = Bill.objects.get(student=s["plain_student"], billing_period=s["period"])
        account = get_balance_account(
            s["plain_student"].student_id, s["semester"].semester_id
        )
        assert account.current_balance == -bill.final_amount
        assert account.current_balance < 0

        result = record_meal(
            transaction_id=uuid.uuid4(),
            student=s["plain_student"],
            meal_date=date(2026, 11, 20),
            meal_type="LUNCH",
            mess=s["mess_a"],
            recorded_by_user=s["manager_user"],
            device_registration=s["manager_device"],
        )
        assert result.status == "SYNCHRONIZED"

    def test_verify_balances_job_alerts_on_drift(self, billing_setup):
        s = billing_setup
        run_to_locked(s)
        call_command("verify_balances", verbosity=0)

        account = BalanceAccount.objects.first()
        BalanceAccount.objects.filter(balance_account_id=account.balance_account_id).update(
            current_balance=account.current_balance + Decimal("1.0000")
        )
        with pytest.raises(CommandError):
            call_command("verify_balances", verbosity=0)

    def test_open_billing_period_job_creates_previous_month(self, billing_setup):
        call_command("open_billing_period", "--date", "2027-02-05", verbosity=0)
        period = BillingPeriod.objects.get(year=2027, month=1)
        assert period.period_start == date(2027, 1, 1)
        assert period.period_end == date(2027, 1, 31)
        assert period.status == "OPEN"
        # Re-running does not create a second row.
        call_command("open_billing_period", "--date", "2027-02-05", verbosity=0)
        assert BillingPeriod.objects.filter(year=2027, month=1).count() == 1


# ---------------------------------------------------------------------------
# Role visibility
# ---------------------------------------------------------------------------


class TestVisibility:
    def test_student_sees_own_bill_only_after_lock(self, billing_setup, api_client):
        s = billing_setup
        generate(s)
        client = auth_client(api_client, s["plain_user"], "STUDENT")

        response = client.get("/api/v1/billing/bills")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

        billing.review_period(
            billing_period_id=s["period"].billing_period_id, actor=s["admin"]
        )
        billing.lock_period(
            billing_period_id=s["period"].billing_period_id, actor=s["admin"]
        )
        response = client.get("/api/v1/billing/bills")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["student_id"] == s["plain_student"].student_id

    def test_manager_has_no_billing_read(self, billing_setup, api_client):
        s = billing_setup
        generate(s)
        client = auth_client(api_client, s["manager_user"], "MESS_MANAGER")
        response = client.get("/api/v1/billing/bills")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == "PERMISSION_DENIED"

    def test_clerk_reads_hostel_bills_and_super_admin_reads_all(self, billing_setup, api_client):
        s = billing_setup
        generate(s)
        clerk = auth_client(api_client, s["clerk_user"], "HOSTEL_CLERK")
        response = clerk.get("/api/v1/billing/bills")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 5  # hostel A students (transfer student lives in hostel B)

        admin = auth_client(api_client, s["admin"], "SUPER_ADMIN")
        response = admin.get("/api/v1/billing/bills")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 8

    def test_student_cannot_read_another_balance(self, billing_setup, api_client):
        s = billing_setup
        billing.set_opening_balance(
            student_id=s["c01_student"].student_id,
            semester_id=s["semester"].semester_id,
            amount=Decimal("100.0000"),
            actor=s["admin"],
        )
        client = auth_client(api_client, s["plain_user"], "STUDENT")
        response = client.get(
            "/api/v1/billing/balances",
            {"student_id": s["c01_student"].student_id},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


class TestConcurrentLock:
    @pytest.mark.django_db(transaction=True)
    def test_two_simultaneous_lock_calls_produce_one_lock(self, billing_setup):
        s = billing_setup
        generate(s)
        billing.review_period(
            billing_period_id=s["period"].billing_period_id, actor=s["admin"]
        )
        bill_count = Bill.objects.filter(billing_period=s["period"]).count()
        barrier = threading.Barrier(2)

        def attempt() -> tuple[str, Any]:
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    result = billing.lock_period(
                        billing_period_id=s["period"].billing_period_id,
                        actor=s["admin"],
                    )
                    return ("locked", result)
                except ConflictError:
                    return ("conflict", None)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=60) for future in [pool.submit(attempt) for _ in range(2)]]

        assert sorted(result[0] for result in results) == ["conflict", "locked"]
        s["period"].refresh_from_db()
        assert s["period"].status == "LOCKED"
        charges = BalanceLedgerEntry.objects.filter(entry_type="BILL_CHARGE").count()
        assert charges == bill_count


# ---------------------------------------------------------------------------
# Exit gate
# ---------------------------------------------------------------------------


class TestPhase10ExitGate:
    @pytest.mark.django_db(transaction=True)
    def test_full_month_300_students_end_to_end(self):
        """
        300 students, two messes, a mid-month rate change, three pauses, a
        transfer, extras, adjustments, lock, unlock and relock.
        """
        admin = make_user("admin_gate@college.edu", "Gate Admin", "SUPER_ADMIN")
        hostel_a = Hostel.objects.create(code="H-GATE-A", name="Gate Hostel A", status="ACTIVE")
        hostel_b = Hostel.objects.create(code="H-GATE-B", name="Gate Hostel B", status="ACTIVE")
        mess_a = Mess.objects.create(code="M-GATE-A", name="Gate Mess A", status="ACTIVE")
        mess_b = Mess.objects.create(code="M-GATE-B", name="Gate Mess B", status="ACTIVE")

        semester = Semester.objects.create(
            code="GATE-2026",
            name="Gate Semester",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
        )
        BillingPolicy.objects.create(
            mess=mess_a,
            minimum_diet_count=30,
            effective_from=PERIOD_START,
            policy_version=1,
            created_by=admin,
        )
        BillingPolicy.objects.create(
            mess=mess_b,
            minimum_diet_count=30,
            effective_from=PERIOD_START,
            policy_version=1,
            created_by=admin,
        )
        MealRate.objects.create(
            mess=mess_a,
            effective_from=PERIOD_START,
            effective_to=date(2026, 11, 15),
            rate=Decimal("150.0000"),
            created_by=admin,
        )
        MealRate.objects.create(
            mess=mess_a,
            effective_from=date(2026, 11, 15),
            rate=Decimal("200.0000"),
            created_by=admin,
        )
        MealRate.objects.create(
            mess=mess_b,
            effective_from=PERIOD_START,
            rate=Decimal("150.0000"),
            created_by=admin,
        )
        create_calendar(mess_a)
        create_calendar(mess_b)

        period = BillingPeriod.objects.create(
            year=2026,
            month=11,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            status="OPEN",
        )

        # --- 300 students, alternating between the two messes ---------------
        users = [
            User(
                email=f"gate{index}@college.edu",
                normalized_email=f"gate{index}@college.edu",
                full_name=f"Gate Student {index}",
                status="ACTIVE",
            )
            for index in range(300)
        ]
        User.objects.bulk_create(users)
        student_role = Role.objects.get(name="STUDENT")
        UserRole.objects.bulk_create(
            [UserRole(user=user, role=student_role) for user in users]
        )
        students = [
            Student(
                user=user,
                roll_number=f"GATE{index:04d}",
                hostel=hostel_a if index % 2 == 0 else hostel_b,
                status="ACTIVE",
            )
            for index, user in enumerate(users)
        ]
        Student.objects.bulk_create(students)

        assignments = []
        for index, student in enumerate(students):
            if index == 0:
                # Mid-month transfer from mess A to mess B (DEC-24).
                assignments.append(
                    StudentMessAssignment(
                        student=student,
                        hostel=hostel_a,
                        mess=mess_a,
                        status="ENDED",
                        effective_from=PERIOD_START,
                        effective_to=date(2026, 11, 16),
                    )
                )
                assignments.append(
                    StudentMessAssignment(
                        student=student,
                        hostel=hostel_b,
                        mess=mess_b,
                        status="ACTIVE",
                        effective_from=date(2026, 11, 16),
                    )
                )
            else:
                mess = mess_a if index % 2 == 0 else mess_b
                hostel = hostel_a if index % 2 == 0 else hostel_b
                assignments.append(
                    StudentMessAssignment(
                        student=student,
                        hostel=hostel,
                        mess=mess,
                        status="ACTIVE",
                        effective_from=PERIOD_START,
                    )
                )
        StudentMessAssignment.objects.bulk_create(assignments)

        # --- A deterministic spread of meals (some below, some above min) ---
        meal_types = [MealType.objects.get(code=code) for code in QUALIFYING_CODES]
        meals = []
        for index, student in enumerate(students):
            count = index % 12
            mess = mess_a if index % 2 == 0 else mess_b
            for slot in range(count):
                day = PERIOD_START + timedelta(days=slot // 3)
                meal_type = meal_types[slot % 3]
                meals.append(
                    MealConsumption(
                        transaction_id=uuid.uuid4(),
                        student=student,
                        roll_number_snapshot=student.roll_number,
                        mess=mess,
                        meal_type=meal_type,
                        meal_date=day,
                        price_at_transaction=Decimal("150.0000"),
                        transaction_timestamp=ist_dt(day, time(12, 0)),
                        recorded_by_user=admin,
                        source="QR",
                        sync_status="SYNCHRONIZED",
                        accepted_at=clock.now(),
                    )
                )
        MealConsumption.objects.bulk_create(meals)

        # --- Three pauses for mess A students --------------------------------
        for student in [students[10], students[12], students[14]]:
            MessPause.objects.create(
                student=student,
                mess=mess_a,
                requested_start_date=date(2026, 11, 10),
                requested_end_date=date(2026, 11, 14),
                effective_start_date=date(2026, 11, 10),
                effective_end_date=date(2026, 11, 14),
                activation_meal_date=date(2026, 11, 9),
                status="ACTIVE",
                requested_at=clock.now(),
            )

        # --- Extras for five students ---------------------------------------
        extra_item = ExtraItem.objects.create(
            hostel=hostel_a,
            name="Gate Juice",
            normalized_name="GATE JUICE",
            status="ACTIVE",
        )
        for index in range(5):
            create_extra(
                student=students[index],
                hostel=students[index].hostel,
                mess=mess_a if index % 2 == 0 else mess_b,
                item=extra_item,
                quantity=2,
                unit_price=Decimal("20.0000"),
                when=ist_dt(date(2026, 11, 20), time(12, 0)),
                recorded_by=admin,
            )

        # --- Opening balances for five students ------------------------------
        for student in students[:5]:
            billing.set_opening_balance(
                student_id=student.student_id,
                semester_id=semester.semester_id,
                amount=Decimal("5000.0000"),
                actor=admin,
            )

        result = billing.generate_bills(
            billing_period_id=period.billing_period_id, actor=admin
        )
        assert result["generated"] == 301
        assert Bill.objects.filter(billing_period=period).count() == 301

        # First-day rate snapshot must win on mess A despite the later rate.
        assert not Bill.objects.filter(billing_period=period, mess=mess_a).exclude(
            common_diet_rate_snapshot=Decimal("150.0000")
        ).exists()

        # --- Adjustments on two bills ----------------------------------------
        for bill in Bill.objects.filter(billing_period=period).order_by("bill_id")[:2]:
            billing.add_bill_adjustment(
                bill_id=bill.bill_id,
                amount=Decimal("100.0000"),
                adjustment_type="FEE",
                reason="Gate fee",
                actor=admin,
            )

        expected = independent_totals(period)
        actual = bill_totals(period)
        assert actual["total_billed"] == expected["total_billed"]
        assert actual["total_extras"] == expected["total_extras"]
        assert actual["total_adjustments"] == expected["total_adjustments"]
        assert actual["bill_count"] == 301
        assert actual["student_count"] == 300

        billing.review_period(billing_period_id=period.billing_period_id, actor=admin)
        lock_result = billing.lock_period(
            billing_period_id=period.billing_period_id, actor=admin
        )
        assert lock_result["bill_count"] == 301
        period.refresh_from_db()
        assert period.status == "LOCKED"
        assert_balances_match_ledger()

        unlock_result = billing.unlock_period(
            billing_period_id=period.billing_period_id,
            reason="Exit gate relock",
            actor=admin,
        )
        assert unlock_result["reversed_bill_count"] == 301
        assert_balances_match_ledger()

        relock_result = billing.lock_period(
            billing_period_id=period.billing_period_id, actor=admin
        )
        assert relock_result["bill_count"] == 301
        assert_balances_match_ledger()
        assert billing.verify_balances()["drifts"] == []

        # The ledger tells the whole story: every bill was charged, reversed and
        # charged again, with the final charges sitting after the last reversal.
        for account in BalanceAccount.objects.all():
            entries = list(
                BalanceLedgerEntry.objects.filter(balance_account=account)
                .order_by("ledger_entry_id")
                .values_list("entry_type", flat=True)
            )
            assert entries[-1] == "BILL_CHARGE"
            last_reversal = max(
                index
                for index, entry_type in enumerate(entries)
                if entry_type == "BILL_REVERSAL"
            )
            final_charges = entries[last_reversal + 1 :]
            assert final_charges == ["BILL_CHARGE"] * len(final_charges)
            bill_count_for_student = Bill.objects.filter(
                student_id=account.student_id, billing_period=period
            ).count()
            assert len(final_charges) == bill_count_for_student

        event_types = set(AuditLog.objects.values_list("event_type", flat=True))
        assert {
            "BILLING_PERIOD_GENERATED",
            "BILLING_PERIOD_REVIEWED",
            "BILL_LOCKED",
            "BILL_UNLOCKED",
            "BILL_ADJUSTED",
            "BALANCE_OPENING_SET",
        }.issubset(event_types)

        # Every audit event is present and no lock/unlock event is missing.
        assert AuditLog.objects.filter(event_type="BILL_LOCKED").count() == 2
        assert AuditLog.objects.filter(event_type="BILL_UNLOCKED").count() == 1
        unlock_audit = AuditLog.objects.get(event_type="BILL_UNLOCKED")
        assert unlock_audit.old_values_json["status"] == "LOCKED"
        assert unlock_audit.new_values_json["status"] == "REVIEWED"
        assert unlock_audit.actor_user_id == admin.user_id
