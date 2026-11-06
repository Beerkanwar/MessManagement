"""
Mess domain services — Phase 5.
Implements:
- Mess master data management (Super Admin).
- Mess Manager staff accounts (Super Admin, DEC-21 single active manager per mess).
- Meal types read access.
- Meal occurrence generation and cancellation.
- Common meal rate effective-dating and versioning.
- Extra items and effective-dated extra pricing.
- Authoritative lookup service for rates, prices, occurrences, and scopes.
- Change signalling for sync cursors.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F, Q, QuerySet

from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.core.concurrency import check_optimistic_lock
from apps.core.exceptions import ConflictError, NotFoundError, ValidationError
from apps.hostel.models import Hostel, StudentMessAssignment
from apps.identity.models import Role, User, UserRole
from apps.identity.selectors import get_clerk_hostel, get_manager_mess, get_user_role
from apps.mess.models import (
    ExtraItem,
    ExtraPrice,
    MealOccurrence,
    MealRate,
    MealType,
    Mess,
    MessManagerAssignment,
)
from apps.sync.models import ChangeCursor


# ---------------------------------------------------------------------------
# Change Signalling [SPEC DBDD §11, Phase 5 build item 2]
# ---------------------------------------------------------------------------


def advance_change_cursor(cursor_key: str) -> int:
    """
    Advance the change cursor for the given aggregate key.
    Returns the new version number.
    """
    obj, created = ChangeCursor.objects.get_or_create(
        aggregate_type=cursor_key,
        defaults={"current_version": 1},
    )
    if not created:
        ChangeCursor.objects.filter(cursor_id=obj.cursor_id).update(
            current_version=F("current_version") + 1
        )
        obj.refresh_from_db()
    return obj.current_version


# ---------------------------------------------------------------------------
# 1. Mess Management (Super Admin) [Phase 5 build item 1]
# ---------------------------------------------------------------------------


@transaction.atomic
def create_mess(
    *,
    code: str,
    name: str,
    actor: User,
    correlation_id: str = "",
) -> Mess:
    """Create a new mess hall [SPEC DBDD §1, §5]."""
    clean_code = code.strip().upper()
    clean_name = name.strip()

    if not clean_code or not clean_name:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Mess code and name are required.",
        )

    if Mess.objects.filter(code=clean_code).exists():
        raise ConflictError(
            code="DUPLICATE_CODE",
            message=f"A mess with code '{clean_code}' already exists.",
        )

    mess = Mess.objects.create(
        code=clean_code,
        name=clean_name,
        status="ACTIVE",
        version=1,
    )

    advance_change_cursor("messes")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="Mess",
        entity_id=mess.mess_id,
        reason=f"Created mess {clean_code}",
        new_values={"code": mess.code, "name": mess.name, "status": mess.status},
        correlation_id=correlation_id,
    )

    return mess


@transaction.atomic
def update_mess(
    *,
    mess_id: int,
    name: str,
    version: int,
    actor: User,
    correlation_id: str = "",
) -> Mess:
    """Update a mess hall's display name with optimistic locking."""
    mess = Mess.objects.filter(mess_id=mess_id).first()
    if not mess:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Mess not found.")

    check_optimistic_lock(mess, version)

    clean_name = name.strip()
    if not clean_name:
        raise ValidationError(code="VALIDATION_ERROR", message="Mess name cannot be empty.")

    old_name = mess.name
    mess.name = clean_name
    mess.version += 1
    mess.save()

    advance_change_cursor("messes")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="Mess",
        entity_id=mess.mess_id,
        reason=f"Renamed mess from '{old_name}' to '{clean_name}'",
        old_values={"name": old_name},
        new_values={"name": clean_name},
        correlation_id=correlation_id,
    )

    return mess


