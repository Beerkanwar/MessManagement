"""
List-endpoint query budgets [ImplementationGuide Phase 13].

A list endpoint must not issue one query per row. These tests exercise every
GET collection endpoint against a dense fixture and assert that:

1. The number of SQL statements is below a tight, reviewed budget.
2. For paginated endpoints the count does not grow when the page grows from one
   row to the whole fixture (an N+1 regression makes the counts differ).

The budgets are exact ceilings measured against the fixture below. Adding a new
query to a list endpoint breaks this test on purpose: either remove the query or
update the budget with the reviewer's agreement.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.attendance.models import (
    AttendanceCorrection,
    ExtraTransaction,
    MealConsumption,
)
from apps.audit.models import AuditLog
from apps.billing.models import (
    BalanceAccount,
    BalanceLedgerEntry,
    Bill,
    BillAdjustment,
    BillLine,
    BillingPeriod,
    BillingPolicy,
    Semester,
)
from apps.config.models import ApplicationVersionPolicy
from apps.config.services import clear_settings_cache
from apps.core.clock import IST_ZONE, clock
from apps.feedback.models import Feedback
from apps.hostel.models import (
    Hostel,
    HostelClerkAssignment,
    Student,
    StudentMessAssignment,
)
from apps.identity.models import DeviceRegistration, Role, User, UserRole
from apps.menu.models import FoodItem, Menu, MenuItem, MenuMeal
from apps.mess.models import (
    ExtraItem,
    ExtraPrice,
    MealOccurrence,
    MealRate,
    MealType,
    Mess,
    MessManagerAssignment,
)
from apps.pause.models import MessPause, MessPauseMealSlot
from apps.sync.models import SyncBatch, SyncConflict, SyncTransaction


@pytest.fixture(autouse=True)
def frozen_clock_and_clean_cache():
    clock.set_time(datetime(2026, 11, 12, 12, 0, tzinfo=IST_ZONE))
    clear_settings_cache()
    cache.clear()
    yield
    clear_settings_cache()
    cache.clear()
    clock.reset()


def _make_user(email: str, full_name: str, role_name: str) -> User:
    user = User.objects.create_user(
        email=email,
        password="StrongP@ssw0rd123!",
        full_name=full_name,
    )
    UserRole.objects.create(user=user, role=Role.objects.get(name=role_name))
    return user


@pytest.fixture
def dense_campus(db):
    """Six rows of every listable entity, spread over three hostels/messes."""
    for name in ["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]:
        Role.objects.get_or_create(
            name=name, defaults={"description": f"{name} role"}
        )

    admin = User.objects.create_superuser(
        email="qb-admin@college.edu",
        full_name="Query Budget Admin",
        password="StrongP@ssw0rd123!",
    )

    hostels = [
        Hostel.objects.create(code=f"H-QB-{i}", name=f"QB Hostel {i}")
        for i in range(3)
    ]
    messes = [
        Mess.objects.create(code=f"M-QB-{i}", name=f"QB Mess {i}")
        for i in range(3)
    ]

    clerks = [_make_user(f"qb-clerk-{i}@college.edu", f"QB Clerk {i}", "HOSTEL_CLERK") for i in range(3)]
    managers = [_make_user(f"qb-manager-{i}@college.edu", f"QB Manager {i}", "MESS_MANAGER") for i in range(3)]
    for i, clerk in enumerate(clerks):
        HostelClerkAssignment.objects.create(
            user=clerk, hostel=hostels[i], is_active=True, assigned_at=clock.now()
        )
    for i, manager in enumerate(managers):
        MessManagerAssignment.objects.create(
            user=manager, mess=messes[i], is_active=True, assigned_at=clock.now()
        )

    students = []
    student_users = []
    for i in range(6):
        user = _make_user(f"qb-student-{i}@college.edu", f"QB Student {i}", "STUDENT")
        student = Student.objects.create(
            user=user,
            roll_number=f"QBROLL{i:04d}",
            hostel=hostels[i % 3],
            status="ACTIVE",
        )
        StudentMessAssignment.objects.create(
            student=student,
            hostel=hostels[i % 3],
            mess=messes[i % 3],
            status="ACTIVE",
            effective_from=clock.today() - timedelta(days=30),
        )
        students.append(student)
        student_users.append(user)

    # Pending assignments for the clerk verification screen.
    for i in range(3):
        user = _make_user(f"qb-pending-{i}@college.edu", f"QB Pending {i}", "STUDENT")
        student = Student.objects.create(
            user=user,
            roll_number=f"QBPEND{i:04d}",
            hostel=hostels[0],
            status="ACTIVE",
        )
        StudentMessAssignment.objects.create(
            student=student,
            hostel=hostels[0],
            mess=messes[0],
            status="PENDING_VERIFICATION",
            effective_from=clock.today(),
        )

    meal_types = {}
    for code, name, seq in [
        ("BREAKFAST", "Breakfast", 1),
        ("LUNCH", "Lunch", 2),
        ("EVENING_SNACKS", "Evening Snacks", 3),
        ("DINNER", "Dinner", 4),
    ]:
        meal_types[code], _ = MealType.objects.get_or_create(
            code=code, defaults={"name": name, "sequence_no": seq}
        )

    occurrences = []
    for mess in messes:
        for days_ago in range(1, 4):
            occurrences.append(
                MealOccurrence.objects.create(
                    mess=mess,
                    meal_type=meal_types["LUNCH"],
                    meal_date=clock.today() - timedelta(days=days_ago),
                    status="SCHEDULED",
                )
            )

    for mess in messes:
        MealRate.objects.create(
            mess=mess,
            rate=Decimal("100.0000"),
            effective_from=clock.today() - timedelta(days=60),
            effective_to=clock.today() - timedelta(days=30),
            created_by=admin,
        )
        MealRate.objects.create(
            mess=mess,
            rate=Decimal("110.0000"),
            effective_from=clock.today() - timedelta(days=30),
            created_by=admin,
        )

    food_items = [
        FoodItem.objects.create(name=f"QB Food {i}", normalized_name=f"QB FOOD {i}")
        for i in range(4)
    ]

    extra_items = []
    for i, hostel in enumerate(hostels):
        for j in range(2):
            item = ExtraItem.objects.create(
                hostel=hostel,
                name=f"QB Item {i}-{j}",
                normalized_name=f"QB ITEM {i}-{j}",
            )
            ExtraPrice.objects.create(
                extra_item=item,
                unit_price=Decimal("20.0000"),
                effective_from=clock.today() - timedelta(days=30),
                effective_to=clock.today() - timedelta(days=10),
                created_by=admin,
            )
            ExtraPrice.objects.create(
                extra_item=item,
                unit_price=Decimal("25.0000"),
                effective_from=clock.today() - timedelta(days=10),
                created_by=admin,
            )
            extra_items.append(item)

    for i in range(12):
        student = students[i // 2]
        meal_date = clock.today() - timedelta(days=1 + (i % 2))
        MealConsumption.objects.create(
            transaction_id=uuid.uuid4(),
            student=student,
            roll_number_snapshot=student.roll_number,
            mess=messes[i % 3],
            meal_type=meal_types["LUNCH"],
            meal_date=meal_date,
            price_at_transaction=Decimal("100.0000"),
            transaction_timestamp=clock.now() - timedelta(hours=i),
            recorded_by_user=admin,
        )

    for i in range(6):
        ExtraTransaction.objects.create(
            transaction_id=uuid.uuid4(),
            student=students[i],
            hostel=hostels[i % 3],
            mess=messes[i % 3],
            extra_item=extra_items[i],
            quantity=2,
            unit_price_at_transaction=Decimal("20.0000"),
            total_amount=Decimal("40.0000"),
            transaction_timestamp=clock.now() - timedelta(hours=i),
            recorded_by_user=admin,
        )

    for i in range(6):
        AttendanceCorrection.objects.create(
            correction_transaction_id=uuid.uuid4(),
            student=students[i],
            mess=messes[i % 3],
            meal_date=clock.today() - timedelta(days=1 + i),
            meal_type=meal_types["LUNCH"],
            action="ADD_MISSING",
            requested_at=clock.now() - timedelta(hours=i),
            applied_at=clock.now() - timedelta(hours=i),
            reason="Query budget correction.",
            actor_user=admin,
            status="APPLIED",
        )

    for i in range(6):
        pause = MessPause.objects.create(
            student=students[0],
            mess=messes[0],
            requested_start_date=clock.today() - timedelta(days=20 - i),
            requested_end_date=clock.today() - timedelta(days=10 - i),
            effective_start_date=clock.today() - timedelta(days=15 - i),
            effective_end_date=clock.today() - timedelta(days=5 - i),
            status="COMPLETED",
            requested_at=clock.now() - timedelta(days=i),
            completed_at=clock.now() - timedelta(days=i),
        )
        for sequence, occurrence in enumerate(occurrences[:3], start=1):
            MessPauseMealSlot.objects.create(
                pause=pause,
                meal_occurrence=occurrence,
                slot_sequence=sequence,
                qualifies_for_activation=True,
                slot_date=occurrence.meal_date,
                consumed_for_activation=True,
            )

    semesters = [
        Semester.objects.create(
            code="SEM-QB-1",
            name="QB Semester 1",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
        ),
        Semester.objects.create(
            code="SEM-QB-2",
            name="QB Semester 2",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 6, 30),
            status="UPCOMING",
        ),
    ]

    periods = []
    for month in range(6, 12):
        periods.append(
            BillingPeriod.objects.create(
                year=2026,
                month=month,
                period_start=date(2026, month, 1),
                period_end=date(2026, month, 28),
                status="REVIEWED",
                opened_at=clock.now(),
                generated_at=clock.now(),
                reviewed_at=clock.now(),
                locked_at=clock.now(),
                locked_by=admin,
            )
        )

    for mess in messes:
        BillingPolicy.objects.create(
            mess=mess,
            minimum_diet_count=10,
            effective_from=date(2026, 6, 1),
            policy_version=1,
            created_by=admin,
        )

    for i in range(6):
        bill = Bill.objects.create(
            student=students[i],
            mess=messes[i % 3],
            billing_period=periods[i],
            semester=semesters[0],
            meal_component_amount=Decimal("1200.0000"),
            extra_charges_amount=Decimal("0.0000"),
            adjustment_amount=Decimal("0.0000"),
            final_amount=Decimal("1200.0000"),
            common_diet_rate_snapshot=Decimal("100.0000"),
            minimum_diet_count_snapshot=10,
            actual_meal_count=12,
            status="LOCKED",
            generated_at=clock.now(),
            locked_at=clock.now(),
        )
        for order in range(2):
            BillLine.objects.create(
                bill=bill,
                line_type="MINIMUM_DIET",
                description=f"QB line {order}",
                quantity=1,
                unit_rate=Decimal("100.0000"),
                amount=Decimal("100.0000"),
                calculation_order=order + 1,
            )
        for order in range(2):
            BillAdjustment.objects.create(
                bill=bill,
                amount=Decimal("50.0000"),
                adjustment_type="FEE",
                reason=f"QB adjustment {order}",
                created_by=admin,
            )

    for i in range(6):
        account = BalanceAccount.objects.create(
            student=students[i],
            semester=semesters[0],
            opening_balance=Decimal("1000.0000"),
            current_balance=Decimal("500.0000"),
            last_calculated_at=clock.now(),
        )
        BalanceLedgerEntry.objects.create(
            balance_account=account,
            entry_type="CREDIT",
            amount=Decimal("500.0000"),
            effective_date=clock.today(),
            created_by=admin,
        )
        BalanceLedgerEntry.objects.create(
            balance_account=account,
            entry_type="BILL_CHARGE",
            amount=Decimal("-1000.0000"),
            effective_date=clock.today(),
            created_by=admin,
        )

    for i, hostel in enumerate(hostels):
        menu = Menu.objects.create(
            hostel=hostel,
            menu_year=2026,
            menu_month=11,
            status="PUBLISHED",
            published_at=clock.now(),
            published_by_user=admin,
        )
        for meal_index, day in enumerate((1, 2)):
            meal = MenuMeal.objects.create(
                menu=menu,
                menu_date=date(2026, 11, day),
                meal_type=meal_types["LUNCH" if meal_index == 0 else "DINNER"],
            )
            for item_index in range(2):
                MenuItem.objects.create(
                    menu_meal=meal,
                    food_item=food_items[(i + meal_index + item_index) % 4],
                    display_order=item_index + 1,
                )

    for i in range(6):
        Feedback.objects.create(
            student=students[i],
            mess=messes[i % 3],
            calendar_year=2026,
            calendar_month=11,
            food_quality_rating=4,
            taste_rating=5,
            comments="Query budget feedback.",
        )

    manager_device = DeviceRegistration.objects.create(
        user=managers[0],
        device_id="qb-device-manager",
        platform="ANDROID",
        session_status="ACTIVE",
        registered_at=clock.now(),
    )

    for i in range(6):
        batch = SyncBatch.objects.create(
            batch_id=uuid.uuid4(),
            device_registration=manager_device,
            user=managers[0],
            status="COMPLETED",
            client_cursor=i,
            server_cursor_before=i,
            server_cursor_after=i + 1,
            transaction_count=2,
            sent_at=clock.now() - timedelta(hours=i),
            completed_at=clock.now() - timedelta(hours=i),
        )
        for j in range(2):
            transaction = SyncTransaction.objects.create(
                transaction_id=uuid.uuid4(),
                sync_batch=batch,
                entity_type="MEAL_CONSUMPTION",
                entity_id=str(i * 2 + j),
                client_created_at=clock.now() - timedelta(hours=i),
                received_at=clock.now() - timedelta(hours=i),
                processing_status="SYNCHRONIZED",
                result_code="OK",
                idempotency_key=f"qb-{i}-{j}",
            )
            if i < 3:
                SyncConflict.objects.create(
                    sync_transaction=transaction,
                    conflict_type="STALE_STATE",
                    conflict_reason="Query budget conflict.",
                    detected_at=clock.now() - timedelta(hours=i),
                )

    for i in range(12):
        AuditLog.objects.create(
            event_type="LOGIN_SUCCESS" if i % 2 else "SETTING_CHANGED",
            actor_user=admin,
            entity_type="User",
            entity_id=str(admin.user_id),
            occurred_at=clock.now() - timedelta(minutes=i),
            reason="Query budget audit.",
            correlation_id=f"qb-corr-{i}",
        )

    for i in range(3):
        ApplicationVersionPolicy.objects.create(
            platform=["ANDROID", "IOS", "WEB"][i],
            app_version="1.0.0",
            status="SUPPORTED",
        )

    return {
        "admin": admin,
        "clerk": clerks[0],
        "manager": managers[0],
        "student": student_users[0],
        "hostels": hostels,
        "messes": messes,
        "students": students,
        "extra_items": extra_items,
        "occurrences": occurrences,
    }


# path, fixture role key, query params for the one-row page, params for the dense
# page, and the SQL statement ceiling. ``None`` params mean the endpoint ignores
# page size and always returns its (capped) full list.
QUERY_BUDGETS = [
    ("/api/v1/hostels", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/students", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    (
        "/api/v1/students/verifications",
        "clerk",
        {"page_size": 1},
        {"page_size": 200},
        3,
    ),
    ("/api/v1/admin/hostel-clerks", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/admin/mess-managers", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/admin/settings", "admin", {}, {}, 1),
    ("/api/v1/admin/app-versions", "admin", {"page_size": 1}, {"page_size": 200}, 1),
    ("/api/v1/messes", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    (
        "/api/v1/messes/{mess_id}/meal-rates",
        "admin",
        {},
        {},
        4,
    ),
    ("/api/v1/meals/types", "admin", {}, {}, 1),
    ("/api/v1/meals/occurrences", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/extras/items", "admin", {"page_size": 1}, {"page_size": 200}, 3),
    (
        "/api/v1/extras/items/{item_id}/prices",
        "admin",
        {},
        {},
        2,
    ),
    ("/api/v1/attendance", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/attendance/summary", "admin", {}, {}, 2),
    ("/api/v1/attendance/corrections", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/extras/transactions", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/pauses", "student", {"page_size": 1}, {"page_size": 200}, 4),
    ("/api/v1/billing/semesters", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/billing/policies", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/billing/periods", "admin", {"page_size": 1}, {"page_size": 200}, 6),
    ("/api/v1/billing/bills", "admin", {"page_size": 1}, {"page_size": 200}, 4),
    ("/api/v1/billing/balances", "admin", {"page_size": 1}, {"page_size": 200}, 3),
    (
        "/api/v1/billing/opening-balances",
        "admin",
        {"page_size": 1},
        {"page_size": 200},
        3,
    ),
    ("/api/v1/menus", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/menus/food-items", "admin", {"page_size": 1}, {"page_size": 200}, 2),
    ("/api/v1/audit/events", "admin", {"limit": 1}, {"limit": 100}, 2),
    ("/api/v1/sync/batches", "admin", {}, {}, 1),
    ("/api/v1/sync/transactions", "admin", {}, {}, 1),
    ("/api/v1/sync/conflicts", "admin", {}, {}, 1),
]


def _resolve(path: str, campus: dict) -> str:
    return path.format(
        mess_id=campus["messes"][0].mess_id,
        item_id=campus["extra_items"][0].extra_item_id,
    )


def _measure(client, path: str, params: dict) -> tuple[int, int]:
    response = client.get(path, params)
    with CaptureQueriesContext(connection) as captured:
        response = client.get(path, params)
    return response.status_code, len(captured)


@pytest.mark.django_db
def test_list_endpoints_stay_within_query_budgets(api_client, dense_campus):
    problems: list[str] = []

    for path, role, small_params, dense_params, budget in QUERY_BUDGETS:
        resolved = _resolve(path, dense_campus)
        api_client.force_authenticate(user=dense_campus[role])

        small_status, small_count = _measure(api_client, resolved, small_params)
        dense_status, dense_count = _measure(api_client, resolved, dense_params)

        if small_status != 200 or dense_status != 200:
            problems.append(
                f"{resolved}: expected 200, got {small_status}/{dense_status}"
            )
            continue

        if dense_count > budget:
            problems.append(
                f"{resolved}: {dense_count} queries exceeds budget {budget}"
            )

        if small_params != dense_params and dense_count != small_count:
            problems.append(
                f"{resolved}: N+1 regression, {small_count} queries for one row "
                f"but {dense_count} for a full page"
            )

    assert problems == [], "\n".join(problems)
