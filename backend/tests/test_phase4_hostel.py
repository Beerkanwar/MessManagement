"""
Comprehensive Phase 4 Test Suite: Hostels, Student Provisioning, Import Pipeline,
Verification, Assignments, and Clerk Management.

Enforces:
- SPEC SDD §10, §64, §96, §97
- SPEC DBDD §4, §4.1
- SPEC SRS §3.3, §4
- DEC-03, DEC-08
- Phase 4 Test Checkpoints & Exit Gate
"""
import io
import csv
from datetime import date, timedelta
from unittest.mock import patch
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.core.clock import clock
from apps.core.error_codes import ErrorCodes
from apps.core.exceptions import ConflictError, NotFoundError, ValidationError
from apps.hostel.models import (
    Hostel,
    HostelClerkAssignment,
    Student,
    StudentImportBatch,
    StudentImportError,
    StudentMessAssignment,
    StudentVerification,
)
from apps.hostel.services import (
    advance_change_cursor,
    bulk_reject_assignments,
    bulk_verify_assignments,
    cancel_import_batch,
    commit_import_batch,
    create_hostel,
    create_hostel_clerk,
    create_import_batch,
    create_student,
    deactivate_hostel,
    deactivate_hostel_clerk,
    get_import_batch_preview,
    normalize_email,
    normalize_roll_number,
    reassign_hostel_clerk,
    reject_assignment,
    transfer_student,
    update_hostel,
    update_student,
    upload_and_commit_import,
    verify_assignment,
)
from apps.identity.models import DeviceRegistration, Role, UserRole
from apps.identity.services.token_service import generate_access_token
from apps.mess.models import Mess
from apps.sync.models import ChangeCursor

User = get_user_model()


class JsonAPIClient(APIClient):
    """DRF APIClient that defaults to JSON format for requests."""

    def post(self, path, data=None, format="json", **extra):
        return super().post(path, data=data, format=format, **extra)

    def put(self, path, data=None, format="json", **extra):
        return super().put(path, data=data, format=format, **extra)

    def patch(self, path, data=None, format="json", **extra):
        return super().patch(path, data=data, format=format, **extra)


@pytest.fixture
def api_client():
    return JsonAPIClient()


@pytest.fixture(autouse=True)
def clear_cache_and_reset_clock():
    cache.clear()
    clock.reset()
    yield
    cache.clear()
    clock.reset()


@pytest.fixture
def setup_roles(db):
    roles = {}
    for r in ["SUPER_ADMIN", "HOSTEL_CLERK", "MESS_MANAGER", "STUDENT"]:
        role_obj, _ = Role.objects.get_or_create(name=r, defaults={"description": f"{r} role"})
        roles[r] = role_obj
    return roles


@pytest.fixture
def super_admin(db, setup_roles):
    sa = User.objects.create_superuser(
        email="admin@college.edu",
        full_name="Super Admin",
        password="SuperPassword123!",
    )
    UserRole.objects.get_or_create(user=sa, role=setup_roles["SUPER_ADMIN"])
    return sa


@pytest.fixture
def hostel_a(db):
    return Hostel.objects.create(
        code="H1",
        name="Hostel One",
        address="North Campus",
        status="ACTIVE",
    )


@pytest.fixture
def hostel_b(db):
    return Hostel.objects.create(
        code="H2",
        name="Hostel Two",
        address="South Campus",
        status="ACTIVE",
    )


@pytest.fixture
def mess_a(db):
    return Mess.objects.create(
        code="M1",
        name="Mess Alpha",
        status="ACTIVE",
    )


@pytest.fixture
def mess_b(db):
    return Mess.objects.create(
        code="M2",
        name="Mess Beta",
        status="ACTIVE",
    )


@pytest.fixture
def clerk_user(db, setup_roles, hostel_a):
    user = User.objects.create_user(
        email="clerk_h1@college.edu",
        full_name="Clerk One",
        password="ClerkPassword123!",
    )
    UserRole.objects.create(user=user, role=setup_roles["HOSTEL_CLERK"])
    HostelClerkAssignment.objects.create(
        user=user,
        hostel=hostel_a,
        is_active=True,
    )
    return user


