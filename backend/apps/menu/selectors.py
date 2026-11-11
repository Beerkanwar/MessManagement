"""
Read selectors for the menu endpoint group [SPEC DBDD §9, SRS §22, App Flow §3.4].

Scope rules:
- Super Admin reads every hostel's menus.
- Hostel Clerk reads only their assigned hostel's menus.
- Students read only the published menu of their active assignment's hostel through
  ``/menus/current``; earlier months are never exposed.
- Mess Managers have no menu authoring or menu read access.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import date
from typing import Any

from django.db.models import Prefetch, Q, QuerySet

from apps.core.clock import clock
from apps.core.exceptions import NotFoundError
from apps.hostel.models import Hostel, Student, StudentMessAssignment
from apps.identity.models import User
from apps.identity.selectors import get_clerk_hostel, get_user_role
from apps.menu.models import FoodItem, Menu, MenuItem, MenuMeal


def is_super_admin(user: User) -> bool:
    return bool(getattr(user, "is_superuser", False)) or get_user_role(user) == "SUPER_ADMIN"


def list_food_items(
    *, include_inactive: bool = True, status_value: str | None = None
) -> QuerySet[FoodItem]:
    queryset = FoodItem.objects.all().order_by("name", "food_item_id")
    if status_value:
        queryset = queryset.filter(status=status_value)
    elif not include_inactive:
        queryset = queryset.filter(status="ACTIVE")
    return queryset


def get_food_item(food_item_id: int) -> FoodItem | None:
    return FoodItem.objects.filter(food_item_id=food_item_id).first()


def list_menus_scoped(
    user: User,
    *,
    hostel_id: int | None = None,
    year: int | None = None,
    month: int | None = None,
    status_value: str | None = None,
) -> QuerySet[Menu]:
    """Menus visible to a menu author, newest first."""
    role = "SUPER_ADMIN" if is_super_admin(user) else get_user_role(user)
    if role == "SUPER_ADMIN":
        queryset = Menu.objects.all()
    elif role == "HOSTEL_CLERK":
        hostel = get_clerk_hostel(user)
        if not hostel:
            return Menu.objects.none()
        queryset = Menu.objects.filter(hostel=hostel)
    else:
        return Menu.objects.none()

    if hostel_id is not None:
        queryset = queryset.filter(hostel_id=hostel_id)
    if year is not None:
        queryset = queryset.filter(menu_year=year)
    if month is not None:
        queryset = queryset.filter(menu_month=month)
    if status_value:
        queryset = queryset.filter(status=status_value)
    return queryset.select_related("hostel", "published_by_user").order_by(
        "-menu_year", "-menu_month", "hostel__code"
    )


def get_menu_scoped(user: User, menu_id: int) -> Menu:
    """Fetches a menu the caller is allowed to author; out-of-scope is a 404."""
    queryset = list_menus_scoped(user)
    menu = queryset.filter(menu_id=menu_id).first()
    if not menu:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="The requested menu does not exist or is out of your authorized scope.",
        )
    return menu


def get_hostel_for_author(user: User, hostel_id: int) -> Hostel:
    """Resolves the target hostel and refuses cross-hostel Clerk access."""
    if is_super_admin(user):
        hostel = Hostel.objects.filter(hostel_id=hostel_id).first()
    else:
        clerk_hostel = get_clerk_hostel(user)
        hostel = Hostel.objects.filter(hostel_id=hostel_id).first()
        if not clerk_hostel or (hostel and hostel.hostel_id != clerk_hostel.hostel_id):
            hostel = None
    if not hostel:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="The requested hostel does not exist or is out of your authorized scope.",
        )
    return hostel


def get_student_for_user(user: User) -> Student:
    student = Student.objects.select_related("hostel").filter(user=user).first()
    if not student:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="No student profile is associated with this account.",
        )
    return student


def get_active_assignment(student: Student, on_date: date | None = None) -> StudentMessAssignment | None:
    """The student's ACTIVE assignment covering the requested IST date."""
    as_of = on_date or clock.today()
    return (
        StudentMessAssignment.objects.filter(
            student=student,
            status="ACTIVE",
            effective_from__lte=as_of,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=as_of))
        .select_related("hostel", "mess")
        .order_by("-effective_from", "-assignment_id")
        .first()
    )