@transaction.atomic
def deactivate_mess(
    *,
    mess_id: int,
    version: int,
    actor: User,
    correlation_id: str = "",
) -> Mess:
    """
    Deactivate a mess hall [SPEC DBDD §17].
    Refused while ACTIVE assignments or an active Manager exist.
    """
    mess = Mess.objects.filter(mess_id=mess_id).first()
    if not mess:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Mess not found.")

    check_optimistic_lock(mess, version)

    # Invariant: refused while ACTIVE student assignments exist
    if StudentMessAssignment.objects.filter(mess=mess, status="ACTIVE").exists():
        raise ConflictError(
            code="MESS_HAS_ACTIVE_ASSIGNMENTS",
            message="Cannot deactivate mess while active student assignments exist.",
        )

    # Invariant: refused while active Manager exists
    if MessManagerAssignment.objects.filter(mess=mess, is_active=True).exists():
        raise ConflictError(
            code="MESS_HAS_ACTIVE_MANAGER",
            message="Cannot deactivate mess while an active manager assignment exists.",
        )

    mess.status = "INACTIVE"
    mess.version += 1
    mess.save()

    advance_change_cursor("messes")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="Mess",
        entity_id=mess.mess_id,
        reason=f"Deactivated mess {mess.code}",
        old_values={"status": "ACTIVE"},
        new_values={"status": "INACTIVE"},
        correlation_id=correlation_id,
    )

    return mess


# ---------------------------------------------------------------------------
# 2. Mess Manager Accounts (Super Admin) [Phase 5 build item 2]
# ---------------------------------------------------------------------------


@transaction.atomic
def create_mess_manager(
    *,
    email: str,
    full_name: str,
    mess_code: str,
    phone_number: str = "",
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Create a new Mess Manager account with unusable password [SPEC DBDD §5, DEC-21].
    Enforces one active manager per mess.
    """
    normalized_email = email.strip().lower()
    if User.objects.filter(normalized_email=normalized_email).exists():
        raise ConflictError(
            code="DUPLICATE_EMAIL",
            message=f"A user with email '{normalized_email}' already exists.",
        )

    mess = Mess.objects.filter(code=mess_code.strip().upper(), status="ACTIVE").first()
    if not mess:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message=f"Active mess with code '{mess_code}' does not exist.",
        )

    # DEC-21: One active manager per mess
    if MessManagerAssignment.objects.filter(mess=mess, is_active=True).exists():
        raise ConflictError(
            code="MESS_ALREADY_HAS_MANAGER",
            message=f"Mess '{mess.code}' already has an active manager.",
        )

    role_obj = Role.objects.get(name="MESS_MANAGER")
    user = User.objects.create_user(
        email=normalized_email,
        full_name=full_name.strip(),
        phone_number=phone_number.strip(),
    )
    user.set_unusable_password()
    user.save()

    UserRole.objects.create(user=user, role=role_obj)

    assignment = MessManagerAssignment.objects.create(
        user=user,
        mess=mess,
        is_active=True,
        assigned_at=clock.now(),
        version=1,
    )

    advance_change_cursor(f"mess:{mess.mess_id}:manager")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="MessManagerAssignment",
        entity_id=assignment.assignment_id,
        reason=f"Created manager for mess {mess.code}",
        new_values={
            "user_id": user.user_id,
            "mess_code": mess.code,
            "assigned_at": str(assignment.assigned_at),
        },
        correlation_id=correlation_id,
    )

    return {
        "user_id": user.user_id,
        "email": user.normalized_email,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "mess": {"id": mess.mess_id, "code": mess.code, "name": mess.name},
        "assignment_id": assignment.assignment_id,
        "is_active": True,
        "assigned_at": assignment.assigned_at,
    }


@transaction.atomic
def reassign_mess_manager(
    *,
    user_id: int,
    new_mess_code: str,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Reassign a Mess Manager to a different mess.
    Deactivates old assignment, adds new one [SPEC DBDD §5, DEC-21].
    """
    user = User.objects.filter(user_id=user_id).first()
    if not user:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="User not found.")

    role = get_user_role(user)
    if role != "MESS_MANAGER":
        raise ValidationError(code="VALIDATION_ERROR", message="User is not a MESS_MANAGER.")

    new_mess = Mess.objects.filter(code=new_mess_code.strip().upper(), status="ACTIVE").first()
    if not new_mess:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message=f"Active mess '{new_mess_code}' not found.")

    # DEC-21: Enforce single active manager per mess
    existing_manager = MessManagerAssignment.objects.filter(mess=new_mess, is_active=True).first()
    if existing_manager and existing_manager.user_id != user.user_id:
        raise ConflictError(
            code="MESS_ALREADY_HAS_MANAGER",
            message=f"Mess '{new_mess.code}' already has an active manager.",
        )

    # Deactivate current active assignments
    old_assignments = MessManagerAssignment.objects.filter(user=user, is_active=True)
    old_mess_ids = list(old_assignments.values_list("mess_id", flat=True))
    old_assignments.update(is_active=False, deactivated_at=clock.now())

    # Create new assignment
    assignment = MessManagerAssignment.objects.create(
        user=user,
        mess=new_mess,
        is_active=True,
        assigned_at=clock.now(),
        version=1,
    )

    for mid in old_mess_ids:
        advance_change_cursor(f"mess:{mid}:manager")
    advance_change_cursor(f"mess:{new_mess.mess_id}:manager")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="MessManagerAssignment",
        entity_id=assignment.assignment_id,
        reason=f"Reassigned manager to mess {new_mess.code}",
        new_values={"new_mess_code": new_mess.code},
        correlation_id=correlation_id,
    )

    return {
        "user_id": user.user_id,
        "mess": {"id": new_mess.mess_id, "code": new_mess.code, "name": new_mess.name},
        "assignment_id": assignment.assignment_id,
        "is_active": True,
        "new_mess_code": new_mess.code,
    }


