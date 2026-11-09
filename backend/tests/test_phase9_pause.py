"""
Phase 9 test suite: Mess pause [SPEC DBDD §7, §7.1; DEC-06, DEC-23, D23].

Coverage:
- Pure slot-counter: three qualifying slots, snacks walked over, threshold rules,
  boundary timings, shared activation vectors, hypothesis properties.
- Submit validations and the immutable requested end date [DBDD-AC-27].
- The ``advance_pauses`` job: activation, completion, idempotency, time travel.
- Cancellation in SCHEDULED and ACTIVE, including DEC-23 timing.
- D23 automatic cancellation when a meal is taken (online and late through sync).
- ``is_slot_paused`` nuance for billing, sync and reports.
- Student endpoint scoping and Manager pause state through the sync delta.
- Audit events for every transition and change-version bumps.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import threading
import uuid
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from hypothesis import given, settings as hypothesis_settings, strategies as st
from rest_framework import status
from rest_framework.test import APIClient

from apps.attendance.models import MealConsumption
from apps.attendance.services import record_meal
from apps.audit.models import AuditLog
from apps.core.clock import IST_ZONE, clock
from apps.core.exceptions import ConflictError, ValidationError
from apps.hostel.models import Hostel, Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, Role, User, UserRole
from apps.identity.services.token_service import generate_access_token
from apps.mess.models import (
    MealOccurrence,
    MealRate,
    MealType,
    Mess,
    MessManagerAssignment,
)
from apps.pause.models import MessPause, MessPauseMealSlot
from apps.pause.services import (
    ACTIVATION_SLOT_COUNT,
    ActivationPlan,
    SlotInput,
    advance_pause,
    advance_pauses,
    build_activation_plan,
    cancel_active_pause_on_meal,
    cancel_pause,
    get_activation_plan,
    get_pause_state,
    is_slot_paused,
    request_pause,
)
from apps.sync.selectors import get_delta_students
from apps.sync.services import process_sync_batch

IST = ZoneInfo("Asia/Kolkata")
QUALIFYING_CODES = ("BREAKFAST", "LUNCH", "DINNER")
ALL_CODES = ("BREAKFAST", "EVENING_SNACKS", "LUNCH", "DINNER")
SEQUENCE = {"BREAKFAST": 1, "LUNCH": 2, "EVENING_SNACKS": 3, "DINNER": 4}
END_TIMES = {
    "BREAKFAST": time(10, 0),
    "LUNCH": time(14, 30),
    "EVENING_SNACKS": time(18, 30),
    "DINNER": time(22, 0),
}


def ist_dt(day: date, clock_time: time = time(0, 0)) -> datetime:
    """Build an aware Asia/Kolkata datetime."""
    return datetime.combine(day, clock_time).replace(tzinfo=IST)


def end_of(day: date, meal_code: str) -> datetime:
    """Return the configured service end of a meal slot (IST)."""
    return ist_dt(day, END_TIMES[meal_code])


def slot(day: date, meal_code: str) -> SlotInput:
    """Build a SlotInput using the seeded meal end times."""
    return SlotInput(
        meal_date=day,
        meal_type_code=meal_code,
        sequence_no=SEQUENCE[meal_code],
        end_at=end_of(day, meal_code),
    )


@pytest.fixture(autouse=True)
def freeze_clock_at_phase9_start():
    """Freeze the clock so pause dates never rot."""
    clock.set_time(ist_dt(date(2026, 11, 9), time(6, 0)))
    yield


@pytest.fixture(autouse=True)
def setup_roles_and_meal_types(db):
    """Ensure baseline roles and meal types exist."""
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


def auth_client(client: APIClient, user: User, role_name: str) -> APIClient:
    """Authenticate the DRF client with an active device binding.

    The suite freezes the clock to a date in the past relative to real system time.
    PyJWT validates ``exp`` against the real clock, so mint the token with the clock
    momentarily unfrozen, then restore the frozen test time.
    """
    device = DeviceRegistration.objects.filter(
        user=user, session_status="ACTIVE"
    ).first()
    if not device:
        device = DeviceRegistration.objects.create(
            user=user,
            device_id=f"dev-p9-{user.user_id}",
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


def create_calendar(mess: Mess, start_day: date, days: int = 12) -> None:
    """Create a full four-slot meal calendar for a mess."""
    meal_types = {code: MealType.objects.get(code=code) for code in ALL_CODES}
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        for code in ALL_CODES:
            MealOccurrence.objects.create(
                mess=mess, meal_date=day, meal_type=meal_types[code], status="SCHEDULED"
            )


def make_user(email: str, full_name: str, role_name: str) -> User:
    user = User.objects.create(
        email=email,
        normalized_email=email,
        full_name=full_name,
        status="ACTIVE",
    )
    UserRole.objects.create(user=user, role=Role.objects.get(name=role_name))
    return user


@pytest.fixture
def pause_setup(db):
    """A realistic pause environment with students, a manager and full calendars."""
    hostel = Hostel.objects.create(code="H-P9", name="Hostel Phase 9", status="ACTIVE")
    other_hostel = Hostel.objects.create(
        code="H-P9-B", name="Hostel Phase 9 B", status="ACTIVE"
    )
    mess = Mess.objects.create(code="M-P9", name="Mess Phase 9", status="ACTIVE")
    other_mess = Mess.objects.create(
        code="M-P9-B", name="Mess Phase 9 B", status="ACTIVE"
    )

    admin_user = make_user("admin_p9@college.edu", "Admin P9", "SUPER_ADMIN")
    clerk_user = make_user("clerk_p9@college.edu", "Clerk P9", "HOSTEL_CLERK")
    manager_user = make_user("manager_p9@college.edu", "Manager P9", "MESS_MANAGER")
    MessManagerAssignment.objects.create(
        user=manager_user, mess=mess, is_active=True, assigned_at=clock.now()
    )
    manager_device = DeviceRegistration.objects.create(
        user=manager_user,
        device_id="dev-manager-p9",
        platform="ANDROID",
        session_status="ACTIVE",
        registered_at=clock.now(),
    )
    clerk_device = DeviceRegistration.objects.create(
        user=clerk_user,
        device_id="dev-clerk-p9",
        platform="WEB",
        session_status="ACTIVE",
        registered_at=clock.now(),
    )

    student_user = make_user("student_p9@college.edu", "Student P9", "STUDENT")
    student = Student.objects.create(
        user=student_user, roll_number="23109001", hostel=hostel, status="ACTIVE"
    )
    StudentMessAssignment.objects.create(
        student=student,
        hostel=hostel,
        mess=mess,
        status="ACTIVE",
        effective_from=date(2026, 11, 1),
    )
    student_device = DeviceRegistration.objects.create(
        user=student_user,
        device_id="dev-student-p9",
        platform="ANDROID",
        session_status="ACTIVE",
        registered_at=clock.now(),
    )

    other_user = make_user("student_p9_b@college.edu", "Student P9 B", "STUDENT")
    other_student = Student.objects.create(
        user=other_user, roll_number="23109002", hostel=other_hostel, status="ACTIVE"
    )
    StudentMessAssignment.objects.create(
        student=other_student,
        hostel=other_hostel,
        mess=mess,
        status="ACTIVE",
        effective_from=date(2026, 11, 1),
    )

    # A student attached to a mess with only three upcoming qualifying slots.
    sparse_user = make_user("student_p9_sparse@college.edu", "Student Sparse", "STUDENT")
    sparse_student = Student.objects.create(
        user=sparse_user, roll_number="23109003", hostel=hostel, status="ACTIVE"
    )
    StudentMessAssignment.objects.create(
        student=sparse_student,
        hostel=hostel,
        mess=other_mess,
        status="ACTIVE",
        effective_from=date(2026, 11, 1),
    )
    sparse_types = [MealType.objects.get(code=code) for code in QUALIFYING_CODES]
    for code in sparse_types:
        MealOccurrence.objects.create(
            mess=other_mess,
            meal_date=date(2026, 11, 10),
            meal_type=code,
            status="SCHEDULED",
        )

    create_calendar(mess, date(2026, 11, 9), days=12)

    MealRate.objects.create(
        mess=mess,
        effective_from=date(2026, 11, 1),
        rate=Decimal("48.0000"),
        created_by=admin_user,
    )

    return {
        "hostel": hostel,
        "other_hostel": other_hostel,
        "mess": mess,
        "other_mess": other_mess,
        "admin_user": admin_user,
        "clerk_user": clerk_user,
        "clerk_device": clerk_device,
        "manager_user": manager_user,
        "manager_device": manager_device,
        "student": student,
        "student_user": student_user,
        "student_device": student_device,
        "other_student": other_student,
        "other_user": other_user,
        "sparse_student": sparse_student,
        "sparse_user": sparse_user,
    }


def submit_pause(
    setup: dict,
    *,
    start: date = date(2026, 11, 10),
    end: date = date(2026, 11, 15),
    student: Student | None = None,
    mess: Mess | None = None,
    actor: User | None = None,
) -> MessPause:
    return request_pause(
        student=student or setup["student"],
        mess=mess or setup["mess"],
        requested_start_date=start,
        requested_end_date=end,
        actor=actor or setup["student_user"],
    )


def make_active_pause(
    setup: dict,
    *,
    start: date = date(2026, 11, 10),
    end: date = date(2026, 11, 15),
    student: Student | None = None,
) -> MessPause:
    return MessPause.objects.create(
        student=student or setup["student"],
        mess=setup["mess"],
        requested_start_date=start,
        requested_end_date=end,
        effective_start_date=start,
        effective_end_date=end,
        activation_meal_date=date(2026, 11, 9),
        status="ACTIVE",
        requested_at=clock.now(),
    )


def occurrence(setup: dict, day: date, meal_code: str) -> MealOccurrence:
    return MealOccurrence.objects.get(
        mess=setup["mess"], meal_date=day, meal_type__code=meal_code
    )


def record_meal_now(
    setup: dict,
    day: date,
    meal_code: str,
    *,
    transaction_id: uuid.UUID | None = None,
):
    return record_meal(
        transaction_id=transaction_id or uuid.uuid4(),
        student=setup["student"],
        meal_date=day,
        meal_type=meal_code,
        mess=setup["mess"],
        recorded_by_user=setup["manager_user"],
        device_registration=setup["manager_device"],
    )


# =============================================================================
# 1. Pure slot counter [DEC-06]
# =============================================================================


class TestPureSlotCounter:
    """The two-slot counter is the heart of the module; test it hardest."""

    def test_three_core_slots_with_snacks_between(self):
        slots = [
            slot(date(2026, 11, 10), "BREAKFAST"),
            slot(date(2026, 11, 10), "LUNCH"),
            slot(date(2026, 11, 10), "EVENING_SNACKS"),
            slot(date(2026, 11, 10), "DINNER"),
            slot(date(2026, 11, 11), "BREAKFAST"),
        ]
        plan = build_activation_plan(slots, ist_dt(date(2026, 11, 10)))

        assert [s.meal_type_code for s in plan.counted_slots] == [
            "BREAKFAST",
            "LUNCH",
            "DINNER",
        ]
        assert [s.meal_type_code for s in plan.skipped_slots] == ["EVENING_SNACKS"]
        assert plan.activation_meal_date == date(2026, 11, 10)
        assert plan.effective_start_date == date(2026, 11, 11)

    def test_request_exactly_at_slot_end_skips_that_slot(self):
        slots = [
            slot(date(2026, 11, 10), "BREAKFAST"),
            slot(date(2026, 11, 10), "LUNCH"),
            slot(date(2026, 11, 10), "DINNER"),
            slot(date(2026, 11, 11), "BREAKFAST"),
            slot(date(2026, 11, 11), "LUNCH"),
        ]
        plan = build_activation_plan(
            slots, end_of(date(2026, 11, 10), "BREAKFAST")
        )

        assert [s.meal_type_code for s in plan.counted_slots] == [
            "LUNCH",
            "DINNER",
            "BREAKFAST",
        ]
        # Third counted slot is Breakfast on 11-11; the next qualifying is Lunch.
        assert plan.activation_meal_date == date(2026, 11, 11)
        assert plan.effective_start_date == date(2026, 11, 11)

    def test_request_after_last_slot_starts_next_day(self):
        slots = [slot(date(2026, 11, 10), code) for code in ALL_CODES]
        slots += [slot(date(2026, 11, 11), code) for code in ALL_CODES]
        slots += [slot(date(2026, 11, 12), "BREAKFAST")]

        plan = build_activation_plan(
            slots, ist_dt(date(2026, 11, 10), time(22, 30))
        )

        assert plan.counted_slots == (
            slot(date(2026, 11, 11), "BREAKFAST"),
            slot(date(2026, 11, 11), "LUNCH"),
            slot(date(2026, 11, 11), "DINNER"),
        )
        assert plan.activation_meal_date == date(2026, 11, 11)
        assert plan.effective_start_date == date(2026, 11, 12)

    def test_snacks_never_count(self):
        slots = [
            slot(date(2026, 11, 10), "BREAKFAST"),
            slot(date(2026, 11, 10), "EVENING_SNACKS"),
            slot(date(2026, 11, 10), "LUNCH"),
            slot(date(2026, 11, 10), "EVENING_SNACKS"),
            slot(date(2026, 11, 10), "DINNER"),
            slot(date(2026, 11, 11), "BREAKFAST"),
        ]
        plan = build_activation_plan(slots, ist_dt(date(2026, 11, 10)))

        assert len(plan.counted_slots) == ACTIVATION_SLOT_COUNT
        assert len(plan.skipped_slots) == 2
        assert all(not s.qualifies for s in plan.skipped_slots)

    def test_fewer_than_four_qualifying_slots_is_refused(self):
        slots = [slot(date(2026, 11, 10), code) for code in QUALIFYING_CODES]
        with pytest.raises(ValidationError) as exc:
            build_activation_plan(slots, ist_dt(date(2026, 11, 10)))
        assert exc.value.code == "INSUFFICIENT_QUALIFYING_SLOTS"

    def test_three_slots_without_a_following_slot_are_refused(self):
        slots = [
            slot(date(2026, 11, 10), "BREAKFAST"),
            slot(date(2026, 11, 10), "LUNCH"),
            slot(date(2026, 11, 10), "DINNER"),
        ]
        with pytest.raises(ValidationError) as exc:
            build_activation_plan(slots, ist_dt(date(2026, 11, 10)))
        assert exc.value.code == "INSUFFICIENT_QUALIFYING_SLOTS"

    def test_plan_is_pure(self, pause_setup):
        """Calling the counter must never create pause rows or write anything."""
        plan = get_activation_plan(
            mess=pause_setup["mess"],
            request_time=clock.now(),
            requested_start_date=date(2026, 11, 10),
        )
        assert isinstance(plan, ActivationPlan)
        assert MessPause.objects.count() == 0
        assert MessPauseMealSlot.objects.count() == 0


@hypothesis_settings(max_examples=60, deadline=None)
@given(
    day1_slots=st.lists(st.sampled_from(ALL_CODES), unique=True),
    day2_slots=st.lists(st.sampled_from(ALL_CODES), unique=True),
    day3_slots=st.lists(st.sampled_from(ALL_CODES), unique=True),
    day4_slots=st.lists(st.sampled_from(ALL_CODES), unique=True),
)
def test_property_activation_after_exactly_three_qualifying_slots(
    day1_slots, day2_slots, day3_slots, day4_slots
):
    """
    Whatever combination and position of snacks, activation uses exactly the
    first three qualifying slots and the next qualifying slot starts the pause.
    """
    days = [date(2026, 11, 10) + timedelta(days=i) for i in range(4)]
    chosen = [day1_slots, day2_slots, day3_slots, day4_slots]
    slots = [
        slot(day, code) for day, codes in zip(days, chosen) for code in codes
    ]
    threshold = ist_dt(days[0])

    ordered = sorted(slots, key=lambda s: (s.meal_date, s.sequence_no))
    eligible = [s for s in ordered if s.end_at > threshold]
    qualifying = [s for s in eligible if s.qualifies]

    if len(qualifying) < ACTIVATION_SLOT_COUNT:
        with pytest.raises(ValidationError):
            build_activation_plan(slots, threshold)
        return

    counted = qualifying[:ACTIVATION_SLOT_COUNT]
    third = counted[-1]
    later = [
        s
        for s in qualifying
        if (s.meal_date, s.sequence_no) > (third.meal_date, third.sequence_no)
    ]
    if not later:
        with pytest.raises(ValidationError):
            build_activation_plan(slots, threshold)
        return

    plan = build_activation_plan(slots, threshold)
    assert plan.counted_slots == tuple(counted)
    assert plan.activation_meal_date == third.meal_date
    assert plan.effective_start_date == later[0].meal_date

    # Recorded rows are every eligible slot up to and including the third counted.
    stop = eligible.index(third)
    assert plan.recorded_slots == tuple(eligible[: stop + 1])
    assert all(not s.qualifies for s in plan.skipped_slots)
    assert plan.skipped_slots == tuple(
        s for s in plan.recorded_slots if not s.qualifies
    )


# =============================================================================
# 2. Shared vector file
# =============================================================================


class TestPauseVectors:
    """Both the server and the Manager app are checked against the same vectors."""

    @staticmethod
    def _load_vectors() -> dict:
        path = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "test-vectors"
            / "pause-v1.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def test_vector_file_exists_and_is_well_formed(self):
        data = self._load_vectors()
        assert data["protocol"] == "pause-activation-v1"
        assert data["meal_end_times_ist"]["EVENING_SNACKS"] == "18:30"
        assert len(data["cases"]) >= 5

    @pytest.mark.parametrize(
        "case_index",
        range(5),
        ids=[
            "three_core_slots_with_snacks_between",
            "request_exactly_at_slot_end_skips_that_slot",
            "request_after_last_slot_starts_next_day",
            "request_during_snacks_window_walks_over_snacks",
            "fewer_than_four_qualifying_slots_is_refused",
        ],
    )
    def test_shared_vectors(self, case_index):
        case = self._load_vectors()["cases"][case_index]
        request_time = datetime.fromisoformat(case["request_time_ist"])
        start = date.fromisoformat(case["requested_start_date"])

        slots = []
        for row in case["occurrences"]:
            day = date.fromisoformat(row["meal_date"])
            code = row["meal_type"]
            end_time = time.fromisoformat(
                self._load_vectors()["meal_end_times_ist"][code]
            )
            slots.append(
                SlotInput(
                    meal_date=day,
                    meal_type_code=code,
                    sequence_no=SEQUENCE[code],
                    end_at=ist_dt(day, end_time),
                )
            )

        threshold = max(request_time, ist_dt(start))

        expected = case["expected"]
        if "error_code" in expected:
            with pytest.raises(ValidationError) as exc:
                build_activation_plan(slots, threshold)
            assert exc.value.code == expected["error_code"]
            return

        plan = build_activation_plan(slots, threshold)
        assert [
            [s.meal_date.isoformat(), s.meal_type_code] for s in plan.counted_slots
        ] == expected["counted"]
        assert [
            [s.meal_date.isoformat(), s.meal_type_code] for s in plan.skipped_slots
        ] == expected["skipped_snacks"]
        assert [
            [s.meal_date.isoformat(), s.meal_type_code] for s in plan.recorded_slots
        ] == expected["recorded"]
        assert plan.activation_meal_date.isoformat() == expected["activation_meal_date"]
        assert plan.effective_start_date.isoformat() == expected["effective_start_date"]


# =============================================================================
# 3. Submit [DEC-06]
# =============================================================================


@pytest.mark.django_db
class TestPauseSubmit:
    def test_submit_creates_scheduled_pause_with_computed_dates(self, pause_setup):
        pause = submit_pause(pause_setup)

        assert pause.status == "SCHEDULED"
        assert pause.requested_start_date == date(2026, 11, 10)
        assert pause.requested_end_date == date(2026, 11, 15)
        # Requested end date is written unchanged [DBDD-AC-27].
        assert pause.effective_end_date == date(2026, 11, 15)
        assert pause.activation_meal_date == date(2026, 11, 10)
        assert pause.effective_start_date == date(2026, 11, 11)

        slots = list(
            MessPauseMealSlot.objects.filter(pause=pause).order_by("slot_sequence")
        )
        assert len(slots) == 4  # Breakfast, Lunch, Snacks, Dinner on 11-10
        assert [s.qualifies_for_activation for s in slots] == [
            True,
            True,
            False,
            True,
        ]
        assert all(not s.consumed_for_activation for s in slots)

        audit = AuditLog.objects.get(
            event_type="PAUSE_SUBMITTED", entity_id=str(pause.pause_id)
        )
        assert audit.new_values_json["status"] == "SCHEDULED"
        assert "password" not in json.dumps(audit.new_values_json).lower()

    def test_submit_advances_change_version_for_manager_sync(self, pause_setup):
        assignment = StudentMessAssignment.objects.get(
            student=pause_setup["student"]
        )
        before_version = assignment.version
        before_change = assignment.change_version
        submit_pause(pause_setup)
        assignment.refresh_from_db()
        assert assignment.version == before_version + 1

        # The database trigger issues a new change marker so Manager polling
        # sees the pause through the shared cursor [Phase 8, build 6].
        assert assignment.change_version > before_change
        pause = MessPause.objects.get(student=pause_setup["student"])
        assert pause.change_version > 0

        delta = get_delta_students(pause_setup["mess"].mess_id, client_cursor=0)
        student_rows = [
            row for row in delta if row["student_id"] == pause_setup["student"].student_id
        ]
        assert student_rows and student_rows[0]["pause_state"] == "SCHEDULED"

    def test_submit_via_api_returns_computed_dates(self, api_client, pause_setup):
        client = auth_client(
            api_client, pause_setup["student_user"], "STUDENT"
        )
        response = client.post(
            "/api/v1/pauses",
            {
                "mess_id": pause_setup["mess"].mess_id,
                "requested_start_date": "2026-11-10",
                "requested_end_date": "2026-11-15",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "SCHEDULED"
        assert response.data["effective_start_date"] == "2026-11-11"
        assert response.data["effective_end_date"] == "2026-11-15"
        assert response.data["activation_meal_date"] == "2026-11-10"
        assert response.data["slots_remaining"] == ACTIVATION_SLOT_COUNT
        assert len(response.data["meal_slots"]) == 4

    def test_legacy_request_alias_still_works(self, api_client, pause_setup):
        client = auth_client(
            api_client, pause_setup["student_user"], "STUDENT"
        )
        response = client.post(
            "/api/v1/pauses/request",
            {
                "mess_id": pause_setup["mess"].mess_id,
                "requested_start_date": "2026-11-10",
                "requested_end_date": "2026-11-15",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_start_in_past_is_rejected(self, pause_setup):
        with pytest.raises(ValidationError) as exc:
            submit_pause(pause_setup, start=date(2026, 11, 8))
        assert exc.value.code == "PAUSE_START_IN_PAST"

    def test_end_before_start_is_rejected(self, pause_setup):
        with pytest.raises(ValidationError) as exc:
            submit_pause(
                pause_setup, start=date(2026, 11, 12), end=date(2026, 11, 10)
            )
        assert exc.value.code == "INVALID_DATE_RANGE"

    def test_end_before_effective_start_is_rejected(self, pause_setup):
        # Effective start is 11-11, so a same-day pause is refused with a clear message.
        with pytest.raises(ValidationError) as exc:
            submit_pause(
                pause_setup, start=date(2026, 11, 10), end=date(2026, 11, 10)
            )
        assert exc.value.code == "PAUSE_END_BEFORE_EFFECTIVE_START"
        assert "2026-11-11" in exc.value.message

    def test_no_active_assignment_is_rejected(self, pause_setup):
        with pytest.raises(ValidationError) as exc:
            submit_pause(pause_setup, mess=pause_setup["other_mess"])
        assert exc.value.code == "NO_ACTIVE_ASSIGNMENT"

    def test_too_few_future_occurrences_is_rejected(self, pause_setup):
        with pytest.raises(ValidationError) as exc:
            submit_pause(
                pause_setup,
                student=pause_setup["sparse_student"],
                mess=pause_setup["other_mess"],
            )
        assert exc.value.code == "INSUFFICIENT_QUALIFYING_SLOTS"

    def test_duplicate_pause_is_rejected(self, pause_setup):
        submit_pause(pause_setup)
        with pytest.raises(ConflictError) as exc:
            submit_pause(
                pause_setup, start=date(2026, 11, 20), end=date(2026, 11, 22)
            )
        assert exc.value.code == "DUPLICATE_PAUSE"

    def test_database_partial_unique_backs_duplicate_rule(self, pause_setup):
        submit_pause(pause_setup)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MessPause.objects.create(
                    student=pause_setup["student"],
                    mess=pause_setup["mess"],
                    requested_start_date=date(2026, 11, 20),
                    requested_end_date=date(2026, 11, 22),
                    status="SCHEDULED",
                    requested_at=clock.now(),
                )

    def test_request_exactly_at_slot_end_through_service(self, pause_setup):
        clock.set_time(end_of(date(2026, 11, 10), "BREAKFAST"))
        pause = submit_pause(pause_setup)

        # Breakfast at exactly its end time is not counted.
        assert pause.activation_meal_date == date(2026, 11, 11)
        assert pause.effective_start_date == date(2026, 11, 11)
        assert not MessPauseMealSlot.objects.filter(
            pause=pause,
            slot_date=date(2026, 11, 10),
            meal_occurrence__meal_type__code="BREAKFAST",
        ).exists()

    def test_request_after_last_slot_through_service(self, pause_setup):
        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 30)))
        pause = submit_pause(pause_setup)
        assert pause.activation_meal_date == date(2026, 11, 11)
        assert pause.effective_start_date == date(2026, 11, 12)

    @pytest.mark.django_db(transaction=True)
    def test_double_submit_concurrently_one_wins(self, pause_setup):
        """Two simultaneous submits: exactly one pause, the other gets a conflict."""
        barrier = threading.Barrier(2)

        def attempt():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    pause = submit_pause(pause_setup)
                    return ("created", pause.pause_id)
                except ConflictError:
                    return ("conflict", None)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]

        assert sorted(r[0] for r in results) == ["conflict", "created"]
        assert MessPause.objects.filter(student=pause_setup["student"]).count() == 1


# =============================================================================
# 4. State job and time travel
# =============================================================================


@pytest.mark.django_db
class TestAdvancePauses:
    def _request(self, setup: dict) -> MessPause:
        return submit_pause(setup)

    def test_activation_happens_only_after_third_qualifying_slot(self, pause_setup):
        pause = self._request(pause_setup)

        clock.set_time(ist_dt(date(2026, 11, 10), time(9, 59)))
        counts = advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "SCHEDULED"
        assert counts["activated"] == 0

        clock.set_time(ist_dt(date(2026, 11, 10), time(10, 1)))
        advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "SCHEDULED"
        assert (
            MessPauseMealSlot.objects.filter(
                pause=pause, consumed_for_activation=True
            ).count()
            == 1
        )

        clock.set_time(ist_dt(date(2026, 11, 10), time(14, 31)))
        advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "SCHEDULED"

        clock.set_time(ist_dt(date(2026, 11, 10), time(18, 31)))
        advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "SCHEDULED"  # snacks consumed but do not count
        assert pause.activation_meal_date == date(2026, 11, 10)

        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 1)))
        counts = advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "ACTIVE"
        assert pause.activation_meal_date == date(2026, 11, 10)
        assert pause.effective_start_date == date(2026, 11, 11)
        assert counts["activated"] == 1

        assert AuditLog.objects.filter(
            event_type="PAUSE_ACTIVATED", entity_id=str(pause.pause_id)
        ).count() == 1
        assert AuditLog.objects.filter(
            event_type="PAUSE_COMPLETED", entity_id=str(pause.pause_id)
        ).count() == 0

    def test_second_job_run_changes_nothing(self, pause_setup):
        pause = self._request(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 1)))
        advance_pauses()
        pause.refresh_from_db()
        version_after_first = pause.version
        audit_count = AuditLog.objects.filter(
            entity_id=str(pause.pause_id)
        ).count()

        counts = advance_pauses()
        pause.refresh_from_db()

        assert counts["changed"] == 0
        assert pause.version == version_after_first
        assert pause.status == "ACTIVE"
        assert (
            AuditLog.objects.filter(entity_id=str(pause.pause_id)).count()
            == audit_count
        )

    def test_job_completes_after_end_date(self, pause_setup):
        pause = self._request(pause_setup)  # ends 2026-11-15
        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 1)))
        advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "ACTIVE"

        clock.set_time(ist_dt(date(2026, 11, 15), time(23, 0)))
        advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "ACTIVE"  # the end date itself is not "before today"

        clock.set_time(ist_dt(date(2026, 11, 16), time(0, 1)))
        counts = advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "COMPLETED"
        assert pause.completed_at is not None
        assert pause.requested_end_date == date(2026, 11, 15)
        assert pause.effective_end_date == date(2026, 11, 15)
        assert counts["completed"] == 1

        assert AuditLog.objects.filter(
            event_type="PAUSE_COMPLETED", entity_id=str(pause.pause_id)
        ).count() == 1

    def test_completed_is_distinguishable_from_active(self, pause_setup):
        pause = self._request(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 1)))
        advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "ACTIVE"
        assert pause.completed_at is None

        clock.set_time(ist_dt(date(2026, 11, 16), time(0, 1)))
        advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "COMPLETED"
        assert pause.completed_at is not None

    def test_job_can_activate_and_complete_after_a_long_time_jump(self, pause_setup):
        pause = self._request(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 20), time(9, 0)))
        counts = advance_pauses()
        pause.refresh_from_db()

        assert pause.status == "COMPLETED"
        assert counts["activated"] == 1
        # The pause never charged; the requested end date is untouched.
        assert pause.requested_end_date == date(2026, 11, 15)
        event_types = set(
            AuditLog.objects.filter(entity_id=str(pause.pause_id)).values_list(
                "event_type", flat=True
            )
        )
        assert {"PAUSE_ACTIVATED", "PAUSE_COMPLETED"}.issubset(event_types)

    def test_cancelled_counted_slot_is_replaced_mid_wait(self, pause_setup):
        """A counted occurrence cancelled before passing is replaced by the next slot."""
        pause = self._request(pause_setup)
        lunch = occurrence(pause_setup, date(2026, 11, 10), "LUNCH")
        lunch.status = "CANCELLED"
        lunch.save(update_fields=["status"])

        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 1)))
        advance_pauses()
        pause.refresh_from_db()

        # The cancelled lunch row stays for traceability but no longer qualifies.
        lunch_row = MessPauseMealSlot.objects.get(pause=pause, meal_occurrence=lunch)
        assert lunch_row.qualifies_for_activation is False

        replacement = MessPauseMealSlot.objects.filter(
            pause=pause, meal_occurrence__meal_type__code="BREAKFAST",
            slot_date=date(2026, 11, 11),
        ).first()
        assert replacement is not None
        assert replacement.qualifies_for_activation is True
        # Breakfast 11-11 is the replacement third counted slot, so its end must pass.
        assert pause.status == "SCHEDULED"

        clock.set_time(ist_dt(date(2026, 11, 11), time(10, 1)))
        advance_pauses()
        pause.refresh_from_db()

        # Breakfast, Dinner and Breakfast 11-11 are the three counted slots.
        assert pause.status == "ACTIVE"
        assert pause.activation_meal_date == date(2026, 11, 11)
        assert pause.effective_start_date == date(2026, 11, 11)

    def test_occurrence_cancelled_after_passing_still_counts(self, pause_setup):
        pause = self._request(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 10), time(10, 1)))
        advance_pauses()  # breakfast consumed

        breakfast = occurrence(pause_setup, date(2026, 11, 10), "BREAKFAST")
        breakfast.status = "CANCELLED"
        breakfast.save(update_fields=["status"])

        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 1)))
        advance_pauses()
        pause.refresh_from_db()
        assert pause.status == "ACTIVE"
        assert pause.activation_meal_date == date(2026, 11, 10)

    def test_management_command_runs_under_lock(self, pause_setup, capsys):
        pause = self._request(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 1)))
        call_command("advance_pauses")
        pause.refresh_from_db()
        assert pause.status == "ACTIVE"
        captured = capsys.readouterr()
        assert "advance_pauses" in captured.out

    def test_transfer_while_scheduled_keeps_pause_with_student(self, pause_setup):
        pause = self._request(pause_setup)
        assignment = StudentMessAssignment.objects.get(
            student=pause_setup["student"]
        )
        assignment.mess = pause_setup["other_mess"]
        assignment.save(update_fields=["mess"])

        clock.set_time(ist_dt(date(2026, 11, 10), time(22, 1)))
        advance_pauses()
        pause.refresh_from_db()

        assert pause.mess_id == pause_setup["mess"].mess_id
        assert pause.status == "ACTIVE"
        assert pause.cancellation_reason == ""


# =============================================================================
# 5. Cancellation [DEC-23]
# =============================================================================


@pytest.mark.django_db
class TestCancelPause:
    def test_cancel_scheduled_via_api(self, api_client, pause_setup):
        pause = submit_pause(pause_setup)
        client = auth_client(
            api_client, pause_setup["student_user"], "STUDENT"
        )
        response = client.post(
            f"/api/v1/pauses/{pause.pause_id}/cancel", {}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "CANCELLED"
        assert response.data["cancellation_reason"] == "CANCELLED_BY_STUDENT"

        pause.refresh_from_db()
        assert pause.cancelled_at is not None
        assert pause.effective_end_date == clock.today()
        assert AuditLog.objects.filter(
            event_type="PAUSE_CANCELLED", entity_id=str(pause.pause_id)
        ).count() == 1

        # Nothing on the future pause range counts as paused.
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "BREAKFAST")
        )

    def test_cancel_scheduled_with_reason(self, api_client, pause_setup):
        pause = submit_pause(pause_setup)
        client = auth_client(
            api_client, pause_setup["student_user"], "STUDENT"
        )
        response = client.post(
            f"/api/v1/pauses/{pause.pause_id}/cancel",
            {"reason": "Travelling home"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["cancellation_reason"] == "Travelling home"

    def test_cancel_active_sets_cancellation_date_and_dec23_boundary(
        self, pause_setup
    ):
        pause = make_active_pause(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 10), time(15, 0)))

        cancel_pause(pause=pause, actor=pause_setup["student_user"])
        pause.refresh_from_db()

        assert pause.status == "CANCELLED"
        assert pause.effective_end_date == date(2026, 11, 10)
        assert pause.requested_end_date == date(2026, 11, 15)

        # On the cancellation date, only slots already ended at 15:00 stay paused.
        assert is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "BREAKFAST")
        )
        assert is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "LUNCH")
        )
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "DINNER")
        )
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 11), "BREAKFAST")
        )

    def test_cancel_already_cancelled_is_conflict(self, pause_setup):
        pause = submit_pause(pause_setup)
        cancel_pause(pause=pause, actor=pause_setup["student_user"])
        with pytest.raises(ConflictError) as exc:
            cancel_pause(pause=pause, actor=pause_setup["student_user"])
        assert exc.value.code == "PAUSE_ALREADY_TERMINATED"

    def test_cancel_completed_is_conflict(self, pause_setup):
        pause = make_active_pause(pause_setup)
        pause.status = "COMPLETED"
        pause.completed_at = clock.now()
        pause.save(update_fields=["status", "completed_at"])

        with pytest.raises(ConflictError) as exc:
            cancel_pause(pause=pause, actor=pause_setup["student_user"])
        assert exc.value.code == "PAUSE_ALREADY_TERMINATED"

    def test_student_cannot_cancel_another_students_pause(
        self, api_client, pause_setup
    ):
        other_pause = MessPause.objects.create(
            student=pause_setup["other_student"],
            mess=pause_setup["mess"],
            requested_start_date=date(2026, 11, 10),
            requested_end_date=date(2026, 11, 15),
            effective_start_date=date(2026, 11, 11),
            effective_end_date=date(2026, 11, 15),
            status="SCHEDULED",
            requested_at=clock.now(),
        )
        client = auth_client(
            api_client, pause_setup["student_user"], "STUDENT"
        )
        response = client.post(
            f"/api/v1/pauses/{other_pause.pause_id}/cancel", {}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        other_pause.refresh_from_db()
        assert other_pause.status == "SCHEDULED"


# =============================================================================
# 6. D23 automatic cancellation when a meal is taken
# =============================================================================


@pytest.mark.django_db
class TestMealDuringActivePause:
    def test_meal_cancels_active_pause_from_that_meal(self, pause_setup):
        pause = make_active_pause(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 10), time(13, 0)))
        txn_id = uuid.uuid4()

        result = record_meal_now(
            pause_setup, date(2026, 11, 10), "LUNCH", transaction_id=txn_id
        )
        assert result.status == "SYNCHRONIZED"

        pause.refresh_from_db()
        assert pause.status == "CANCELLED"
        assert pause.cancellation_reason == "MEAL_TAKEN"
        assert pause.cancelled_at == end_of(date(2026, 11, 10), "LUNCH")
        assert pause.effective_end_date == date(2026, 11, 10)

        # Meal is billed normally, not suppressed by the pause.
        meal = MealConsumption.objects.get(transaction_id=txn_id)
        assert meal.price_at_transaction == Decimal("48.0000")

        # Slots strictly before the meal stay paused; the meal and later slots are normal.
        assert is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "BREAKFAST")
        )
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "LUNCH")
        )
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "DINNER")
        )
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 11), "BREAKFAST")
        )

        audit = AuditLog.objects.get(
            event_type="PAUSE_CANCELLED", entity_id=str(pause.pause_id)
        )
        assert audit.reason == "MEAL_TAKEN"
        assert audit.metadata_json["transaction_id"] == str(txn_id)

    def test_breakfast_meal_cancels_from_breakfast(self, pause_setup):
        pause = make_active_pause(pause_setup)
        record_meal_now(pause_setup, date(2026, 11, 10), "BREAKFAST")
        pause.refresh_from_db()
        assert pause.status == "CANCELLED"
        assert pause.cancelled_at == end_of(date(2026, 11, 10), "BREAKFAST")
        # No earlier qualifying slot on that day remains paused.
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "BREAKFAST")
        )

    def test_dinner_meal_keeps_earlier_same_day_slots_paused(self, pause_setup):
        pause = make_active_pause(pause_setup)
        record_meal_now(pause_setup, date(2026, 11, 10), "DINNER")
        pause.refresh_from_db()
        assert pause.status == "CANCELLED"
        for code in ("BREAKFAST", "LUNCH"):
            assert is_slot_paused(
                pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), code)
            )
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "DINNER")
        )

    def test_duplicate_meal_does_not_cancel_pause(self, pause_setup):
        pause = make_active_pause(pause_setup)
        # A meal consumption already exists for the slot; a replay must not cancel.
        MealConsumption.objects.create(
            transaction_id=uuid.uuid4(),
            student=pause_setup["student"],
            roll_number_snapshot=pause_setup["student"].roll_number,
            meal_date=date(2026, 11, 10),
            meal_type=MealType.objects.get(code="BREAKFAST"),
            mess=pause_setup["mess"],
            recorded_by_user=pause_setup["manager_user"],
            price_at_transaction=Decimal("48.0000"),
            transaction_timestamp=clock.now(),
        )

        duplicate = record_meal_now(pause_setup, date(2026, 11, 10), "BREAKFAST")
        assert duplicate.status == "DUPLICATE"
        pause.refresh_from_db()
        assert pause.status == "ACTIVE"
        assert pause.cancellation_reason == ""

    def test_late_meal_through_sync_cancels_pause(self, pause_setup):
        """Offline meal uploaded later still cancels from its own slot [D23]."""
        pause = make_active_pause(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 11), time(8, 0)))
        txn_id = uuid.uuid4()

        data = {
            "device_id": pause_setup["manager_device"].device_id,
            "client_version": "1.0.0",
            "last_server_version": 0,
            "transactions": [
                {
                    "transaction_id": str(txn_id),
                    "entity_type": "MEAL",
                    "client_created_at": "2026-11-10T13:00:00+05:30",
                    "payload": {
                        "student_id": pause_setup["student"].student_id,
                        "mess_id": pause_setup["mess"].mess_id,
                        "meal_type": "LUNCH",
                        "meal_date": "2026-11-10",
                    },
                }
            ],
        }
        response = process_sync_batch(
            user=pause_setup["manager_user"], data=data
        )
        assert response["transaction_results"][0]["status"] == "SYNCHRONIZED"

        pause.refresh_from_db()
        assert pause.status == "CANCELLED"
        assert pause.cancellation_reason == "MEAL_TAKEN"
        assert pause.cancelled_at == end_of(date(2026, 11, 10), "LUNCH")
        assert MealConsumption.objects.filter(transaction_id=txn_id).exists()
        assert is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "BREAKFAST")
        )
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 10), "LUNCH")
        )

    def test_meal_outside_pause_range_does_not_cancel(self, pause_setup):
        pause = make_active_pause(
            pause_setup, start=date(2026, 11, 12), end=date(2026, 11, 15)
        )
        result = record_meal_now(pause_setup, date(2026, 11, 10), "LUNCH")
        assert result.status == "SYNCHRONIZED"
        pause.refresh_from_db()
        assert pause.status == "ACTIVE"
        assert pause.cancellation_reason == ""


# =============================================================================
# 7. Shared predicate
# =============================================================================


@pytest.mark.django_db
class TestIsSlotPaused:
    def test_snacks_are_never_paused(self, pause_setup):
        make_active_pause(pause_setup)
        snacks = occurrence(pause_setup, date(2026, 11, 10), "EVENING_SNACKS")
        assert is_slot_paused(pause_setup["student"], snacks) is False

    def test_slot_before_effective_start_is_not_paused(self, pause_setup):
        make_active_pause(pause_setup)
        assert not is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 9), "DINNER")
        )

    def test_completed_pause_still_marks_its_range_paused(self, pause_setup):
        pause = make_active_pause(pause_setup)
        pause.status = "COMPLETED"
        pause.completed_at = clock.now()
        pause.save(update_fields=["status", "completed_at"])
        assert is_slot_paused(
            pause_setup["student"], occurrence(pause_setup, date(2026, 11, 12), "LUNCH")
        )


# =============================================================================
# 8. Read endpoints and scoping
# =============================================================================


@pytest.mark.django_db
class TestPauseReadAndScoping:
    def test_student_lists_only_own_pauses(self, api_client, pause_setup):
        own = submit_pause(pause_setup)
        MessPause.objects.create(
            student=pause_setup["other_student"],
            mess=pause_setup["mess"],
            requested_start_date=date(2026, 11, 12),
            requested_end_date=date(2026, 11, 15),
            effective_start_date=date(2026, 11, 13),
            effective_end_date=date(2026, 11, 15),
            status="SCHEDULED",
            requested_at=clock.now(),
        )
        client = auth_client(
            api_client, pause_setup["student_user"], "STUDENT"
        )
        response = client.get("/api/v1/pauses")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["pause_id"] == own.pause_id

    def test_current_pause_endpoint(self, api_client, pause_setup):
        pause = submit_pause(pause_setup)
        client = auth_client(
            api_client, pause_setup["student_user"], "STUDENT"
        )
        response = client.get("/api/v1/pauses/current")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["has_pause"] is True
        assert response.data["pause_id"] == pause.pause_id
        assert response.data["slots_remaining"] == ACTIVATION_SLOT_COUNT
        assert len(response.data["meal_slots"]) == 4

    def test_current_pause_endpoint_when_none(self, api_client, pause_setup):
        client = auth_client(
            api_client, pause_setup["student_user"], "STUDENT"
        )
        response = client.get("/api/v1/pauses/current")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"has_pause": False, "status": "NONE"}

    def test_current_pause_shows_slot_progress(self, pause_setup):
        submit_pause(pause_setup)
        clock.set_time(ist_dt(date(2026, 11, 10), time(10, 1)))
        advance_pauses()
        state = get_pause_state(pause_setup["student"])
        assert state["status"] == "SCHEDULED"
        assert state["qualifying_slots_consumed"] == 1
        assert state["slots_remaining"] == 2

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/v1/pauses"),
            ("get", "/api/v1/pauses/current"),
        ],
    )
    def test_non_student_cannot_read_pauses(
        self, api_client, pause_setup, method, path
    ):
        client = auth_client(api_client, pause_setup["clerk_user"], "HOSTEL_CLERK")
        response = getattr(client, method)(path)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_non_student_cannot_submit_pause(self, api_client, pause_setup):
        client = auth_client(api_client, pause_setup["clerk_user"], "HOSTEL_CLERK")
        response = client.post(
            "/api/v1/pauses",
            {
                "mess_id": pause_setup["mess"].mess_id,
                "requested_start_date": "2026-11-10",
                "requested_end_date": "2026-11-15",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_manager_receives_pause_state_through_sync_delta(self, pause_setup):
        pause = submit_pause(pause_setup)
        delta = get_delta_students(pause_setup["mess"].mess_id, client_cursor=0)
        row = next(
            r
            for r in delta
            if r["student_id"] == pause_setup["student"].student_id
        )
        assert row["pause_state"] == "SCHEDULED"

        pause.status = "ACTIVE"
        pause.effective_start_date = date(2026, 11, 10)
        pause.save(update_fields=["status", "effective_start_date"])
        delta = get_delta_students(pause_setup["mess"].mess_id, client_cursor=0)
        row = next(
            r
            for r in delta
            if r["student_id"] == pause_setup["student"].student_id
        )
        assert row["pause_state"] == "ACTIVE"

        cancel_pause(pause=pause, actor=pause_setup["student_user"])
        delta = get_delta_students(pause_setup["mess"].mess_id, client_cursor=0)
        row = next(
            r
            for r in delta
            if r["student_id"] == pause_setup["student"].student_id
        )
        assert row["pause_state"] == "NONE"