def get_published_menus_for_hostel(
    hostel_id: int, months: list[tuple[int, int]]
) -> list[Menu]:
    """Published menus for the given (year, month) pairs, in input order."""
    if not months:
        return []
    query = Q()
    for year, month in months:
        query |= Q(menu_year=year, menu_month=month)
    menus = list(
        Menu.objects.filter(query, hostel_id=hostel_id, status="PUBLISHED")
        .select_related("hostel")
        .order_by("menu_year", "menu_month")
    )
    by_month = {(menu.menu_year, menu.menu_month): menu for menu in menus}
    return [by_month[pair] for pair in months if pair in by_month]


def get_current_student_menu(user: User) -> dict[str, Any]:
    """
    The published menu of the student's active-assignment hostel for the current
    IST month, plus the next month when it is already published [SRS §22].
    Earlier months are never returned.
    """
    student = get_student_for_user(user)
    assignment = get_active_assignment(student)
    if not assignment:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message="No active mess assignment is available for this student.",
        )

    today = clock.today()
    if today.month == 12:
        next_year, next_month = today.year + 1, 1
    else:
        next_year, next_month = today.year, today.month + 1
    months = [(today.year, today.month), (next_year, next_month)]
    published = get_published_menus_for_hostel(assignment.hostel_id, months)

    return {
        "student_id": student.student_id,
        "hostel": {
            "hostel_id": assignment.hostel.hostel_id,
            "code": assignment.hostel.code,
            "name": assignment.hostel.name,
        },
        "months": [build_menu_structure(menu_with_meals(menu)) for menu in published],
    }



def menu_with_meals(menu: Menu) -> Menu:
    """Reloads a menu with its meals, meal types and food items in display order."""
    return (
        Menu.objects.select_related("hostel", "published_by_user")
        .prefetch_related(
            Prefetch(
                "meals",
                queryset=MenuMeal.objects.select_related("meal_type").order_by(
                    "menu_date", "meal_type__sequence_no", "menu_meal_id"
                ),
            ),
            Prefetch(
                "meals__items",
                queryset=MenuItem.objects.select_related("food_item").order_by(
                    "display_order", "menu_item_id"
                ),
            ),
        )
        .get(menu_id=menu.menu_id)
    )


def build_menu_structure(menu: Menu) -> dict[str, Any]:
    """
    Serialises Month -> Date -> Meal -> Items [SPEC SRS §22, App Flow §3.4].
    Days with no scheduled meal are omitted so the payload stays compact.
    """
    days: OrderedDict[date, list[dict[str, Any]]] = OrderedDict()
    for meal in menu.meals.all():
        items = [
            {
                "menu_item_id": item.menu_item_id,
                "food_item_id": item.food_item_id,
                "name": item.food_item.name,
                "display_order": item.display_order,
                "notes": item.notes,
            }
            for item in meal.items.all()
        ]
        days.setdefault(meal.menu_date, []).append(
            {
                "menu_meal_id": meal.menu_meal_id,
                "meal_type_id": meal.meal_type_id,
                "meal_type_code": meal.meal_type.code,
                "meal_type_name": meal.meal_type.name,
                "sequence_no": meal.meal_type.sequence_no,
                "status": meal.status,
                "items": items,
            }
        )

    return {
        "menu_id": menu.menu_id,
        "hostel_id": menu.hostel_id,
        "hostel_code": menu.hostel.code,
        "hostel_name": menu.hostel.name,
        "year": menu.menu_year,
        "month": menu.menu_month,
        "month_label": f"{menu.menu_year:04d}-{menu.menu_month:02d}",
        "status": menu.status,
        "published_at": menu.published_at,
        "published_by_user_id": menu.published_by_user_id,
        "version": menu.version,
        "days": [
            {"date": menu_date, "meals": meals}
            for menu_date, meals in days.items()
        ],
    }
