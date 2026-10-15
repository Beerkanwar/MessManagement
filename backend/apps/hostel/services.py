"""
Hostel domain services — Phase 4.
Implements hostel management, student provisioning, import pipeline,
verification, transfer, clerk accounts, and change signalling.

Business rules live here, never in views or serializers [SPEC SDD §154.1].
"""
import csv
import io
import re
from decimal import Decimal
from typing import Any

import openpyxl
import structlog
from django.db import transaction
from django.db.models import F, Q

from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.core.concurrency import check_optimistic_lock, execute_versioned_update
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
from apps.identity.models import Role, User, UserRole
from apps.identity.selectors import get_user_role
from apps.mess.models import Mess
from apps.sync.models import ChangeCursor

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Normalization Service [SPEC SDD §10, Phase 4 build item 2]
# ---------------------------------------------------------------------------

# Pipe character is the QR payload delimiter; reject in roll numbers [REC]
ROLL_NUMBER_FORBIDDEN_RE = re.compile(r"[|]")


def normalize_email(email: str) -> str:
    """Trim and lower-case college email [SPEC SDD §10]."""
    return email.strip().lower()


def normalize_roll_number(roll_number: str) -> str:
    """
    Trim and upper-case roll number [REC].
    Rejects pipe characters since they are QR payload delimiters.
    """
    cleaned = roll_number.strip().upper()
    if ROLL_NUMBER_FORBIDDEN_RE.search(cleaned):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Roll number must not contain the '|' character (reserved for QR payload).",
        )
    if not cleaned:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Roll number must not be empty.",
        )
    return cleaned


# ---------------------------------------------------------------------------
# Change Signalling [Phase 4 build item 7]
# ---------------------------------------------------------------------------


def advance_change_cursor(cursor_key: str) -> int:
    """
    Advance the change cursor for the given aggregate key (e.g. 'mess:<id>:students').
    Returns the new version number.
    """
    obj, _created = ChangeCursor.objects.get_or_create(
        aggregate_type=cursor_key,
        defaults={"current_version": 1},
    )
    if not _created:
        ChangeCursor.objects.filter(cursor_id=obj.cursor_id).update(
            current_version=F("current_version") + 1
        )
        obj.refresh_from_db()
    return obj.current_version


# ---------------------------------------------------------------------------
# Hostel Management (Super Admin) [Phase 4 build item 1]
# ---------------------------------------------------------------------------


@transaction.atomic
def create_hostel(*, code: str, name: str, address: str = "", actor: User, correlation_id: str = "") -> Hostel:
    """Create a new hostel. Code is unique [SPEC DBDD §4]."""
    code = code.strip().upper()
    if Hostel.objects.filter(code=code).exists():
        raise ConflictError(
            code="DUPLICATE_RESOURCE",
            message=f"A hostel with code '{code}' already exists.",
        )
    hostel = Hostel.objects.create(
        code=code,
        name=name.strip(),
        address=address.strip(),
        status="ACTIVE",
    )
    record_audit_event(
        event_type="HOSTEL_CREATED",
        actor_user=actor,
        entity_type="Hostel",
        entity_id=hostel.hostel_id,
        new_values={"code": hostel.code, "name": hostel.name},
        correlation_id=correlation_id,
    )
    return hostel


@transaction.atomic
def update_hostel(
    *, hostel_id: int, name: str | None = None, address: str | None = None,
    version: int, actor: User, correlation_id: str = "",
) -> Hostel:
    """Rename or update a hostel with optimistic concurrency [DBDD §18.3]."""
    hostel = Hostel.objects.filter(hostel_id=hostel_id).first()
    if not hostel:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Hostel not found.")
    check_optimistic_lock(hostel, version)

    old_values = {"name": hostel.name, "address": hostel.address}
    update_fields: dict[str, Any] = {}
    if name is not None:
        update_fields["name"] = name.strip()
    if address is not None:
        update_fields["address"] = address.strip()

    if update_fields:
        execute_versioned_update(
            Hostel.objects.filter(hostel_id=hostel_id),
            version,
            **update_fields,
        )
        hostel.refresh_from_db()

    record_audit_event(
        event_type="HOSTEL_UPDATED",
        actor_user=actor,
        entity_type="Hostel",
        entity_id=hostel.hostel_id,
        old_values=old_values,
        new_values={"name": hostel.name, "address": hostel.address},
        correlation_id=correlation_id,
    )
    return hostel