@pytest.fixture
def clerk_b_user(db, setup_roles, hostel_b):
    user = User.objects.create_user(
        email="clerk_h2@college.edu",
        full_name="Clerk Two",
        password="ClerkPassword123!",
    )
    UserRole.objects.create(user=user, role=setup_roles["HOSTEL_CLERK"])
    HostelClerkAssignment.objects.create(
        user=user,
        hostel=hostel_b,
        is_active=True,
    )
    return user


def auth_client(client, user, role_name):
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
# 1. Normalization Service Tests
# ==============================================================================


@pytest.mark.django_db
class TestNormalizationService:
    def test_email_normalization(self):
        assert normalize_email("  Student@COLLEGE.Edu  ") == "student@college.edu"

    def test_roll_number_normalization(self):
        assert normalize_roll_number("  cs2024-001  ") == "CS2024-001"

    def test_roll_number_with_pipe_rejected(self):
        with pytest.raises(ValidationError) as exc:
            normalize_roll_number("CS|2024|001")
        assert "pipe" in str(exc.value.message).lower()

    def test_duplicate_collision_due_to_casing_and_spaces(self, super_admin, hostel_a, mess_a):
        create_student(
            email="Test.Student@College.EDU",
            full_name="Test Student",
            roll_number="cs2024-001",
            hostel_code=hostel_a.code,
            mess_code=mess_a.code,
            actor=super_admin,
        )

        with pytest.raises(ConflictError):
            create_student(
                email="  test.student@college.edu  ",
                full_name="Duplicate Email",
                roll_number="CS2024-999",
                hostel_code=hostel_a.code,
                mess_code=mess_a.code,
                actor=super_admin,
            )

        with pytest.raises(ConflictError):
            create_student(
                email="other@college.edu",
                full_name="Duplicate Roll",
                roll_number="  CS2024-001  ",
                hostel_code=hostel_a.code,
                mess_code=mess_a.code,
                actor=super_admin,
            )


# ==============================================================================
# 2. Hostel Management (Super Admin)
# ==============================================================================