@transaction.atomic
def deactivate_mess_manager(
    *,
    user_id: int,
    actor: User,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Deactivate a Manager's active assignment."""
    user = User.objects.filter(user_id=user_id).first()
    if not user:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="User not found.")

    active_assignments = MessManagerAssignment.objects.filter(user=user, is_active=True)
    mess_ids = list(active_assignments.values_list("mess_id", flat=True))
    count = active_assignments.update(is_active=False, deactivated_at=clock.now())

    for mid in mess_ids:
        advance_change_cursor(f"mess:{mid}:manager")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="MessManagerAssignment",
        entity_id=user.user_id,
        reason="Deactivated manager assignment",
        correlation_id=correlation_id,
    )

    return {"user_id": user.user_id, "deactivated": count > 0}


# ---------------------------------------------------------------------------
# 3. Meal Types & Occurrences [Phase 5 build items 3 & 4]
# ---------------------------------------------------------------------------


def list_meal_types() -> QuerySet[MealType]:
    """Read-only listing of the four seeded meal types."""
    return MealType.objects.filter(is_active=True).order_by("sequence_no")


@transaction.atomic
def generate_meal_occurrences(
    *,
    horizon_days: int = 35,
    mess_code: str | None = None,
) -> dict[str, int]:
    """
    Idempotent daily occurrence generator [Phase 5 build item 4].
    Creates SCHEDULED occurrences from today to horizon_days forward for active messes.
    """
    messes_qs = Mess.objects.filter(status="ACTIVE")
    if mess_code:
        messes_qs = messes_qs.filter(code=mess_code.strip().upper())

    meal_types = list(MealType.objects.filter(is_active=True).order_by("sequence_no"))
    today = clock.today()

    created_count = 0
    skipped_count = 0

    for day_offset in range(horizon_days):
        occurrence_date = today + timedelta(days=day_offset)
        for mess in messes_qs:
            for mt in meal_types:
                _obj, created = MealOccurrence.objects.get_or_create(
                    mess=mess,
                    meal_date=occurrence_date,
                    meal_type=mt,
                    defaults={
                        "status": "SCHEDULED",
                        "configuration_version": 1,
                    },
                )
                if created:
                    created_count += 1
                else:
                    skipped_count += 1

    return {"created": created_count, "skipped": skipped_count}


