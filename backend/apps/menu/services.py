"""
Menu domain services implementing SPEC DBDD §9, SRS §22, App Flow §3.4 and
ImplementationGuide Phase 11.

Rules:
- FoodItems are a global reusable master list; normalized names are unique.
- Menus are hostel-scoped and unique per calendar month.
- A menu is edited one (date, meal type) at a time. Replacing a meal's items is
  atomic and removes duplicate foods in that meal; the database unique constraint
  is the final guard [DBDD-AC-30, Invariant 10].
- Every mutation checks the submitted menu version under a row lock, so two
  editors cannot overwrite each other silently [DBDD §18.3].
- Publication is DRAFT -> PUBLISHED. Published menus may still be revised, but
  every change writes MENU_REVISED with the old and new items.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Any, Iterable

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.core.concurrency import check_optimistic_lock
from apps.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from apps.identity.models import User
from apps.identity.selectors import get_user_role
from apps.menu.models import FoodItem, Menu, MenuItem, MenuMeal
from apps.menu.selectors import (
    get_hostel_for_author,
    get_menu_scoped,
    is_super_admin,
    menu_with_meals,
)
from apps.mess.models import MealType

AUDIT_TEXT_LIMIT = 500


def _audit_text(value: str | None) -> str:
    """Keeps audit payload strings within the audit service's 500-char cap."""
    return (value or "")[:AUDIT_TEXT_LIMIT]


def _author_role(user: User) -> str:
    role = "SUPER_ADMIN" if is_super_admin(user) else get_user_role(user)
    if role not in ("SUPER_ADMIN", "HOSTEL_CLERK"):
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Menu authoring is limited to hostel clerks and the Super Admin.",
        )
    return role


def _require_super_admin(user: User) -> None:
    if not is_super_admin(user):
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Only the Super Admin may rename or deactivate shared food items.",
        )


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _month_dates(year: int, month: int) -> list[date]:
    return [
        date(year, month, day)
        for day in range(1, calendar.monthrange(year, month)[1] + 1)
    ]


def _validate_menu_date(menu: Menu, menu_date: date) -> None:
    if menu_date.year != menu.menu_year or menu_date.month != menu.menu_month:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=(
                f"Menu date {menu_date.isoformat()} is outside the menu month "
                f"{menu.menu_year:04d}-{menu.menu_month:02d}."
            ),
        )


def _meal_type_by_code(code: str) -> MealType:
    meal_type = MealType.objects.filter(code=code, is_active=True).first()
    if not meal_type:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Unknown or inactive meal type '{code}'.",
        )
    return meal_type


