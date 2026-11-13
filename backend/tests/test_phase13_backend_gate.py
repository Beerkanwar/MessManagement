"""
Phase 13 backend gate tests [ImplementationGuide Phase 13].

Covers:
- Audit read API for Super Admin, filters, keyset paging and output redaction.
- Three-way audit immutability (privileges, trigger, ORM/admin refusal).
- Bounded Django admin: role-only sign-in, one-hour sessions, read-only pages,
  audited master-data edits and no deletes.
- Appendix B2 parameter registry ranges and environment-only secrets.
- Scheduled jobs are safe to run twice.
- Appendix B events have an emission point in the application source.
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, transaction
from django.db.utils import ProgrammingError
from django.test import Client
from django.urls import reverse

from apps.attendance.services import apply_attendance_correction, record_meal
from apps.audit.models import AuditLog
from apps.audit.selectors import decode_cursor
from apps.billing.models import BalanceAccount, BillingPeriod, Semester
from apps.billing.services import add_balance_credit, review_period
from apps.config.services import (
    CONFIG_REGISTRY,
    clear_settings_cache,
    list_system_settings,
    update_setting,
)
from apps.core.admin_site import admin_site
from apps.core.clock import IST_ZONE, clock
from apps.core.exceptions import ValidationError as DomainValidationError
from apps.hostel.models import (
    Hostel,
    Student,
    StudentImportBatch,
    StudentMessAssignment,
)
from apps.hostel.services import (
    commit_import_batch,
    create_student,
    transfer_student,
)
from apps.identity.models import Role, UserRole
from apps.identity.services.auth_service import login_user
from apps.menu.models import FoodItem
from apps.mess.models import MealOccurrence, MealType, Mess
from apps.pause.models import MessPause
from apps.pause.services import advance_pauses
from apps.reports.scope import ReportContext
from apps.reports.services import record_export_audit

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def freeze_clock():
    clock.set_time(datetime(2026, 11, 12, 12, 0, tzinfo=IST_ZONE))
    clear_settings_cache()
    yield
    clear_settings_cache()
    clock.reset()


@pytest.fixture
def roles(db):
    created = {}
    for name in ["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]:
        role, _ = Role.objects.get_or_create(
            name=name, defaults={"description": f"{name} role"}
        )
        created[name] = role
    return created


@pytest.fixture
def super_admin(db, roles):
    user = User.objects.create_superuser(
        email="phase13-sa@college.edu",
        full_name="Phase 13 Super Admin",
        password="StrongP@ssw0rd123!",
    )
    UserRole.objects.create(user=user, role=roles["SUPER_ADMIN"])
    return user


@pytest.fixture
def student_user(db, roles):
    user = User.objects.create_user(
        email="phase13-student@college.edu",
        full_name="Phase 13 Student",
        password="StrongP@ssw0rd123!",
    )
    UserRole.objects.create(user=user, role=roles["STUDENT"])
    return user


@pytest.fixture
def campus(db, roles, student_user):
    hostel = Hostel.objects.create(code="P13-H", name="Phase 13 Hostel", status="ACTIVE")
    mess = Mess.objects.create(code="P13-M", name="Phase 13 Mess", status="ACTIVE")
    student = Student.objects.create(
        user=student_user,
        roll_number="P13ROLL01",
        hostel=hostel,
        status="ACTIVE",
    )
    StudentMessAssignment.objects.create(
        student=student,
        hostel=hostel,
        mess=mess,
        status="ACTIVE",
        effective_from=clock.today() - timedelta(days=10),
    )
    meal_type, _ = MealType.objects.get_or_create(
        code="LUNCH", defaults={"name": "Lunch", "sequence_no": 2}
    )
    MealOccurrence.objects.create(
        mess=mess,
        meal_type=meal_type,
        meal_date=clock.today(),
        status="SCHEDULED",
    )
    return {
        "hostel": hostel,
        "mess": mess,
        "student": student,
        "meal_type": meal_type,
    }


# ---------------------------------------------------------------------------
# Audit read API
# ---------------------------------------------------------------------------


def _create_audit(event_type="LOGIN_SUCCESS", **overrides):
    values = {
        "event_type": event_type,
        "entity_type": "User",
        "entity_id": "1",
        "occurred_at": clock.now(),
        "reason": "",
        "correlation_id": "",
        "old_values_json": None,
        "new_values_json": None,
        "metadata_json": None,
    }
    values.update(overrides)
    return AuditLog.objects.create(**values)


@pytest.mark.django_db
class TestAuditReadApi:
    def test_super_admin_can_list_and_non_admin_is_denied(
        self, api_client, super_admin, student_user
    ):
        _create_audit()

        api_client.force_authenticate(user=student_user)
        denied = api_client.get("/api/v1/audit/events")
        assert denied.status_code == 403

        api_client.force_authenticate(user=super_admin)
        allowed = api_client.get("/api/v1/audit/events")
        assert allowed.status_code == 200
        assert allowed.json()["count"] == 1

    def test_filters_and_unknown_parameters(self, api_client, super_admin):
        _create_audit(
            event_type="STUDENT_CREATED",
            entity_type="Student",
            entity_id="77",
            correlation_id="corr-77",
        )
        _create_audit(event_type="LOGIN_SUCCESS", correlation_id="corr-other")
        api_client.force_authenticate(user=super_admin)

        by_type = api_client.get("/api/v1/audit/events?event_type=STUDENT_CREATED")
        assert by_type.json()["count"] == 1

        by_entity = api_client.get("/api/v1/audit/events?entity_type=Student&entity_id=77")
        assert by_entity.json()["count"] == 1

        by_correlation = api_client.get("/api/v1/audit/events?correlation_id=corr-77")
        assert by_correlation.json()["count"] == 1

        unknown = api_client.get("/api/v1/audit/events?bogus=1")
        assert unknown.status_code == 400
        assert unknown.json()["code"] == "VALIDATION_ERROR"

    def test_keyset_paging_has_no_repeats(self, api_client, super_admin):
        base = clock.now()
        for index in range(5):
            _create_audit(
                event_type=f"EVENT_{index}",
                occurred_at=base + timedelta(seconds=index),
            )
        api_client.force_authenticate(user=super_admin)

        first = api_client.get("/api/v1/audit/events?limit=2").json()
        assert len(first["results"]) == 2
        assert first["has_more"] is True
        assert first["next_cursor"]

        second = api_client.get(
            f"/api/v1/audit/events?limit=2&cursor={first['next_cursor']}"
        ).json()
        first_ids = {row["audit_id"] for row in first["results"]}
        second_ids = {row["audit_id"] for row in second["results"]}
        assert first_ids.isdisjoint(second_ids)
        # The cursor decodes to the last row of the previous page.
        occurred_at, audit_id = decode_cursor(first["next_cursor"])
        assert audit_id == first["results"][-1]["audit_id"]
        assert occurred_at == datetime.fromisoformat(first["results"][-1]["occurred_at"])

    def test_output_redacts_secret_looking_values(self, api_client, super_admin):
        _create_audit(
            old_values_json={"api_token": "should-not-appear", "safe": "visible"},
            new_values_json={"password": "should-not-appear"},
        )
        api_client.force_authenticate(user=super_admin)

        response = api_client.get("/api/v1/audit/events")
        payload = response.json()
        serialized = str(payload)
        assert "should-not-appear" not in serialized
        assert "[REDACTED]" in serialized
        assert payload["results"][0]["old_values"]["safe"] == "visible"

    def test_date_range_is_inclusive_of_ist_days(self, api_client, super_admin):
        _create_audit(occurred_at=datetime(2026, 11, 10, 0, 30, tzinfo=IST_ZONE))
        _create_audit(occurred_at=datetime(2026, 11, 11, 23, 30, tzinfo=IST_ZONE))
        api_client.force_authenticate(user=super_admin)

        response = api_client.get("/api/v1/audit/events?from=2026-11-10&to=2026-11-10")
        assert response.json()["count"] == 1

        bad_range = api_client.get("/api/v1/audit/events?from=2026-11-12&to=2026-11-10")
        assert bad_range.status_code == 400


# ---------------------------------------------------------------------------
# Audit immutability
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_audit_immutability_privileges_trigger_and_model(super_admin):
    log = _create_audit(actor_user=super_admin)

    # Model-level refusal.
    with pytest.raises(ValueError):
        log.reason = "tamper"
        log.save()
    with pytest.raises(ValueError):
        log.delete()

    # Restricted application role: INSERT/SELECT only.
    role_name = f"audit_app_{uuid.uuid4().hex[:10]}"
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE ROLE "{role_name}" NOLOGIN')
        cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{role_name}"')
        cursor.execute(
            f'GRANT SELECT, INSERT ON TABLE audit_audit_log TO "{role_name}"'
        )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{role_name}"')
        try:
            assert _table_privilege(role_name, "SELECT") is True
            assert _table_privilege(role_name, "INSERT") is True
            assert _table_privilege(role_name, "UPDATE") is False
            assert _table_privilege(role_name, "DELETE") is False

            with pytest.raises(ProgrammingError):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "UPDATE audit_audit_log SET reason = %s WHERE audit_id = %s",
                            ["tamper", log.audit_id],
                        )
            with pytest.raises(ProgrammingError):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM audit_audit_log WHERE audit_id = %s",
                            [log.audit_id],
                        )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP OWNED BY "{role_name}"')
            cursor.execute(f'DROP ROLE "{role_name}"')

    # The insert-only trigger still protects the table.
    with pytest.raises(Exception):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_audit_log SET reason = %s WHERE audit_id = %s",
                    ["tamper", log.audit_id],
                )


def _table_privilege(role_name, privilege):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT has_table_privilege(%s, 'audit_audit_log', %s)",
            [role_name, privilege],
        )
        return cursor.fetchone()[0]


@pytest.mark.django_db
def test_admin_registers_audit_read_only(super_admin):
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.user = super_admin
    model_admin = admin_site._registry[AuditLog]
    assert model_admin.has_change_permission(request) is False
    assert model_admin.has_delete_permission(request) is False
    assert model_admin.has_add_permission(request) is False


# ---------------------------------------------------------------------------
# Bounded Django admin
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBoundedAdmin:
    def test_admin_path_is_not_default(self):
        assert settings.ADMIN_PATH != "admin"
        assert settings.SESSION_COOKIE_AGE == settings.ADMIN_SESSION_SECONDS <= 3600

    def test_non_super_admin_cannot_sign_in(self, student_user):
        client = Client()
        response = client.post(
            f"/{settings.ADMIN_PATH}/login/",
            {
                "username": student_user.email,
                "password": "StrongP@ssw0rd123!",
                "next": f"/{settings.ADMIN_PATH}/",
            },
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_super_admin_signs_in_and_session_lasts_one_hour(self, super_admin):
        client = Client()
        response = client.post(
            f"/{settings.ADMIN_PATH}/login/",
            {
                "username": super_admin.email,
                "password": "StrongP@ssw0rd123!",
                "next": f"/{settings.ADMIN_PATH}/",
            },
        )
        assert response.status_code == 302
        assert client.session["_auth_user_id"] == str(super_admin.user_id)
        assert client.session.get_expiry_age() <= 3600

    def test_default_admin_path_is_absent(self):
        assert Client().get("/admin/").status_code == 404

    def test_read_only_model_has_no_save_button(self, super_admin):
        client = Client()
        client.force_login(super_admin)
        response = client.get(
            f"/{settings.ADMIN_PATH}/identity/user/{super_admin.user_id}/change/"
        )
        assert response.status_code == 200
        assert b'name="_save"' not in response.content
        assert b"deletelink" not in response.content

    def test_editable_master_save_is_audited(self, super_admin, campus):
        hostel = campus["hostel"]
        client = Client()
        client.force_login(super_admin)

        change_page = client.get(
            f"/{settings.ADMIN_PATH}/hostel/hostel/{hostel.hostel_id}/change/"
        )
        assert b'name="_save"' in change_page.content

        response = client.post(
            f"/{settings.ADMIN_PATH}/hostel/hostel/{hostel.hostel_id}/change/",
            {
                "code": hostel.code,
                "name": "Phase 13 Hostel Renamed",
                "address": "Updated address",
                "status": "ACTIVE",
                "version": str(hostel.version),
                "_save": "Save",
            },
        )
        assert response.status_code == 302

        hostel.refresh_from_db()
        assert hostel.name == "Phase 13 Hostel Renamed"

        audit = AuditLog.objects.filter(
            event_type="MASTER_DATA_CHANGED",
            entity_type="Hostel",
            entity_id=str(hostel.hostel_id),
        ).latest("audit_id")
        assert audit.old_values_json["name"] == "Phase 13 Hostel"
        assert audit.new_values_json["name"] == "Phase 13 Hostel Renamed"

    def test_no_delete_permission_on_referenced_models(self, super_admin):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = super_admin
        for model in (Hostel, Mess, FoodItem):
            assert admin_site._registry[model].has_delete_permission(request) is False


# ---------------------------------------------------------------------------
# Parameter registry
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestParameterRegistry:
    def test_registry_has_type_range_sensitivity_default_and_phase(self, super_admin):
        spec = CONFIG_REGISTRY["qr.step_seconds"]
        assert spec.data_type == "INTEGER"
        assert spec.minimum == 10 and spec.maximum == 120
        assert spec.default == "30"
        assert spec.phase == "P6"
        assert spec.is_sensitive is False

    def test_out_of_range_value_is_rejected(self, super_admin):
        with pytest.raises(DomainValidationError) as excinfo:
            update_setting(
                key="qr.step_seconds",
                value="999",
                actor=super_admin,
            )
        assert "<= 120" in str(excinfo.value)

    def test_environment_only_secret_cannot_be_a_setting(self, super_admin):
        assert CONFIG_REGISTRY["secrets.jwt_signing_key"].env_only is True
        with pytest.raises(DomainValidationError) as excinfo:
            update_setting(
                key="secrets.jwt_signing_key",
                value="leaked",
                actor=super_admin,
            )
        assert "deployment-managed" in str(excinfo.value)

    def test_listing_exposes_registry_metadata_and_masks_secrets(self, super_admin):
        rows = {row["key"]: row for row in list_system_settings(mask_sensitive=True)}
        assert rows["qr.step_seconds"]["phase"] == "P6"
        assert rows["qr.step_seconds"]["minimum"] == "10"
        assert rows["qr.step_seconds"]["editable"] is True
        assert rows["secrets.jwt_signing_key"]["env_only"] is True
        assert rows["secrets.jwt_signing_key"]["editable"] is False
        assert rows["secrets.jwt_signing_key"]["value"] == "******"

    def test_settings_api_exposes_metadata_and_rejects_env_only(
        self, api_client, super_admin
    ):
        api_client.force_authenticate(user=super_admin)
        listing = api_client.get("/api/v1/admin/settings")
        assert listing.status_code == 200
        row = next(
            item for item in listing.json() if item["key"] == "sync.batch_max_transactions"
        )
        assert row["maximum"] == "500"
        assert row["phase"] == "P8"

        rejected = api_client.post(
            "/api/v1/admin/settings",
            {"key": "secrets.database_password", "value": "leaked"},
            format="json",
        )
        assert rejected.status_code == 400
        assert rejected.json()["code"] == "ENV_ONLY_SETTING"


# ---------------------------------------------------------------------------
# Appendix B events produced by Phase 13 changes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_login_events_and_device_registration_are_audited(super_admin):
    login_user(
        email=super_admin.email,
        password="StrongP@ssw0rd123!",
        device_id="p13-admin-device",
        platform="WEB",
    )
    assert AuditLog.objects.filter(
        event_type="DEVICE_REGISTERED", entity_type="DeviceRegistration"
    ).exists()
    assert AuditLog.objects.filter(event_type="LOGIN_SUCCESS").exists()

    with pytest.raises(Exception):
        login_user(
            email=super_admin.email,
            password="WrongP@ssw0rd123!",
            device_id="p13-other-device",
            platform="WEB",
        )
    assert AuditLog.objects.filter(event_type="LOGIN_FAILURE").exists()


@pytest.mark.django_db
def test_assignment_and_qr_events(super_admin, campus, roles, student_user):
    student = campus["student"]

    created = create_student(
        roll_number="P13ROLL02",
        email="p13second@college.edu",
        full_name="Second Student",
        hostel_code=campus["hostel"].code,
        mess_code=campus["mess"].code,
        actor=super_admin,
    )
    assert AuditLog.objects.filter(
        event_type="ASSIGNMENT_CREATED",
        entity_type="StudentMessAssignment",
        entity_id=str(created["assignment_id"]),
    ).exists()

    transfer_student(
        student_id=student.student_id,
        new_hostel_code=campus["hostel"].code,
        new_mess_code=campus["mess"].code,
        effective_from=clock.today() + timedelta(days=1),
        reason="Phase 13 transfer test",
        actor=super_admin,
    )
    assert AuditLog.objects.filter(event_type="ASSIGNMENT_TRANSFERRED").exists()

    first_transaction = uuid.uuid4()
    result = record_meal(
        transaction_id=first_transaction,
        student=student,
        meal_date=clock.today(),
        meal_type=campus["meal_type"],
        mess=campus["mess"],
        recorded_by_user=super_admin,
        source="QR",
    )
    assert result.status == "SYNCHRONIZED"
    assert AuditLog.objects.filter(event_type="QR_SUCCESS").exists()

    duplicate = record_meal(
        transaction_id=uuid.uuid4(),
        student=student,
        meal_date=clock.today(),
        meal_type=campus["meal_type"],
        mess=campus["mess"],
        recorded_by_user=super_admin,
        source="QR",
    )
    assert duplicate.status == "DUPLICATE"
    assert AuditLog.objects.filter(event_type="ATTENDANCE_DUPLICATE").exists()
    assert AuditLog.objects.filter(event_type="QR_DUPLICATE").exists()


@pytest.mark.django_db
def test_import_commit_emits_audit_event(super_admin):
    batch = StudentImportBatch.objects.create(
        imported_by=super_admin,
        file_name="phase13-empty.csv",
        total_rows=0,
        status="STAGED",
    )
    result = commit_import_batch(batch_id=batch.batch_id, actor=super_admin)
    assert result["status"] == "COMMITTED"
    assert AuditLog.objects.filter(
        event_type="STUDENT_IMPORT_COMMITTED",
        entity_type="StudentImportBatch",
        entity_id=str(batch.batch_id),
    ).exists()


@pytest.mark.django_db
def test_attendance_correction_emits_audit_event(super_admin, campus):
    correction = apply_attendance_correction(
        correction_transaction_id=uuid.uuid4(),
        student_id=campus["student"].student_id,
        meal_date=clock.today(),
        meal_type=campus["meal_type"],
        action="ADD_MISSING",
        reason="Phase 13 correction audit",
        actor=super_admin,
    )
    assert correction.status == "APPLIED"
    assert AuditLog.objects.filter(
        event_type="ATTENDANCE_CORRECTED",
        reason="Phase 13 correction audit",
    ).exists()


@pytest.mark.django_db
def test_bill_review_emits_audit_event(super_admin):
    period = BillingPeriod.objects.create(
        year=2026,
        month=10,
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        status="BILL_GENERATED",
        generated_at=clock.now(),
    )
    reviewed = review_period(
        billing_period_id=period.billing_period_id,
        actor=super_admin,
    )
    assert reviewed.status == "REVIEWED"
    assert AuditLog.objects.filter(
        event_type="BILL_REVIEWED",
        entity_type="BillingPeriod",
        entity_id=str(period.billing_period_id),
    ).exists()


@pytest.mark.django_db
def test_credit_emits_audit_event(super_admin, campus):
    semester = Semester.objects.create(
        code="P13-SEM",
        name="Phase 13 Semester",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status="ACTIVE",
    )
    account = BalanceAccount.objects.create(
        student=campus["student"],
        semester=semester,
        opening_balance=Decimal("1000.0000"),
        current_balance=Decimal("1000.0000"),
        last_calculated_at=clock.now(),
    )
    add_balance_credit(
        student_id=campus["student"].student_id,
        semester_id=semester.semester_id,
        amount=Decimal("100.0000"),
        reference="P13-CREDIT-REF",
        reason="Phase 13 credit audit",
        actor=super_admin,
    )
    assert AuditLog.objects.filter(
        event_type="CREDIT_ADDED",
        entity_type="BalanceAccount",
        entity_id=str(account.balance_account_id),
    ).exists()


APPENDIX_B_EVENTS = [
    "LOGIN_SUCCESS",
    "LOGIN_FAILURE",
    "PASSWORD_RESET",
    "PASSWORD_CHANGED",
    "TOKEN_REUSE_DETECTED",
    "DEVICE_REGISTERED",
    "DEVICE_REVOKE_PENDING_SYNC",
    "DEVICE_REVOKED",
    "SECRET_ROTATED",
    "STUDENT_CREATED",
    "STUDENT_IMPORT_COMMITTED",
    "STUDENT_VERIFIED",
    "ASSIGNMENT_CREATED",
    "ASSIGNMENT_TRANSFERRED",
    "ATTENDANCE_DUPLICATE",
    "ATTENDANCE_CORRECTED",
    "SYNC_SUCCESS",
    "SYNC_FAILURE",
    "SYNC_CONFLICT",
    "SYNC_CONFLICT_RESOLVED",
    "PAUSE_SUBMITTED",
    "PAUSE_ACTIVATED",
    "PAUSE_COMPLETED",
    "PAUSE_CANCELLED",
    "BILL_GENERATED",
    "BILL_ADJUSTED",
    "BILL_LOCKED",
    "BILL_UNLOCKED",
    "BILL_REVIEWED",
    "CREDIT_ADDED",
    "RATE_CHANGED",
    "SETTING_CHANGED",
    "MASTER_DATA_CHANGED",
    "MENU_PUBLISHED",
    "MENU_REVISED",
    "REPORT_EXPORTED",
]

# Transitions must record a before and an after snapshot [Appendix B].
TRANSITION_EVENTS = {
    "ATTENDANCE_CORRECTED",
    "BILL_ADJUSTED",
    "BILL_LOCKED",
    "BILL_UNLOCKED",
    "BILL_REVIEWED",
    "PAUSE_ACTIVATED",
    "PAUSE_COMPLETED",
    "PAUSE_CANCELLED",
    "SECRET_ROTATED",
}

# Actions an operator may be asked to justify in a review must carry a reason.
REASON_REQUIRED_EVENTS = {
    "ASSIGNMENT_TRANSFERRED",
    "ATTENDANCE_CORRECTED",
    "BILL_ADJUSTED",
    "BILL_UNLOCKED",
    "DEVICE_REVOKED",
    "MASTER_DATA_CHANGED",
    "PAUSE_CANCELLED",
    "RATE_CHANGED",
    "SETTING_CHANGED",
}

# These events are tied to a registered device and must link to it.
DEVICE_REQUIRED_EVENTS = {
    "ATTENDANCE_DUPLICATE",
    "DEVICE_REGISTERED",
    "DEVICE_REVOKE_PENDING_SYNC",
    "DEVICE_REVOKED",
    "LOGIN_SUCCESS",
    "SYNC_CONFLICT",
    "SYNC_FAILURE",
    "SYNC_SUCCESS",
    "TOKEN_REUSE_DETECTED",
}


def _audit_calls():
    """Yield (event_type, kwargs, path, lineno) for every audit emission."""
    import ast
    from pathlib import Path

    apps_dir = Path(__file__).resolve().parent.parent / "apps"
    for path in apps_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name != "record_audit_event":
                continue
            keywords = {kw.arg: kw.value for kw in node.keywords}
            event_node = keywords.get("event_type")
            event_type = (
                event_node.value
                if isinstance(event_node, ast.Constant)
                and isinstance(event_node.value, str)
                else ""
            )
            yield event_type, set(keywords), str(path), node.lineno


def test_appendix_b_events_have_emission_points():
    """Every Appendix B event code is emitted somewhere in application code."""
    from pathlib import Path

    apps_dir = Path(__file__).resolve().parent.parent / "apps"
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in apps_dir.rglob("*.py")
    )
    missing = [event for event in APPENDIX_B_EVENTS if event not in source]
    assert missing == []


def test_appendix_b_payload_contract():
    """
    Every emission of an Appendix B event carries the shared envelope, and the
    event families carry the extra context the specification requires.
    """
    calls = [call for call in _audit_calls() if call[0] in APPENDIX_B_EVENTS]
    assert calls, "No Appendix B audit emissions found."

    problems = []
    for event_type, kwargs, path, lineno in calls:
        location = f"{event_type} at {path}:{lineno}"
        required = {"event_type", "entity_type", "entity_id", "correlation_id"}
        if event_type != "LOGIN_FAILURE":
            # A failed login for an unknown email has no actor row to reference.
            required.add("actor_user")
        missing = required - kwargs
        if missing:
            problems.append(f"{location}: missing {sorted(missing)}")
        if event_type in TRANSITION_EVENTS:
            transition_missing = {"old_values", "new_values"} - kwargs
            if transition_missing:
                problems.append(
                    f"{location}: transition missing {sorted(transition_missing)}"
                )
        if event_type in REASON_REQUIRED_EVENTS and "reason" not in kwargs:
            problems.append(f"{location}: missing reason")
        if event_type in DEVICE_REQUIRED_EVENTS and "device_registration" not in kwargs:
            problems.append(f"{location}: missing device_registration")
        if not ({"old_values", "new_values", "metadata", "reason"} & kwargs):
            problems.append(f"{location}: no before/after/context payload")

    assert problems == []


@pytest.mark.django_db
def test_pause_completed_audit_carries_correlation_and_snapshots(
    super_admin, campus
):
    pause = MessPause.objects.create(
        student=campus["student"],
        mess=campus["mess"],
        requested_start_date=date(2026, 11, 1),
        requested_end_date=date(2026, 11, 5),
        effective_start_date=date(2026, 11, 1),
        effective_end_date=date(2026, 11, 5),
        status="ACTIVE",
        requested_at=clock.now(),
    )

    advance_pauses(now=clock.now())

    log = AuditLog.objects.get(event_type="PAUSE_COMPLETED")
    assert log.entity_type == "MessPause"
    assert log.entity_id == str(pause.pause_id)
    assert log.correlation_id.startswith("job:advance_pauses:")
    assert log.old_values_json == {"status": "ACTIVE"}
    assert log.new_values_json == {
        "status": "COMPLETED",
        "effective_end_date": "2026-11-05",
    }


@pytest.mark.django_db
def test_report_exported_audit_carries_actor_correlation_and_context(super_admin):
    definition = type("Definition", (), {"id": "attendance-daily"})()
    ctx = ReportContext(
        user=super_admin,
        role="SUPER_ADMIN",
        date_from=date(2026, 11, 1),
        date_to=date(2026, 11, 2),
        applied_filters={"hostel": 7},
        correlation_id="req-export-123",
    )

    record_export_audit(definition, ctx, "csv", row_count=42)

    log = AuditLog.objects.get(event_type="REPORT_EXPORTED")
    assert log.actor_user == super_admin
    assert log.entity_type == "REPORT"
    assert log.entity_id == "attendance-daily"
    assert log.correlation_id == "req-export-123"
    assert log.metadata_json["row_count"] == 42
    assert log.metadata_json["format"] == "csv"
    assert log.metadata_json["hostel"] == 7



# ---------------------------------------------------------------------------
# Scheduled jobs and cold start
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_scheduled_jobs_run_twice_safely():
    jobs = [
        ("generate_meal_occurrences", {"days": 1}),
        ("advance_pauses", {}),
        ("open_billing_period", {"date": "2026-11-01"}),
        ("verify_balances", {}),
        ("provision_missing_secrets", {}),
    ]
    for command, options in jobs:
        call_command(command, **options)
        call_command(command, **options)


@pytest.mark.django_db
def test_cold_start_seeds_are_present():
    """Migrations run seed data required by a working empty-database start."""
    assert Role.objects.filter(
        name__in=["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]
    ).count() == 4
    assert MealType.objects.filter(
        code__in=["BREAKFAST", "LUNCH", "EVENING_SNACKS", "DINNER"]
    ).count() == 4
    assert User.objects.count() == 0
    assert Mess.objects.count() == 0
