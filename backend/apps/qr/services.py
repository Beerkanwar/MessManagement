"""
QR domain services [SPEC SDD §19-21, DBDD §13, ImplementationGuide Phase 6].
Enforces:
- 32-byte cryptographically secure secret generation [REC size].
- Authenticated AES-256-GCM encryption at rest.
- Single decryption points: plain secret exists in memory only when fetched by authorized student or manager sync.
- Idempotent secret provisioning on student creation and backfill.
- Secret rotation with version monotonicity, mess change cursor advance, and audit trail without secrets.
"""
import os
import secrets
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.hostel.models import Student, StudentMessAssignment
from apps.identity.models import StudentSecret, User
from apps.qr.crypto import SecretEncryptionService
from apps.sync.models import ChangeCursor


from apps.sync.services import advance_change_cursor


def generate_student_secret_bytes() -> bytes:
    """
    Generates 32 random bytes from operating system's secure CSPRNG [REC size, SPEC SDD §20].
    """
    return secrets.token_bytes(32)


@transaction.atomic
def provision_student_secret(student: Student, actor: User | None = None) -> StudentSecret:
    """
    Provisions an ACTIVE secret for the student if one does not already exist [SPEC SDD §19].
    Idempotent: returns existing ACTIVE secret if already provisioned.
    Stored only as ciphertext in StudentSecret.
    """
    existing = StudentSecret.objects.filter(student=student, status="ACTIVE").first()
    if existing:
        return existing

    plain_secret = generate_student_secret_bytes()
    encrypted_secret = SecretEncryptionService.encrypt_secret(plain_secret)
    now = clock.now()

    student_secret = StudentSecret.objects.create(
        student=student,
        secret_version=1,
        encrypted_secret=encrypted_secret,
        status="ACTIVE",
        effective_from=now,
    )

    # Advance change cursor for student's active mess if assigned
    active_assignment = StudentMessAssignment.objects.filter(
        student=student, status="ACTIVE"
    ).select_related("mess").first()
    if active_assignment and active_assignment.mess_id:
        advance_change_cursor(f"mess:{active_assignment.mess_id}:secrets")

    return student_secret


def get_active_student_secret(student: Student) -> tuple[StudentSecret, bytes]:
    """
    Single decryption point [ImplementationGuide Phase 6 requirement 2].
    Decrypts the student's active secret key into memory ONLY for authorized callers.
    Returns (StudentSecret, plain_secret_bytes).
    Plain secret MUST NEVER be logged, serialized into audit rows, or cached outside secure memory.
    """
    student_secret = StudentSecret.objects.filter(student=student, status="ACTIVE").first()
    if not student_secret:
        # Self-healing: provision if missing
        student_secret = provision_student_secret(student)

    plain_bytes = SecretEncryptionService.decrypt_secret(bytes(student_secret.encrypted_secret))
    return student_secret, plain_bytes


@transaction.atomic
def rotate_student_secret(
    *,
    student_id: int | None = None,
    hostel_id: int | None = None,
    mess_id: int | None = None,
    reason: str,
    actor: User,
    correlation_id: str = "",
) -> list[dict[str, Any]]:
    """
    Rotates secrets for one student, a hostel, or a mess [SPEC SDD §21, DEC-13, ImplementationGuide Phase 6].
    In one database transaction:
    - Retires the ACTIVE version (sets status=RETIRED, effective_to=now, rotated_by, rotated_at).
    - Creates version n+1 ACTIVE with newly generated random 32-byte secret.
    - Advances change cursor 'mess:<id>:secrets' for affected mess(es).
    - Records SECRET_ROTATED audit event with student id and version numbers only (NEVER secret material).
    """
    if not reason or not reason.strip():
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="A reason is required to rotate student secrets.",
        )

    # Resolve target students
    if student_id is not None:
        students = list(Student.objects.filter(student_id=student_id, status="ACTIVE").select_for_update())
        if not students:
            raise ValidationError(
                code="NOT_FOUND",
                message=f"Active student with ID {student_id} not found.",
            )
    elif mess_id is not None:
        # Students actively assigned to this mess
        student_ids = StudentMessAssignment.objects.filter(
            mess_id=mess_id, status="ACTIVE"
        ).values_list("student_id", flat=True)
        students = list(
            Student.objects.filter(student_id__in=student_ids, status="ACTIVE").select_for_update()
        )
        if not students:
            raise ValidationError(
                code="NOT_FOUND",
                message=f"No active students found assigned to mess ID {mess_id}.",
            )
    elif hostel_id is not None:
        students = list(
            Student.objects.filter(hostel_id=hostel_id, status="ACTIVE").select_for_update()
        )
        if not students:
            raise ValidationError(
                code="NOT_FOUND",
                message=f"No active students found in hostel ID {hostel_id}.",
            )
    else:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Must provide at least one target: student_id, mess_id, or hostel_id.",
        )

    now = clock.now()
    results = []
    affected_mess_ids: set[int] = set()

    for student in students:
        # Find active secret
        current = StudentSecret.objects.filter(student=student, status="ACTIVE").first()
        if current:
            old_version = current.secret_version
            new_version = old_version + 1
            current.status = "RETIRED"
            current.effective_to = now
            current.rotated_by = actor
            current.rotated_at = now
            current.save(update_fields=["status", "effective_to", "rotated_by", "rotated_at", "updated_at"])
        else:
            old_version = None
            new_version = 1

        # Generate new secret and encrypt
        plain_bytes = generate_student_secret_bytes()
        encrypted = SecretEncryptionService.encrypt_secret(plain_bytes)

        StudentSecret.objects.create(
            student=student,
            secret_version=new_version,
            encrypted_secret=encrypted,
            status="ACTIVE",
            effective_from=now,
        )

        # Audit SECRET_ROTATED: Note that dict keys must avoid prohibited sensitive substrings (e.g. 'secret', 'key')
        record_audit_event(
            event_type="SECRET_ROTATED",
            actor_user=actor,
            entity_type="Student",
            entity_id=student.student_id,
            reason=reason.strip(),
            old_values={"version": old_version} if old_version else {},
            new_values={"version": new_version},
            correlation_id=correlation_id,
        )

        # Check student's active mess for change cursor
        active_assignment = StudentMessAssignment.objects.filter(
            student=student, status="ACTIVE"
        ).first()
        if active_assignment and active_assignment.mess_id:
            affected_mess_ids.add(active_assignment.mess_id)

        results.append({
            "student_id": student.student_id,
            "roll_number": student.roll_number,
            "old_version": old_version,
            "new_version": new_version,
        })

    # If mess_id was explicitly targeted, ensure it is included in cursor advances
    if mess_id is not None:
        affected_mess_ids.add(mess_id)

    # Advance change cursor for all affected messes
    for m_id in affected_mess_ids:
        advance_change_cursor(f"mess:{m_id}:secrets")

    return results