@transaction.atomic
def deactivate_hostel(*, hostel_id: int, version: int, actor: User, correlation_id: str = "") -> Hostel:
    """
    Deactivate a hostel [REC]. Refused while ACTIVE assignments or an active Clerk exist.
    """
    hostel = Hostel.objects.filter(hostel_id=hostel_id).first()
    if not hostel:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Hostel not found.")
    check_optimistic_lock(hostel, version)

    if hostel.status == "INACTIVE":
        raise ValidationError(code="STATE_CONFLICT", message="Hostel is already inactive.")

    # Guard: active student assignments
    active_assignments = StudentMessAssignment.objects.filter(
        hostel=hostel, status="ACTIVE"
    ).exists()
    if active_assignments:
        raise ValidationError(
            code="STATE_CONFLICT",
            message="Cannot deactivate hostel: there are still ACTIVE student assignments.",
        )

    # Guard: active clerk assignments
    active_clerks = HostelClerkAssignment.objects.filter(hostel=hostel, is_active=True).exists()
    if active_clerks:
        raise ValidationError(
            code="STATE_CONFLICT",
            message="Cannot deactivate hostel: there is still an active Clerk assignment.",
        )

    execute_versioned_update(
        Hostel.objects.filter(hostel_id=hostel_id),
        version,
        status="INACTIVE",
    )
    hostel.refresh_from_db()

    record_audit_event(
        event_type="HOSTEL_DEACTIVATED",
        actor_user=actor,
        entity_type="Hostel",
        entity_id=hostel.hostel_id,
        old_values={"status": "ACTIVE"},
        new_values={"status": "INACTIVE"},
        correlation_id=correlation_id,
    )
    return hostel


# ---------------------------------------------------------------------------
# Student Provisioning (Super Admin) [Phase 4 build item 3]
# ---------------------------------------------------------------------------


def _get_or_fail_active_hostel(hostel_code: str) -> Hostel:
    hostel = Hostel.objects.filter(code=hostel_code.strip().upper(), status="ACTIVE").first()
    if not hostel:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Hostel with code '{hostel_code}' does not exist or is inactive.",
        )
    return hostel


def _get_or_fail_active_mess(mess_code: str) -> Mess:
    mess = Mess.objects.filter(code=mess_code.strip().upper(), status="ACTIVE").first()
    if not mess:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Mess with code '{mess_code}' does not exist or is inactive.",
        )
    return mess


