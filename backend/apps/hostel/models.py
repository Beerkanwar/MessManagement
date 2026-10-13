"""
Hostel, Student, and assignment models matching SPEC DBDD §4.
Student-mess assignments carry both hostel_id and mess_id [CONFLICT-10].
ExclusionConstraint on assignment date ranges added via RunSQL migration.
"""
from django.conf import settings
from django.db import models
from apps.core.models import VersionedModel, InsertOnlyModel


class Hostel(VersionedModel):
    """Hostel master data [SPEC DBDD §4]. Deactivated, never deleted [DBDD §17]."""
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    hostel_id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True, help_text="Short hostel code")
    name = models.CharField(max_length=255, help_text="Hostel display name")
    address = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        db_table = "hostel_hostel"
        verbose_name = "Hostel"
        verbose_name_plural = "Hostels"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "INACTIVE"]),
                name="hostel_hostel_status_check",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Student(VersionedModel):
    """
    Student profile [SPEC DBDD §4].
    One-to-one with identity.User; unique roll_number.
    """
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    student_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="student_profile"
    )
    roll_number = models.CharField(max_length=50, unique=True)
    hostel = models.ForeignKey(Hostel, on_delete=models.PROTECT, related_name="students")
    department = models.CharField(max_length=255, blank=True, default="")
    year_of_study = models.IntegerField(null=True, blank=True)
    room_number = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        db_table = "hostel_student"
        verbose_name = "Student"
        verbose_name_plural = "Students"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "INACTIVE"]),
                name="hostel_student_status_check",
            ),
        ]
        indexes = [
            models.Index(fields=["roll_number"], name="idx_hostel_student_roll"),
        ]

    def __str__(self):
        return self.roll_number


class StudentMessAssignment(VersionedModel):
    """
    Student-to-mess assignment with date ranges [SPEC DBDD §4, CONFLICT-10].
    Assignment carries both hostel_id and mess_id (one mess may serve several hostels).
    ExclusionConstraint on (student, daterange) WHERE status=ACTIVE added via RunSQL.
    """
    STATUS_CHOICES = [
        ("PENDING_VERIFICATION", "Pending Verification"),
        ("ACTIVE", "Active"),
        ("ENDED", "Ended"),
        ("REJECTED", "Rejected"),
    ]

    assignment_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="mess_assignments")
    mess = models.ForeignKey("mess.Mess", on_delete=models.PROTECT, related_name="student_assignments")
    hostel = models.ForeignKey(Hostel, on_delete=models.PROTECT, related_name="student_assignments")
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="PENDING_VERIFICATION"
    )
    effective_from = models.DateField(help_text="Start date of assignment (IST calendar)")
    effective_to = models.DateField(
        null=True, blank=True,
        help_text="End date of assignment (IST calendar, null=open-ended)"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="verified_assignments"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "hostel_student_mess_assignment"
        verbose_name = "Student Mess Assignment"
        verbose_name_plural = "Student Mess Assignments"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    "PENDING_VERIFICATION", "ACTIVE", "ENDED", "REJECTED"
                ]),
                name="hostel_assignment_status_check",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "status"], name="idx_hostel_assign_stud_stat"),
            models.Index(fields=["mess", "status"], name="idx_hostel_assign_mess_status"),
        ]

    def __str__(self):
        return f"Student {self.student_id} -> Mess {self.mess_id} ({self.status})"


class HostelClerkAssignment(VersionedModel):
    """
    Hostel clerk assignment [SPEC DBDD §4].
    Partial unique: one active clerk assignment per user.
    """
    clerk_assignment_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="clerk_assignments"
    )
    hostel = models.ForeignKey(Hostel, on_delete=models.PROTECT, related_name="clerk_assignments")
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(help_text="When the clerk was assigned")
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "hostel_clerk_assignment"
        verbose_name = "Hostel Clerk Assignment"
        verbose_name_plural = "Hostel Clerk Assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="uq_hostel_clerk_one_active_per_user",
            ),
        ]

    def __str__(self):
        return f"Clerk {self.user_id} -> Hostel {self.hostel_id}"


class StudentVerification(InsertOnlyModel):
    """
    Record of student assignment verification [SPEC DBDD §4].
    Insert-only: once verified/rejected, the record is immutable.
    """
    VERIFICATION_STATUS_CHOICES = [
        ("VERIFIED", "Verified"),
        ("REJECTED", "Rejected"),
    ]

    verification_id = models.AutoField(primary_key=True)
    assignment = models.ForeignKey(
        StudentMessAssignment, on_delete=models.PROTECT, related_name="verifications"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="student_verifications"
    )
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_STATUS_CHOICES)
    verification_notes = models.TextField(blank=True, default="")
    verified_at = models.DateTimeField()

    class Meta:
        db_table = "hostel_student_verification"
        verbose_name = "Student Verification"
        verbose_name_plural = "Student Verifications"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(verification_status__in=["VERIFIED", "REJECTED"]),
                name="hostel_verification_status_check",
            ),
        ]


class StudentImportBatch(VersionedModel):
    """Batch student import tracking [SPEC DBDD §4]."""
    STATUS_CHOICES = [
        ("STAGED", "Staged"),
        ("VALIDATED", "Validated"),
        ("COMMITTED", "Committed"),
        ("FAILED", "Failed"),
        ("CANCELLED", "Cancelled"),
    ]

    batch_id = models.AutoField(primary_key=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="import_batches"
    )
    file_name = models.CharField(max_length=255)
    total_rows = models.IntegerField(default=0)
    successful_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="STAGED")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "hostel_student_import_batch"
        verbose_name = "Student Import Batch"
        verbose_name_plural = "Student Import Batches"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    "STAGED", "VALIDATED", "COMMITTED", "FAILED", "CANCELLED"
                ]),
                name="hostel_import_batch_status_check",
            ),
        ]


class StudentImportError(models.Model):
    """Individual import error within a batch [SPEC DBDD §4]. Keeps raw row JSON."""
    error_id = models.AutoField(primary_key=True)
    batch = models.ForeignKey(StudentImportBatch, on_delete=models.PROTECT, related_name="errors")
    row_number = models.IntegerField()
    roll_number = models.CharField(max_length=50, blank=True, default="")
    error_message = models.TextField()
    raw_row_data = models.JSONField(help_text="Raw row content as JSON for debugging")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "hostel_student_import_error"
        verbose_name = "Student Import Error"
        verbose_name_plural = "Student Import Errors"
