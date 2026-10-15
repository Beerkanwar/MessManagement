"""
Views for hostel management, student provisioning, import pipeline,
verification, transfer, and clerk account management — Phase 4.

Business rules are in services.py; views only handle HTTP concerns.
"""
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardPageNumberPagination
from apps.core.permissions import IsHostelClerk, IsStudent, IsSuperAdmin
from apps.hostel.models import (
    Hostel,
    HostelClerkAssignment,
    Student,
    StudentImportBatch,
    StudentImportError,
    StudentMessAssignment,
)
from apps.hostel.serializers import (
    BulkRejectSerializer,
    BulkVerifySerializer,
    ClerkCreateSerializer,
    ClerkReassignSerializer,
    HostelCreateSerializer,
    HostelDeactivateSerializer,
    HostelSerializer,
    HostelUpdateSerializer,
    ImportBatchSerializer,
    ImportErrorSerializer,
    PendingVerificationSerializer,
    RejectAssignmentSerializer,
    StudentCreateSerializer,
    StudentDetailSerializer,
    StudentListSerializer,
    StudentMeSerializer,
    StudentUpdateSerializer,
    TransferStudentSerializer,
    VerifyAssignmentSerializer,
)
from apps.hostel.services import (
    bulk_reject_assignments,
    bulk_verify_assignments,
    cancel_import_batch,
    create_hostel,
    create_hostel_clerk,
    create_import_batch,
    create_student,
    deactivate_hostel,
    deactivate_hostel_clerk,
    get_import_batch_preview,
    reassign_hostel_clerk,
    reject_assignment,
    transfer_student,
    update_hostel,
    update_student,
    upload_and_commit_import,
    verify_assignment,
)
from apps.identity.selectors import get_clerk_hostel, get_user_role, get_visible_students_queryset


# ==============================================================================
# Hostel Management (Super Admin write; authenticated read)
# ==============================================================================