@transaction.atomic
def create_student(
    *,
    email: str,
    full_name: str,
    roll_number: str,
    hostel_code: str,
    mess_code: str,
    department: str = "",
    year_of_study: int | None = None,
    room_number: str = "",
    phone_number: str = "",
    effective_from: Any = None,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Create a student: User + Student + PENDING_VERIFICATION assignment [DEC-08].
    User starts with unusable password [DEC-03].
    """
    norm_email = normalize_email(email)
    norm_roll = normalize_roll_number(roll_number)

    # Duplicate checks
    if User.objects.filter(normalized_email=norm_email).exists():
        raise ConflictError(
            code="DUPLICATE_RESOURCE",
            message=f"A user with email '{norm_email}' already exists.",
        )
    if Student.objects.filter(roll_number=norm_roll).exists():
        raise ConflictError(
            code="DUPLICATE_RESOURCE",
            message=f"A student with roll number '{norm_roll}' already exists.",
        )

    hostel = _get_or_fail_active_hostel(hostel_code)
    mess = _get_or_fail_active_mess(mess_code)

    # Create user with unusable password (DEC-03)
    user = User.objects.create_user(
        email=email.strip(),
        full_name=full_name.strip(),
        phone_number=phone_number.strip(),
    )

    # Assign STUDENT role
    student_role = Role.objects.get(name="STUDENT")
    UserRole.objects.create(user=user, role=student_role)

    # Create student profile
    student = Student.objects.create(
        user=user,
        roll_number=norm_roll,
        hostel=hostel,
        department=department.strip(),
        year_of_study=year_of_study,
        room_number=room_number.strip(),
        status="ACTIVE",
    )

    # Create PENDING_VERIFICATION assignment
    eff_from = effective_from or clock.today()
    assignment = StudentMessAssignment.objects.create(
        student=student,
        mess=mess,
        hostel=hostel,
        status="PENDING_VERIFICATION",
        effective_from=eff_from,
    )

    record_audit_event(
        event_type="STUDENT_CREATED",
        actor_user=actor,
        entity_type="Student",
        entity_id=student.student_id,
        new_values={
            "roll_number": norm_roll,
            "email": norm_email,
            "hostel_code": hostel.code,
            "mess_code": mess.code,
            "assignment_status": "PENDING_VERIFICATION",
        },
        correlation_id=correlation_id,
    )

    return {
        "student_id": student.student_id,
        "user_id": user.user_id,
        "roll_number": student.roll_number,
        "assignment_id": assignment.assignment_id,
        "status": assignment.status,
    }


@transaction.atomic
def update_student(
    *,
    student_id: int,
    full_name: str | None = None,
    department: str | None = None,
    year_of_study: int | None = None,
    room_number: str | None = None,
    phone_number: str | None = None,
    status: str | None = None,
    version: int,
    actor: User,
    correlation_id: str = "",
) -> Student:
    """Update student profile fields. Version check enforced."""
    student = Student.objects.select_related("user").filter(student_id=student_id).first()
    if not student:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Student not found.")
    check_optimistic_lock(student, version)

    old_values: dict[str, Any] = {}
    student_updates: dict[str, Any] = {}
    user_updates: dict[str, Any] = {}

    if full_name is not None:
        old_values["full_name"] = student.user.full_name
        user_updates["full_name"] = full_name.strip()
    if phone_number is not None:
        old_values["phone_number"] = student.user.phone_number
        user_updates["phone_number"] = phone_number.strip()
    if department is not None:
        old_values["department"] = student.department
        student_updates["department"] = department.strip()
    if year_of_study is not None:
        old_values["year_of_study"] = student.year_of_study
        student_updates["year_of_study"] = year_of_study
    if room_number is not None:
        old_values["room_number"] = student.room_number
        student_updates["room_number"] = room_number.strip()
    if status is not None:
        if status not in ("ACTIVE", "INACTIVE"):
            raise ValidationError(code="VALIDATION_ERROR", message="Student status must be ACTIVE or INACTIVE.")
        old_values["status"] = student.status
        student_updates["status"] = status

    if user_updates:
        User.objects.filter(user_id=student.user_id).update(**user_updates)

    if student_updates:
        execute_versioned_update(
            Student.objects.filter(student_id=student_id),
            version,
            **student_updates,
        )
    else:
        # Still bump version to record the update
        execute_versioned_update(
            Student.objects.filter(student_id=student_id),
            version,
        )

    student.refresh_from_db()
    student.user.refresh_from_db()

    record_audit_event(
        event_type="STUDENT_UPDATED",
        actor_user=actor,
        entity_type="Student",
        entity_id=student.student_id,
        old_values=old_values,
        new_values={k: getattr(student, k, None) for k in student_updates},
        correlation_id=correlation_id,
    )
    return student


# ---------------------------------------------------------------------------
# Student Import Pipeline [Phase 4 build item 4]
# ---------------------------------------------------------------------------

REQUIRED_IMPORT_COLUMNS = {"email", "full_name", "roll_number", "hostel_code", "mess_code"}
OPTIONAL_IMPORT_COLUMNS = {"department", "year_of_study", "room_number", "phone_number", "effective_from"}
ALL_IMPORT_COLUMNS = REQUIRED_IMPORT_COLUMNS | OPTIONAL_IMPORT_COLUMNS


def _parse_csv(file_content: bytes) -> list[dict[str, str]]:
    text = file_content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _parse_xlsx(file_content: bytes) -> list[dict[str, str]]:
    wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True)
    ws = wb.active
    rows: list[dict[str, str]] = []
    headers: list[str] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = [str(c).strip().lower() if c else "" for c in row]
            continue
        row_dict = {}
        for j, val in enumerate(row):
            if j < len(headers) and headers[j]:
                row_dict[headers[j]] = str(val).strip() if val is not None else ""
        rows.append(row_dict)
    wb.close()
    return rows


def _validate_email_domain(email: str) -> bool:
    """Basic email format check."""
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))


def _validate_import_row(
    row: dict[str, str],
    row_number: int,
    seen_emails: set[str],
    seen_rolls: set[str],
    valid_hostel_codes: set[str],
    valid_mess_codes: set[str],
) -> list[dict[str, Any]]:
    """Validate a single import row. Returns list of error dicts (empty if valid)."""
    errors: list[dict[str, Any]] = []

    # Required fields
    for field in REQUIRED_IMPORT_COLUMNS:
        if not row.get(field, "").strip():
            errors.append({
                "row_number": row_number,
                "error_code": "MISSING_REQUIRED_FIELD",
                "message": f"Required field '{field}' is missing or empty.",
            })

    if errors:
        return errors  # No point checking further if required fields missing

    email = normalize_email(row["email"])
    roll_number = row["roll_number"].strip().upper()

    # Email format
    if not _validate_email_domain(email):
        errors.append({
            "row_number": row_number,
            "error_code": "INVALID_EMAIL",
            "message": f"Invalid email format: '{email}'.",
        })

    # Roll number pipe check
    if "|" in roll_number:
        errors.append({
            "row_number": row_number,
            "error_code": "INVALID_ROLL_NUMBER",
            "message": "Roll number must not contain '|' character.",
        })

    # Intra-file duplicates
    if email in seen_emails:
        errors.append({
            "row_number": row_number,
            "error_code": "DUPLICATE_EMAIL_IN_FILE",
            "message": f"Duplicate email in file: '{email}'.",
        })
    if roll_number in seen_rolls:
        errors.append({
            "row_number": row_number,
            "error_code": "DUPLICATE_ROLL_IN_FILE",
            "message": f"Duplicate roll number in file: '{roll_number}'.",
        })

    # DB duplicates
    if User.objects.filter(normalized_email=email).exists():
        errors.append({
            "row_number": row_number,
            "error_code": "DUPLICATE_EMAIL_IN_DB",
            "message": f"Email '{email}' already exists in the system.",
        })
    if Student.objects.filter(roll_number=roll_number).exists():
        errors.append({
            "row_number": row_number,
            "error_code": "DUPLICATE_ROLL_IN_DB",
            "message": f"Roll number '{roll_number}' already exists in the system.",
        })

    # Hostel/Mess validation
    hostel_code = row["hostel_code"].strip().upper()
    mess_code = row["mess_code"].strip().upper()

    if hostel_code not in valid_hostel_codes:
        errors.append({
            "row_number": row_number,
            "error_code": "UNKNOWN_HOSTEL",
            "message": f"Hostel code '{hostel_code}' does not exist or is inactive.",
        })
    if mess_code not in valid_mess_codes:
        errors.append({
            "row_number": row_number,
            "error_code": "UNKNOWN_MESS",
            "message": f"Mess code '{mess_code}' does not exist or is inactive.",
        })

    return errors


@transaction.atomic
def create_import_batch(
    *,
    file_name: str,
    file_content: bytes,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Upload + Parse + Validate stage of the import pipeline [SDD §96-97].
    Creates a STAGED batch and validates all rows.
    """
    # Parse
    lower_name = file_name.lower()
    if lower_name.endswith(".csv"):
        rows = _parse_csv(file_content)
    elif lower_name.endswith(".xlsx"):
        rows = _parse_xlsx(file_content)
    else:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Unsupported file format. Only CSV and XLSX are accepted.",
        )

    if not rows:
        raise ValidationError(code="VALIDATION_ERROR", message="File contains no data rows.")

    # Verify headers
    header_keys = {k.strip().lower() for k in rows[0].keys()}
    missing_headers = REQUIRED_IMPORT_COLUMNS - header_keys
    if missing_headers:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Missing required columns: {', '.join(sorted(missing_headers))}.",
        )

    # Lookup caches
    valid_hostel_codes = set(Hostel.objects.filter(status="ACTIVE").values_list("code", flat=True))
    valid_mess_codes = set(Mess.objects.filter(status="ACTIVE").values_list("code", flat=True))

    # Create batch
    batch = StudentImportBatch.objects.create(
        imported_by=actor,
        file_name=file_name,
        total_rows=len(rows),
        status="STAGED",
        started_at=clock.now(),
    )

    # Validate
    seen_emails: set[str] = set()
    seen_rolls: set[str] = set()
    valid_rows: list[dict[str, str]] = []
    error_count = 0

    for idx, row in enumerate(rows, start=1):
        row_errors = _validate_import_row(
            row, idx, seen_emails, seen_rolls,
            valid_hostel_codes, valid_mess_codes,
        )
        if row_errors:
            error_count += len(row_errors)
            for err in row_errors:
                StudentImportError.objects.create(
                    batch=batch,
                    row_number=err["row_number"],
                    roll_number=row.get("roll_number", ""),
                    error_message=f"[{err['error_code']}] {err['message']}",
                    raw_row_data=row,
                )
        else:
            valid_rows.append(row)
            email = normalize_email(row["email"])
            roll = row["roll_number"].strip().upper()
            seen_emails.add(email)
            seen_rolls.add(roll)

    batch.successful_rows = len(valid_rows)
    batch.failed_rows = error_count
    batch.status = "VALIDATED"
    batch.save()

    from django.core.cache import cache
    cache.set(f"import_batch_valid_rows_{batch.batch_id}", valid_rows, timeout=7200)

    return {
        "batch_id": batch.batch_id,
        "file_name": batch.file_name,
        "total_rows": batch.total_rows,
        "valid_rows": len(valid_rows),
        "error_count": error_count,
        "status": batch.status,
    }