@pytest.mark.django_db
class TestHostelManagement:
    def test_super_admin_creates_hostel(self, api_client, super_admin):
        auth_client(api_client, super_admin, "SUPER_ADMIN")
        response = api_client.post("/api/v1/hostels", {
            "code": "H3",
            "name": "Hostel Three",
            "address": "East Campus",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["code"] == "H3"
        assert response.json()["version"] == 1

    def test_clerk_cannot_create_hostel(self, api_client, clerk_user):
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")
        response = api_client.post("/api/v1/hostels", {
            "code": "H4",
            "name": "Hostel Four",
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hostel_update_and_optimistic_locking(self, api_client, super_admin, hostel_a):
        auth_client(api_client, super_admin, "SUPER_ADMIN")
        # Valid update
        response = api_client.patch(f"/api/v1/hostels/{hostel_a.hostel_id}", {
            "name": "Hostel One Renamed",
            "version": hostel_a.version,
        })
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "Hostel One Renamed"
        assert response.json()["version"] == 2

        # Stale version update rejected
        response = api_client.patch(f"/api/v1/hostels/{hostel_a.hostel_id}", {
            "name": "Another Rename",
            "version": 1,  # Stale!
        })
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_hostel_deactivation_refused_if_active_clerk_or_assignment(
        self, api_client, super_admin, hostel_a, clerk_user
    ):
        auth_client(api_client, super_admin, "SUPER_ADMIN")
        # Clerk exists for hostel_a
        response = api_client.post(f"/api/v1/hostels/{hostel_a.hostel_id}/deactivate", {
            "version": hostel_a.version,
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_hostel_scope_read(self, api_client, super_admin, clerk_user, hostel_a, hostel_b):
        # Super Admin sees all
        auth_client(api_client, super_admin, "SUPER_ADMIN")
        r_admin = api_client.get("/api/v1/hostels")
        assert r_admin.status_code == status.HTTP_200_OK
        assert r_admin.json()["count"] == 2

        # Clerk sees only own hostel
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")
        r_clerk = api_client.get("/api/v1/hostels")
        assert r_clerk.status_code == status.HTTP_200_OK
        assert r_clerk.json()["count"] == 1
        assert r_clerk.json()["results"][0]["code"] == "H1"


# ==============================================================================
# 3. Direct Student Creation & Provisioning
# ==============================================================================


@pytest.mark.django_db
class TestStudentProvisioning:
    def test_super_admin_creates_student(self, api_client, super_admin, hostel_a, mess_a):
        auth_client(api_client, super_admin, "SUPER_ADMIN")
        response = api_client.post("/api/v1/students", {
            "email": "student1@college.edu",
            "full_name": "Student One",
            "roll_number": "CS2024-001",
            "hostel_code": "H1",
            "mess_code": "M1",
            "department": "Computer Science",
            "year_of_study": 2,
        })
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["status"] == "PENDING_VERIFICATION"
        assert data["roll_number"] == "CS2024-001"

        # Verify User has unusable password
        user = User.objects.get(user_id=data["user_id"])
        assert not user.has_usable_password()

        # Audit event recorded
        audit = AuditLog.objects.filter(event_type="STUDENT_CREATED", entity_id=data["student_id"]).first()
        assert audit is not None
        assert audit.actor_user == super_admin

    def test_clerk_cannot_create_or_edit_student(self, api_client, clerk_user, super_admin, hostel_a, mess_a):
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")
        # Create attempt
        r_create = api_client.post("/api/v1/students", {
            "email": "student2@college.edu",
            "full_name": "Student Two",
            "roll_number": "CS2024-002",
            "hostel_code": "H1",
            "mess_code": "M1",
        })
        assert r_create.status_code == status.HTTP_403_FORBIDDEN

        # Create one via service
        st = create_student(
            email="student2@college.edu",
            full_name="Student Two",
            roll_number="CS2024-002",
            hostel_code="H1",
            mess_code="M1",
            actor=super_admin,
        )

        # Edit attempt by Clerk
        r_edit = api_client.patch(f"/api/v1/students/{st['student_id']}", {
            "full_name": "Hacked Name",
            "version": 1,
        })
        assert r_edit.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 4. Verification Workflow (Hostel Clerk)
# ==============================================================================


@pytest.mark.django_db
class TestVerificationWorkflow:
    def test_clerk_lists_pending_verifications_for_own_hostel(
        self, api_client, clerk_user, clerk_b_user, super_admin, hostel_a, hostel_b, mess_a
    ):
        # Student in hostel A
        s_a = create_student(
            email="st_a@college.edu",
            full_name="Student A",
            roll_number="CSA-01",
            hostel_code="H1",
            mess_code="M1",
            actor=super_admin,
        )
        # Student in hostel B
        s_b = create_student(
            email="st_b@college.edu",
            full_name="Student B",
            roll_number="CSB-01",
            hostel_code="H2",
            mess_code="M1",
            actor=super_admin,
        )

        # Clerk A queries verifications
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")
        resp = api_client.get("/api/v1/students/verifications")
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["student"]["roll_number"] == "CSA-01"

    def test_clerk_cannot_verify_other_hostels_assignment(
        self, api_client, clerk_user, super_admin, hostel_b, mess_a
    ):
        # Student in hostel B
        st = create_student(
            email="st_b2@college.edu",
            full_name="Student B2",
            roll_number="CSB-02",
            hostel_code="H2",
            mess_code="M1",
            actor=super_admin,
        )

        # Clerk of hostel A tries to verify
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")
        resp = api_client.post(f"/api/v1/students/verifications/{st['assignment_id']}/verify", {
            "notes": "Trying to verify another hostel",
        })
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_verification_closes_overlapping_active_assignment(
        self, api_client, clerk_user, clerk_b_user, super_admin, hostel_a, hostel_b, mess_a, mess_b
    ):
        # 1. Create and verify initial assignment in Hostel A
        st = create_student(
            email="transfer_test@college.edu",
            full_name="Transfer Student",
            roll_number="TF-001",
            hostel_code="H1",
            mess_code="M1",
            effective_from=date(2026, 1, 1),
            actor=super_admin,
        )
        verify_assignment(assignment_id=st["assignment_id"], actor=clerk_user)

        old_assignment = StudentMessAssignment.objects.get(assignment_id=st["assignment_id"])
        assert old_assignment.status == "ACTIVE"

        # 2. Transfer student to Hostel B
        transfer_eff = date(2026, 2, 1)
        new_assignment = transfer_student(
            student_id=st["student_id"],
            new_hostel_code="H2",
            new_mess_code="M2",
            effective_from=transfer_eff,
            reason="Hostel room change",
            actor=super_admin,
        )
        assert new_assignment.status == "PENDING_VERIFICATION"

        # 3. Clerk B verifies the new assignment
        auth_client(api_client, clerk_b_user, "HOSTEL_CLERK")
        resp = api_client.post(f"/api/v1/students/verifications/{new_assignment.assignment_id}/verify", {
            "notes": "Verified transfer",
        })
        assert resp.status_code == status.HTTP_200_OK

        # 4. Check old assignment is closed at effective_from of new assignment
        old_assignment.refresh_from_db()
        assert old_assignment.status == "ENDED"
        assert old_assignment.effective_to == transfer_eff

        # 5. Check new assignment is ACTIVE
        new_assignment.refresh_from_db()
        assert new_assignment.status == "ACTIVE"

        # 6. Check audit log
        audit = AuditLog.objects.filter(
            event_type="STUDENT_VERIFIED",
            entity_id=new_assignment.assignment_id,
        ).first()
        assert audit is not None
        assert audit.actor_user == clerk_b_user

    def test_bulk_verify_and_bulk_reject(
        self, api_client, clerk_user, super_admin, hostel_a, mess_a
    ):
        s1 = create_student(email="b1@college.edu", full_name="B1", roll_number="B1", hostel_code="H1", mess_code="M1", actor=super_admin)
        s2 = create_student(email="b2@college.edu", full_name="B2", roll_number="B2", hostel_code="H1", mess_code="M1", actor=super_admin)

        auth_client(api_client, clerk_user, "HOSTEL_CLERK")

        # Bulk verify
        resp = api_client.post("/api/v1/students/verifications/bulk-verify", {
            "assignment_ids": [s1["assignment_id"]],
            "notes": "Bulk approved",
        })
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["status"] == "SUCCESS"

        # Bulk reject
        resp_rej = api_client.post("/api/v1/students/verifications/bulk-reject", {
            "assignment_ids": [s2["assignment_id"]],
            "notes": "Details mismatch",
        })
        assert resp_rej.status_code == status.HTTP_200_OK
        rej_results = resp_rej.json()["results"]
        assert len(rej_results) == 1
        assert rej_results[0]["status"] == "SUCCESS"


# ==============================================================================
# 5. Clerk Staff Accounts Management
# ==============================================================================


@pytest.mark.django_db
class TestClerkStaffManagement:
    def test_create_and_reassign_clerk(self, api_client, super_admin, hostel_a, hostel_b):
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        # Create clerk
        r_create = api_client.post("/api/v1/admin/hostel-clerks", {
            "email": "new_clerk@college.edu",
            "full_name": "New Clerk",
            "hostel_code": "H1",
        })
        assert r_create.status_code == status.HTTP_201_CREATED
        clerk_id = r_create.json()["user_id"]

        # Reassign clerk to Hostel B
        r_reassign = api_client.post(f"/api/v1/admin/hostel-clerks/{clerk_id}/reassign", {
            "new_hostel_code": "H2",
        })
        assert r_reassign.status_code == status.HTTP_200_OK
        assert r_reassign.json()["new_hostel_code"] == "H2"

        # Verify old assignment deactivated, new active
        assignments = HostelClerkAssignment.objects.filter(user_id=clerk_id).order_by("assigned_at")
        assert assignments.count() == 2
        assert assignments.filter(is_active=True).count() == 1
        assert assignments.filter(is_active=True).first().hostel == hostel_b


# ==============================================================================
# 6. Import Pipeline Tests (Staged, Preview, Errors, Commit)
# ==============================================================================


@pytest.mark.django_db
class TestImportPipeline:
    def _generate_csv(self, rows: list[dict[str, str]]) -> io.BytesIO:
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        buf = io.BytesIO(output.getvalue().encode("utf-8"))
        buf.name = "students.csv"
        return buf

    def test_import_with_validation_errors(self, api_client, super_admin, hostel_a, mess_a):
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        rows = [
            # Valid row
            {
                "email": "valid1@college.edu",
                "full_name": "Valid One",
                "roll_number": "V001",
                "hostel_code": "H1",
                "mess_code": "M1",
                "department": "CS",
                "year_of_study": "1",
                "room_number": "101",
                "phone_number": "9876543210",
                "effective_from": "2026-08-01",
            },
            # Invalid email domain
            {
                "email": "invalid@gmail.com",
                "full_name": "Bad Domain",
                "roll_number": "V002",
                "hostel_code": "H1",
                "mess_code": "M1",
                "department": "CS",
                "year_of_study": "1",
                "room_number": "102",
                "phone_number": "9876543211",
                "effective_from": "2026-08-01",
            },
            # Unknown hostel
            {
                "email": "badhostel@college.edu",
                "full_name": "Bad Hostel",
                "roll_number": "V003",
                "hostel_code": "NONEXISTENT",
                "mess_code": "M1",
                "department": "CS",
                "year_of_study": "1",
                "room_number": "103",
                "phone_number": "9876543212",
                "effective_from": "2026-08-01",
            },
            # Forbidden pipe in roll number
            {
                "email": "pipe@college.edu",
                "full_name": "Pipe Roll",
                "roll_number": "V|004",
                "hostel_code": "H1",
                "mess_code": "M1",
                "department": "CS",
                "year_of_study": "1",
                "room_number": "104",
                "phone_number": "9876543213",
                "effective_from": "2026-08-01",
            },
            # In-file duplicate email
            {
                "email": "valid1@college.edu",
                "full_name": "Duplicate In File",
                "roll_number": "V005",
                "hostel_code": "H1",
                "mess_code": "M1",
                "department": "CS",
                "year_of_study": "1",
                "room_number": "105",
                "phone_number": "9876543214",
                "effective_from": "2026-08-01",
            },
        ]

        csv_file = self._generate_csv(rows)

        # 1. Upload & Stage
        resp = api_client.post(
            "/api/v1/students/imports",
            {"file": csv_file},
            format="multipart",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        batch_id = resp.json()["batch_id"]
        assert resp.json()["valid_rows"] == 1
        assert resp.json()["error_count"] == 4

        # 2. Preview
        r_prev = api_client.get(f"/api/v1/students/imports/{batch_id}/preview")
        assert r_prev.status_code == status.HTTP_200_OK
        assert r_prev.json()["valid_rows"] == 1
        assert len(r_prev.json()["errors"]) == 4

        # 3. Commit
        r_commit = api_client.post(f"/api/v1/students/imports/{batch_id}/commit")
        assert r_commit.status_code == status.HTTP_200_OK
        assert r_commit.json()["committed_rows"] == 1

        # 4. Verify created student in DB
        st = Student.objects.filter(roll_number="V001").first()
        assert st is not None
        assert st.user.email == "valid1@college.edu"


# ==============================================================================
# 7. Phase 4 Exit Gate Test
# ==============================================================================


@pytest.mark.django_db
class TestPhase4ExitGate:
    """
    Exit Gate:
    Through the API alone:
    1. Super Admin creates a hostel, mess and student
    2. Hostel's Clerk verifies the student
    3. The assignment is ACTIVE and visible to the correct scope selectors
    4. An import of a 2,000-row CSV with seeded errors previews, commits and reports exact counts.
    """

    def test_complete_phase4_exit_gate(
        self, api_client, super_admin, setup_roles
    ):
        # Step 1: Super Admin creates hostel and student (Mess created directly per Phase 4 spec)
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        # Create Hostel
        r_h = api_client.post("/api/v1/hostels", {
            "code": "EG-H1",
            "name": "Exit Gate Hostel",
            "address": "Main Campus",
        })
        assert r_h.status_code == status.HTTP_201_CREATED
        hostel_id = r_h.json()["hostel_id"]

        # Create Mess directly (Phase 5 will add Mess APIs)
        mess = Mess.objects.create(code="EG-M1", name="Exit Gate Mess", status="ACTIVE")

        # Create Hostel Clerk via API
        r_clerk = api_client.post("/api/v1/admin/hostel-clerks", {
            "email": "eg_clerk@college.edu",
            "full_name": "Exit Gate Clerk",
            "hostel_code": "EG-H1",
        })
        assert r_clerk.status_code == status.HTTP_201_CREATED
        clerk_user = User.objects.get(user_id=r_clerk.json()["user_id"])

        # Super Admin creates a student
        r_st = api_client.post("/api/v1/students", {
            "email": "eg_student@college.edu",
            "full_name": "Exit Gate Student",
            "roll_number": "EG-2026-001",
            "hostel_code": "EG-H1",
            "mess_code": "EG-M1",
            "department": "Computer Science",
            "year_of_study": 1,
        })
        assert r_st.status_code == status.HTTP_201_CREATED
        assignment_id = r_st.json()["assignment_id"]
        student_id = r_st.json()["student_id"]

        # Step 2: The hostel's Clerk verifies
        auth_client(api_client, clerk_user, "HOSTEL_CLERK")
        r_pending = api_client.get("/api/v1/students/verifications")
        assert r_pending.status_code == status.HTTP_200_OK
        assert r_pending.json()["count"] == 1

        r_verify = api_client.post(f"/api/v1/students/verifications/{assignment_id}/verify", {
            "notes": "Verified at Exit Gate checkpoint",
        })
        assert r_verify.status_code == status.HTTP_200_OK
        assert r_verify.json()["status"] == "ACTIVE"

        # Step 3: Assignment is ACTIVE and visible to the correct scope selectors
        assignment = StudentMessAssignment.objects.get(assignment_id=assignment_id)
        assert assignment.status == "ACTIVE"

        # Clerk sees student in scope
        r_scope = api_client.get("/api/v1/students")
        assert r_scope.status_code == status.HTTP_200_OK
        assert r_scope.json()["count"] == 1
        assert r_scope.json()["results"][0]["roll_number"] == "EG-2026-001"

        # Student accesses /students/me
        student_user = User.objects.get(email="eg_student@college.edu")
        auth_client(api_client, student_user, "STUDENT")
        r_me = api_client.get("/api/v1/students/me")
        assert r_me.status_code == status.HTTP_200_OK
        assert r_me.json()["roll_number"] == "EG-2026-001"
        assert r_me.json()["current_assignment"]["status"] == "ACTIVE"
        assert r_me.json()["current_assignment"]["mess"]["code"] == "EG-M1"

        # Step 4: Import of a 2,000-row CSV with seeded errors previews, commits and reports exact counts
        auth_client(api_client, super_admin, "SUPER_ADMIN")

        total_rows = 2000
        seeded_errors = 50  # Rows with bad domain
        expected_valid = total_rows - seeded_errors

        output = io.StringIO()
        fieldnames = ["email", "full_name", "roll_number", "hostel_code", "mess_code", "department", "year_of_study", "room_number", "phone_number", "effective_from"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for i in range(1, total_rows + 1):
            if i <= seeded_errors:
                domain = "yahoo.com"  # Seeded invalid email domain
            else:
                domain = "college.edu"

            writer.writerow({
                "email": f"eg_import_{i}@{domain}",
                "full_name": f"Imported Student {i}",
                "roll_number": f"IMP-2026-{i:05d}",
                "hostel_code": "EG-H1",
                "mess_code": "EG-M1",
                "department": "Engineering",
                "year_of_study": "1",
                "room_number": f"{100 + (i % 200)}",
                "phone_number": f"90000{i:05d}",
                "effective_from": "2026-09-01",
            })

        csv_file = io.BytesIO(output.getvalue().encode("utf-8"))
        csv_file.name = "batch_2000_seeded.csv"

        # Upload and preview
        r_upload = api_client.post("/api/v1/students/imports", {"file": csv_file}, format="multipart")
        assert r_upload.status_code == status.HTTP_201_CREATED
        batch_id = r_upload.json()["batch_id"]
        assert r_upload.json()["total_rows"] == total_rows
        assert r_upload.json()["valid_rows"] == expected_valid
        assert r_upload.json()["error_count"] == seeded_errors

        # Preview
        r_preview = api_client.get(f"/api/v1/students/imports/{batch_id}/preview")
        assert r_preview.status_code == status.HTTP_200_OK
        assert r_preview.json()["valid_rows"] == expected_valid
        assert r_preview.json()["error_count"] == seeded_errors

        # Commit
        r_commit = api_client.post(f"/api/v1/students/imports/{batch_id}/commit")
        assert r_commit.status_code == status.HTTP_200_OK
        assert r_commit.json()["status"] == "COMMITTED"
        assert r_commit.json()["committed_rows"] == expected_valid
        assert r_commit.json()["error_count"] == seeded_errors

        # Check total students in DB
        imported_in_db = Student.objects.filter(roll_number__startswith="IMP-2026-").count()
        assert imported_in_db == expected_valid