@transaction.atomic
def cancel_meal_occurrence(
    *,
    occurrence_id: int,
    reason: str,
    actor: User,
    correlation_id: str = "",
) -> MealOccurrence:
    """
    Cancels a scheduled meal occurrence [SPEC DBDD §5].
    Refused if any MealConsumption exists for it.
    Increments configuration_version.
    """
    if not reason or len(reason.strip()) < 5:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="A cancellation reason of at least 5 characters is required.",
        )

    occurrence = (
        MealOccurrence.objects
        .select_related("mess", "meal_type")
        .filter(meal_occurrence_id=occurrence_id)
        .first()
    )
    if not occurrence:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Meal occurrence not found.")

    if occurrence.status == "CANCELLED":
        return occurrence

    # Check if consumption exists
    from apps.attendance.models import MealConsumption
    has_consumptions = MealConsumption.objects.filter(
        Q(meal_occurrence=occurrence) |
        Q(mess=occurrence.mess, meal_date=occurrence.meal_date, meal_type=occurrence.meal_type)
    ).exists()

    if has_consumptions:
        raise ConflictError(
            code="OCCURRENCE_HAS_CONSUMPTIONS",
            message="Cannot cancel a meal occurrence that already has recorded consumptions.",
        )

    occurrence.status = "CANCELLED"
    occurrence.configuration_version = F("configuration_version") + 1
    occurrence.save(update_fields=["status", "configuration_version", "updated_at"])
    occurrence.refresh_from_db()

    advance_change_cursor(f"mess:{occurrence.mess_id}:occurrences")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="MealOccurrence",
        entity_id=occurrence.meal_occurrence_id,
        reason=reason.strip(),
        old_values={"status": "SCHEDULED"},
        new_values={"status": "CANCELLED"},
        correlation_id=correlation_id,
    )

    return occurrence


# ---------------------------------------------------------------------------
# 4. Common Meal Rate [Phase 5 build item 5]
# ---------------------------------------------------------------------------


@transaction.atomic
def add_meal_rate(
    *,
    mess_id: int,
    rate: Decimal,
    effective_from: date,
    reason: str = "",
    actor: User,
    correlation_id: str = "",
) -> MealRate:
    """
    Creates a new effective-dated common meal rate [SPEC DBDD §5].
    EffectiveFrom is inclusive, EffectiveTo is exclusive.
    Must start today or later. Closes earlier open-ended rate at effective_from.
    """
    mess = Mess.objects.filter(mess_id=mess_id).first()
    if not mess:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Mess not found.")

    if rate <= Decimal("0"):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Meal rate must be greater than zero.",
        )

    today = clock.today()
    if effective_from < today:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Effective start date cannot be in the past.",
        )

    # Close previous active rates that extend into or beyond effective_from
    active_rates = MealRate.objects.filter(mess=mess).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gt=effective_from)
    )

    for prev in active_rates:
        if prev.effective_from < effective_from:
            prev.effective_to = effective_from
            prev.save(update_fields=["effective_to", "updated_at"])

    new_rate = MealRate.objects.create(
        mess=mess,
        rate=rate,
        effective_from=effective_from,
        effective_to=None,
        created_by=actor,
    )

    advance_change_cursor(f"mess:{mess.mess_id}:rates")

    record_audit_event(
        event_type="RATE_CHANGED",
        actor_user=actor,
        entity_type="MealRate",
        entity_id=new_rate.meal_rate_id,
        reason=reason or f"Rate updated to {rate} effective {effective_from}",
        new_values={
            "rate": str(rate),
            "effective_from": str(effective_from),
            "mess_code": mess.code,
        },
        correlation_id=correlation_id,
    )

    return new_rate


def list_meal_rates(mess_id: int) -> QuerySet[MealRate]:
    """Returns rate versions for a mess ordered by -effective_from."""
    return MealRate.objects.filter(mess_id=mess_id).order_by("-effective_from")


# ---------------------------------------------------------------------------
# 5. Extra Items & Prices [Phase 5 build item 6]
# ---------------------------------------------------------------------------