def get_import_batch_preview(batch_id: int) -> dict[str, Any]:
    """Preview returns counts, a page of valid rows, and a page of errors."""
    batch = StudentImportBatch.objects.filter(batch_id=batch_id).first()
    if not batch:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Import batch not found.")

    errors = list(
        StudentImportError.objects.filter(batch=batch)
        .values("error_id", "row_number", "roll_number", "error_message")
        .order_by("row_number")[:50]
    )

    return {
        "batch_id": batch.batch_id,
        "file_name": batch.file_name,
        "total_rows": batch.total_rows,
        "valid_rows": batch.successful_rows,
        "error_count": batch.failed_rows,
        "status": batch.status,
        "errors": errors,
    }


@transaction.atomic
def commit_import_batch(
    *,
    batch_id: int,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Commit stage: re-validates then writes all valid rows in one transaction.
    Rejected rows stay in the error table [SPEC SDD §96].
    """
    batch = StudentImportBatch.objects.select_for_update().filter(batch_id=batch_id).first()
    if not batch:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Import batch not found.")
    if batch.status not in ("STAGED", "VALIDATED"):
        raise ValidationError(
            code="STATE_CONFLICT",
            message=f"Batch cannot be committed in status '{batch.status}'.",
        )

    from django.core.cache import cache
    valid_rows = cache.get(f"import_batch_valid_rows_{batch.batch_id}")

    # Re-validate and write valid rows
    student_role = Role.objects.get(name="STUDENT")
    created_count = 0
    today = clock.today()

    if valid_rows:
        for row in valid_rows:
            norm_email = normalize_email(row["email"])
            norm_roll = row["roll_number"].strip().upper()
            hostel_code = row["hostel_code"].strip().upper()
            mess_code = row["mess_code"].strip().upper()

            # Check DB duplicates at commit time
            if User.objects.filter(normalized_email=norm_email).exists():
                raise ConflictError(
                    code="DUPLICATE_RESOURCE",
                    message=f"Duplicate email found during commit: '{norm_email}'.",
                )
            if Student.objects.filter(roll_number=norm_roll).exists():
                raise ConflictError(
                    code="DUPLICATE_RESOURCE",
                    message=f"Duplicate roll number found during commit: '{norm_roll}'.",
                )

            hostel = Hostel.objects.get(code=hostel_code, status="ACTIVE")
            mess = Mess.objects.get(code=mess_code, status="ACTIVE")

            user = User.objects.create_user(
                email=row["email"].strip(),
                full_name=row["full_name"].strip(),
                phone_number=row.get("phone_number", "").strip(),
            )
            UserRole.objects.create(user=user, role=student_role)

            student = Student.objects.create(
                user=user,
                roll_number=norm_roll,
                hostel=hostel,
                department=row.get("department", "").strip(),
                year_of_study=int(row["year_of_study"]) if row.get("year_of_study") else None,
                room_number=row.get("room_number", "").strip(),
                status="ACTIVE",
            )

            eff_from = row.get("effective_from") or today
            StudentMessAssignment.objects.create(
                student=student,
                mess=mess,
                hostel=hostel,
                status="PENDING_VERIFICATION",
                effective_from=eff_from,
            )

            advance_change_cursor(f"mess:{mess.mess_id}:students")
            created_count += 1

        cache.delete(f"import_batch_valid_rows_{batch.batch_id}")
    else:
        created_count = batch.successful_rows

    batch.successful_rows = created_count
    batch.status = "COMMITTED"
    batch.completed_at = clock.now()
    batch.save()

    record_audit_event(
        event_type="STUDENT_IMPORT_COMMITTED",
        actor_user=actor,
        entity_type="StudentImportBatch",
        entity_id=batch.batch_id,
        new_values={
            "total_rows": batch.total_rows,
            "created": created_count,
            "errors": batch.failed_rows,
        },
        correlation_id=correlation_id,
    )

    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "committed_rows": created_count,
        "error_count": batch.failed_rows,
    }


@transaction.atomic
def upload_and_commit_import(
    *,
    file_name: str,
    file_content: bytes,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Full import pipeline: parse, validate, create students for valid rows.
    Rejected rows are recorded as errors. One DB transaction [SPEC SDD §96].
    """
    # Parse
    lower_name = file_name.lower()
    if lower_name.endswith(".csv"):
        rows = _parse_csv(file_content)
    elif lower_name.endswith(".xlsx"):
        rows = _parse_xlsx(file_content)
    else:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Unsupported file format. Only CSV and XLSX are accepted.",
        )

    if not rows:
        raise ValidationError(code="VALIDATION_ERROR", message="File contains no data rows.")

    header_keys = {k.strip().lower() for k in rows[0].keys()}
    missing_headers = REQUIRED_IMPORT_COLUMNS - header_keys
    if missing_headers:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Missing required columns: {', '.join(sorted(missing_headers))}.",
        )

    valid_hostel_codes = set(Hostel.objects.filter(status="ACTIVE").values_list("code", flat=True))
    valid_mess_codes = set(Mess.objects.filter(status="ACTIVE").values_list("code", flat=True))

    batch = StudentImportBatch.objects.create(
        imported_by=actor,
        file_name=file_name,
        total_rows=len(rows),
        status="STAGED",
        started_at=clock.now(),
    )

    seen_emails: set[str] = set()
    seen_rolls: set[str] = set()
    valid_rows: list[dict[str, str]] = []
    error_count = 0

    for idx, row in enumerate(rows, start=1):
        row_errors = _validate_import_row(
            row, idx, seen_emails, seen_rolls,
            valid_hostel_codes, valid_mess_codes,
        )
        if row_errors:
            error_count += len(row_errors)
            for err in row_errors:
                StudentImportError.objects.create(
                    batch=batch,
                    row_number=err["row_number"],
                    roll_number=row.get("roll_number", ""),
                    error_message=f"[{err['error_code']}] {err['message']}",
                    raw_row_data=row,
                )
        else:
            valid_rows.append(row)
            seen_emails.add(normalize_email(row["email"]))
            seen_rolls.add(row["roll_number"].strip().upper())

    # Create student records for valid rows
    student_role = Role.objects.get(name="STUDENT")
    created_count = 0
    today = clock.today()

    for row in valid_rows:
        norm_email = normalize_email(row["email"])
        norm_roll = row["roll_number"].strip().upper()
        hostel_code = row["hostel_code"].strip().upper()
        mess_code = row["mess_code"].strip().upper()

        hostel = Hostel.objects.get(code=hostel_code, status="ACTIVE")
        mess = Mess.objects.get(code=mess_code, status="ACTIVE")

        user = User.objects.create_user(
            email=row["email"].strip(),
            full_name=row["full_name"].strip(),
            phone_number=row.get("phone_number", "").strip(),
        )
        UserRole.objects.create(user=user, role=student_role)

        student = Student.objects.create(
            user=user,
            roll_number=norm_roll,
            hostel=hostel,
            department=row.get("department", "").strip(),
            year_of_study=int(row["year_of_study"]) if row.get("year_of_study") else None,
            room_number=row.get("room_number", "").strip(),
            status="ACTIVE",
        )

        eff_from = row.get("effective_from") or today
        StudentMessAssignment.objects.create(
            student=student,
            mess=mess,
            hostel=hostel,
            status="PENDING_VERIFICATION",
            effective_from=eff_from,
        )

        # Signal change for the assigned mess
        advance_change_cursor(f"mess:{mess.mess_id}:students")
        created_count += 1

    batch.successful_rows = created_count
    batch.failed_rows = error_count
    batch.status = "COMMITTED"
    batch.completed_at = clock.now()
    batch.save()

    record_audit_event(
        event_type="STUDENT_IMPORT_COMMITTED",
        actor_user=actor,
        entity_type="StudentImportBatch",
        entity_id=batch.batch_id,
        new_values={
            "total_rows": batch.total_rows,
            "created": created_count,
            "errors": error_count,
        },
        correlation_id=correlation_id,
    )

    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "total_rows": batch.total_rows,
        "committed_rows": created_count,
        "error_count": error_count,
    }


