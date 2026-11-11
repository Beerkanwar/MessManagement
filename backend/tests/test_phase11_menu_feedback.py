"""
Phase 11 test suite: menu and feedback
[SPEC DBDD §9/§10, SRS §22/§23, SDD §48/§49, App Flow §3.4/§3.5,
ImplementationGuide Phase 11].

Coverage:
- Duplicate food in a meal rejected at the database and at the API [DBDD-AC-30].
- Cross-hostel Clerk denial; Student published-only reads; transfer visibility.
- Month rollover at IST midnight for menus and feedback.
- Optimistic concurrency on the menu version (stale edit -> 409).
- Publish warnings and audited revisions (MENU_PUBLISHED, MENU_REVISED).
- One immutable monthly feedback per student, including a concurrent double
  submit where exactly one request wins [DBDD-AC-29].
- Rating range, comment length, inert markup, and blocked update/delete.
- The Phase 11 exit gate end to end.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from django.db import DatabaseError, IntegrityError, connection, connections, transaction
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
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
from apps.menu.models import FoodItem, Menu, MenuItem, MenuMeal
from apps.mess.models import MealType, Mess, MessManagerAssignment

IST = ZoneInfo("Asia/Kolkata")
CURRENT_YEAR = 2026
CURRENT_MONTH = 12
NEXT_YEAR = 2027
NEXT_MONTH = 1


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
    """Authenticate a DRF client even while the domain clock is frozen."""
    device = DeviceRegistration.objects.filter(
        user=user, session_status="ACTIVE"
    ).first()
    if not device:
        device = DeviceRegistration.objects.create(
            user=user,
            device_id=f"dev-p11-{user.user_id}",
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
    assert response.status_code == http_status, response.data
    assert "traceId" in response.data
    if code is not None:
        assert response.data["code"] == code, response.data


def create_food_item(client: APIClient, name: str, description: str = "") -> dict:
    response = client.post(
        "/api/v1/menus/food-items",
        {"name": name, "description": description},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return response.data


def create_menu(client: APIClient, hostel_id: int, year: int, month: int) -> dict:
    response = client.post(
        "/api/v1/menus",
        {"hostel_id": hostel_id, "year": year, "month": month},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return response.data


def set_meal(
    client: APIClient,
    menu_id: int,
    version: int,
    menu_date: date,
    meal_type_code: str,
    food_item_ids: list[int],
) -> object:
    return client.put(
        f"/api/v1/menus/{menu_id}/meals",
        {
            "version": version,
            "menu_date": menu_date.isoformat(),
            "meal_type_code": meal_type_code,
            "items": [
                {"food_item_id": food_item_id, "display_order": index}
                for index, food_item_id in enumerate(food_item_ids, start=1)
            ],
        },
        format="json",
    )


def publish_menu(client: APIClient, menu_id: int, version: int) -> object:
    return client.post(
        f"/api/v1/menus/{menu_id}/publish", {"version": version}, format="json"
    )


def submit_feedback(client: APIClient, **overrides) -> object:
    payload = {
        "food_quality_rating": 4,
        "taste_rating": 5,
        "comments": "",
    }
    payload.update(overrides)
    return client.post("/api/v1/feedback", payload, format="json")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def freeze_phase11_clock():
    clock.set_time(ist_dt(date(CURRENT_YEAR, CURRENT_MONTH, 15)))
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
    hostel_a = Hostel.objects.create(code="H-P11-A", name="Hostel P11 A", status="ACTIVE")
    hostel_b = Hostel.objects.create(code="H-P11-B", name="Hostel P11 B", status="ACTIVE")
    mess_a = Mess.objects.create(code="M-P11-A", name="Mess P11 A", status="ACTIVE")
    mess_b = Mess.objects.create(code="M-P11-B", name="Mess P11 B", status="ACTIVE")

    admin = make_user("admin_p11@college.edu", "Admin P11", "SUPER_ADMIN")
    clerk_a = make_user("clerk_a_p11@college.edu", "Clerk A P11", "HOSTEL_CLERK")
    clerk_b = make_user("clerk_b_p11@college.edu", "Clerk B P11", "HOSTEL_CLERK")
    HostelClerkAssignment.objects.create(
        user=clerk_a, hostel=hostel_a, is_active=True, assigned_at=clock.now()
    )
    HostelClerkAssignment.objects.create(
        user=clerk_b, hostel=hostel_b, is_active=True, assigned_at=clock.now()
    )
    manager = make_user("manager_p11@college.edu", "Manager P11", "MESS_MANAGER")
    MessManagerAssignment.objects.create(
        user=manager, mess=mess_a, is_active=True, assigned_at=clock.now()
    )

    student_a, student_a_user = make_student(
        email="student_a_p11@college.edu", roll_number="P110001", hostel=hostel_a
    )
    student_b, student_b_user = make_student(
        email="student_b_p11@college.edu", roll_number="P110002", hostel=hostel_b
    )
    transfer_student, transfer_user = make_student(
        email="transfer_p11@college.edu", roll_number="P110003", hostel=hostel_b
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
    # Transferred on 1 December: the earlier assignment ended just before it.
    StudentMessAssignment.objects.create(
        student=transfer_student,
        hostel=hostel_a,
        mess=mess_a,
        status="ENDED",
        effective_from=date(2026, 6, 1),
        effective_to=date(2026, 12, 1),
    )
    StudentMessAssignment.objects.create(
        student=transfer_student,
        hostel=hostel_b,
        mess=mess_b,
        status="ACTIVE",
        effective_from=date(2026, 12, 1),
    )

    return {
        "hostel_a": hostel_a,
        "hostel_b": hostel_b,
        "mess_a": mess_a,
        "mess_b": mess_b,
        "admin": admin,
        "clerk_a": clerk_a,
        "clerk_b": clerk_b,
        "manager": manager,
        "student_a": student_a,
        "student_a_user": student_a_user,
        "student_b": student_b,
        "student_b_user": student_b_user,
        "transfer_student": transfer_student,
        "transfer_user": transfer_user,
    }


def clients(setup) -> dict[str, APIClient]:
    return {
        "admin": auth_client(APIClient(), setup["admin"], "SUPER_ADMIN"),
        "clerk_a": auth_client(APIClient(), setup["clerk_a"], "HOSTEL_CLERK"),
        "clerk_b": auth_client(APIClient(), setup["clerk_b"], "HOSTEL_CLERK"),
        "manager": auth_client(APIClient(), setup["manager"], "MESS_MANAGER"),
        "student_a": auth_client(APIClient(), setup["student_a_user"], "STUDENT"),
        "student_b": auth_client(APIClient(), setup["student_b_user"], "STUDENT"),
        "transfer": auth_client(APIClient(), setup["transfer_user"], "STUDENT"),
    }


# ---------------------------------------------------------------------------
# Menu authoring
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMenuAuthoring:
    def test_food_item_master_permissions_and_duplicate_names(self, setup):
        c = clients(setup)

        created = create_food_item(c["clerk_a"], "  Veg Pulao  ")
        assert created["name"] == "Veg Pulao"
        assert created["normalized_name"] == "VEG PULAO"
        assert created["status"] == "ACTIVE"

        duplicate = c["clerk_a"].post(
            "/api/v1/menus/food-items", {"name": "veg   pulao"}, format="json"
        )
        assert_error(duplicate, status.HTTP_409_CONFLICT, "DUPLICATE_RESOURCE")

        # Only the Super Admin may rename or deactivate a shared item [REC].
        rename_payload = {"version": created["version"], "name": "Veg Pulao Special"}
        assert_error(
            c["clerk_a"].patch(
                f"/api/v1/menus/food-items/{created['food_item_id']}",
                rename_payload,
                format="json",
            ),
            status.HTTP_403_FORBIDDEN,
            "PERMISSION_DENIED",
        )
        renamed = c["admin"].patch(
            f"/api/v1/menus/food-items/{created['food_item_id']}",
            rename_payload,
            format="json",
        )
        assert renamed.status_code == status.HTTP_200_OK, renamed.data
        assert renamed.data["name"] == "Veg Pulao Special"
        assert renamed.data["normalized_name"] == "VEG PULAO SPECIAL"

        assert_error(
            c["clerk_a"].post(
                f"/api/v1/menus/food-items/{created['food_item_id']}/deactivate",
                {"version": renamed.data["version"]},
                format="json",
            ),
            status.HTTP_403_FORBIDDEN,
            "PERMISSION_DENIED",
        )
        deactivated = c["admin"].post(
            f"/api/v1/menus/food-items/{created['food_item_id']}/deactivate",
            {"version": renamed.data["version"]},
            format="json",
        )
        assert deactivated.status_code == status.HTTP_200_OK, deactivated.data
        assert deactivated.data["status"] == "INACTIVE"

        listing = c["clerk_a"].get("/api/v1/menus/food-items?status=ACTIVE")
        assert listing.status_code == status.HTTP_200_OK, listing.data
        assert all(row["status"] == "ACTIVE" for row in listing.data["results"])

    def test_duplicate_food_in_a_meal_rejected_at_api_and_database(self, setup):
        c = clients(setup)
        food = create_food_item(c["clerk_a"], "Rice")
        menu = create_menu(c["clerk_a"], setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH)

        duplicate = set_meal(
            c["clerk_a"],
            menu["menu_id"],
            1,
            date(CURRENT_YEAR, CURRENT_MONTH, 1),
            "LUNCH",
            [food["food_item_id"], food["food_item_id"]],
        )
        assert_error(duplicate, status.HTTP_400_BAD_REQUEST, "DUPLICATE_RESOURCE")

        db_menu = Menu.objects.create(
            hostel=setup["hostel_a"],
            menu_year=NEXT_YEAR,
            menu_month=NEXT_MONTH,
            status="DRAFT",
        )
        db_meal = MenuMeal.objects.create(
            menu=db_menu,
            menu_date=date(NEXT_YEAR, NEXT_MONTH, 1),
            meal_type=MealType.objects.get(code="LUNCH"),
        )
        db_food = FoodItem.objects.create(name="Dal", normalized_name="DAL")
        MenuItem.objects.create(menu_meal=db_meal, food_item=db_food)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MenuItem.objects.create(menu_meal=db_meal, food_item=db_food)

    def test_clerk_cannot_edit_another_hostels_menu(self, setup):
        c = clients(setup)
        foreign = create_menu(
            c["clerk_b"], setup["hostel_b"].hostel_id, CURRENT_YEAR, CURRENT_MONTH
        )
        food = create_food_item(c["clerk_b"], "Idli")

        assert_error(
            c["clerk_a"].get(f"/api/v1/menus/{foreign['menu_id']}"),
            status.HTTP_404_NOT_FOUND,
            "OBJECT_NOT_FOUND",
        )
        assert_error(
            set_meal(
                c["clerk_a"],
                foreign["menu_id"],
                foreign["version"],
                date(CURRENT_YEAR, CURRENT_MONTH, 2),
                "BREAKFAST",
                [food["food_item_id"]],
            ),
            status.HTTP_404_NOT_FOUND,
            "OBJECT_NOT_FOUND",
        )
        assert_error(
            c["clerk_a"].post(
                "/api/v1/menus",
                {
                    "hostel_id": setup["hostel_b"].hostel_id,
                    "year": CURRENT_YEAR,
                    "month": CURRENT_MONTH,
                },
                format="json",
            ),
            status.HTTP_404_NOT_FOUND,
            "OBJECT_NOT_FOUND",
        )
        listing = c["clerk_a"].get("/api/v1/menus")
        assert listing.status_code == status.HTTP_200_OK
        assert all(row["hostel_id"] == setup["hostel_a"].hostel_id for row in listing.data["results"])

        # Mess Managers have no menu access at all [DEC-15 default].
        assert_error(c["manager"].get("/api/v1/menus"), status.HTTP_403_FORBIDDEN, "PERMISSION_DENIED")
        assert_error(
            c["manager"].get("/api/v1/menus/current"),
            status.HTTP_403_FORBIDDEN,
            "PERMISSION_DENIED",
        )

    def test_menu_date_must_fall_inside_the_month(self, setup):
        c = clients(setup)
        food = create_food_item(c["clerk_a"], "Poha")
        menu = create_menu(c["clerk_a"], setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH)
        response = set_meal(
            c["clerk_a"],
            menu["menu_id"],
            1,
            date(NEXT_YEAR, NEXT_MONTH, 1),
            "BREAKFAST",
            [food["food_item_id"]],
        )
        assert_error(response, status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR")

    def test_stale_version_edit_returns_409(self, setup):
        c = clients(setup)
        food = create_food_item(c["clerk_a"], "Upma")
        menu = create_menu(c["clerk_a"], setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH)

        first = set_meal(
            c["clerk_a"],
            menu["menu_id"],
            1,
            date(CURRENT_YEAR, CURRENT_MONTH, 3),
            "BREAKFAST",
            [food["food_item_id"]],
        )
        assert first.status_code == status.HTTP_200_OK, first.data
        assert first.data["version"] == 2

        stale = set_meal(
            c["clerk_a"],
            menu["menu_id"],
            1,
            date(CURRENT_YEAR, CURRENT_MONTH, 4),
            "BREAKFAST",
            [food["food_item_id"]],
        )
        assert_error(stale, status.HTTP_409_CONFLICT, "VERSION_CONFLICT")

    def test_publish_warns_and_revision_is_audited(self, setup):
        c = clients(setup)
        food = create_food_item(c["clerk_a"], "Chapati")
        menu = create_menu(c["clerk_a"], setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH)
        set_meal(
            c["clerk_a"],
            menu["menu_id"],
            1,
            date(CURRENT_YEAR, CURRENT_MONTH, 1),
            "LUNCH",
            [food["food_item_id"]],
        )
        published = publish_menu(c["clerk_a"], menu["menu_id"], 2)
        assert published.status_code == status.HTTP_200_OK, published.data
        assert published.data["menu"]["status"] == "PUBLISHED"
        assert published.data["menu"]["published_at"] is not None
        assert published.data["menu"]["published_by_user_id"] == setup["clerk_a"].user_id
        # 30 other days have no items; warnings do not block publication.
        assert len(published.data["warnings"]) == 30

        assert AuditLog.objects.filter(
            event_type="MENU_PUBLISHED", entity_id=str(menu["menu_id"])
        ).exists()

        # Revise the published meal; old and new item lists are both audited.
        revised = set_meal(
            c["clerk_a"],
            menu["menu_id"],
            published.data["menu"]["version"],
            date(CURRENT_YEAR, CURRENT_MONTH, 1),
            "LUNCH",
            [food["food_item_id"]],
        )
        assert revised.status_code == status.HTTP_200_OK, revised.data

        audit = AuditLog.objects.get(
            event_type="MENU_REVISED", entity_id=str(menu["menu_id"])
        )
        assert audit.old_values_json["items"][0]["name"] == "Chapati"
        assert audit.new_values_json["items"][0]["name"] == "Chapati"
        assert audit.new_values_json["meal_type_code"] == "LUNCH"

        already = publish_menu(
            c["clerk_a"], menu["menu_id"], revised.data["version"]
        )
        assert_error(already, status.HTTP_409_CONFLICT, "CONFLICT")

    def test_copy_previous_weekday_pattern(self, setup):
        c = clients(setup)
        food = create_food_item(c["clerk_a"], "Sambar")
        previous = create_menu(
            c["clerk_a"], setup["hostel_a"].hostel_id, 2026, 11
        )
        # 1 November 2026 is a Sunday.
        set_meal(
            c["clerk_a"],
            previous["menu_id"],
            previous["version"],
            date(2026, 11, 1),
            "LUNCH",
            [food["food_item_id"]],
        )
        current = create_menu(
            c["clerk_a"], setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH
        )
        copied = c["clerk_a"].post(
            f"/api/v1/menus/{current['menu_id']}/copy-previous",
            {"version": current["version"]},
            format="json",
        )
        assert copied.status_code == status.HTTP_200_OK, copied.data

        # December 2026 Sundays: 6, 13, 20, 27.
        sundays = {
            day["date"] for day in copied.data["days"]
        }
        assert sundays == {"2026-12-06", "2026-12-13", "2026-12-20", "2026-12-27"}
        assert all(
            day["meals"][0]["items"][0]["name"] == "Sambar" for day in copied.data["days"]
        )

    def test_menu_structure_is_month_date_meal_items(self, setup):
        c = clients(setup)
        food = create_food_item(c["clerk_a"], "Kheer")
        menu = create_menu(c["clerk_a"], setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH)
        set_meal(
            c["clerk_a"],
            menu["menu_id"],
            1,
            date(CURRENT_YEAR, CURRENT_MONTH, 5),
            "DINNER",
            [food["food_item_id"]],
        )
        detail = c["clerk_a"].get(f"/api/v1/menus/{menu['menu_id']}")
        assert detail.status_code == status.HTTP_200_OK, detail.data
        assert detail.data["year"] == CURRENT_YEAR
        assert detail.data["month"] == CURRENT_MONTH
        day = detail.data["days"][0]
        assert day["date"] == "2026-12-05"
        assert day["meals"][0]["meal_type_code"] == "DINNER"
        assert day["meals"][0]["items"][0]["name"] == "Kheer"
        assert day["meals"][0]["items"][0]["notes"] == ""


# ---------------------------------------------------------------------------
# Student menu reads
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStudentMenu:
    def _publish_month(
        self, c: dict[str, APIClient], hostel_id: int, year: int, month: int
    ) -> dict:
        food = create_food_item(c["admin"], f"Meal {hostel_id}-{year}-{month}")
        menu = create_menu(c["admin"], hostel_id, year, month)
        set_meal(
            c["admin"],
            menu["menu_id"],
            menu["version"],
            date(year, month, 1),
            "LUNCH",
            [food["food_item_id"]],
        )
        published = publish_menu(c["admin"], menu["menu_id"], 2)
        assert published.status_code == status.HTTP_200_OK, published.data
        return published.data["menu"]

    def test_students_see_only_published_menus_of_their_own_hostel(self, setup):
        c = clients(setup)
        food = create_food_item(c["admin"], "Rajma")

        draft = create_menu(
            c["admin"], setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH
        )
        set_meal(
            c["admin"],
            draft["menu_id"],
            draft["version"],
            date(CURRENT_YEAR, CURRENT_MONTH, 2),
            "LUNCH",
            [food["food_item_id"]],
        )

        # The A draft is invisible while unpublished.
        before = c["student_a"].get("/api/v1/menus/current")
        assert before.status_code == status.HTTP_200_OK, before.data
        assert before.data["months"] == []

        publish_menu(c["admin"], draft["menu_id"], 2)
        after = c["student_a"].get("/api/v1/menus/current")
        assert after.status_code == status.HTTP_200_OK, after.data
        assert [month["month"] for month in after.data["months"]] == [CURRENT_MONTH]
        assert after.data["months"][0]["status"] == "PUBLISHED"

        # Student B is in hostel B and must not see hostel A's menu.
        other = c["student_b"].get("/api/v1/menus/current")
        assert other.status_code == status.HTTP_200_OK
        assert other.data["months"] == []

        # Students cannot access the authoring surface.
        assert_error(
            c["student_a"].get("/api/v1/menus"),
            status.HTTP_403_FORBIDDEN,
            "PERMISSION_DENIED",
        )

    def test_transferred_student_sees_new_hostels_menu(self, setup):
        c = clients(setup)
        self._publish_month(c, setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH)
        self._publish_month(c, setup["hostel_b"].hostel_id, CURRENT_YEAR, CURRENT_MONTH)

        response = c["transfer"].get("/api/v1/menus/current")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["hostel"]["hostel_id"] == setup["hostel_b"].hostel_id
        assert response.data["months"][0]["hostel_code"] == "H-P11-B"

    def test_ist_month_rollover_for_current_menu(self, setup):
        c = clients(setup)
        self._publish_month(c, setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH)
        self._publish_month(c, setup["hostel_a"].hostel_id, NEXT_YEAR, NEXT_MONTH)

        with clock.freeze(ist_dt(date(2026, 12, 31), time(23, 59))):
            december = c["student_a"].get("/api/v1/menus/current")
            assert december.status_code == status.HTTP_200_OK, december.data
            months = [month["month_label"] for month in december.data["months"]]
            # Current month plus the already-published next month.
            assert months == ["2026-12", "2027-01"]

        with clock.freeze(ist_dt(date(2027, 1, 1), time(0, 1))):
            january = c["student_a"].get("/api/v1/menus/current")
            assert january.status_code == status.HTTP_200_OK, january.data
            assert [month["month_label"] for month in january.data["months"]] == ["2027-01"]


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFeedback:
    def test_submit_once_and_current_status(self, setup):
        c = clients(setup)
        created = submit_feedback(
            c["student_a"],
            food_quality_rating=5,
            taste_rating=4,
            comments="Good food this month.",
        )
        assert created.status_code == status.HTTP_201_CREATED, created.data
        assert created.data["mess_id"] == setup["mess_a"].mess_id
        assert created.data["calendar_year"] == CURRENT_YEAR
        assert created.data["calendar_month"] == CURRENT_MONTH
        assert created.data["food_quality_rating"] == 5
        assert created.data["taste_rating"] == 4

        duplicate = submit_feedback(c["student_a"])
        assert_error(duplicate, status.HTTP_409_CONFLICT, "FEEDBACK_ALREADY_SUBMITTED")

        current = c["student_a"].get("/api/v1/feedback/current")
        assert current.status_code == status.HTTP_200_OK, current.data
        assert current.data["submitted"] is True
        assert current.data["calendar_year"] == CURRENT_YEAR
        assert current.data["calendar_month"] == CURRENT_MONTH
        assert current.data["feedback"]["comments"] == "Good food this month."

        # The client cannot send the mess or month; they are ignored/derived.
        student_b_submit = submit_feedback(
            c["student_b"], mess=setup["mess_a"].mess_id, month=1, year=2020
        )
        assert student_b_submit.status_code == status.HTTP_201_CREATED, student_b_submit.data
        assert student_b_submit.data["mess_id"] == setup["mess_b"].mess_id
        assert student_b_submit.data["calendar_year"] == CURRENT_YEAR
        assert student_b_submit.data["calendar_month"] == CURRENT_MONTH

    def test_rating_range_is_enforced(self, setup):
        c = clients(setup)
        for payload in [
            {"food_quality_rating": 0, "taste_rating": 3},
            {"food_quality_rating": 6, "taste_rating": 3},
            {"food_quality_rating": 3.5, "taste_rating": 3},
            {"food_quality_rating": 3, "taste_rating": 0},
            {"food_quality_rating": 3, "taste_rating": 6},
            {"food_quality_rating": 3, "taste_rating": 2.5},
        ]:
            assert_error(
                submit_feedback(c["student_a"], **payload),
                status.HTTP_400_BAD_REQUEST,
            )
        assert Feedback.objects.count() == 0

    def test_comments_are_length_limited_and_inert_text(self, setup):
        c = clients(setup)
        too_long = submit_feedback(c["student_a"], comments="x" * 1001)
        assert_error(too_long, status.HTTP_400_BAD_REQUEST)
        assert Feedback.objects.count() == 0

        markup = '<script>alert("menu")</script> & <b>bold</b>'
        created = submit_feedback(c["student_a"], comments=markup)
        assert created.status_code == status.HTTP_201_CREATED, created.data
        assert created.data["comments"] == markup

        current = c["student_a"].get("/api/v1/feedback/current")
        assert current.data["feedback"]["comments"] == markup

    def test_feedback_is_insert_only_through_orm_sql_and_api(self, setup):
        c = clients(setup)
        submit_feedback(c["student_a"])
        feedback = Feedback.objects.get(student=setup["student_a"])

        feedback.comments = "edited"
        with pytest.raises(ValueError):
            feedback.save()
        with pytest.raises(ValueError):
            feedback.delete()

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE feedback_feedback SET comments = %s WHERE feedback_id = %s",
                        ["edited", feedback.feedback_id],
                    )
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM feedback_feedback WHERE feedback_id = %s",
                        [feedback.feedback_id],
                    )

        # There is deliberately no update or delete endpoint.
        assert c["student_a"].put(
            f"/api/v1/feedback/{feedback.feedback_id}", {"comments": "x"}, format="json"
        ).status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED)
        assert c["student_a"].delete(
            f"/api/v1/feedback/{feedback.feedback_id}"
        ).status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED)

        feedback.refresh_from_db()
        assert feedback.comments == ""

    def test_feedback_requires_an_active_assignment(self, setup):
        c = clients(setup)
        student, user = make_student(
            email="unassigned_p11@college.edu",
            roll_number="P119999",
            hostel=setup["hostel_a"],
        )
        client = auth_client(APIClient(), user, "STUDENT")
        assert_error(
            submit_feedback(client),
            status.HTTP_404_NOT_FOUND,
            "OBJECT_NOT_FOUND",
        )

    def test_feedback_month_rollover_at_ist_midnight(self, setup):
        c = clients(setup)
        with clock.freeze(ist_dt(date(2026, 12, 31), time(23, 59))):
            december = submit_feedback(c["student_a"], comments="December")
            assert december.status_code == status.HTTP_201_CREATED, december.data
            assert december.data["calendar_month"] == 12

            before = c["student_a"].get("/api/v1/feedback/current")
            assert before.data["calendar_month"] == 12
            assert before.data["submitted"] is True

        with clock.freeze(ist_dt(date(2027, 1, 1), time(0, 1))):
            january = submit_feedback(c["student_a"], comments="January")
            assert january.status_code == status.HTTP_201_CREATED, january.data
            assert january.data["calendar_month"] == 1

            after = c["student_a"].get("/api/v1/feedback/current")
            assert after.data["calendar_month"] == 1
            assert after.data["feedback"]["comments"] == "January"

        assert Feedback.objects.filter(student=setup["student_a"]).count() == 2


class TestFeedbackConcurrency:
    @pytest.mark.django_db(transaction=True)
    def test_concurrent_double_submit_has_exactly_one_winner(self, setup):
        device = DeviceRegistration.objects.create(
            user=setup["student_a_user"],
            device_id="dev-p11-concurrent",
            platform="WEB",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
        frozen = clock._frozen_dt
        clock.reset()
        try:
            token = generate_access_token(setup["student_a_user"], "STUDENT", device)
        finally:
            if frozen is not None:
                clock.set_time(frozen)

        def submit() -> int:
            try:
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post(
                    "/api/v1/feedback",
                    {
                        "food_quality_rating": 4,
                        "taste_rating": 4,
                        "comments": "concurrent",
                    },
                    format="json",
                )
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: submit(), range(4)))

        assert results.count(status.HTTP_201_CREATED) == 1, results
        assert results.count(status.HTTP_409_CONFLICT) == 3, results
        assert Feedback.objects.filter(student=setup["student_a"]).count() == 1


# ---------------------------------------------------------------------------
# Exit gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPhase11ExitGate:
    def test_clerk_publishes_and_revises_student_reads_and_feedback_locks(self, setup):
        c = clients(setup)

        # 1. The Clerk drafts a month.
        rice = create_food_item(c["clerk_a"], "Jeera Rice")
        dal = create_food_item(c["clerk_a"], "Dal Fry")
        menu = create_menu(
            c["clerk_a"], setup["hostel_a"].hostel_id, CURRENT_YEAR, CURRENT_MONTH
        )
        drafted = set_meal(
            c["clerk_a"],
            menu["menu_id"],
            menu["version"],
            date(CURRENT_YEAR, CURRENT_MONTH, 1),
            "LUNCH",
            [rice["food_item_id"], dal["food_item_id"]],
        )
        assert drafted.status_code == status.HTTP_200_OK, drafted.data

        # 2. Publish.
        published = publish_menu(c["clerk_a"], menu["menu_id"], drafted.data["version"])
        assert published.status_code == status.HTTP_200_OK, published.data
        assert published.data["menu"]["status"] == "PUBLISHED"
        assert AuditLog.objects.filter(
            event_type="MENU_PUBLISHED", entity_id=str(menu["menu_id"])
        ).exists()

        # 3. Revise the published meal.
        revised = set_meal(
            c["clerk_a"],
            menu["menu_id"],
            published.data["menu"]["version"],
            date(CURRENT_YEAR, CURRENT_MONTH, 1),
            "LUNCH",
            [rice["food_item_id"]],
        )
        assert revised.status_code == status.HTTP_200_OK, revised.data
        assert AuditLog.objects.filter(
            event_type="MENU_REVISED", entity_id=str(menu["menu_id"])
        ).exists()

        # 4. The Student reads the published menu.
        current_menu = c["student_a"].get("/api/v1/menus/current")
        assert current_menu.status_code == status.HTTP_200_OK, current_menu.data
        assert current_menu.data["hostel"]["hostel_id"] == setup["hostel_a"].hostel_id
        month = current_menu.data["months"][0]
        assert month["status"] == "PUBLISHED"
        day = month["days"][0]
        assert day["date"] == "2026-12-01"
        assert [item["name"] for item in day["meals"][0]["items"]] == ["Jeera Rice"]

        # 5. The Student submits feedback once and sees it locked for the month.
        created = submit_feedback(
            c["student_a"],
            food_quality_rating=5,
            taste_rating=5,
            comments="<b>Loved it</b>",
        )
        assert created.status_code == status.HTTP_201_CREATED, created.data

        assert_error(
            submit_feedback(c["student_a"]),
            status.HTTP_409_CONFLICT,
            "FEEDBACK_ALREADY_SUBMITTED",
        )
        current_feedback = c["student_a"].get("/api/v1/feedback/current")
        assert current_feedback.data["submitted"] is True
        assert current_feedback.data["feedback"]["feedback_id"] == created.data["feedback_id"]
        assert current_feedback.data["feedback"]["comments"] == "<b>Loved it</b>"
        assert Feedback.objects.filter(student=setup["student_a"]).count() == 1