@transaction.atomic
def create_extra_item(
    *,
    name: str,
    hostel_id: int,
    initial_price: Decimal | None = None,
    effective_from: date | None = None,
    actor: User,
    correlation_id: str = "",
) -> ExtraItem:
    """
    Creates a new extra item for a hostel [SPEC DBDD §5].
    Optionally creates its initial effective-dated price.
    """
    clean_name = name.strip()
    if not clean_name:
        raise ValidationError(code="VALIDATION_ERROR", message="Extra item name cannot be empty.")

    hostel = Hostel.objects.filter(hostel_id=hostel_id).first()
    if not hostel:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Hostel not found.")

    norm_name = clean_name.upper()
    if ExtraItem.objects.filter(hostel=hostel, normalized_name=norm_name).exists():
        raise ConflictError(
            code="DUPLICATE_EXTRA_ITEM",
            message=f"An extra item named '{clean_name}' already exists in this hostel.",
        )

    item = ExtraItem.objects.create(
        hostel=hostel,
        name=clean_name,
        normalized_name=norm_name,
        status="ACTIVE",
        version=1,
    )

    if initial_price is not None:
        add_extra_price(
            extra_item_id=item.extra_item_id,
            unit_price=initial_price,
            effective_from=effective_from or clock.today(),
            reason="Initial price setup",
            actor=actor,
            correlation_id=correlation_id,
        )

    advance_change_cursor(f"hostel:{hostel.hostel_id}:extras")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="ExtraItem",
        entity_id=item.extra_item_id,
        reason=f"Created extra item {clean_name}",
        new_values={"name": clean_name, "hostel_code": hostel.code},
        correlation_id=correlation_id,
    )

    return item


@transaction.atomic
def update_extra_item(
    *,
    extra_item_id: int,
    name: str,
    version: int,
    actor: User,
    correlation_id: str = "",
) -> ExtraItem:
    """Update extra item name with optimistic locking."""
    item = ExtraItem.objects.filter(extra_item_id=extra_item_id).first()
    if not item:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Extra item not found.")

    check_optimistic_lock(item, version)

    clean_name = name.strip()
    if not clean_name:
        raise ValidationError(code="VALIDATION_ERROR", message="Extra item name cannot be empty.")

    norm_name = clean_name.upper()
    existing = ExtraItem.objects.filter(
        hostel=item.hostel, normalized_name=norm_name
    ).exclude(extra_item_id=item.extra_item_id).first()

    if existing:
        raise ConflictError(
            code="DUPLICATE_EXTRA_ITEM",
            message=f"An extra item named '{clean_name}' already exists in this hostel.",
        )

    old_name = item.name
    item.name = clean_name
    item.normalized_name = norm_name
    item.version += 1
    item.save()

    advance_change_cursor(f"hostel:{item.hostel_id}:extras")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="ExtraItem",
        entity_id=item.extra_item_id,
        reason=f"Renamed extra item from '{old_name}' to '{clean_name}'",
        old_values={"name": old_name},
        new_values={"name": clean_name},
        correlation_id=correlation_id,
    )

    return item


@transaction.atomic
def deactivate_extra_item(
    *,
    extra_item_id: int,
    version: int,
    actor: User,
    correlation_id: str = "",
) -> ExtraItem:
    """Deactivate an extra item."""
    item = ExtraItem.objects.filter(extra_item_id=extra_item_id).first()
    if not item:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Extra item not found.")

    check_optimistic_lock(item, version)

    item.status = "INACTIVE"
    item.version += 1
    item.save()

    advance_change_cursor(f"hostel:{item.hostel_id}:extras")

    record_audit_event(
        event_type="MASTER_DATA_CHANGED",
        actor_user=actor,
        entity_type="ExtraItem",
        entity_id=item.extra_item_id,
        reason=f"Deactivated extra item {item.name}",
        old_values={"status": "ACTIVE"},
        new_values={"status": "INACTIVE"},
        correlation_id=correlation_id,
    )

    return item