@extend_schema(
    summary="List Hostels",
    description="Lists all hostels. Super Admin sees all; Clerks see their own hostel.",
    tags=["hostels"],
    responses={200: HostelSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hostel_list_view(request):
    role = get_user_role(request.user)
    if role == "HOSTEL_CLERK":
        hostel = get_clerk_hostel(request.user)
        qs = Hostel.objects.filter(hostel_id=hostel.hostel_id) if hostel else Hostel.objects.none()
    elif role == "SUPER_ADMIN" or getattr(request.user, "is_superuser", False):
        qs = Hostel.objects.all()
    else:
        # Students and Managers see nothing from this endpoint
        qs = Hostel.objects.none()

    # Optional status filter
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter.upper())

    qs = qs.order_by("code")
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = HostelSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    summary="Create Hostel",
    description="Creates a new hostel. Super Admin only.",
    tags=["hostels"],
    request=HostelCreateSerializer,
    responses={201: HostelSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def hostel_create_view(request):
    serializer = HostelCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    hostel = create_hostel(
        code=serializer.validated_data["code"],
        name=serializer.validated_data["name"],
        address=serializer.validated_data.get("address", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(HostelSerializer(hostel).data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Get Hostel Detail",
    description="Returns a single hostel by ID.",
    tags=["hostels"],
    responses={200: HostelSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hostel_detail_view(request, hostel_id: int):
    hostel = Hostel.objects.filter(hostel_id=hostel_id).first()
    if not hostel:
        return Response(
            {"code": "OBJECT_NOT_FOUND", "message": "Hostel not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(HostelSerializer(hostel).data)


@extend_schema(
    summary="Update Hostel",
    description="Rename or update hostel. Version check enforced. Super Admin only.",
    tags=["hostels"],
    request=HostelUpdateSerializer,
    responses={200: HostelSerializer},
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def hostel_update_view(request, hostel_id: int):
    serializer = HostelUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    hostel = update_hostel(
        hostel_id=hostel_id,
        name=serializer.validated_data.get("name"),
        address=serializer.validated_data.get("address"),
        version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(HostelSerializer(hostel).data)


@extend_schema(
    summary="Deactivate Hostel",
    description="Deactivate a hostel. Refused if ACTIVE assignments or Clerk exist. Super Admin only.",
    tags=["hostels"],
    request=HostelDeactivateSerializer,
    responses={200: HostelSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def hostel_deactivate_view(request, hostel_id: int):
    serializer = HostelDeactivateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    hostel = deactivate_hostel(
        hostel_id=hostel_id,
        version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(HostelSerializer(hostel).data)


# ==============================================================================
# Student Management (Super Admin create/update; Clerk read in scope)
# ==============================================================================


@extend_schema(
    summary="List Students",
    description="Lists students scoped by authorization. Filterable by status, hostel, roll_number.",
    tags=["students"],
    parameters=[
        OpenApiParameter(name="status", type=str, required=False),
        OpenApiParameter(name="hostel_id", type=int, required=False),
        OpenApiParameter(name="roll_number", type=str, required=False),
        OpenApiParameter(name="search", type=str, required=False, description="Search by name, email, or roll"),
    ],
    responses={200: StudentListSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_list_view(request):
    qs = get_visible_students_queryset(request.user)
    qs = qs.select_related("user", "hostel")

    # Filters
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter.upper())

    hostel_id = request.query_params.get("hostel_id")
    if hostel_id:
        qs = qs.filter(hostel_id=hostel_id)

    roll_number = request.query_params.get("roll_number")
    if roll_number:
        qs = qs.filter(roll_number__icontains=roll_number.strip().upper())

    search = request.query_params.get("search")
    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(roll_number__icontains=search) |
            Q(user__full_name__icontains=search) |
            Q(user__email__icontains=search)
        )

    qs = qs.order_by("roll_number")
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = StudentListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    summary="Get Student Detail",
    description="Returns a student's full profile with current assignment. Scoped by authorization.",
    tags=["students"],
    responses={200: StudentDetailSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_detail_view(request, student_id: int):
    from apps.identity.selectors import get_student_in_scope
    student = get_student_in_scope(request.user, student_id)
    student = Student.objects.select_related("user", "hostel").get(student_id=student.student_id)
    return Response(StudentDetailSerializer(student).data)


@extend_schema(
    summary="Create Student",
    description="Creates a new student with PENDING_VERIFICATION assignment. Super Admin only.",
    tags=["students"],
    request=StudentCreateSerializer,
    responses={201: OpenApiResponse(description="Student created")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def student_create_view(request):
    serializer = StudentCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = create_student(
        email=serializer.validated_data["email"],
        full_name=serializer.validated_data["full_name"],
        roll_number=serializer.validated_data["roll_number"],
        hostel_code=serializer.validated_data["hostel_code"],
        mess_code=serializer.validated_data["mess_code"],
        department=serializer.validated_data.get("department", ""),
        year_of_study=serializer.validated_data.get("year_of_study"),
        room_number=serializer.validated_data.get("room_number", ""),
        phone_number=serializer.validated_data.get("phone_number", ""),
        effective_from=serializer.validated_data.get("effective_from"),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Update Student",
    description="Updates student profile fields. Super Admin only. Version check enforced.",
    tags=["students"],
    request=StudentUpdateSerializer,
    responses={200: StudentDetailSerializer},
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def student_update_view(request, student_id: int):
    serializer = StudentUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    student = update_student(
        student_id=student_id,
        full_name=serializer.validated_data.get("full_name"),
        department=serializer.validated_data.get("department"),
        year_of_study=serializer.validated_data.get("year_of_study"),
        room_number=serializer.validated_data.get("room_number"),
        phone_number=serializer.validated_data.get("phone_number"),
        status=serializer.validated_data.get("status"),
        version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    student = Student.objects.select_related("user", "hostel").get(student_id=student.student_id)
    return Response(StudentDetailSerializer(student).data)


@extend_schema(
    summary="My Profile (Student)",
    description="Returns the authenticated student's own profile and current assignment.",
    tags=["students"],
    responses={200: StudentMeSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStudent])
def student_me_view(request):
    student = Student.objects.select_related("user", "hostel").filter(user=request.user).first()
    if not student:
        return Response(
            {"code": "OBJECT_NOT_FOUND", "message": "Student profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(StudentMeSerializer(student).data)


# ==============================================================================
# Import Pipeline (Super Admin)
# ==============================================================================


@extend_schema(
    summary="Upload and Validate Import File",
    description="Uploads a CSV/XLSX file, parses and validates all rows. Creates a VALIDATED batch.",
    tags=["students"],
    request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
    responses={201: ImportBatchSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
@parser_classes([MultiPartParser])
def import_upload_view(request):
    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response(
            {"code": "VALIDATION_ERROR", "message": "No file uploaded."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    commit_flag = (
        request.query_params.get("commit", "").lower() in ("true", "1")
        or request.data.get("commit") in (True, "true", "1")
    )
    if commit_flag:
        result = upload_and_commit_import(
            file_name=file_obj.name,
            file_content=file_obj.read(),
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )
        return Response(result, status=status.HTTP_201_CREATED)

    result = create_import_batch(
        file_name=file_obj.name,
        file_content=file_obj.read(),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Get Import Batch Detail",
    description="Returns batch status and counts.",
    tags=["students"],
    responses={200: ImportBatchSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def import_detail_view(request, batch_id: int):
    batch = StudentImportBatch.objects.filter(batch_id=batch_id).first()
    if not batch:
        return Response(
            {"code": "OBJECT_NOT_FOUND", "message": "Import batch not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(ImportBatchSerializer(batch).data)


@extend_schema(
    summary="Get Import Batch Errors",
    description="Returns validation errors for the batch.",
    tags=["students"],
    responses={200: ImportErrorSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def import_errors_view(request, batch_id: int):
    batch = StudentImportBatch.objects.filter(batch_id=batch_id).first()
    if not batch:
        return Response(
            {"code": "OBJECT_NOT_FOUND", "message": "Import batch not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    errors = StudentImportError.objects.filter(batch=batch).order_by("row_number")
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(errors, request)
    serializer = ImportErrorSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    summary="Preview Import Batch",
    description="Returns counts, valid rows, and a page of errors.",
    tags=["students"],
    responses={200: OpenApiResponse(description="Batch preview")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def import_preview_view(request, batch_id: int):
    preview = get_import_batch_preview(batch_id)
    return Response(preview)


@extend_schema(
    summary="Commit Import Batch (Upload + Commit)",
    description="Uploads a CSV/XLSX, validates, and commits valid rows in one transaction.",
    tags=["students"],
    request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
    responses={200: OpenApiResponse(description="Commit result")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
@parser_classes([MultiPartParser])
def import_commit_view(request, batch_id: int = None):
    file_obj = request.FILES.get("file")
    if not file_obj:
        # If no file, try to commit existing batch
        if batch_id is not None:
            from apps.hostel.services import commit_import_batch
            result = commit_import_batch(
                batch_id=batch_id,
                actor=request.user,
                correlation_id=getattr(request, "correlation_id", ""),
            )
            return Response(result)
        return Response(
            {"code": "VALIDATION_ERROR", "message": "No file uploaded."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = upload_and_commit_import(
        file_name=file_obj.name,
        file_content=file_obj.read(),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Cancel Import Batch",
    description="Cancels a STAGED or VALIDATED import batch.",
    tags=["students"],
    responses={200: OpenApiResponse(description="Batch cancelled")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def import_cancel_view(request, batch_id: int):
    result = cancel_import_batch(
        batch_id=batch_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result)


# ==============================================================================
# Verification (Hostel Clerk — own hostel only)
# ==============================================================================


@extend_schema(
    summary="List Pending Verifications",
    description="Lists PENDING_VERIFICATION assignments for the Clerk's hostel.",
    tags=["students"],
    responses={200: PendingVerificationSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsHostelClerk])
def verification_list_view(request):
    role = get_user_role(request.user)
    if role == "SUPER_ADMIN" or getattr(request.user, "is_superuser", False):
        qs = StudentMessAssignment.objects.filter(status="PENDING_VERIFICATION")
    else:
        hostel = get_clerk_hostel(request.user)
        if not hostel:
            return Response(
                {"code": "STATE_CONFLICT", "message": "No active hostel assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = StudentMessAssignment.objects.filter(
            hostel=hostel,
            status="PENDING_VERIFICATION",
        )

    qs = qs.select_related("student__user", "mess", "hostel").order_by("created_at")
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = PendingVerificationSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    summary="Verify Assignment",
    description="Verifies a PENDING_VERIFICATION assignment. Clerk (own hostel) only.",
    tags=["students"],
    request=VerifyAssignmentSerializer,
    responses={200: OpenApiResponse(description="Assignment verified")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsHostelClerk])
def verification_verify_view(request, assignment_id: int):
    # Scope check: clerk can only verify their hostel's assignments
    role = get_user_role(request.user)
    if role not in ("SUPER_ADMIN",) and not getattr(request.user, "is_superuser", False):
        hostel = get_clerk_hostel(request.user)
        assignment = StudentMessAssignment.objects.filter(
            assignment_id=assignment_id
        ).first()
        if not assignment or (hostel and assignment.hostel_id != hostel.hostel_id):
            return Response(
                {"code": "OBJECT_NOT_FOUND", "message": "Assignment not found in your hostel."},
                status=status.HTTP_404_NOT_FOUND,
            )

    serializer = VerifyAssignmentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    assignment = verify_assignment(
        assignment_id=assignment_id,
        notes=serializer.validated_data.get("notes", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response({
        "assignment_id": assignment.assignment_id,
        "status": assignment.status,
        "student_id": assignment.student_id,
        "message": "Assignment verified successfully.",
    })


@extend_schema(
    summary="Reject Assignment",
    description="Rejects a PENDING_VERIFICATION assignment. Goes back to Super Admin.",
    tags=["students"],
    request=RejectAssignmentSerializer,
    responses={200: OpenApiResponse(description="Assignment rejected")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsHostelClerk])
def verification_reject_view(request, assignment_id: int):
    # Scope check
    role = get_user_role(request.user)
    if role not in ("SUPER_ADMIN",) and not getattr(request.user, "is_superuser", False):
        hostel = get_clerk_hostel(request.user)
        assignment = StudentMessAssignment.objects.filter(
            assignment_id=assignment_id
        ).first()
        if not assignment or (hostel and assignment.hostel_id != hostel.hostel_id):
            return Response(
                {"code": "OBJECT_NOT_FOUND", "message": "Assignment not found in your hostel."},
                status=status.HTTP_404_NOT_FOUND,
            )

    serializer = RejectAssignmentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    assignment = reject_assignment(
        assignment_id=assignment_id,
        notes=serializer.validated_data.get("notes", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response({
        "assignment_id": assignment.assignment_id,
        "status": assignment.status,
        "student_id": assignment.student_id,
        "message": "Assignment rejected.",
    })


@extend_schema(
    summary="Bulk Verify Assignments",
    description="Verifies multiple assignments with per-row result.",
    tags=["students"],
    request=BulkVerifySerializer,
    responses={200: OpenApiResponse(description="Bulk verification results")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsHostelClerk])
def verification_bulk_verify_view(request):
    serializer = BulkVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    results = bulk_verify_assignments(
        assignment_ids=serializer.validated_data["assignment_ids"],
        notes=serializer.validated_data.get("notes", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response({"results": results})


@extend_schema(
    summary="Bulk Reject Assignments",
    description="Rejects multiple assignments with per-row result.",
    tags=["students"],
    request=BulkRejectSerializer,
    responses={200: OpenApiResponse(description="Bulk rejection results")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsHostelClerk])
def verification_bulk_reject_view(request):
    serializer = BulkRejectSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    results = bulk_reject_assignments(
        assignment_ids=serializer.validated_data["assignment_ids"],
        notes=serializer.validated_data.get("notes", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response({"results": results})


# ==============================================================================
# Transfer (Super Admin)
# ==============================================================================


@extend_schema(
    summary="Transfer Student",
    description="Creates a new PENDING_VERIFICATION assignment for a different hostel/mess.",
    tags=["students"],
    request=TransferStudentSerializer,
    responses={200: OpenApiResponse(description="Transfer initiated")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def student_transfer_view(request, student_id: int):
    serializer = TransferStudentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    assignment = transfer_student(
        student_id=student_id,
        new_hostel_code=serializer.validated_data["new_hostel_code"],
        new_mess_code=serializer.validated_data["new_mess_code"],
        effective_from=serializer.validated_data["effective_from"],
        reason=serializer.validated_data.get("reason", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response({
        "assignment_id": assignment.assignment_id,
        "student_id": assignment.student_id,
        "status": assignment.status,
        "effective_from": str(assignment.effective_from),
        "message": "Transfer initiated. Pending Clerk verification.",
    })


# ==============================================================================
# Hostel Clerk Management (Super Admin)
# ==============================================================================


@extend_schema(
    summary="List Hostel Clerks",
    description="Lists all hostel clerks with their assignments.",
    tags=["admin"],
    responses={200: OpenApiResponse(description="List of clerks")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def clerk_list_view(request):
    assignments = (
        HostelClerkAssignment.objects
        .select_related("user", "hostel")
        .order_by("-is_active", "hostel__code")
    )

    # Optional filters
    is_active = request.query_params.get("is_active")
    if is_active is not None:
        assignments = assignments.filter(is_active=is_active.lower() == "true")

    hostel_id = request.query_params.get("hostel_id")
    if hostel_id:
        assignments = assignments.filter(hostel_id=hostel_id)

    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(assignments, request)

    results = []
    for a in page:
        results.append({
            "user_id": a.user_id,
            "email": a.user.normalized_email,
            "full_name": a.user.full_name,
            "phone_number": a.user.phone_number,
            "hostel": {
                "id": a.hostel.hostel_id,
                "code": a.hostel.code,
                "name": a.hostel.name,
            },
            "assignment_id": a.clerk_assignment_id,
            "is_active": a.is_active,
            "assigned_at": a.assigned_at,
        })
    return paginator.get_paginated_response(results)


@extend_schema(
    summary="Create Hostel Clerk",
    description="Creates a new Clerk account with unusable password.",
    tags=["admin"],
    request=ClerkCreateSerializer,
    responses={201: OpenApiResponse(description="Clerk created")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def clerk_create_view(request):
    serializer = ClerkCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = create_hostel_clerk(
        email=serializer.validated_data["email"],
        full_name=serializer.validated_data["full_name"],
        phone_number=serializer.validated_data.get("phone_number", ""),
        hostel_code=serializer.validated_data["hostel_code"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Reassign Hostel Clerk",
    description="Reassigns a Clerk to a different hostel.",
    tags=["admin"],
    request=ClerkReassignSerializer,
    responses={200: OpenApiResponse(description="Clerk reassigned")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def clerk_reassign_view(request, user_id: int):
    serializer = ClerkReassignSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = reassign_hostel_clerk(
        user_id=user_id,
        new_hostel_code=serializer.validated_data["new_hostel_code"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result)


@extend_schema(
    summary="Deactivate Hostel Clerk",
    description="Deactivates a Clerk's assignment.",
    tags=["admin"],
    responses={200: OpenApiResponse(description="Clerk deactivated")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def clerk_deactivate_view(request, user_id: int):
    result = deactivate_hostel_clerk(
        user_id=user_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result)


# ==============================================================================
# Unified Endpoints (Routing Dispatchers)
# ==============================================================================


@extend_schema(
    methods=["GET"],
    summary="List Hostels",
    description="Lists all hostels. Super Admin sees all; Clerks see their own hostel.",
    tags=["hostels"],
    responses={200: HostelSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    summary="Create Hostel",
    description="Creates a new hostel. Super Admin only.",
    tags=["hostels"],
    request=HostelCreateSerializer,
    responses={201: HostelSerializer},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def hostel_list_create_view(request):
    if request.method == "POST":
        role = get_user_role(request.user)
        if role != "SUPER_ADMIN" and not getattr(request.user, "is_superuser", False):
            return Response(
                {"code": "PERMISSION_DENIED", "message": "Only Super Admin can create hostels."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = HostelCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hostel = create_hostel(
            code=serializer.validated_data["code"],
            name=serializer.validated_data["name"],
            address=serializer.validated_data.get("address", ""),
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )
        return Response(HostelSerializer(hostel).data, status=status.HTTP_201_CREATED)

    # GET
    role = get_user_role(request.user)
    if role == "HOSTEL_CLERK":
        hostel = get_clerk_hostel(request.user)
        qs = Hostel.objects.filter(hostel_id=hostel.hostel_id) if hostel else Hostel.objects.none()
    elif role == "SUPER_ADMIN" or getattr(request.user, "is_superuser", False):
        qs = Hostel.objects.all()
    else:
        qs = Hostel.objects.none()

    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter.upper())

    qs = qs.order_by("code")
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = HostelSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    methods=["GET"],
    summary="Get Hostel Detail",
    description="Returns a single hostel by ID.",
    tags=["hostels"],
    responses={200: HostelSerializer},
)
@extend_schema(
    methods=["PATCH"],
    summary="Update Hostel",
    description="Rename or update hostel. Version check enforced. Super Admin only.",
    tags=["hostels"],
    request=HostelUpdateSerializer,
    responses={200: HostelSerializer},
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def hostel_detail_update_view(request, hostel_id: int):
    hostel = Hostel.objects.filter(hostel_id=hostel_id).first()
    if not hostel:
        return Response(
            {"code": "OBJECT_NOT_FOUND", "message": "Hostel not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "PATCH":
        role = get_user_role(request.user)
        if role != "SUPER_ADMIN" and not getattr(request.user, "is_superuser", False):
            return Response(
                {"code": "PERMISSION_DENIED", "message": "Only Super Admin can update hostels."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = HostelUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hostel = update_hostel(
            hostel_id=hostel_id,
            name=serializer.validated_data.get("name"),
            address=serializer.validated_data.get("address"),
            version=serializer.validated_data["version"],
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )
        return Response(HostelSerializer(hostel).data)

    # GET
    role = get_user_role(request.user)
    if role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_hostel(request.user)
        if not clerk_hostel or clerk_hostel.hostel_id != hostel_id:
            return Response(
                {"code": "OBJECT_NOT_FOUND", "message": "Hostel not found in your scope."},
                status=status.HTTP_404_NOT_FOUND,
            )
    return Response(HostelSerializer(hostel).data)


@extend_schema(
    methods=["GET"],
    summary="List Students",
    tags=["students"],
    responses={200: StudentListSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    summary="Create Student",
    tags=["students"],
    request=StudentCreateSerializer,
    responses={201: OpenApiResponse(description="Student created")},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def student_list_create_view(request):
    if request.method == "POST":
        role = get_user_role(request.user)
        if role != "SUPER_ADMIN" and not getattr(request.user, "is_superuser", False):
            return Response(
                {"code": "PERMISSION_DENIED", "message": "Only Super Admin can create students."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = StudentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_student(
            email=serializer.validated_data["email"],
            full_name=serializer.validated_data["full_name"],
            roll_number=serializer.validated_data["roll_number"],
            hostel_code=serializer.validated_data["hostel_code"],
            mess_code=serializer.validated_data["mess_code"],
            department=serializer.validated_data.get("department", ""),
            year_of_study=serializer.validated_data.get("year_of_study"),
            room_number=serializer.validated_data.get("room_number", ""),
            phone_number=serializer.validated_data.get("phone_number", ""),
            effective_from=serializer.validated_data.get("effective_from"),
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )
        return Response(result, status=status.HTTP_201_CREATED)

    # GET
    qs = get_visible_students_queryset(request.user)
    qs = qs.select_related("user", "hostel")

    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter.upper())

    hostel_id = request.query_params.get("hostel_id")
    if hostel_id:
        qs = qs.filter(hostel_id=hostel_id)

    roll_number = request.query_params.get("roll_number")
    if roll_number:
        qs = qs.filter(roll_number__icontains=roll_number.strip().upper())

    search = request.query_params.get("search")
    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(roll_number__icontains=search) |
            Q(user__full_name__icontains=search) |
            Q(user__email__icontains=search)
        )

    qs = qs.order_by("roll_number")
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = StudentListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    methods=["GET"],
    summary="Get Student Detail",
    tags=["students"],
    responses={200: StudentDetailSerializer},
)
@extend_schema(
    methods=["PATCH"],
    summary="Update Student",
    tags=["students"],
    request=StudentUpdateSerializer,
    responses={200: StudentDetailSerializer},
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def student_detail_update_view(request, student_id: int):
    if request.method == "PATCH":
        role = get_user_role(request.user)
        if role != "SUPER_ADMIN" and not getattr(request.user, "is_superuser", False):
            return Response(
                {"code": "PERMISSION_DENIED", "message": "Only Super Admin can update students."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = StudentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = update_student(
            student_id=student_id,
            full_name=serializer.validated_data.get("full_name"),
            department=serializer.validated_data.get("department"),
            year_of_study=serializer.validated_data.get("year_of_study"),
            room_number=serializer.validated_data.get("room_number"),
            phone_number=serializer.validated_data.get("phone_number"),
            status=serializer.validated_data.get("status"),
            version=serializer.validated_data["version"],
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )
        student = Student.objects.select_related("user", "hostel").get(student_id=student.student_id)
        return Response(StudentDetailSerializer(student).data)

    # GET
    from apps.identity.selectors import get_student_in_scope
    student = get_student_in_scope(request.user, student_id)
    student = Student.objects.select_related("user", "hostel").get(student_id=student.student_id)
    return Response(StudentDetailSerializer(student).data)


@extend_schema(
    methods=["GET"],
    summary="List Hostel Clerks",
    tags=["admin"],
    responses={200: OpenApiResponse(description="List of clerks")},
)
@extend_schema(
    methods=["POST"],
    summary="Create Hostel Clerk",
    tags=["admin"],
    request=ClerkCreateSerializer,
    responses={201: OpenApiResponse(description="Clerk created")},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def clerk_list_create_view(request):
    if request.method == "POST":
        serializer = ClerkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_hostel_clerk(
            email=serializer.validated_data["email"],
            full_name=serializer.validated_data["full_name"],
            phone_number=serializer.validated_data.get("phone_number", ""),
            hostel_code=serializer.validated_data["hostel_code"],
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )
        return Response(result, status=status.HTTP_201_CREATED)

    # GET
    assignments = (
        HostelClerkAssignment.objects
        .select_related("user", "hostel")
        .order_by("-is_active", "hostel__code")
    )
    is_active = request.query_params.get("is_active")
    if is_active is not None:
        assignments = assignments.filter(is_active=is_active.lower() == "true")

    hostel_id = request.query_params.get("hostel_id")
    if hostel_id:
        assignments = assignments.filter(hostel_id=hostel_id)

    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(assignments, request)
    results = []
    for a in page:
        results.append({
            "user_id": a.user_id,
            "email": a.user.normalized_email,
            "full_name": a.user.full_name,
            "phone_number": a.user.phone_number,
            "hostel": {
                "id": a.hostel.hostel_id,
                "code": a.hostel.code,
                "name": a.hostel.name,
            },
            "assignment_id": a.clerk_assignment_id,
            "is_active": a.is_active,
            "assigned_at": a.assigned_at,
        })
    return paginator.get_paginated_response(results)
