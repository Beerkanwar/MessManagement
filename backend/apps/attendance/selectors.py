"""
Attendance selectors implementing effective attendance evaluation and role scoping [SPEC DBDD §6, §11, ImplementationGuide Phase 7].
Enforces:
- Phase 2 rule: A meal row counts unless its latest applied correction is REMOVE_INCORRECT.
- Scoped reads: Student (own), Manager (assigned mess), Clerk (assigned hostel), Super Admin (system-wide).
"""
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Count, F, OuterRef, Q, QuerySet, Subquery, Sum
from django.utils import timezone as django_tz

from apps.attendance.models import AttendanceCorrection, ExtraTransaction, MealConsumption
from apps.hostel.models import Hostel, Student
from apps.identity.models import User
from apps.identity.selectors import get_user_role
from apps.mess.models import MealType, Mess
from apps.mess.services import get_clerk_scope, get_manager_scope


def get_effective_meal_consumptions(
    base_queryset: QuerySet[MealConsumption] | None = None,
    *,
    student: Student | int | None = None,
    mess: Mess | int | None = None,
    hostel: Hostel | int | None = None,
    meal_type: MealType | str | int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> QuerySet[MealConsumption]:
    """
    Selects effective meal consumptions implementing the Phase 2 rule:
    A consumption row counts unless its latest applied AttendanceCorrection is REMOVE_INCORRECT.
    [SPEC DBDD §6, Invariant 12, ImplementationGuide Phase 7].
    """
    if base_queryset is None:
        qs = MealConsumption.objects.all()
    else:
        qs = base_queryset

    # Subquery finding the latest applied correction action for each (student, date, meal_type)
    latest_correction_subquery = Subquery(
        AttendanceCorrection.objects.filter(
            student_id=OuterRef("student_id"),
            meal_date=OuterRef("meal_date"),
            meal_type_id=OuterRef("meal_type_id"),
            status="APPLIED",
        )
        .order_by("-requested_at", "-correction_id")
        .values("action")[:1]
    )

    qs = qs.annotate(latest_applied_action=latest_correction_subquery).filter(
        Q(latest_applied_action__isnull=True) | ~Q(latest_applied_action="REMOVE_INCORRECT")
    )

    # Optional filter criteria
    if student is not None:
        student_id = student.student_id if isinstance(student, Student) else student
        qs = qs.filter(student_id=student_id)

    if mess is not None:
        mess_id = mess.mess_id if isinstance(mess, Mess) else mess
        qs = qs.filter(mess_id=mess_id)

    if hostel is not None:
        hostel_id = hostel.hostel_id if isinstance(hostel, Hostel) else hostel
        qs = qs.filter(student__hostel_id=hostel_id)

    if meal_type is not None:
        if isinstance(meal_type, MealType):
            qs = qs.filter(meal_type=meal_type)
        elif isinstance(meal_type, int) or (isinstance(meal_type, str) and meal_type.isdigit()):
            qs = qs.filter(meal_type_id=int(meal_type))
        else:
            qs = qs.filter(meal_type__code__iexact=str(meal_type))

    if start_date is not None:
        qs = qs.filter(meal_date__gte=start_date)

    if end_date is not None:
        qs = qs.filter(meal_date__lte=end_date)

    return qs.select_related(
        "student", "student__user", "mess", "meal_type"
    ).order_by("-meal_date", "-meal_consumption_id")


def get_scoped_meal_consumptions(
    user: User,
    *,
    student_id: int | None = None,
    mess_id: int | None = None,
    hostel_id: int | None = None,
    meal_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> QuerySet[MealConsumption]:
    """
    Returns effective meal consumptions scoped to the calling user's role and assignments.
    - Super Admin: All effective meals across all messes and hostels.
    - Hostel Clerk: Effective meals for students belonging to Clerk's assigned hostel.
    - Mess Manager: Effective meals recorded for Manager's assigned mess.
    - Student: Effective meals recorded for the student's own account.
    """
    role = get_user_role(user)
    base_qs = MealConsumption.objects.all()

    if role == "SUPER_ADMIN" or getattr(user, "is_superuser", False):
        pass
    elif role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_scope(user)
        if not clerk_hostel:
            return MealConsumption.objects.none()
        base_qs = base_qs.filter(student__hostel=clerk_hostel)
    elif role == "MESS_MANAGER":
        manager_mess = get_manager_scope(user)
        if not manager_mess:
            return MealConsumption.objects.none()
        base_qs = base_qs.filter(mess=manager_mess)
    elif role == "STUDENT":
        student_obj = Student.objects.filter(user=user, status="ACTIVE").first()
        if not student_obj:
            return MealConsumption.objects.none()
        base_qs = base_qs.filter(student=student_obj)
    else:
        return MealConsumption.objects.none()

    return get_effective_meal_consumptions(
        base_queryset=base_qs,
        student=student_id,
        mess=mess_id,
        hostel=hostel_id,
        meal_type=meal_type,
        start_date=start_date,
        end_date=end_date,
    )


def get_attendance_summary(
    user: User,
    *,
    student_id: int | None = None,
    mess_id: int | None = None,
    hostel_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """
    Calculates monthly/filtered attendance summary counts and financial snapshots.
    """
    effective_qs = get_scoped_meal_consumptions(
        user,
        student_id=student_id,
        mess_id=mess_id,
        hostel_id=hostel_id,
        start_date=start_date,
        end_date=end_date,
    )

    counts_by_type = effective_qs.values("meal_type__code").annotate(count=Count("meal_consumption_id"))
    type_map = {item["meal_type__code"]: item["count"] for item in counts_by_type}

    total_meals = sum(type_map.values())
    total_amount = effective_qs.aggregate(total=Sum("price_at_transaction"))["total"] or Decimal("0.0000")

    return {
        "breakfast_count": type_map.get("BREAKFAST", 0),
        "lunch_count": type_map.get("LUNCH", 0),
        "dinner_count": type_map.get("DINNER", 0),
        "total_meals": total_meals,
        "total_amount": str(total_amount),
        "start_date": str(start_date) if start_date else None,
        "end_date": str(end_date) if end_date else None,
    }


def get_scoped_extra_transactions(
    user: User,
    *,
    student_id: int | None = None,
    mess_id: int | None = None,
    hostel_id: int | None = None,
    extra_item_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> QuerySet[ExtraTransaction]:
    """
    Returns ExtraTransaction queryset scoped to caller role.
    """
    role = get_user_role(user)
    qs = ExtraTransaction.objects.all().select_related(
        "student", "student__user", "hostel", "mess", "extra_item"
    )

    if role == "SUPER_ADMIN" or getattr(user, "is_superuser", False):
        pass
    elif role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_scope(user)
        if not clerk_hostel:
            return ExtraTransaction.objects.none()
        qs = qs.filter(hostel=clerk_hostel)
    elif role == "MESS_MANAGER":
        manager_mess = get_manager_scope(user)
        if not manager_mess:
            return ExtraTransaction.objects.none()
        qs = qs.filter(mess=manager_mess)
    elif role == "STUDENT":
        student_obj = Student.objects.filter(user=user, status="ACTIVE").first()
        if not student_obj:
            return ExtraTransaction.objects.none()
        qs = qs.filter(student=student_obj)
    else:
        return ExtraTransaction.objects.none()

    if student_id:
        qs = qs.filter(student_id=student_id)
    if mess_id:
        qs = qs.filter(mess_id=mess_id)
    if hostel_id:
        qs = qs.filter(hostel_id=hostel_id)
    if extra_item_id:
        qs = qs.filter(extra_item_id=extra_item_id)
    if start_date:
        qs = qs.filter(transaction_timestamp__date__gte=start_date)
    if end_date:
        qs = qs.filter(transaction_timestamp__date__lte=end_date)

    return qs.order_by("-transaction_timestamp", "-extra_transaction_id")


def get_scoped_attendance_corrections(
    user: User,
    *,
    student_id: int | None = None,
    mess_id: int | None = None,
    action: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> QuerySet[AttendanceCorrection]:
    """
    Returns AttendanceCorrection queryset scoped to caller role.
    """
    role = get_user_role(user)
    qs = AttendanceCorrection.objects.all().select_related("student", "mess", "meal_type", "actor_user")

    if role == "SUPER_ADMIN" or getattr(user, "is_superuser", False):
        pass
    elif role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_scope(user)
        if not clerk_hostel:
            return AttendanceCorrection.objects.none()
        qs = qs.filter(student__hostel=clerk_hostel)
    elif role == "MESS_MANAGER":
        manager_mess = get_manager_scope(user)
        if not manager_mess:
            return AttendanceCorrection.objects.none()
        qs = qs.filter(mess=manager_mess)
    elif role == "STUDENT":
        student_obj = Student.objects.filter(user=user, status="ACTIVE").first()
        if not student_obj:
            return AttendanceCorrection.objects.none()
        qs = qs.filter(student=student_obj)
    else:
        return AttendanceCorrection.objects.none()

    if student_id:
        qs = qs.filter(student_id=student_id)
    if mess_id:
        qs = qs.filter(mess_id=mess_id)
    if action:
        qs = qs.filter(action=action)
    if start_date:
        qs = qs.filter(meal_date__gte=start_date)
    if end_date:
        qs = qs.filter(meal_date__lte=end_date)

    return qs.order_by("-requested_at", "-correction_id")