def _resolve_food_items(
    items: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Validates the submitted meal items and assigns display order. Duplicate food
    items are refused before the database unique constraint is reached.
    """
    rows = list(items)
    food_ids = [int(row["food_item_id"]) for row in rows]
    if len(food_ids) != len(set(food_ids)):
        raise ValidationError(
            code="DUPLICATE_RESOURCE",
            message="The same food item cannot appear twice in one menu meal.",
        )

    food_items = {
        item.food_item_id: item
        for item in FoodItem.objects.filter(food_item_id__in=food_ids, status="ACTIVE")
    }
    missing = sorted(set(food_ids) - set(food_items))
    if missing:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Unknown or inactive food item(s): {', '.join(map(str, missing))}.",
        )

    resolved = []
    for index, row in enumerate(rows, start=1):
        resolved.append(
            {
                "food_item": food_items[int(row["food_item_id"])],
                "display_order": int(row.get("display_order") or index),
                "notes": row.get("notes") or "",
            }
        )
    return resolved


def _item_snapshot(meal: MenuMeal | None) -> list[dict[str, Any]]:
    if meal is None:
        return []
    meal = (
        MenuMeal.objects.select_related("meal_type")
        .prefetch_related("items__food_item")
        .get(menu_meal_id=meal.menu_meal_id)
    )
    return [
        {
            "food_item_id": item.food_item_id,
            "name": item.food_item.name,
            "display_order": item.display_order,
            "notes": _audit_text(item.notes),
        }
        for item in meal.items.all()
    ]


def _dates_without_items(menu: Menu) -> list[str]:
    covered = set(
        MenuMeal.objects.filter(menu=menu, items__isnull=False)
        .values_list("menu_date", flat=True)
        .distinct()
    )
    return [day.isoformat() for day in _month_dates(menu.menu_year, menu.menu_month) if day not in covered]


# ---------------------------------------------------------------------------
# Food item master
# ---------------------------------------------------------------------------


def create_food_item(
    *, name: str, description: str = "", actor: User, correlation_id: str = ""
) -> FoodItem:
    """Clerk or Super Admin adds a reusable food item."""
    _author_role(actor)
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError(code="VALIDATION_ERROR", message="A food item name is required.")
    normalized = " ".join(clean_name.upper().split())
    try:
        with transaction.atomic():
            food_item = FoodItem.objects.create(
                name=clean_name,
                normalized_name=normalized,
                description=description or "",
            )
    except IntegrityError:
        raise ConflictError(
            code="DUPLICATE_RESOURCE",
            message=f"A food item named '{clean_name}' already exists.",
        )

    record_audit_event(
        event_type="FOOD_ITEM_CREATED",
        actor_user=actor,
        entity_type="FoodItem",
        entity_id=food_item.food_item_id,
        new_values={
            "food_item_id": food_item.food_item_id,
            "name": food_item.name,
            "normalized_name": food_item.normalized_name,
        },
        correlation_id=correlation_id,
    )
    return food_item


def update_food_item(
    *,
    food_item_id: int,
    name: str | None = None,
    description: str | None = None,
    expected_version: int,
    actor: User,
    correlation_id: str = "",
) -> FoodItem:
    """Super Admin renames a shared food item (and optionally its description)."""
    _require_super_admin(actor)
    with transaction.atomic():
        food_item = (
            FoodItem.objects.select_for_update()
            .filter(food_item_id=food_item_id)
            .first()
        )
        if not food_item:
            raise NotFoundError(code="OBJECT_NOT_FOUND", message="Food item not found.")
        check_optimistic_lock(food_item, expected_version)

        old_values = {
            "name": food_item.name,
            "description": _audit_text(food_item.description),
        }
        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValidationError(
                    code="VALIDATION_ERROR", message="A food item name is required."
                )
            food_item.name = clean_name
            food_item.normalized_name = " ".join(clean_name.upper().split())
        if description is not None:
            food_item.description = description
        food_item.version = F("version") + 1
        try:
            food_item.save(
                update_fields=["name", "normalized_name", "description", "version", "updated_at"]
            )
        except IntegrityError:
            raise ConflictError(
                code="DUPLICATE_RESOURCE",
                message="Another food item already uses that name.",
            )

    food_item.refresh_from_db()
    record_audit_event(
        event_type="FOOD_ITEM_RENAMED",
        actor_user=actor,
        entity_type="FoodItem",
        entity_id=food_item.food_item_id,
        old_values=old_values,
        new_values={
            "name": food_item.name,
            "description": _audit_text(food_item.description),
        },
        correlation_id=correlation_id,
    )
    return food_item


def deactivate_food_item(
    *, food_item_id: int, expected_version: int, actor: User, correlation_id: str = ""
) -> FoodItem:
    """Super Admin deactivates a shared food item; it is never hard-deleted."""
    _require_super_admin(actor)
    changed = False
    with transaction.atomic():
        food_item = (
            FoodItem.objects.select_for_update()
            .filter(food_item_id=food_item_id)
            .first()
        )
        if not food_item:
            raise NotFoundError(code="OBJECT_NOT_FOUND", message="Food item not found.")
        check_optimistic_lock(food_item, expected_version)
        if food_item.status == "ACTIVE":
            food_item.status = "INACTIVE"
            food_item.version = F("version") + 1
            food_item.save(update_fields=["status", "version", "updated_at"])
            changed = True

    food_item.refresh_from_db()
    if changed:
        record_audit_event(
            event_type="FOOD_ITEM_DEACTIVATED",
            actor_user=actor,
            entity_type="FoodItem",
            entity_id=food_item.food_item_id,
            old_values={"status": "ACTIVE"},
            new_values={"status": food_item.status},
            correlation_id=correlation_id,
        )
    return food_item


# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------


def create_menu(
    *,
    hostel_id: int,
    year: int,
    month: int,
    actor: User,
    correlation_id: str = "",
) -> Menu:
    """Creates an empty DRAFT monthly menu for a hostel."""
    _author_role(actor)
    if month < 1 or month > 12:
        raise ValidationError(
            code="VALIDATION_ERROR", message="Menu month must be between 1 and 12."
        )
    hostel = get_hostel_for_author(actor, hostel_id)
    try:
        with transaction.atomic():
            menu = Menu.objects.create(
                hostel=hostel,
                menu_year=year,
                menu_month=month,
                status="DRAFT",
            )
    except IntegrityError:
        raise ConflictError(
            code="DUPLICATE_RESOURCE",
            message=f"A menu already exists for {hostel.code} in {year:04d}-{month:02d}.",
        )

    record_audit_event(
        event_type="MENU_CREATED",
        actor_user=actor,
        entity_type="Menu",
        entity_id=menu.menu_id,
        new_values={
            "menu_id": menu.menu_id,
            "hostel_id": hostel.hostel_id,
            "year": year,
            "month": month,
            "status": menu.status,
        },
        correlation_id=correlation_id,
    )
    return menu


@transaction.atomic
def set_menu_meal(
    *,
    menu_id: int,
    menu_date: date,
    meal_type_code: str,
    items: Iterable[dict[str, Any]],
    expected_version: int,
    actor: User,
    correlation_id: str = "",
) -> Menu:
    """
    Replaces the complete item list of one (date, meal type) in one call.
    An empty list clears the meal. Draft edits are silent; published edits audit
    MENU_REVISED with the old and the new item lists.
    """
    _author_role(actor)
    menu = (
        Menu.objects.select_for_update()
        .select_related("hostel")
        .filter(menu_id=menu_id)
        .first()
    )
    if not menu:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Menu not found.")
    get_menu_scoped(actor, menu.menu_id)
    check_optimistic_lock(menu, expected_version)
    _validate_menu_date(menu, menu_date)
    meal_type = _meal_type_by_code(meal_type_code)
    resolved_items = _resolve_food_items(items)

    existing = MenuMeal.objects.filter(
        menu=menu, menu_date=menu_date, meal_type=meal_type
    ).first()
    old_items = _item_snapshot(existing)
    was_published = menu.status == "PUBLISHED"

    if existing:
        menu_meal = existing
        menu_meal.status = menu.status
        menu_meal.save(update_fields=["status", "updated_at"])
        menu_meal.items.all().delete()
    else:
        menu_meal = MenuMeal.objects.create(
            menu=menu,
            menu_date=menu_date,
            meal_type=meal_type,
            status=menu.status,
        )

    MenuItem.objects.bulk_create(
        [
            MenuItem(
                menu_meal=menu_meal,
                food_item=row["food_item"],
                display_order=row["display_order"],
                notes=row["notes"],
            )
            for row in resolved_items
        ]
    )

    menu.version = F("version") + 1
    menu.save(update_fields=["version", "updated_at"])
    menu.refresh_from_db()

    if was_published:
        record_audit_event(
            event_type="MENU_REVISED",
            actor_user=actor,
            entity_type="Menu",
            entity_id=menu.menu_id,
            old_values={
                "menu_date": menu_date.isoformat(),
                "meal_type_code": meal_type.code,
                "items": old_items,
            },
            new_values={
                "menu_date": menu_date.isoformat(),
                "meal_type_code": meal_type.code,
                "items": [
                    {
                        "food_item_id": row["food_item"].food_item_id,
                        "name": row["food_item"].name,
                        "display_order": row["display_order"],
                        "notes": _audit_text(row["notes"]),
                    }
                    for row in resolved_items
                ],
            },
            correlation_id=correlation_id,
        )
    return menu_with_meals(menu)


@transaction.atomic
def publish_menu(
    *,
    menu_id: int,
    expected_version: int,
    actor: User,
    correlation_id: str = "",
) -> tuple[Menu, list[str]]:
    """
    DRAFT -> PUBLISHED. Missing dates are returned as warnings but do not block
    publication, because the specifications do not require full coverage.
    """
    _author_role(actor)
    menu = (
        Menu.objects.select_for_update()
        .select_related("hostel")
        .filter(menu_id=menu_id)
        .first()
    )
    if not menu:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Menu not found.")
    get_menu_scoped(actor, menu.menu_id)
    check_optimistic_lock(menu, expected_version)
    if menu.status == "PUBLISHED":
        raise ConflictError(
            code="CONFLICT", message="The menu is already published."
        )

    warnings = _dates_without_items(menu)
    now = clock.now()
    menu.status = "PUBLISHED"
    menu.published_at = now
    menu.published_by_user = actor
    menu.version = F("version") + 1
    menu.save(
        update_fields=[
            "status",
            "published_at",
            "published_by_user",
            "version",
            "updated_at",
        ]
    )
    menu.meals.all().update(status="PUBLISHED")
    menu.refresh_from_db()

    record_audit_event(
        event_type="MENU_PUBLISHED",
        actor_user=actor,
        entity_type="Menu",
        entity_id=menu.menu_id,
        old_values={"status": "DRAFT"},
        new_values={
            "status": "PUBLISHED",
            "hostel_id": menu.hostel_id,
            "year": menu.menu_year,
            "month": menu.menu_month,
            "published_at": now.isoformat(),
            "dates_without_items": len(warnings),
        },
        correlation_id=correlation_id,
    )
    return menu_with_meals(menu), warnings


@transaction.atomic
def copy_previous_month_pattern(
    *,
    menu_id: int,
    expected_version: int,
    actor: User,
    correlation_id: str = "",
) -> Menu:
    """
    Copies the previous month's weekday pattern into this DRAFT menu [REC].
    The first previous-month date for each weekday supplies that weekday's meals.
    """
    _author_role(actor)
    menu = (
        Menu.objects.select_for_update()
        .select_related("hostel")
        .filter(menu_id=menu_id)
        .first()
    )
    if not menu:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Menu not found.")
    get_menu_scoped(actor, menu.menu_id)
    check_optimistic_lock(menu, expected_version)
    if menu.status != "DRAFT":
        raise ConflictError(
            code="CONFLICT",
            message="Only a DRAFT menu can be populated from the previous month.",
        )

    previous_year, previous_month = _previous_month(menu.menu_year, menu.menu_month)
    previous_menu = Menu.objects.filter(
        hostel_id=menu.hostel_id,
        menu_year=previous_year,
        menu_month=previous_month,
    ).first()
    if not previous_menu:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message=(
                f"No menu exists for {previous_year:04d}-{previous_month:02d} "
                "to copy from."
            ),
        )

    source_meals = list(
        MenuMeal.objects.filter(menu=previous_menu)
        .select_related("meal_type")
        .prefetch_related("items__food_item")
        .order_by("menu_date", "meal_type__sequence_no")
    )
    first_date_by_weekday: dict[int, date] = {}
    for meal in source_meals:
        first_date_by_weekday.setdefault(meal.menu_date.weekday(), meal.menu_date)
    pattern = [
        meal
        for meal in source_meals
        if meal.menu_date == first_date_by_weekday[meal.menu_date.weekday()]
    ]

    MenuItem.objects.filter(menu_meal__menu=menu).delete()
    MenuMeal.objects.filter(menu=menu).delete()

    copied_meals = 0
    for target_date in _month_dates(menu.menu_year, menu.menu_month):
        for source in pattern:
            if source.menu_date.weekday() != target_date.weekday():
                continue
            target_meal = MenuMeal.objects.create(
                menu=menu,
                menu_date=target_date,
                meal_type=source.meal_type,
                status="DRAFT",
            )
            MenuItem.objects.bulk_create(
                [
                    MenuItem(
                        menu_meal=target_meal,
                        food_item=item.food_item,
                        display_order=item.display_order,
                        notes=item.notes,
                    )
                    for item in source.items.all()
                ]
            )
            copied_meals += 1

    menu.version = F("version") + 1
    menu.save(update_fields=["version", "updated_at"])
    menu.refresh_from_db()

    record_audit_event(
        event_type="MENU_COPIED_FROM_PREVIOUS",
        actor_user=actor,
        entity_type="Menu",
        entity_id=menu.menu_id,
        new_values={
            "menu_id": menu.menu_id,
            "source_year": previous_year,
            "source_month": previous_month,
            "copied_meals": copied_meals,
        },
        correlation_id=correlation_id,
    )
    return menu_with_meals(menu)
