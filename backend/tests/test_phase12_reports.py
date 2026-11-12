"""
Phase 12 test suite: reports and exports
[SPEC DBDD §20, SDD §50/§51, SRS §25, App Flow §16, ImplementationGuide Phase 12].

Coverage:
- The role/report matrix, including every "No" cell (403) and empty scopes (200).
- Transfer scoping: history follows the assignment effective on the row's date.
- Totals versus independent SQL.
- CSV formula neutralisation, XLSX typing and PDF output/parity.
- Range limits, export row caps and empty exports.
- IST transaction-date semantics for extras and MealDate semantics for meals.
- REPORT_EXPORTED audit metadata (never content).
- The Phase 12 exit gate.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import uuid
import zlib
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.db.models import Sum
from openpyxl import load_workbook
from rest_framework import status
from rest_framework.test import APIClient

from apps.attendance.models import ExtraTransaction, MealConsumption
from apps.audit.models import AuditLog
from apps.billing.models import (
    BalanceAccount,
    BalanceLedgerEntry,
    Bill,
    BillingPeriod,
    Semester,
)
from apps.core.clock import clock
from apps.feedback.models import Feedback
from apps.hostel.models import (
    Hostel,
    HostelClerkAssignment,
    Student,
    StudentMessAssignment,
)
from apps.identity.models import DeviceRegistration, Role, User, UserRole
from apps.identity.services.token_service import generate_access_token
from apps.mess.models import ExtraItem, MealOccurrence, MealType, Mess, MessManagerAssignment
from apps.pause.models import MessPause, MessPauseMealSlot
from apps.reports import exporters, services

IST = ZoneInfo("Asia/Kolkata")
REPORT_FROM = date(2026, 8, 1)
REPORT_TO = date(2026, 8, 31)

ALL_REPORTS = [
    "student-billing",
    "meal-consumption",
    "extra-item-usage",
    "pause",
    "feedback",
    "student-balance",
    "hostel-comparison",
    "mess-comparison",
    "cross-hostel-statistics",
]

EXPECTED_MATRIX = {
    "student-billing": {"manager": True, "clerk_a": True, "clerk_b": True, "admin": True},
    "meal-consumption": {"manager": True, "clerk_a": True, "clerk_b": True, "admin": True},
    "extra-item-usage": {"manager": True, "clerk_a": True, "clerk_b": True, "admin": True},
    "pause": {"manager": True, "clerk_a": True, "clerk_b": True, "admin": True},
    "feedback": {"manager": False, "clerk_a": True, "clerk_b": True, "admin": True},
    "student-balance": {"manager": False, "clerk_a": True, "clerk_b": True, "admin": True},
    "hostel-comparison": {"manager": False, "clerk_a": False, "clerk_b": False, "admin": True},
    "mess-comparison": {"manager": False, "clerk_a": False, "clerk_b": False, "admin": True},
    "cross-hostel-statistics": {"manager": False, "clerk_a": False, "clerk_b": False, "admin": True},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ist_dt(day: date, clock_time: time = time(9, 0)) -> datetime:
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


def make_student(*, email: str, roll_number: str, hostel: Hostel) -> tuple[Student, User]:
    user = make_user(email, roll_number, "STUDENT")
    student = Student.objects.create(
        user=user, roll_number=roll_number, hostel=hostel, status="ACTIVE"
    )
    return student, user


def auth_client(client: APIClient, user: User, role_name: str) -> APIClient:
    device = DeviceRegistration.objects.filter(
        user=user, session_status="ACTIVE"
    ).first()
    if not device:
        device = DeviceRegistration.objects.create(
            user=user,
            device_id=f"dev-p12-{user.user_id}",
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


def assert_error(response, http_status: int, code: str | None = None) -> None:
    assert response.status_code == http_status, getattr(response, "data", response.content)
    assert "traceId" in response.data
    if code is not None:
        assert response.data["code"] == code, response.data


def report_params(**overrides) -> dict:
    params = {
        "from": REPORT_FROM.isoformat(),
        "to": REPORT_TO.isoformat(),
    }
    params.update(overrides)
    return params


def get_json(client: APIClient, report_id: str, **overrides) -> dict:
    response = client.get(f"/api/v1/reports/{report_id}", report_params(**overrides))
    assert response.status_code == status.HTTP_200_OK, response.data
    return response.data


def get_file(client: APIClient, report_id: str, fmt: str, **overrides):
    response = client.get(
        f"/api/v1/reports/{report_id}", report_params(format=fmt, **overrides)
    )
    assert response.status_code == status.HTTP_200_OK, getattr(response, "data", response)
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def freeze_phase12_clock():
    clock.set_time(ist_dt(date(2026, 8, 20)))
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
def setup(db):
    hostel_a = Hostel.objects.create(code="H-P12-A", name="Hostel P12 A", status="ACTIVE")
    hostel_b = Hostel.objects.create(code="H-P12-B", name="Hostel P12 B", status="ACTIVE")
    mess_a = Mess.objects.create(code="M-P12-A", name="Mess P12 A", status="ACTIVE")
    mess_b = Mess.objects.create(code="M-P12-B", name="Mess P12 B", status="ACTIVE")

    admin = make_user("admin_p12@college.edu", "Admin P12", "SUPER_ADMIN")
    clerk_a = make_user("clerk_a_p12@college.edu", "Clerk A P12", "HOSTEL_CLERK")
    clerk_b = make_user("clerk_b_p12@college.edu", "Clerk B P12", "HOSTEL_CLERK")
    HostelClerkAssignment.objects.create(
        user=clerk_a, hostel=hostel_a, is_active=True, assigned_at=clock.now()
    )
    HostelClerkAssignment.objects.create(
        user=clerk_b, hostel=hostel_b, is_active=True, assigned_at=clock.now()
    )
    manager_a = make_user("manager_a_p12@college.edu", "Manager A P12", "MESS_MANAGER")
    manager_b = make_user("manager_b_p12@college.edu", "Manager B P12", "MESS_MANAGER")
    MessManagerAssignment.objects.create(
        user=manager_a, mess=mess_a, is_active=True, assigned_at=clock.now()
    )
    MessManagerAssignment.objects.create(
        user=manager_b, mess=mess_b, is_active=True, assigned_at=clock.now()
    )

    student_a, student_a_user = make_student(
        email="student_a_p12@college.edu", roll_number="P120001", hostel=hostel_a
    )
    student_b, student_b_user = make_student(
        email="student_b_p12@college.edu", roll_number="P120002", hostel=hostel_b
    )
    transfer, transfer_user = make_student(
        email="transfer_p12@college.edu", roll_number="P120003", hostel=hostel_b
    )

    StudentMessAssignment.objects.create(
        student=student_a,
        hostel=hostel_a,
        mess=mess_a,
        status="ACTIVE",
        effective_from=date(2026, 6, 1),
    )
    StudentMessAssignment.objects.create(
        student=student_b,
        hostel=hostel_b,
        mess=mess_b,
        status="ACTIVE",
        effective_from=date(2026, 6, 1),
    )
    StudentMessAssignment.objects.create(
        student=transfer,
        hostel=hostel_a,
        mess=mess_a,
        status="ENDED",
        effective_from=date(2026, 6, 1),
        effective_to=date(2026, 8, 15),
    )
    StudentMessAssignment.objects.create(
        student=transfer,
        hostel=hostel_b,
        mess=mess_b,
        status="ACTIVE",
        effective_from=date(2026, 8, 15),
    )

    return {
        "hostel_a": hostel_a,
        "hostel_b": hostel_b,
        "mess_a": mess_a,
        "mess_b": mess_b,
        "admin": admin,
        "clerk_a": clerk_a,
        "clerk_b": clerk_b,
        "manager_a": manager_a,
        "manager_b": manager_b,
        "student_a": student_a,
        "student_a_user": student_a_user,
        "student_b": student_b,
        "student_b_user": student_b_user,
        "transfer": transfer,
        "transfer_user": transfer_user,
    }


def _meal(
    *,
    student,
    mess,
    meal_type_code,
    meal_date,
    price="100.0000",
    actor,
    transaction_timestamp=None,
):
    return MealConsumption.objects.create(
        transaction_id=uuid.uuid4(),
        student=student,
        mess=mess,
        meal_type=MealType.objects.get(code=meal_type_code),
        meal_date=meal_date,
        price_at_transaction=Decimal(price),
        transaction_timestamp=transaction_timestamp
        or datetime.combine(meal_date, time(12, 0), tzinfo=IST),
        recorded_by_user=actor,
        source="QR",
        sync_status="SYNCHRONIZED",
        roll_number_snapshot=student.roll_number,
    )


def _extra(
    *,
    student,
    hostel,
    mess,
    item,
    quantity,
    unit_price,
    actor,
    timestamp,
    accepted_at=None,
):
    return ExtraTransaction.objects.create(
        transaction_id=uuid.uuid4(),
        student=student,
        hostel=hostel,
        mess=mess,
        extra_item=item,
        quantity=quantity,
        unit_price_at_transaction=Decimal(unit_price),
        total_amount=Decimal(unit_price) * quantity,
        transaction_timestamp=timestamp,
        accepted_at=accepted_at,
        recorded_by_user=actor,
        source="SCAN_CONFIRMATION",
        sync_status="SYNCHRONIZED",
    )


def _slot(pause, occurrence):
    sequence = pause.meal_slots.count() + 1
    return MessPauseMealSlot.objects.create(
        pause=pause,
        meal_occurrence=occurrence,
        slot_sequence=sequence,
        qualifies_for_activation=True,
        slot_date=occurrence.meal_date,
        consumed_for_activation=True,
    )


@pytest.fixture
def data(setup):
    actor = setup["admin"]
    meal_types = {meal_type.code: meal_type for meal_type in MealType.objects.all()}

    # --- Meals: transfer history must stay on the old hostel/mess -------------
    _meal(
        student=setup["student_a"],
        mess=setup["mess_a"],
        meal_type_code="BREAKFAST",
        meal_date=date(2026, 8, 10),
        actor=actor,
    )
    _meal(
        student=setup["transfer"],
        mess=setup["mess_a"],
        meal_type_code="LUNCH",
        meal_date=date(2026, 8, 10),
        actor=actor,
    )
    _meal(
        student=setup["student_b"],
        mess=setup["mess_b"],
        meal_type_code="LUNCH",
        meal_date=date(2026, 8, 20),
        actor=actor,
    )
    _meal(
        student=setup["transfer"],
        mess=setup["mess_b"],
        meal_type_code="DINNER",
        meal_date=date(2026, 8, 20),
        actor=actor,
    )
    # MealDate stays 21 Aug even though the transaction arrived after IST midnight.
    _meal(
        student=setup["student_a"],
        mess=setup["mess_a"],
        meal_type_code="DINNER",
        meal_date=date(2026, 8, 21),
        actor=actor,
        transaction_timestamp=ist_dt(date(2026, 8, 22), time(0, 10)),
    )

    item_a = ExtraItem.objects.create(
        hostel=setup["hostel_a"], name="Egg Curry", normalized_name="EGG CURRY"
    )
    item_b = ExtraItem.objects.create(
        hostel=setup["hostel_b"], name="Fruit Juice", normalized_name="FRUIT JUICE"
    )
    _extra(
        student=setup["student_a"],
        hostel=setup["hostel_a"],
        mess=setup["mess_a"],
        item=item_a,
        quantity=2,
        unit_price="50.0000",
        actor=actor,
        timestamp=ist_dt(date(2026, 8, 10), time(10, 0)),
    )
    _extra(
        student=setup["transfer"],
        hostel=setup["hostel_a"],
        mess=setup["mess_a"],
        item=item_a,
        quantity=1,
        unit_price="50.0000",
        actor=actor,
        timestamp=ist_dt(date(2026, 8, 10), time(12, 0)),
    )
    _extra(
        student=setup["student_b"],
        hostel=setup["hostel_b"],
        mess=setup["mess_b"],
        item=item_b,
        quantity=1,
        unit_price="30.0000",
        actor=actor,
        timestamp=ist_dt(date(2026, 8, 20), time(12, 0)),
    )
    _extra(
        student=setup["transfer"],
        hostel=setup["hostel_b"],
        mess=setup["mess_b"],
        item=item_b,
        quantity=1,
        unit_price="30.0000",
        actor=actor,
        timestamp=ist_dt(date(2026, 8, 20), time(13, 0)),
    )
    # 21 Aug 23:30 IST -> 21 Aug for reporting, even though it synced on 22 Aug.
    _extra(
        student=setup["student_a"],
        hostel=setup["hostel_a"],
        mess=setup["mess_a"],
        item=item_a,
        quantity=1,
        unit_price="50.0000",
        actor=actor,
        timestamp=ist_dt(date(2026, 8, 21), time(23, 30)),
        accepted_at=ist_dt(date(2026, 8, 22), time(0, 20)),
    )

    # --- Billing -------------------------------------------------------------
    semester = Semester.objects.create(
        code="AUT-2026",
        name="Autumn 2026",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
        status="ACTIVE",
    )
    period = BillingPeriod.objects.create(
        year=2026,
        month=8,
        period_start=REPORT_FROM,
        period_end=REPORT_TO,
        status="OPEN",
    )
    bill_a = Bill.objects.create(
        student=setup["student_a"],
        mess=setup["mess_a"],
        billing_period=period,
        semester=semester,
        meal_component_amount=Decimal("2000.0000"),
        extra_charges_amount=Decimal("100.0000"),
        adjustment_amount=Decimal("50.0000"),
        final_amount=Decimal("2150.0000"),
        common_diet_rate_snapshot=Decimal("100.0000"),
        minimum_diet_count_snapshot=20,
        actual_meal_count=20,
        status="LOCKED",
        generated_at=clock.now(),
        locked_at=clock.now(),
    )
    bill_b = Bill.objects.create(
        student=setup["student_b"],
        mess=setup["mess_b"],
        billing_period=period,
        semester=semester,
        meal_component_amount=Decimal("3000.0000"),
        extra_charges_amount=Decimal("30.0000"),
        adjustment_amount=Decimal("0.0000"),
        final_amount=Decimal("3030.0000"),
        common_diet_rate_snapshot=Decimal("100.0000"),
        minimum_diet_count_snapshot=20,
        actual_meal_count=30,
        status="DRAFT",
        generated_at=clock.now(),
    )
    # Lock the period only after the bills exist: the DB guard rejects bill
    # inserts/updates while the parent period is LOCKED [DBDD §8].
    period.status = "LOCKED"
    period.save(update_fields=["status"])

    account_a = BalanceAccount.objects.create(
        student=setup["student_a"],
        semester=semester,
        opening_balance=Decimal("1000.0000"),
        current_balance=Decimal("1200.0000"),
    )
    account_b = BalanceAccount.objects.create(
        student=setup["student_b"],
        semester=semester,
        opening_balance=Decimal("0.0000"),
        current_balance=Decimal("-200.0000"),
    )
    for account, entry_type, amount, effective in [
        (account_a, "OPENING", Decimal("1000.0000"), date(2026, 8, 1)),
        (account_a, "CREDIT", Decimal("500.0000"), date(2026, 8, 5)),
        (account_a, "BILL_CHARGE", Decimal("-300.0000"), date(2026, 8, 10)),
        (account_b, "OPENING", Decimal("0.0000"), date(2026, 8, 1)),
        (account_b, "BILL_CHARGE", Decimal("-200.0000"), date(2026, 8, 20)),
    ]:
        BalanceLedgerEntry.objects.create(
            balance_account=account,
            entry_type=entry_type,
            amount=amount,
            effective_date=effective,
            created_by=actor,
        )

    # --- Pause ---------------------------------------------------------------
    pause_a = MessPause.objects.create(
        student=setup["student_a"],
        mess=setup["mess_a"],
        requested_start_date=date(2026, 8, 5),
        requested_end_date=date(2026, 8, 7),
        effective_start_date=date(2026, 8, 5),
        effective_end_date=date(2026, 8, 7),
        status="COMPLETED",
        requested_at=clock.now(),
    )
    occurrence_dates = [date(2026, 8, 6), date(2026, 8, 7), date(2026, 8, 8)]
    for occurrence_date in occurrence_dates:
        occurrence, _ = MealOccurrence.objects.get_or_create(
            mess=setup["mess_a"],
            meal_date=occurrence_date,
            meal_type=meal_types["BREAKFAST"],
        )
        _slot(pause_a, occurrence)
    pause_transfer = MessPause.objects.create(
        student=setup["transfer"],
        mess=setup["mess_a"],
        requested_start_date=date(2026, 8, 10),
        requested_end_date=date(2026, 8, 12),
        effective_start_date=date(2026, 8, 10),
        effective_end_date=date(2026, 8, 12),
        status="COMPLETED",
        requested_at=clock.now(),
    )
    pause_b = MessPause.objects.create(
        student=setup["student_b"],
        mess=setup["mess_b"],
        requested_start_date=date(2026, 8, 25),
        requested_end_date=date(2026, 8, 26),
        effective_start_date=date(2026, 8, 25),
        effective_end_date=date(2026, 8, 26),
        status="COMPLETED",
        requested_at=clock.now(),
    )

    # --- Feedback ------------------------------------------------------------
    Feedback.objects.create(
        student=setup["student_a"],
        mess=setup["mess_a"],
        calendar_year=2026,
        calendar_month=8,
        food_quality_rating=4,
        taste_rating=5,
        comments='=HYPERLINK("http://evil.example")',
    )
    Feedback.objects.create(
        student=setup["transfer"],
        mess=setup["mess_a"],
        calendar_year=2026,
        calendar_month=8,
        food_quality_rating=2,
        taste_rating=3,
        comments="-2+3",
    )
    Feedback.objects.create(
        student=setup["student_b"],
        mess=setup["mess_b"],
        calendar_year=2026,
        calendar_month=8,
        food_quality_rating=5,
        taste_rating=4,
        comments="@SUM(1,1)",
    )
    Feedback.objects.create(
        student=setup["student_a"],
        mess=setup["mess_a"],
        calendar_year=2026,
        calendar_month=7,
        food_quality_rating=1,
        taste_rating=1,
        comments="Out of range",
    )

    return {
        **setup,
        "semester": semester,
        "period": period,
        "bill_a": bill_a,
        "bill_b": bill_b,
        "account_a": account_a,
        "account_b": account_b,
        "item_a": item_a,
        "item_b": item_b,
        "pause_a": pause_a,
        "pause_transfer": pause_transfer,
        "pause_b": pause_b,
    }


def clients(setup) -> dict[str, APIClient]:
    return {
        "admin": auth_client(APIClient(), setup["admin"], "SUPER_ADMIN"),
        "clerk_a": auth_client(APIClient(), setup["clerk_a"], "HOSTEL_CLERK"),
        "clerk_b": auth_client(APIClient(), setup["clerk_b"], "HOSTEL_CLERK"),
        "manager": auth_client(APIClient(), setup["manager_a"], "MESS_MANAGER"),
        "manager_b": auth_client(APIClient(), setup["manager_b"], "MESS_MANAGER"),
        "student": auth_client(APIClient(), setup["student_a_user"], "STUDENT"),
    }


# ---------------------------------------------------------------------------
# Role matrix
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRoleMatrix:
    def test_catalog_lists_only_permitted_reports(self, setup):
        c = clients(setup)

        manager_ids = [item["id"] for item in c["manager"].get("/api/v1/reports").data["reports"]]
        clerk_ids = [item["id"] for item in c["clerk_a"].get("/api/v1/reports").data["reports"]]
        admin_ids = [item["id"] for item in c["admin"].get("/api/v1/reports").data["reports"]]

        assert manager_ids == ALL_REPORTS[:4]
        assert clerk_ids == ALL_REPORTS[:6]
        assert admin_ids == ALL_REPORTS

        assert_error(
            c["student"].get("/api/v1/reports"),
            status.HTTP_403_FORBIDDEN,
            "PERMISSION_DENIED",
        )

    @pytest.mark.parametrize("report_id", ALL_REPORTS)
    @pytest.mark.parametrize("client_key", ["manager", "clerk_a", "clerk_b", "admin"])
    def test_report_matrix(self, data, report_id, client_key):
        c = clients(data)
        allowed = EXPECTED_MATRIX[report_id][client_key]
        response = c[client_key].get(
            f"/api/v1/reports/{report_id}", report_params()
        )
        if allowed:
            assert response.status_code == status.HTTP_200_OK, response.data
        else:
            assert_error(response, status.HTTP_403_FORBIDDEN, "PERMISSION_DENIED")

    def test_student_is_refused_every_report(self, data):
        c = clients(data)
        for report_id in ALL_REPORTS:
            assert_error(
                c["student"].get(f"/api/v1/reports/{report_id}", report_params()),
                status.HTTP_403_FORBIDDEN,
                "PERMISSION_DENIED",
            )

    def test_empty_scope_is_200_with_no_rows(self, data):
        c = clients(data)
        response = c["clerk_a"].get(
            "/api/v1/reports/meal-consumption",
            report_params(**{"from": "2026-07-01", "to": "2026-07-02"}),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0
        assert response.data["results"] == []

    def test_manager_sees_locked_bills_only_for_own_mess(self, data):
        c = clients(data)
        payload = get_json(c["manager"], "student-billing")
        assert payload["count"] == 1
        assert payload["results"][0]["status"] == "LOCKED"
        assert payload["results"][0]["mess"] == data["mess_a"].name

        admin_payload = get_json(c["admin"], "student-billing")
        assert admin_payload["count"] == 2


# ---------------------------------------------------------------------------
# Transfer scoping
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTransferScoping:
    def test_super_admin_report_resolves_hostel_per_meal_date(self, data):
        c = clients(data)
        payload = get_json(c["admin"], "meal-consumption", page_size=200)
        transfer_rows = [
            row for row in payload["results"] if row["roll_number"] == "P120003"
        ]
        assert len(transfer_rows) == 2
        by_date = {row["date"]: row for row in transfer_rows}
        assert by_date["2026-08-10"]["hostel"] == data["hostel_a"].name
        assert by_date["2026-08-10"]["mess"] == data["mess_a"].name
        assert by_date["2026-08-20"]["hostel"] == data["hostel_b"].name
        assert by_date["2026-08-20"]["mess"] == data["mess_b"].name

    def test_clerk_scopes_follow_the_assignment_on_each_meal_date(self, data):
        c = clients(data)
        clerk_a = get_json(c["clerk_a"], "meal-consumption", page_size=200)
        clerk_b = get_json(c["clerk_b"], "meal-consumption", page_size=200)

        a_dates = {
            row["date"]
            for row in clerk_a["results"]
            if row["roll_number"] == "P120003"
        }
        b_dates = {
            row["date"]
            for row in clerk_b["results"]
            if row["roll_number"] == "P120003"
        }
        assert a_dates == {"2026-08-10"}
        assert b_dates == {"2026-08-20"}

    def test_manager_scope_is_own_mess_only(self, data):
        c = clients(data)
        manager_a = get_json(c["manager"], "meal-consumption", page_size=200)
        manager_b = get_json(c["manager_b"], "meal-consumption", page_size=200)

        assert {row["mess"] for row in manager_a["results"]} == {data["mess_a"].name}
        assert {row["mess"] for row in manager_b["results"]} == {data["mess_b"].name}
        assert all(row["roll_number"] != "P120003" or row["mess"] == data["mess_a"].name for row in manager_a["results"])


# ---------------------------------------------------------------------------
# Totals vs independent SQL
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTotals:
    def test_meal_and_extra_totals_match_independent_sql(self, data):
        c = clients(data)
        meal_payload = get_json(c["admin"], "meal-consumption")
        meal_expected = MealConsumption.objects.filter(
            meal_date__gte=REPORT_FROM, meal_date__lte=REPORT_TO
        ).aggregate(count=Sum("meal_consumption_id", distinct=True), amount=Sum("price_at_transaction"))
        # Sum(pk) is not a count; use count()/Sum(amount) explicitly.
        assert meal_payload["totals"]["meal_count"] == MealConsumption.objects.filter(
            meal_date__gte=REPORT_FROM, meal_date__lte=REPORT_TO
        ).count()
        assert Decimal(meal_payload["totals"]["amount"]) == MealConsumption.objects.filter(
            meal_date__gte=REPORT_FROM, meal_date__lte=REPORT_TO
        ).aggregate(total=Sum("price_at_transaction"))["total"]

        extra_payload = get_json(c["admin"], "extra-item-usage")
        expected_extras = ExtraTransaction.objects.filter(
            sync_status__in=("SYNCHRONIZED", "IDEMPOTENT_SUCCESS"),
            transaction_timestamp__date__gte=REPORT_FROM,
            transaction_timestamp__date__lte=REPORT_TO,
        )
        assert extra_payload["totals"]["transaction_count"] == expected_extras.count()
        assert extra_payload["totals"]["quantity"] == expected_extras.aggregate(total=Sum("quantity"))["total"]
        assert Decimal(extra_payload["totals"]["amount"]) == expected_extras.aggregate(total=Sum("total_amount"))["total"]

    def test_billing_pause_feedback_balance_totals(self, data):
        c = clients(data)

        billing = get_json(c["admin"], "student-billing")
        assert billing["totals"]["bill_count"] == 2
        assert Decimal(billing["totals"]["final_amount"]) == Decimal("5180.0000")

        pause = get_json(c["admin"], "pause")
        assert pause["totals"]["pause_count"] == 3
        assert pause["totals"]["counted_slots"] == 3

        feedback = get_json(c["admin"], "feedback")
        assert feedback["totals"]["response_count"] == 3
        assert Decimal(feedback["totals"]["average_quality"]) == Decimal("3.67")
        assert Decimal(feedback["totals"]["average_taste"]) == Decimal("4.00")

        balance = get_json(c["admin"], "student-balance")
        assert balance["totals"]["account_count"] == 2
        assert Decimal(balance["totals"]["opening"]) == Decimal("1000.0000")
        assert Decimal(balance["totals"]["credits"]) == Decimal("500.0000")
        assert Decimal(balance["totals"]["charges"]) == Decimal("500.0000")
        assert Decimal(balance["totals"]["current_balance"]) == Decimal("1000.0000")

    def test_comparison_totals_match_rows(self, data):
        c = clients(data)
        for report_id, total_key in [
            ("hostel-comparison", "hostel_count"),
            ("mess-comparison", "mess_count"),
            ("cross-hostel-statistics", "row_count"),
        ]:
            payload = get_json(c["admin"], report_id, page_size=200)
            assert payload["count"] == payload["totals"][total_key]
            assert payload["count"] > 0


# ---------------------------------------------------------------------------
# CSV / XLSX / PDF
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExports:
    def test_csv_neutralises_formula_cells(self, data):
        c = clients(data)
        response = get_file(c["admin"], "feedback", "csv")
        assert response["Content-Type"].startswith("text/csv")
        assert response.content.startswith(b"\xef\xbb\xbf")

        text = response.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        flat = [cell for row in rows for cell in row]
        assert any(cell.startswith("'=HYPERLINK") for cell in flat)
        assert any(cell.startswith("'-2+3") for cell in flat)
        assert any(cell.startswith("'@SUM") for cell in flat)

    def test_csv_matches_json_rows_and_totals(self, data):
        c = clients(data)
        payload = get_json(c["admin"], "meal-consumption", page_size=200)
        response = get_file(c["admin"], "meal-consumption", "csv")
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))

        header = rows[0]
        data_rows = rows[1 : 1 + payload["count"]]
        assert len(data_rows) == payload["count"]
        assert header[0] == "Date"
        # Totals section follows the data rows.
        totals_index = rows.index(["Totals"])
        assert rows[totals_index + 1][0] == "Meal Count"
        assert rows[totals_index + 1][1] == str(payload["totals"]["meal_count"])

    def test_xlsx_has_typed_cells_frozen_header_and_totals(self, data):
        c = clients(data)
        payload = get_json(c["admin"], "meal-consumption", page_size=200)
        response = get_file(c["admin"], "meal-consumption", "xlsx")
        workbook = load_workbook(io.BytesIO(response.content), data_only=True)

        assert workbook.sheetnames[0] == "Data"
        sheet = workbook["Data"]
        assert sheet.freeze_panes == "A2"
        assert sheet.max_row == payload["count"] + 1
        # Date and money columns are real typed cells, not strings.
        assert isinstance(sheet.cell(row=2, column=1).value, (date, datetime))
        assert isinstance(sheet.cell(row=2, column=7).value, (int, float))

        totals_sheet = workbook["Totals"]
        values = [cell.value for row in totals_sheet.iter_rows() for cell in row]
        assert "Meal Count" in values

    def test_pdf_is_generated_and_contains_report_text(self, data):
        c = clients(data)
        response = get_file(c["admin"], "meal-consumption", "pdf")
        assert response["Content-Type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

        pdftotext = shutil.which("pdftotext")
        if pdftotext:
            with open("_phase12_probe.pdf", "wb") as handle:
                handle.write(response.content)
            try:
                result = subprocess.run(
                    [pdftotext, "-raw", "_phase12_probe.pdf", "-"],
                    capture_output=True,
                    check=True,
                )
                text = result.stdout.decode("utf-8", errors="replace")
                assert "Meal Consumption" in text
                assert "P120001" in text
                assert "Totals" in text
            finally:
                import os

                os.remove("_phase12_probe.pdf")

        # Poppler's text layout can discard the rupee glyph even when it is
        # rendered, so verify the embedded font's ToUnicode map instead.
        maps = []
        for match in re.finditer(rb"stream\r?\n(.*?)endstream", response.content, re.S):
            try:
                maps.append(zlib.decompress(match.group(1)))
            except zlib.error:
                continue
        assert any(b"20B9" in cmap.upper() for cmap in maps)
        assert exporters._money(Decimal("500")) == "₹500.00"

    def test_export_audit_records_metadata_not_content(self, data):
        c = clients(data)
        before = AuditLog.objects.filter(event_type="REPORT_EXPORTED").count()
        get_file(c["admin"], "feedback", "csv")
        after = AuditLog.objects.filter(event_type="REPORT_EXPORTED").count()
        assert after == before + 1

        log = AuditLog.objects.filter(event_type="REPORT_EXPORTED").latest("audit_id")
        assert log.actor_user_id == data["admin"].user_id
        assert log.entity_type == "REPORT"
        assert log.entity_id == "feedback"
        assert log.metadata_json["format"] == "csv"
        assert log.metadata_json["report_id"] == "feedback"
        assert "row_count" in log.metadata_json
        serialized = str(log.metadata_json)
        assert "HYPERLINK" not in serialized
        assert "comments" not in serialized

    def test_empty_export_contains_headers_only(self, data):
        c = clients(data)
        response = get_file(
            c["admin"],
            "meal-consumption",
            "csv",
            **{"from": "2026-07-01", "to": "2026-07-02"},
        )
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert len(rows) == 1
        assert rows[0][0] == "Date"


# ---------------------------------------------------------------------------
# Validation and caps
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestValidation:
    def test_missing_or_invalid_range(self, data):
        c = clients(data)
        assert_error(
            c["admin"].get("/api/v1/reports/meal-consumption", {"to": "2026-08-31"}),
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
        )
        assert_error(
            c["admin"].get(
                "/api/v1/reports/meal-consumption",
                {"from": "2026-08-31", "to": "2026-08-01"},
            ),
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
        )
        assert_error(
            c["admin"].get(
                "/api/v1/reports/meal-consumption",
                {"from": "2025-01-01", "to": "2026-01-02"},
            ),
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
        )

    def test_bad_format_and_unknown_report(self, data):
        c = clients(data)
        assert_error(
            c["admin"].get(
                "/api/v1/reports/meal-consumption", report_params(format="xml")
            ),
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
        )
        assert_error(
            c["admin"].get("/api/v1/reports/not-a-report", report_params()),
            status.HTTP_404_NOT_FOUND,
            "OBJECT_NOT_FOUND",
        )

    def test_pdf_row_cap(self, data, monkeypatch):
        monkeypatch.setattr(services, "PDF_ROW_CAP", 2)
        c = clients(data)
        assert_error(
            c["admin"].get(
                "/api/v1/reports/meal-consumption",
                report_params(format="pdf"),
            ),
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
        )


# ---------------------------------------------------------------------------
# IST date semantics
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIstSemantics:
    def test_extra_transaction_uses_ist_calendar_date(self, data):
        c = clients(data)
        payload = get_json(
            c["admin"],
            "extra-item-usage",
            **{"from": "2026-08-21", "to": "2026-08-21"},
        )
        assert payload["count"] == 1
        assert payload["results"][0]["date"] == "2026-08-21"
        assert payload["results"][0]["total_amount"] == "50.0000"

    def test_meal_date_is_not_the_sync_date(self, data):
        c = clients(data)
        payload = get_json(
            c["admin"],
            "meal-consumption",
            **{"from": "2026-08-21", "to": "2026-08-21"},
        )
        assert payload["count"] == 1
        assert payload["results"][0]["date"] == "2026-08-21"


# ---------------------------------------------------------------------------
# Exit gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_phase12_exit_gate(data):
    c = clients(data)

    # Matrix: every report reachable by the right roles only.
    for report_id in ALL_REPORTS:
        for client_key in ["manager", "clerk_a", "clerk_b", "admin"]:
            response = c[client_key].get(
                f"/api/v1/reports/{report_id}", report_params()
            )
            if EXPECTED_MATRIX[report_id][client_key]:
                assert response.status_code == status.HTTP_200_OK, (
                    report_id,
                    client_key,
                    response.data,
                )
            else:
                assert response.status_code == status.HTTP_403_FORBIDDEN

    # Three formats verified for a representative report.
    for fmt in ("csv", "xlsx", "pdf"):
        response = get_file(c["admin"], "meal-consumption", fmt)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.content) > 0
        assert "attachment" in response["Content-Disposition"]

    # Range guard and catalog are live.
    assert_error(
        c["admin"].get(
            "/api/v1/reports/meal-consumption",
            {"from": "2025-01-01", "to": "2026-01-02"},
        ),
        status.HTTP_400_BAD_REQUEST,
        "VALIDATION_ERROR",
    )
    assert len(c["admin"].get("/api/v1/reports").data["reports"]) == 9
