"""
Hostel, student, import, verification, transfer, and clerk serializers — Phase 4.
"""
from rest_framework import serializers
from apps.hostel.models import (
    Hostel,
    HostelClerkAssignment,
    Student,
    StudentImportBatch,
    StudentImportError,
    StudentMessAssignment,
    StudentVerification,
)


# ---------------------------------------------------------------------------
# Hostel
# ---------------------------------------------------------------------------


class HostelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hostel
        fields = ["hostel_id", "code", "name", "address", "status", "version", "created_at", "updated_at"]
        read_only_fields = ["hostel_id", "created_at", "updated_at"]


class HostelCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20, help_text="Short unique hostel code")
    name = serializers.CharField(max_length=255, help_text="Hostel display name")
    address = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class HostelUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    address = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    version = serializers.IntegerField(help_text="Optimistic concurrency version")


class HostelDeactivateSerializer(serializers.Serializer):
    version = serializers.IntegerField(help_text="Optimistic concurrency version")


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------


class StudentAssignmentSerializer(serializers.ModelSerializer):
    mess_code = serializers.CharField(source="mess.code", read_only=True)
    mess_name = serializers.CharField(source="mess.name", read_only=True)
    hostel_code = serializers.CharField(source="hostel.code", read_only=True)
    hostel_name = serializers.CharField(source="hostel.name", read_only=True)

    class Meta:
        model = StudentMessAssignment
        fields = [
            "assignment_id", "status", "effective_from", "effective_to",
            "mess_id", "mess_code", "mess_name",
            "hostel_id", "hostel_code", "hostel_name",
            "verified_by_id", "verified_at", "rejection_reason",
            "version", "created_at", "updated_at",
        ]


class StudentListSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    hostel_code = serializers.CharField(source="hostel.code", read_only=True)
    hostel_name = serializers.CharField(source="hostel.name", read_only=True)

    class Meta:
        model = Student
        fields = [
            "student_id", "roll_number", "email", "full_name",
            "hostel_id", "hostel_code", "hostel_name",
            "department", "year_of_study", "room_number",
            "status", "version", "created_at", "updated_at",
        ]


class StudentDetailSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    hostel_code = serializers.CharField(source="hostel.code", read_only=True)
    hostel_name = serializers.CharField(source="hostel.name", read_only=True)
    user_id = serializers.IntegerField(source="user.user_id", read_only=True)
    current_assignment = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "student_id", "user_id", "roll_number", "email", "full_name",
            "phone_number", "hostel_id", "hostel_code", "hostel_name",
            "department", "year_of_study", "room_number",
            "status", "version", "created_at", "updated_at",
            "current_assignment",
        ]

    def get_current_assignment(self, obj):
        from apps.core.clock import clock
        from django.db.models import Q

        today = clock.today()
        assignment = StudentMessAssignment.objects.filter(
            student=obj,
            status="ACTIVE",
            effective_from__lte=today,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=today)
        ).select_related("mess", "hostel").first()

        if assignment:
            return StudentAssignmentSerializer(assignment).data
        return None


class StudentCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Institutional college email")
    full_name = serializers.CharField(max_length=150)
    roll_number = serializers.CharField(max_length=50)
    hostel_code = serializers.CharField(max_length=20, help_text="Active hostel code")
    mess_code = serializers.CharField(max_length=20, help_text="Active mess code")
    department = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    year_of_study = serializers.IntegerField(required=False, allow_null=True, default=None)
    room_number = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    effective_from = serializers.DateField(required=False, allow_null=True, default=None)


class StudentUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, required=False)
    department = serializers.CharField(max_length=255, required=False, allow_blank=True)
    year_of_study = serializers.IntegerField(required=False, allow_null=True)
    room_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=["ACTIVE", "INACTIVE"], required=False)
    version = serializers.IntegerField(help_text="Optimistic concurrency version")


class StudentMeSerializer(serializers.ModelSerializer):
    """Read-only profile for the authenticated student."""
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    hostel_code = serializers.CharField(source="hostel.code", read_only=True)
    hostel_name = serializers.CharField(source="hostel.name", read_only=True)
    current_assignment = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "student_id", "roll_number", "email", "full_name",
            "phone_number", "hostel_id", "hostel_code", "hostel_name",
            "department", "year_of_study", "room_number", "status",
            "current_assignment",
        ]

    def get_current_assignment(self, obj):
        from apps.core.clock import clock
        from django.db.models import Q

        today = clock.today()
        assignment = StudentMessAssignment.objects.filter(
            student=obj,
            status="ACTIVE",
            effective_from__lte=today,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=today)
        ).select_related("mess", "hostel").first()

        if assignment:
            return StudentAssignmentSerializer(assignment).data
        return None


# ---------------------------------------------------------------------------
# Import Pipeline
# ---------------------------------------------------------------------------


class ImportBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentImportBatch
        fields = [
            "batch_id", "file_name", "total_rows", "successful_rows",
            "failed_rows", "status", "started_at", "completed_at",
            "created_at", "updated_at",
        ]


class ImportErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentImportError
        fields = ["error_id", "row_number", "roll_number", "error_message", "raw_row_data"]


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class PendingVerificationSerializer(serializers.ModelSerializer):
    """Serializer for pending verification assignments as seen by the Clerk."""
    roll_number = serializers.CharField(source="student.roll_number", read_only=True)
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    student_email = serializers.CharField(source="student.user.email", read_only=True)
    mess_code = serializers.CharField(source="mess.code", read_only=True)
    mess_name = serializers.CharField(source="mess.name", read_only=True)
    hostel_code = serializers.CharField(source="hostel.code", read_only=True)

    class Meta:
        model = StudentMessAssignment
        fields = [
            "assignment_id", "student_id", "roll_number", "student_name", "student_email",
            "hostel_id", "hostel_code", "mess_id", "mess_code", "mess_name",
            "effective_from", "status", "created_at",
        ]


class VerifyAssignmentSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class RejectAssignmentSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class BulkVerifySerializer(serializers.Serializer):
    assignment_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=200,
        help_text="List of assignment IDs to verify",
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class BulkRejectSerializer(serializers.Serializer):
    assignment_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=200,
        help_text="List of assignment IDs to reject",
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------


class TransferStudentSerializer(serializers.Serializer):
    new_hostel_code = serializers.CharField(max_length=20, help_text="Target hostel code")
    new_mess_code = serializers.CharField(max_length=20, help_text="Target mess code")
    effective_from = serializers.DateField(help_text="Transfer effective date")
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# Clerk Account Management
# ---------------------------------------------------------------------------


class ClerkCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Clerk's institutional email")
    full_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    hostel_code = serializers.CharField(max_length=20, help_text="Hostel to assign the clerk to")


class ClerkReassignSerializer(serializers.Serializer):
    new_hostel_code = serializers.CharField(max_length=20, help_text="New hostel code to assign")


class ClerkListSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    phone_number = serializers.CharField()
    hostel = serializers.DictField()
    assignment_id = serializers.IntegerField()
    is_active = serializers.BooleanField()
    assigned_at = serializers.DateTimeField()
