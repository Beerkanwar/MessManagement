"""
Identity and authorization scope selectors.
Enforces DBDD §3.1, SDD §154.1, and Phase 3 authorization rules:
- No view may read Student or any student-owned table without going through a selector.
- Out-of-scope objects return 404 (OBJECT_NOT_FOUND) so existence is not revealed.
"""
from datetime import date
from django.db.models import Q, QuerySet
from apps.core.clock import clock
from apps.core.exceptions import NotFoundError
from apps.hostel.models import Hostel, HostelClerkAssignment, Student, StudentMessAssignment
from apps.identity.models import User, UserRole
from apps.mess.models import Mess, MessManagerAssignment


def get_user_role(user: User) -> str | None:
    """
    Returns the user's single primary role name (DEC-20).
    If user is marked superuser and lacks a UserRole entry, returns 'SUPER_ADMIN'.
    """
    if not user or not user.is_authenticated:
        return None

    ur = UserRole.objects.select_related("role").filter(user=user).first()
    if ur:
        return ur.role.name
    if getattr(user, "is_superuser", False):
        return "SUPER_ADMIN"
    return None


def get_clerk_hostel(user: User) -> Hostel | None:
    """Returns the single active hostel assigned to the Clerk, or None."""
    clerk_assign = HostelClerkAssignment.objects.filter(user=user, is_active=True).select_related("hostel").first()
    return clerk_assign.hostel if clerk_assign else None


def get_manager_mess(user: User) -> Mess | None:
    """Returns the single active mess assigned to the Manager, or None."""
    mgr_assign = MessManagerAssignment.objects.filter(user=user, is_active=True).select_related("mess").first()
    return mgr_assign.mess if mgr_assign else None


def get_visible_students_queryset(user: User, target_date: date | None = None) -> QuerySet[Student]:
    """
    Authoritative scope selector for students.
    Enforces scope:
    - Super Admin: all students.
    - Clerk: students in the Clerk's assigned hostel.
    - Manager: students with an ACTIVE assignment to the Manager's mess on target_date [DBDD §3.1].
    - Student: only their own profile.
    """
    if not user or not user.is_authenticated:
        return Student.objects.none()

    role = get_user_role(user)
    as_of_date = target_date or clock.today()

    if role == "SUPER_ADMIN" or getattr(user, "is_superuser", False):
        return Student.objects.all()

    if role == "HOSTEL_CLERK":
        hostel = get_clerk_hostel(user)
        if not hostel:
            return Student.objects.none()
        return Student.objects.filter(hostel=hostel)

    if role == "MESS_MANAGER":
        mess = get_manager_mess(user)
        if not mess:
            return Student.objects.none()

        # Active assignments on as_of_date
        active_student_ids = StudentMessAssignment.objects.filter(
            mess=mess,
            status="ACTIVE",
            effective_from__lte=as_of_date,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=as_of_date)
        ).values_list("student_id", flat=True)

        return Student.objects.filter(student_id__in=active_student_ids)

    if role == "STUDENT":
        return Student.objects.filter(user=user)

    return Student.objects.none()


def get_student_in_scope(user: User, student_id: int, target_date: date | None = None) -> Student:
    """
    Fetches a student ensuring they are within the caller's authorization scope.
    Raises NotFoundError (404) if out-of-scope or non-existent, preventing enumeration [REC].
    """
    qs = get_visible_students_queryset(user, target_date=target_date)
    student = qs.filter(student_id=student_id).first()
    if not student:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="The requested student does not exist or is out of your authorized scope.",
        )
    return student


def get_user_assignment_summary(user: User, target_date: date | None = None) -> dict:
    """Builds assignment summary dictionary for authentication responses."""
    role = get_user_role(user)
    as_of = target_date or clock.today()

    summary = {
        "role": role,
        "hostel": None,
        "mess": None,
    }

    if role == "HOSTEL_CLERK":
        hostel = get_clerk_hostel(user)
        if hostel:
            summary["hostel"] = {"id": hostel.hostel_id, "code": hostel.code, "name": hostel.name}

    elif role == "MESS_MANAGER":
        mess = get_manager_mess(user)
        if mess:
            summary["mess"] = {"id": mess.mess_id, "code": mess.code, "name": mess.name}

    elif role == "STUDENT":
        student = Student.objects.filter(user=user).select_related("hostel").first()
        if student:
            summary["student_id"] = student.student_id
            summary["roll_number"] = student.roll_number
            summary["hostel"] = {
                "id": student.hostel.hostel_id,
                "code": student.hostel.code,
                "name": student.hostel.name,
            }
            # Active assignment
            assign = StudentMessAssignment.objects.filter(
                student=student,
                status="ACTIVE",
                effective_from__lte=as_of,
            ).filter(
                Q(effective_to__isnull=True) | Q(effective_to__gt=as_of)
            ).select_related("mess").first()
            if assign:
                summary["mess"] = {
                    "id": assign.mess.mess_id,
                    "code": assign.mess.code,
                    "name": assign.mess.name,
                }

    return summary