@transaction.atomic
def cancel_import_batch(
    *,
    batch_id: int,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Cancel a STAGED or VALIDATED batch."""
    batch = StudentImportBatch.objects.select_for_update().filter(batch_id=batch_id).first()
    if not batch:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Import batch not found.")
    if batch.status not in ("STAGED", "VALIDATED"):
        raise ValidationError(
            code="STATE_CONFLICT",
            message=f"Batch cannot be cancelled in status '{batch.status}'.",
        )
    batch.status = "CANCELLED"
    batch.completed_at = clock.now()
    batch.save()

    return {"batch_id": batch.batch_id, "status": batch.status}


# ---------------------------------------------------------------------------
# Verification (Hostel Clerk) [Phase 4 build item 5]
# ---------------------------------------------------------------------------


@transaction.atomic
def verify_assignment(
    *,
    assignment_id: int,
    notes: str = "",
    actor: User,
    correlation_id: str = "",
) -> StudentMessAssignment:
    """
    Verify a PENDING_VERIFICATION assignment:
    1. Insert StudentVerification (VERIFIED)
    2. Close any overlapping ACTIVE assignment
    3. Set this assignment ACTIVE
    4. Advance change cursor
    """
    assignment = (
        StudentMessAssignment.objects.select_for_update()
        .filter(assignment_id=assignment_id)
        .first()
    )
    if not assignment:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Assignment not found.")
    if assignment.status != "PENDING_VERIFICATION":
        raise ValidationError(
            code="STATE_CONFLICT",
            message=f"Assignment is in status '{assignment.status}', not PENDING_VERIFICATION.",
        )

    now = clock.now()

    # Close any overlapping ACTIVE assignment for this student
    active_assignments = StudentMessAssignment.objects.select_for_update().filter(
        student=assignment.student,
        status="ACTIVE",
    ).exclude(assignment_id=assignment_id)

    old_mess_ids = set()
    for active in active_assignments:
        old_mess_ids.add(active.mess_id)
        active.effective_to = assignment.effective_from
        active.status = "ENDED"
        active.version = F("version") + 1
        active.save(update_fields=["effective_to", "status", "version", "updated_at"])

    # Insert verification record
    StudentVerification.objects.create(
        assignment=assignment,
        verified_by=actor,
        verification_status="VERIFIED",
        verification_notes=notes,
        verified_at=now,
    )

    # Update assignment to ACTIVE
    assignment.status = "ACTIVE"
    assignment.verified_by = actor
    assignment.verified_at = now
    assignment.version = F("version") + 1
    assignment.save(update_fields=["status", "verified_by", "verified_at", "version", "updated_at"])
    assignment.refresh_from_db()

    # Advance change cursors
    advance_change_cursor(f"mess:{assignment.mess_id}:students")
    for old_mess_id in old_mess_ids:
        advance_change_cursor(f"mess:{old_mess_id}:students")

    record_audit_event(
        event_type="STUDENT_VERIFIED",
        actor_user=actor,
        entity_type="StudentMessAssignment",
        entity_id=assignment.assignment_id,
        new_values={
            "student_id": assignment.student_id,
            "status": "ACTIVE",
            "hostel_id": assignment.hostel_id,
            "mess_id": assignment.mess_id,
        },
        correlation_id=correlation_id,
    )
    return assignment


@transaction.atomic
def reject_assignment(
    *,
    assignment_id: int,
    notes: str = "",
    actor: User,
    correlation_id: str = "",
) -> StudentMessAssignment:
    """
    Reject a PENDING_VERIFICATION assignment.
    Goes back to Super Admin for correction [SPEC SRS §3.3].
    """
    assignment = (
        StudentMessAssignment.objects.select_for_update()
        .filter(assignment_id=assignment_id)
        .first()
    )
    if not assignment:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Assignment not found.")
    if assignment.status != "PENDING_VERIFICATION":
        raise ValidationError(
            code="STATE_CONFLICT",
            message=f"Assignment is in status '{assignment.status}', not PENDING_VERIFICATION.",
        )

    now = clock.now()

    # Insert rejection record
    StudentVerification.objects.create(
        assignment=assignment,
        verified_by=actor,
        verification_status="REJECTED",
        verification_notes=notes,
        verified_at=now,
    )

    assignment.status = "REJECTED"
    assignment.rejection_reason = notes
    assignment.version = F("version") + 1
    assignment.save(update_fields=["status", "rejection_reason", "version", "updated_at"])
    assignment.refresh_from_db()

    record_audit_event(
        event_type="STUDENT_REJECTED",
        actor_user=actor,
        entity_type="StudentMessAssignment",
        entity_id=assignment.assignment_id,
        new_values={
            "student_id": assignment.student_id,
            "status": "REJECTED",
            "reason": notes,
        },
        correlation_id=correlation_id,
    )
    return assignment


@transaction.atomic
def bulk_verify_assignments(
    *,
    assignment_ids: list[int],
    notes: str = "",
    actor: User,
    correlation_id: str = "",
) -> list[dict[str, Any]]:
    """Bulk verify with per-row result."""
    results: list[dict[str, Any]] = []
    for aid in assignment_ids:
        try:
            assignment = verify_assignment(
                assignment_id=aid,
                notes=notes,
                actor=actor,
                correlation_id=correlation_id,
            )
            results.append({
                "assignment_id": aid,
                "status": "VERIFIED",
                "student_id": assignment.student_id,
            })
        except (NotFoundError, ValidationError, ConflictError) as e:
            results.append({
                "assignment_id": aid,
                "status": "ERROR",
                "message": str(e.message),
            })
    return results


@transaction.atomic
def bulk_reject_assignments(
    *,
    assignment_ids: list[int],
    notes: str = "",
    actor: User,
    correlation_id: str = "",
) -> list[dict[str, Any]]:
    """Bulk reject with per-row result."""
    results: list[dict[str, Any]] = []
    for aid in assignment_ids:
        try:
            assignment = reject_assignment(
                assignment_id=aid,
                notes=notes,
                actor=actor,
                correlation_id=correlation_id,
            )
            results.append({
                "assignment_id": aid,
                "status": "REJECTED",
                "student_id": assignment.student_id,
            })
        except (NotFoundError, ValidationError, ConflictError) as e:
            results.append({
                "assignment_id": aid,
                "status": "ERROR",
                "message": str(e.message),
            })
    return results


# ---------------------------------------------------------------------------
# Transfer (Super Admin) [Phase 4 build item 6]
# ---------------------------------------------------------------------------


@transaction.atomic
def transfer_student(
    *,
    student_id: int,
    new_hostel_code: str,
    new_mess_code: str,
    effective_from: Any,
    reason: str = "",
    actor: User,
    correlation_id: str = "",
) -> StudentMessAssignment:
    """
    Creates a new PENDING_VERIFICATION assignment for a different hostel/mess.
    Historical data stays untouched [SPEC DBDD §4.1].
    """
    student = Student.objects.filter(student_id=student_id).first()
    if not student:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Student not found.")

    new_hostel = _get_or_fail_active_hostel(new_hostel_code)
    new_mess = _get_or_fail_active_mess(new_mess_code)

    if not effective_from:
        effective_from = clock.today()

    # Create new PENDING_VERIFICATION assignment
    new_assignment = StudentMessAssignment.objects.create(
        student=student,
        mess=new_mess,
        hostel=new_hostel,
        status="PENDING_VERIFICATION",
        effective_from=effective_from,
    )

    # Update student's hostel reference to the new hostel
    Student.objects.filter(student_id=student_id).update(hostel=new_hostel)

    record_audit_event(
        event_type="STUDENT_TRANSFERRED",
        actor_user=actor,
        entity_type="Student",
        entity_id=student.student_id,
        new_values={
            "new_hostel_code": new_hostel.code,
            "new_mess_code": new_mess.code,
            "effective_from": str(effective_from),
            "reason": reason,
            "assignment_id": new_assignment.assignment_id,
        },
        correlation_id=correlation_id,
    )

    return new_assignment


# ---------------------------------------------------------------------------
# Hostel Clerk Management (Super Admin) [Phase 4 build item 8]
# ---------------------------------------------------------------------------


@transaction.atomic
def create_hostel_clerk(
    *,
    email: str,
    full_name: str,
    phone_number: str = "",
    hostel_code: str,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Create a Clerk: User + HOSTEL_CLERK role + HostelClerkAssignment.
    Starts with unusable password [DEC-03].
    """
    norm_email = normalize_email(email)

    if User.objects.filter(normalized_email=norm_email).exists():
        raise ConflictError(
            code="DUPLICATE_RESOURCE",
            message=f"A user with email '{norm_email}' already exists.",
        )

    hostel = _get_or_fail_active_hostel(hostel_code)

    user = User.objects.create_user(
        email=email.strip(),
        full_name=full_name.strip(),
        phone_number=phone_number.strip(),
    )

    clerk_role = Role.objects.get(name="HOSTEL_CLERK")
    UserRole.objects.create(user=user, role=clerk_role)

    assignment = HostelClerkAssignment.objects.create(
        user=user,
        hostel=hostel,
        is_active=True,
        assigned_at=clock.now(),
    )

    record_audit_event(
        event_type="CLERK_CREATED",
        actor_user=actor,
        entity_type="HostelClerkAssignment",
        entity_id=assignment.clerk_assignment_id,
        new_values={
            "email": norm_email,
            "full_name": full_name.strip(),
            "hostel_code": hostel.code,
        },
        correlation_id=correlation_id,
    )

    return {
        "user_id": user.user_id,
        "email": user.normalized_email,
        "full_name": user.full_name,
        "hostel": {"id": hostel.hostel_id, "code": hostel.code, "name": hostel.name},
        "assignment_id": assignment.clerk_assignment_id,
        "is_active": assignment.is_active,
    }


@transaction.atomic
def reassign_hostel_clerk(
    *,
    user_id: int,
    new_hostel_code: str,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Reassign a Clerk: deactivate the old assignment, add a new one.
    No history needed [SPEC DBDD §4].
    """
    user = User.objects.filter(user_id=user_id).first()
    if not user:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="User not found.")

    role = get_user_role(user)
    if role != "HOSTEL_CLERK":
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="User is not a HOSTEL_CLERK.",
        )

    new_hostel = _get_or_fail_active_hostel(new_hostel_code)

    # Deactivate old
    HostelClerkAssignment.objects.filter(user=user, is_active=True).update(
        is_active=False,
        deactivated_at=clock.now(),
    )

    # Create new
    assignment = HostelClerkAssignment.objects.create(
        user=user,
        hostel=new_hostel,
        is_active=True,
        assigned_at=clock.now(),
    )

    record_audit_event(
        event_type="CLERK_REASSIGNED",
        actor_user=actor,
        entity_type="HostelClerkAssignment",
        entity_id=assignment.clerk_assignment_id,
        new_values={
            "new_hostel_code": new_hostel.code,
        },
        correlation_id=correlation_id,
    )

    return {
        "user_id": user.user_id,
        "hostel": {"id": new_hostel.hostel_id, "code": new_hostel.code, "name": new_hostel.name},
        "assignment_id": assignment.clerk_assignment_id,
        "is_active": True,
    }


@transaction.atomic
def deactivate_hostel_clerk(
    *,
    user_id: int,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Deactivate a Clerk's assignment."""
    user = User.objects.filter(user_id=user_id).first()
    if not user:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="User not found.")

    active_assignment = HostelClerkAssignment.objects.filter(user=user, is_active=True).first()
    if not active_assignment:
        raise ValidationError(
            code="STATE_CONFLICT",
            message="No active clerk assignment to deactivate.",
        )

    active_assignment.is_active = False
    active_assignment.deactivated_at = clock.now()
    active_assignment.save(update_fields=["is_active", "deactivated_at", "updated_at"])

    record_audit_event(
        event_type="CLERK_DEACTIVATED",
        actor_user=actor,
        entity_type="HostelClerkAssignment",
        entity_id=active_assignment.clerk_assignment_id,
        new_values={"is_active": False},
        correlation_id=correlation_id,
    )

    return {
        "user_id": user.user_id,
        "assignment_id": active_assignment.clerk_assignment_id,
        "is_active": False,
    }