@transaction.atomic
def add_extra_price(
    *,
    extra_item_id: int,
    unit_price: Decimal,
    effective_from: date,
    reason: str = "",
    actor: User,
    correlation_id: str = "",
) -> ExtraPrice:
    """
    Creates a new effective-dated price for an ExtraItem [SPEC DBDD §5, CONFLICT-06].
    EffectiveFrom is inclusive, EffectiveTo is exclusive.
    Must start today or later. Closes earlier open-ended price.
    """
    item = ExtraItem.objects.filter(extra_item_id=extra_item_id).first()
    if not item:
        raise NotFoundError(code="OBJECT_NOT_FOUND", message="Extra item not found.")

    if unit_price < Decimal("0"):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Unit price cannot be negative.",
        )

    today = clock.today()
    if effective_from < today:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Effective start date cannot be in the past.",
        )

    # Close previous active prices
    active_prices = ExtraPrice.objects.filter(extra_item=item).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gt=effective_from)
    )

    for prev in active_prices:
        if prev.effective_from < effective_from:
            prev.effective_to = effective_from
            prev.save(update_fields=["effective_to", "updated_at"])

    new_price = ExtraPrice.objects.create(
        extra_item=item,
        unit_price=unit_price,
        effective_from=effective_from,
        effective_to=None,
        created_by=actor,
    )

    advance_change_cursor(f"extra_item:{item.extra_item_id}:prices")

    record_audit_event(
        event_type="RATE_CHANGED",
        actor_user=actor,
        entity_type="ExtraPrice",
        entity_id=new_price.extra_price_id,
        reason=reason or f"Extra price updated to {unit_price} effective {effective_from}",
        new_values={
            "unit_price": str(unit_price),
            "effective_from": str(effective_from),
            "extra_item": item.name,
        },
        correlation_id=correlation_id,
    )

    return new_price


def list_extra_prices(extra_item_id: int) -> QuerySet[ExtraPrice]:
    """Returns price versions for an extra item ordered by -effective_from."""
    return ExtraPrice.objects.filter(extra_item_id=extra_item_id).order_by("-effective_from")


# ---------------------------------------------------------------------------
# 6. Authoritative Lookup Service [Phase 5 build item 7]
# ---------------------------------------------------------------------------


def get_meal_rate(mess: Mess | int, target_date: date) -> Decimal | None:
    """
    Looks up the common meal rate for (mess, target_date).
    Boundary: effective_from is inclusive, effective_to is exclusive.
    Returns None if no rate covers that date.
    """
    mess_id = mess.mess_id if isinstance(mess, Mess) else mess
    rate_obj = (
        MealRate.objects
        .filter(mess_id=mess_id, effective_from__lte=target_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=target_date))
        .order_by("-effective_from")
        .first()
    )
    return rate_obj.rate if rate_obj else None


def get_extra_price(extra_item: ExtraItem | int, target_date: date) -> Decimal | None:
    """
    Looks up the extra item price for (extra_item, target_date).
    Boundary: effective_from is inclusive, effective_to is exclusive.
    Returns None if no price covers that date.
    """
    item_id = extra_item.extra_item_id if isinstance(extra_item, ExtraItem) else extra_item
    price_obj = (
        ExtraPrice.objects
        .filter(extra_item_id=item_id, effective_from__lte=target_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=target_date))
        .order_by("-effective_from")
        .first()
    )
    return price_obj.unit_price if price_obj else None


def is_meal_scheduled(
    mess: Mess | int,
    meal_date: date,
    meal_type: MealType | str | int,
) -> bool:
    """Checks whether an occurrence exists and is SCHEDULED."""
    mess_id = mess.mess_id if isinstance(mess, Mess) else mess
    q = Q(mess_id=mess_id, meal_date=meal_date, status="SCHEDULED")

    if isinstance(meal_type, MealType):
        q &= Q(meal_type=meal_type)
    elif isinstance(meal_type, int):
        q &= Q(meal_type_id=meal_type)
    else:
        q &= Q(meal_type__code=str(meal_type).upper())

    return MealOccurrence.objects.filter(q).exists()


def get_meal_occurrence(
    mess: Mess | int,
    meal_date: date,
    meal_type: MealType | str | int,
) -> MealOccurrence | None:
    """Returns the MealOccurrence instance or None."""
    mess_id = mess.mess_id if isinstance(mess, Mess) else mess
    q = Q(mess_id=mess_id, meal_date=meal_date)

    if isinstance(meal_type, MealType):
        q &= Q(meal_type=meal_type)
    elif isinstance(meal_type, int):
        q &= Q(meal_type_id=meal_type)
    else:
        q &= Q(meal_type__code=str(meal_type).upper())

    return MealOccurrence.objects.filter(q).select_related("mess", "meal_type").first()


def get_manager_scope(user: User) -> Mess | None:
    """Returns the single active mess assigned to the Manager."""
    return get_manager_mess(user)


def get_clerk_scope(user: User) -> Hostel | None:
    """Returns the single active hostel assigned to the Clerk."""
    return get_clerk_hostel(user)

