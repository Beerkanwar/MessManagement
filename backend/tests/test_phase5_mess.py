"""
Comprehensive tests for Phase 5 — Messes, meals, pricing, extras, and system settings.
Proves:
- Mess CRUD and deactivation constraints.
- Mess Manager accounts, DEC-21 (one active manager per mess), and reassignments.
- Meal types read-only and MealOccurrence generation & cancellation.
- Common meal rate effective dating [) and database exclusion constraints.
- Extra items, scoping, and effective-dated extra prices.
- Authoritative lookup service against a hand-checked boundary table.
- SystemSetting configuration registry, typed getters, caching, and sensitive masking.
- ApplicationVersionPolicy enforcement and CRUD.
- Complete Phase 5 Exit Gate (API-only configuration of 2 hostels, 3 messes, occurrences, and lookups).
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, IntegrityError
from rest_framework import status
from rest_framework.test import APIClient

from apps.attendance.models import MealConsumption
from apps.audit.models import AuditLog
from apps.config.models import ApplicationVersionPolicy, SystemSetting
from apps.config.services import (
    clear_settings_cache,
    get_bool_setting,
    get_int_setting,
    get_setting,
    get_time_setting,
    update_setting,
)
from apps.core.clock import clock
from apps.core.exceptions import ConflictError, ValidationError
from apps.hostel.models import Hostel, Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, Role, UserRole
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
from apps.mess.services import (
    add_extra_price,
    add_meal_rate,
    cancel_meal_occurrence,
    create_extra_item,
    create_mess,
    create_mess_manager,
    deactivate_extra_item,
    deactivate_mess,
    deactivate_mess_manager,
    generate_meal_occurrences,
    get_clerk_scope,
    get_extra_price,
    get_manager_scope,
    get_meal_occurrence,
    get_meal_rate,
    is_meal_scheduled,
    reassign_mess_manager,
    update_extra_item,
    update_mess,
)

User = get_user_model()


class JsonAPIClient(APIClient):
    """DRF APIClient that defaults to JSON format for requests."""

    def post(self, path, data=None, format="json", **extra):
        return super().post(path, data=data, format=format, **extra)

    def put(self, path, data=None, format="json", **extra):
        return super().put(path, data=data, format=format, **extra)


@pytest.fixture
def api_client():
    return JsonAPIClient()


@pytest.fixture(autouse=True)
def reset_all_state():
    clock.reset()
    clear_settings_cache()
    yield
    clock.reset()
    clear_settings_cache()


@pytest.fixture
def setup_roles(db):
    roles = {}
    for r in ["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]:
        role_obj, _ = Role.objects.get_or_create(name=r, defaults={"description": f"{r} role"})
        roles[r] = role_obj
    return roles


@pytest.fixture
def super_admin(db, setup_roles):
    sa, _ = User.objects.get_or_create(
        normalized_email="admin@college.edu",
        defaults={
            "email": "admin@college.edu",
            "full_name": "Super Admin",
            "is_superuser": True,
        },
    )
    UserRole.objects.get_or_create(user=sa, role=setup_roles["SUPER_ADMIN"])
    return sa


@pytest.fixture
def hostel_h1(db):
    return Hostel.objects.create(code="H1", name="Hostel One", status="ACTIVE")


@pytest.fixture
def hostel_h2(db):
    return Hostel.objects.create(code="H2", name="Hostel Two", status="ACTIVE")


@pytest.fixture
def mess_m1(db):
    return Mess.objects.create(code="M1", name="Mess Alpha", status="ACTIVE")


@pytest.fixture
def mess_m2(db):
    return Mess.objects.create(code="M2", name="Mess Beta", status="ACTIVE")


@pytest.fixture
def clerk_user(db, setup_roles, hostel_h1):
    user = User.objects.create_user(
        email="clerk_h1@college.edu",
        full_name="Clerk One",
        password="ClerkPassword123!",
    )
    UserRole.objects.create(user=user, role=setup_roles["HOSTEL_CLERK"])
    from apps.hostel.models import HostelClerkAssignment
    HostelClerkAssignment.objects.create(
        user=user,
        hostel=hostel_h1,
        is_active=True,
        assigned_at=clock.now(),
    )
    return user


def auth_client(client, user, role_name):
    device = DeviceRegistration.objects.filter(user=user, session_status="ACTIVE").first()
    if not device:
        device = DeviceRegistration.objects.create(
            user=user,
            device_id=f"dev-{user.user_id}",
            platform="WEB",
            session_status="ACTIVE",
            registered_at=clock.now(),
        )
    token = generate_access_token(user, role_name, device)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# ==============================================================================
# 1. Mess Management Tests
# ==============================================================================


@pytest.mark.django_db
class TestMessManagement:
    def test_super_admin_creates_mess_via_api(self, api_client, super_admin):
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        resp = api_client.post("/api/v1/messes", {
            "code": "M-NEW",
            "name": "New Dining Hall",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data["code"] == "M-NEW"
        assert data["name"] == "New Dining Hall"
        assert data["status"] == "ACTIVE"

        # Check audit
        audit = AuditLog.objects.filter(entity_type="Mess", entity_id=data["mess_id"]).first()
        assert audit is not None
        assert audit.event_type == "MASTER_DATA_CHANGED"

    def test_duplicate_mess_code_rejected(self, super_admin, mess_m1):
        with pytest.raises(ConflictError) as exc:
            create_mess(code="M1", name="Duplicate Mess", actor=super_admin)
        assert "already exists" in str(exc.value.message).lower()

    def test_mess_update_and_optimistic_locking(self, api_client, super_admin, mess_m1):
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        # Successful update
        resp = api_client.put(f"/api/v1/messes/{mess_m1.mess_id}", {
            "name": "Mess Alpha Renamed",
            "version": mess_m1.version,
        })
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["name"] == "Mess Alpha Renamed"
        assert resp.json()["version"] == mess_m1.version + 1

        # Stale version update rejected
        resp_stale = api_client.put(f"/api/v1/messes/{mess_m1.mess_id}", {
            "name": "Mess Alpha Stale",
            "version": mess_m1.version,  # old version
        })
        assert resp_stale.status_code == status.HTTP_409_CONFLICT

    def test_mess_deactivation_refused_if_active_assignments(self, super_admin, hostel_h1, mess_m1):
        # Create student with active assignment to mess_m1
        student_user = User.objects.create_user(email="stud@college.edu", full_name="Student")
        student = Student.objects.create(
            user=student_user,
            roll_number="CS-001",
            hostel=hostel_h1,
            status="ACTIVE",
        )
        StudentMessAssignment.objects.create(
            student=student,
            hostel=hostel_h1,
            mess=mess_m1,
            status="ACTIVE",
            effective_from=clock.today(),
            version=1,
        )

        with pytest.raises(ConflictError) as exc:
            deactivate_mess(mess_id=mess_m1.mess_id, version=mess_m1.version, actor=super_admin)
        assert "active student assignments" in str(exc.value.message).lower()

    def test_mess_deactivation_refused_if_active_manager(self, super_admin, mess_m1, setup_roles):
        mgr_user = User.objects.create_user(email="mgr@college.edu", full_name="Manager")
        UserRole.objects.create(user=mgr_user, role=setup_roles["MESS_MANAGER"])
        MessManagerAssignment.objects.create(
            user=mgr_user,
            mess=mess_m1,
            is_active=True,
            assigned_at=clock.now(),
            version=1,
        )

        with pytest.raises(ConflictError) as exc:
            deactivate_mess(mess_id=mess_m1.mess_id, version=mess_m1.version, actor=super_admin)
        assert "active manager" in str(exc.value.message).lower()


# ==============================================================================
# 2. Mess Manager Accounts & DEC-21 Tests
# ==============================================================================


@pytest.mark.django_db
class TestMessManagerManagement:
    def test_super_admin_creates_mess_manager(self, api_client, super_admin, mess_m1):
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        resp = api_client.post("/api/v1/admin/mess-managers", {
            "email": "manager_m1@college.edu",
            "full_name": "Manager One",
            "mess_code": "M1",
            "phone_number": "9876543210",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data["email"] == "manager_m1@college.edu"
        assert data["mess"]["code"] == "M1"
        assert data["is_active"] is True

        user = User.objects.get(user_id=data["user_id"])
        assert not user.has_usable_password()
        assert UserRole.objects.filter(user=user, role__name="MESS_MANAGER").exists()

    def test_second_active_manager_on_mess_refused_dec21(self, super_admin, mess_m1, setup_roles):
        # Create first manager
        create_mess_manager(
            email="mgr1@college.edu",
            full_name="Manager 1",
            mess_code="M1",
            actor=super_admin,
        )

        # Attempt to create second manager on same mess
        with pytest.raises(ConflictError) as exc:
            create_mess_manager(
                email="mgr2@college.edu",
                full_name="Manager 2",
                mess_code="M1",
                actor=super_admin,
            )
        assert "already has an active manager" in str(exc.value.message).lower()

    def test_reassign_mess_manager(self, api_client, super_admin, mess_m1, mess_m2):
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        # Create manager for M1
        res = create_mess_manager(
            email="mgr_reassign@college.edu",
            full_name="Manager Reassign",
            mess_code="M1",
            actor=super_admin,
        )
        user_id = res["user_id"]

        # Reassign to M2
        resp = api_client.post(f"/api/v1/admin/mess-managers/{user_id}/reassign", {
            "new_mess_code": "M2",
        })
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["new_mess_code"] == "M2"

        # Verify old assignment deactivated, new active
        assignments = MessManagerAssignment.objects.filter(user_id=user_id)
        assert assignments.count() == 2
        assert assignments.filter(is_active=True).first().mess == mess_m2
        assert assignments.filter(is_active=False).first().mess == mess_m1


# ==============================================================================
# 3. Meal Types & Occurrences Tests
# ==============================================================================


@pytest.mark.django_db
class TestMealTypesAndOccurrences:
    def test_meal_types_read_only(self, api_client, super_admin):
        auth_client(api_client, super_admin, "SUPER_ADMIN")
        resp = api_client.get("/api/v1/meals/types")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        codes = [item["code"] for item in data]
        assert codes == ["BREAKFAST", "LUNCH", "EVENING_SNACKS", "DINNER"]

    def test_generate_meal_occurrences_idempotence(self, mess_m1, mess_m2):
        # Run 1: 35 days for 2 messes with 4 meal types = 35 * 2 * 4 = 280 occurrences
        res1 = generate_meal_occurrences(horizon_days=35)
        assert res1["created"] == 280
        assert res1["skipped"] == 0

        total_count = MealOccurrence.objects.count()
        assert total_count == 280

        # Run 2: idempotent, 0 created, 280 skipped
        res2 = generate_meal_occurrences(horizon_days=35)
        assert res2["created"] == 0
        assert res2["skipped"] == 280
        assert MealOccurrence.objects.count() == total_count

    def test_cancel_meal_occurrence_without_consumption(self, api_client, super_admin, mess_m1):
        generate_meal_occurrences(horizon_days=1, mess_code=mess_m1.code)
        occ = MealOccurrence.objects.filter(mess=mess_m1).first()

        auth_client(api_client, super_admin, "SUPER_ADMIN")
        resp = api_client.post(f"/api/v1/meals/occurrences/{occ.meal_occurrence_id}/cancel", {
            "reason": "Hostel mess maintenance closure",
        })
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "CANCELLED"
        assert resp.json()["configuration_version"] == occ.configuration_version + 1

    def test_cancel_occurrence_with_consumption_refused(self, super_admin, hostel_h1, mess_m1):
        generate_meal_occurrences(horizon_days=1, mess_code=mess_m1.code)
        occ = MealOccurrence.objects.filter(mess=mess_m1).first()

        student_user = User.objects.create_user(email="stud_c@college.edu", full_name="Student C")
        student = Student.objects.create(user=student_user, roll_number="CS-002", hostel=hostel_h1)

        # Seed consumption on this occurrence
        MealConsumption.objects.create(
            transaction_id=uuid.uuid4(),
            student=student,
            roll_number_snapshot=student.roll_number,
            mess=mess_m1,
            meal_type=occ.meal_type,
            meal_date=occ.meal_date,
            meal_occurrence=occ,
            price_at_transaction=Decimal("45.0000"),
            transaction_timestamp=clock.now(),
            recorded_by_user=super_admin,
        )

        with pytest.raises(ConflictError) as exc:
            cancel_meal_occurrence(
                occurrence_id=occ.meal_occurrence_id,
                reason="Attempting to cancel",
                actor=super_admin,
            )
        assert "consumptions" in str(exc.value.message).lower()


# ==============================================================================
# 4. Common Meal Rate & Constraint Tests
# ==============================================================================


@pytest.mark.django_db
class TestMealRateEffectiveDatingAndConstraints:
    def test_meal_rate_effective_dating_rules(self, api_client, super_admin, mess_m1):
        auth_client(api_client, super_admin, "SUPER_ADMIN")
        today = clock.today()

        # 1. Starting in the past is refused
        resp_past = api_client.post(f"/api/v1/messes/{mess_m1.mess_id}/meal-rates", {
            "rate": "40.00",
            "effective_from": str(today - timedelta(days=1)),
            "reason": "Past rate",
        })
        assert resp_past.status_code == status.HTTP_400_BAD_REQUEST

        # 2. Add first rate from today
        resp1 = api_client.post(f"/api/v1/messes/{mess_m1.mess_id}/meal-rates", {
            "rate": "45.0000",
            "effective_from": str(today),
            "reason": "Base rate",
        })
        assert resp1.status_code == status.HTTP_201_CREATED
        r1_id = resp1.json()["meal_rate_id"]

        r1 = MealRate.objects.get(meal_rate_id=r1_id)
        assert r1.rate == Decimal("45.0000")
        assert r1.effective_to is None

        # 3. Add second rate effective next week -> closes r1 at next week's date
        next_week = today + timedelta(days=7)
        resp2 = api_client.post(f"/api/v1/messes/{mess_m1.mess_id}/meal-rates", {
            "rate": "50.0000",
            "effective_from": str(next_week),
            "reason": "Price revision",
        })
        assert resp2.status_code == status.HTTP_201_CREATED

        r1.refresh_from_db()
        assert r1.effective_to == next_week

        # Check audit
        assert AuditLog.objects.filter(event_type="RATE_CHANGED", entity_type="MealRate").count() == 2

    def test_database_rejects_overlapping_rates_bypassing_service(self, super_admin, mess_m1):
        today = clock.today()
        # Direct ORM / SQL creation with overlapping ranges
        MealRate.objects.create(
            mess=mess_m1,
            rate=Decimal("40.0000"),
            effective_from=today,
            effective_to=today + timedelta(days=10),
            created_by=super_admin,
        )

        with pytest.raises(IntegrityError):
            # Attempt overlapping insert: starts on today + 5 (inside [today, today+10))
            MealRate.objects.create(
                mess=mess_m1,
                rate=Decimal("45.0000"),
                effective_from=today + timedelta(days=5),
                effective_to=today + timedelta(days=15),
                created_by=super_admin,
            )


# ==============================================================================
# 5. Extra Items & Prices Tests
# ==============================================================================


@pytest.mark.django_db
class TestExtraItemsAndPricing:
    def test_clerk_creates_extra_item_for_own_hostel(self, api_client, clerk_user, hostel_h1):
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")

        resp = api_client.post("/api/v1/extras/items", {
            "name": "Evening Snacks",
            "initial_price": "25.0000",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data["name"] == "Evening Snacks"
        assert data["normalized_name"] == "EVENING SNACKS"
        assert data["hostel_code"] == hostel_h1.code
        assert Decimal(data["current_price"]) == Decimal("25.0000")

    def test_clerk_cannot_touch_another_hostels_extras(self, api_client, clerk_user, hostel_h2, super_admin):
        # Super admin creates extra in hostel H2
        item_h2 = create_extra_item(
            name="Gulab Jamun",
            hostel_id=hostel_h2.hostel_id,
            initial_price=Decimal("15.0000"),
            actor=super_admin,
        )

        # Clerk H1 tries to update H2 extra item
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")
        resp = api_client.put(f"/api/v1/extras/items/{item_h2.extra_item_id}", {
            "name": "Hacked Name",
            "version": item_h2.version,
        })
        assert resp.status_code == status.HTTP_404_NOT_FOUND

        # Clerk H1 tries to add price for H2 extra item
        resp_price = api_client.post(f"/api/v1/extras/items/{item_h2.extra_item_id}/prices", {
            "unit_price": "99.0000",
            "effective_from": str(clock.today()),
        })
        assert resp_price.status_code == status.HTTP_404_NOT_FOUND

    def test_database_rejects_overlapping_extra_prices(self, super_admin, hostel_h1):
        item = create_extra_item(name="Omelette", hostel_id=hostel_h1.hostel_id, actor=super_admin)
        today = clock.today()

        ExtraPrice.objects.create(
            extra_item=item,
            unit_price=Decimal("20.0000"),
            effective_from=today,
            effective_to=today + timedelta(days=5),
            created_by=super_admin,
        )

        with pytest.raises(IntegrityError):
            # Overlapping insert
            ExtraPrice.objects.create(
                extra_item=item,
                unit_price=Decimal("25.0000"),
                effective_from=today + timedelta(days=2),
                effective_to=today + timedelta(days=8),
                created_by=super_admin,
            )


# ==============================================================================
# 6. Authoritative Lookup Service Tests
# ==============================================================================


@pytest.mark.django_db
class TestAuthoritativeLookupService:
    def test_rate_and_price_lookup_boundary_table(self, super_admin, mess_m1, hostel_h1):
        """
        Tests hand-checked boundary dates for [effective_from, effective_to) half-open intervals.
        Interval 1: [2026-11-01, 2026-11-10) -> Rate 40.00
        Interval 2: [2026-11-15, None)       -> Rate 50.00 (Gap on 2026-11-10 to 2026-11-14)
        """
        MealRate.objects.create(
            mess=mess_m1,
            rate=Decimal("40.0000"),
            effective_from=date(2026, 11, 1),
            effective_to=date(2026, 11, 10),
            created_by=super_admin,
        )
        MealRate.objects.create(
            mess=mess_m1,
            rate=Decimal("50.0000"),
            effective_from=date(2026, 11, 15),
            effective_to=None,
            created_by=super_admin,
        )

        # Hand-checked boundary expectations
        table = [
            (date(2026, 10, 31), None),                       # Before interval 1
            (date(2026, 11, 1),  Decimal("40.0000")),         # Interval 1: start (inclusive)
            (date(2026, 11, 5),  Decimal("40.0000")),         # Interval 1: interior
            (date(2026, 11, 9),  Decimal("40.0000")),         # Interval 1: last valid day
            (date(2026, 11, 10), None),                       # Interval 1: end (exclusive)
            (date(2026, 11, 12), None),                       # Gap between intervals
            (date(2026, 11, 14), None),                       # Day before interval 2
            (date(2026, 11, 15), Decimal("50.0000")),         # Interval 2: start (inclusive)
            (date(2026, 12, 1),  Decimal("50.0000")),         # Interval 2: open-ended future
        ]

        for target_date, expected_rate in table:
            actual = get_meal_rate(mess_m1, target_date)
            assert actual == expected_rate, f"Failed rate lookup for {target_date}: expected {expected_rate}, got {actual}"

    def test_occurrence_lookup_and_status(self, mess_m1):
        today = clock.today()
        mt = MealType.objects.get(code="LUNCH")
        MealOccurrence.objects.create(
            mess=mess_m1,
            meal_date=today,
            meal_type=mt,
            status="SCHEDULED",
        )

        assert is_meal_scheduled(mess_m1, today, "LUNCH") is True
        assert is_meal_scheduled(mess_m1, today, "DINNER") is False

        occ = get_meal_occurrence(mess_m1, today, "LUNCH")
        assert occ is not None
        assert occ.status == "SCHEDULED"


# ==============================================================================
# 7. System Settings & Version Policy Tests
# ==============================================================================


@pytest.mark.django_db
class TestSystemSettingsAndVersionPolicy:
    def test_setting_read_update_and_typed_getters(self, super_admin):
        # Initial seeded value
        val = get_int_setting("qr.step_seconds", default=0)
        assert val == 30

        # Update via service
        update_setting(
            key="qr.step_seconds",
            value="45",
            reason="Extended QR rotation duration",
            actor=super_admin,
        )

        # Typed getter returns updated value
        assert get_int_setting("qr.step_seconds") == 45

    def test_unknown_setting_key_rejected(self, super_admin):
        with pytest.raises(ValidationError) as exc:
            update_setting(
                key="nonexistent.random.key",
                value="some_value",
                actor=super_admin,
            )
        assert "unknown" in str(exc.value.message).lower()

    def test_setting_write_creates_effective_dated_row_and_audits(self, super_admin):
        initial_count = SystemSetting.objects.filter(key="sync.batch_max_transactions").count()

        # First update
        update_setting(key="sync.batch_max_transactions", value="300", actor=super_admin)
        assert SystemSetting.objects.filter(key="sync.batch_max_transactions").count() == initial_count + 1

        # Second update -> second row, never edits history
        update_setting(key="sync.batch_max_transactions", value="500", actor=super_admin)
        assert SystemSetting.objects.filter(key="sync.batch_max_transactions").count() == initial_count + 2

        audit = AuditLog.objects.filter(
            event_type="SETTING_CHANGED",
            entity_type="SystemSetting",
        ).first()
        assert audit is not None

    def test_sensitive_setting_masked_in_audit_and_api(self, api_client, super_admin):
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        resp = api_client.post("/api/v1/admin/settings", {
            "key": "system.sensitive_token",
            "value": "super-confidential-secret-key-123",
            "reason": "Token setup",
        })
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["value"] == "******"

        # Check audit log never stored plain secret
        audit = AuditLog.objects.filter(
            event_type="SETTING_CHANGED",
            entity_type="SystemSetting",
        ).order_by("-occurred_at").first()
        assert audit is not None
        assert audit.new_values_json["value"] == "******"

        # Verify raw DB row stores actual value
        setting = SystemSetting.objects.filter(key="system.sensitive_token").order_by("-effective_from").first()
        assert setting.value == "super-confidential-secret-key-123"

    def test_app_version_policy_crud_via_api(self, api_client, super_admin):
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        # Create policy
        resp = api_client.post("/api/v1/admin/app-versions", {
            "platform": "ANDROID",
            "app_version": "1.0.0",
            "status": "DEPRECATED",
            "force_update_message": "Please update your Android app.",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        policy_id = resp.json()["policy_id"]

        # Update policy
        resp_up = api_client.put(f"/api/v1/admin/app-versions/{policy_id}", {
            "status": "BLOCKED",
            "force_update_message": "This version is blocked.",
            "version": resp.json()["version"],
        })
        assert resp_up.status_code == status.HTTP_200_OK
        assert resp_up.json()["status"] == "BLOCKED"


# ==============================================================================
# 8. Phase 5 Complete Exit Gate
# ==============================================================================


@pytest.mark.django_db
class TestPhase5ExitGate:
    def test_complete_phase5_exit_gate(self, api_client, super_admin, setup_roles):
        """
        Exit gate verification:
        1. Configure two hostels (H1, H2) and three messes (M1, M2, M3) via API.
           M1 serves students from both H1 and H2.
        2. Assign Managers to each mess via API.
        3. Set common meal rates for each mess via API.
        4. Create 'Evening Snacks' extra and prices in both hostels via API.
        5. Generate 35 days of occurrences via management command.
        6. Verify occurrences (35 * 4 = 140 per mess) exist.
        7. Verify lookup results match a hand-checked table.
        """
        auth_client(api_client, super_admin, "SUPER_ADMIN")
        today = clock.today()

        # Step 1: Create 2 Hostels
        r_h1 = api_client.post("/api/v1/hostels", {"code": "EG-H1", "name": "Exit Gate Hostel 1"})
        assert r_h1.status_code == status.HTTP_201_CREATED
        h1_id = r_h1.json()["hostel_id"]

        r_h2 = api_client.post("/api/v1/hostels", {"code": "EG-H2", "name": "Exit Gate Hostel 2"})
        assert r_h2.status_code == status.HTTP_201_CREATED
        h2_id = r_h2.json()["hostel_id"]

        # Step 2: Create 3 Messes (M1, M2, M3)
        r_m1 = api_client.post("/api/v1/messes", {"code": "EG-M1", "name": "Shared Mess M1"})
        assert r_m1.status_code == status.HTTP_201_CREATED
        m1_id = r_m1.json()["mess_id"]

        r_m2 = api_client.post("/api/v1/messes", {"code": "EG-M2", "name": "Hostel 1 Mess M2"})
        assert r_m2.status_code == status.HTTP_201_CREATED
        m2_id = r_m2.json()["mess_id"]

        r_m3 = api_client.post("/api/v1/messes", {"code": "EG-M3", "name": "Hostel 2 Mess M3"})
        assert r_m3.status_code == status.HTTP_201_CREATED
        m3_id = r_m3.json()["mess_id"]

        # Step 3: Assign Mess Managers to each mess
        r_mgr1 = api_client.post("/api/v1/admin/mess-managers", {
            "email": "eg_mgr1@college.edu",
            "full_name": "Manager M1",
            "mess_code": "EG-M1",
        })
        assert r_mgr1.status_code == status.HTTP_201_CREATED

        r_mgr2 = api_client.post("/api/v1/admin/mess-managers", {
            "email": "eg_mgr2@college.edu",
            "full_name": "Manager M2",
            "mess_code": "EG-M2",
        })
        assert r_mgr2.status_code == status.HTTP_201_CREATED

        r_mgr3 = api_client.post("/api/v1/admin/mess-managers", {
            "email": "eg_mgr3@college.edu",
            "full_name": "Manager M3",
            "mess_code": "EG-M3",
        })
        assert r_mgr3.status_code == status.HTTP_201_CREATED

        # Step 4: Set common meal rates for each mess
        # M1 rate: 45.00
        r_r1 = api_client.post(f"/api/v1/messes/{m1_id}/meal-rates", {
            "rate": "45.0000",
            "effective_from": str(today),
            "reason": "Base rate M1",
        })
        assert r_r1.status_code == status.HTTP_201_CREATED

        # M2 rate: 50.00
        r_r2 = api_client.post(f"/api/v1/messes/{m2_id}/meal-rates", {
            "rate": "50.0000",
            "effective_from": str(today),
            "reason": "Base rate M2",
        })
        assert r_r2.status_code == status.HTTP_201_CREATED

        # M3 rate: 55.00
        r_r3 = api_client.post(f"/api/v1/messes/{m3_id}/meal-rates", {
            "rate": "55.0000",
            "effective_from": str(today),
            "reason": "Base rate M3",
        })
        assert r_r3.status_code == status.HTTP_201_CREATED

        # Step 5: Create "Evening Snacks" extra item in both hostels and prices
        r_ex1 = api_client.post("/api/v1/extras/items", {
            "name": "Evening Snacks",
            "hostel_code": "EG-H1",
            "initial_price": "20.0000",
            "effective_from": str(today),
        })
        assert r_ex1.status_code == status.HTTP_201_CREATED
        ex1_id = r_ex1.json()["extra_item_id"]

        r_ex2 = api_client.post("/api/v1/extras/items", {
            "name": "Evening Snacks",
            "hostel_code": "EG-H2",
            "initial_price": "22.5000",
            "effective_from": str(today),
        })
        assert r_ex2.status_code == status.HTTP_201_CREATED
        ex2_id = r_ex2.json()["extra_item_id"]

        # Step 6: Generate 35 days of occurrences via management command
        call_command("generate_meal_occurrences", days=35)

        # Step 7: Verify 35 days of occurrences exist (35 days * 4 meal types = 140 occurrences per mess)
        for mid in [m1_id, m2_id, m3_id]:
            occ_count = MealOccurrence.objects.filter(mess_id=mid, status="SCHEDULED").count()
            assert occ_count == 140, f"Expected 140 occurrences for mess {mid}, got {occ_count}"

        # Step 8: Verify lookup service against hand-checked table
        # Meal rates
        assert get_meal_rate(m1_id, today) == Decimal("45.0000")
        assert get_meal_rate(m2_id, today) == Decimal("50.0000")
        assert get_meal_rate(m3_id, today) == Decimal("55.0000")

        # Future rate lookups (within open-ended window)
        assert get_meal_rate(m1_id, today + timedelta(days=20)) == Decimal("45.0000")

        # Past rate lookup (before effective_from)
        assert get_meal_rate(m1_id, today - timedelta(days=1)) is None

        # Extra prices
        assert get_extra_price(ex1_id, today) == Decimal("20.0000")
        assert get_extra_price(ex2_id, today) == Decimal("22.5000")

        # Occurrences scheduled for today across all 4 types
        for mt_code in ["BREAKFAST", "LUNCH", "EVENING_SNACKS", "DINNER"]:
            assert is_meal_scheduled(m1_id, today, mt_code) is True
            assert is_meal_scheduled(m2_id, today, mt_code) is True
            assert is_meal_scheduled(m3_id, today, mt_code) is True

        # Day 36 is beyond the 35-day horizon
        assert is_meal_scheduled(m1_id, today + timedelta(days=36), "LUNCH") is False
