"""
Attendance domain services [SPEC SDD §52, §77, DBDD §6, §11, ImplementationGuide Phase 7].
Implements:
- record_meal: Central meal acceptance rules pipeline.
- record_extra: Central extra item acceptance rules.
- apply_attendance_correction: Online attendance corrections (ADD_MISSING / REMOVE_INCORRECT).
- Duplicate and idempotency handling inside savepoints.
- Audit event recording within the same database transaction.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import uuid
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from zoneinfo import ZoneInfo

from apps.attendance.models import AttendanceCorrection, ExtraTransaction, MealConsumption
from apps.audit.services import record_audit_event
from apps.billing.models import BillingPeriod
from apps.config.services import get_int_setting
from apps.core.clock import clock
from apps.core.exceptions import ConflictError, NotFoundError, ValidationError
from apps.hostel.models import Hostel, HostelClerkAssignment, Student, StudentMessAssignment
from apps.identity.models import DeviceRegistration, User
from apps.identity.selectors import get_user_role
from apps.mess.models import ExtraItem, MealOccurrence, MealType, Mess, MessManagerAssignment
from apps.mess.services import get_clerk_scope, get_extra_price, get_manager_scope, get_meal_rate
from apps.pause.models import MessPause

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class RecordMealResult:
    """Outcome of record_meal domain command."""
    status: str  # "SYNCHRONIZED", "IDEMPOTENT_SUCCESS", "DUPLICATE", "REJECTED", "CONFLICT"
    meal_consumption: MealConsumption | None = None
    code: str = ""
    message: str = ""
    price: Decimal = Decimal("0.0000")
    transaction_id: uuid.UUID | None = None


@dataclass
class RecordExtraResult:
    """Outcome of record_extra domain command."""
    status: str  # "SYNCHRONIZED", "IDEMPOTENT_SUCCESS", "DUPLICATE", "REJECTED", "CONFLICT"
    extra_transaction: ExtraTransaction | None = None
    code: str = ""
    message: str = ""
    unit_price: Decimal = Decimal("0.0000")
    total_amount: Decimal = Decimal("0.0000")
    transaction_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# 1. record_meal command [SPEC SDD §52, §77, DBDD §11]
# ---------------------------------------------------------------------------

@transaction.atomic
def record_meal(
    *,
    transaction_id: uuid.UUID | str,
    student: Student | int,
    meal_date: date,
    meal_type: MealType | str | int,
    mess: Mess | int,
    recorded_by_user: User,
    roll_number_snapshot: str = "",
    transaction_timestamp: datetime | None = None,
    verification_method: str = "QR_HMAC_SHA256",
    verification_result: str = "SUCCESS",
    device_registration: DeviceRegistration | None = None,
    source: str = "QR",
    correlation_id: str = "",
) -> RecordMealResult:
    """
    Executes the 9-step meal acceptance rules pipeline in order [SPEC SDD §52]:
    1. Caller is active Manager on active device; transaction mess is Manager's mess.
    2. Structure validation.
    3. Meal type is Breakfast, Lunch or Dinner (Snacks rejected).
    4. MealOccurrence exists (Missing -> REJECTED; Cancelled -> CONFLICT).
    5. Student active, active assignment on MealDate matches this mess.
    6. Pause check (ACTIVE pause -> meal accepted, pause CANCELLED with MEAL_TAKEN, audited).
    7. BillingPeriod check (LOCKED -> late meal accepted per DEC-05).
    8. Price snapshot lookup (Server looks up common rate).
    9. Duplicate and idempotency handling (inside savepoint).
    """
    if isinstance(transaction_id, str):
        transaction_id = uuid.UUID(transaction_id)

    # Fast-path idempotency check before locking
    existing_by_txn = MealConsumption.objects.filter(transaction_id=transaction_id).first()
    if existing_by_txn:
        return RecordMealResult(
            status="IDEMPOTENT_SUCCESS",
            meal_consumption=existing_by_txn,
            code="IDEMPOTENT_SUCCESS",
            message="Transaction already processed successfully.",
            price=existing_by_txn.price_at_transaction,
            transaction_id=transaction_id,
        )

    # Resolve mess
    if isinstance(mess, int):
        mess_obj = Mess.objects.filter(mess_id=mess).first()
        if not mess_obj:
            return RecordMealResult(
                status="REJECTED",
                code="MESS_NOT_FOUND",
                message=f"Mess ID {mess} not found.",
                transaction_id=transaction_id,
            )
    else:
        mess_obj = mess

    # Step 1: Caller & Device Check
    role = get_user_role(recorded_by_user)
    if role == "MESS_MANAGER":
        manager_mess = get_manager_scope(recorded_by_user)
        if not manager_mess or manager_mess.mess_id != mess_obj.mess_id:
            return RecordMealResult(
                status="REJECTED",
                code="MESS_SCOPE_MISMATCH",
                message="Manager is not assigned to this mess [SRS-AC-11].",
                transaction_id=transaction_id,
            )
        if device_registration and device_registration.session_status != "ACTIVE":
            return RecordMealResult(
                status="REJECTED",
                code="DEVICE_NOT_ACTIVE",
                message="Device session is not active.",
                transaction_id=transaction_id,
            )
    elif role == "SUPER_ADMIN" or getattr(recorded_by_user, "is_superuser", False):
        pass
    else:
        return RecordMealResult(
            status="REJECTED",
            code="UNAUTHORIZED_ROLE",
            message="Only Mess Managers and Super Admins may record meals.",
            transaction_id=transaction_id,
        )

    # Step 2: Resolve Student
    if isinstance(student, int):
        student_obj = Student.objects.filter(student_id=student).select_related("user", "hostel").first()
    else:
        student_obj = student

    if not student_obj or student_obj.status != "ACTIVE":
        return RecordMealResult(
            status="REJECTED",
            code="STUDENT_INACTIVE",
            message="Student not found or inactive.",
            transaction_id=transaction_id,
        )

    if not roll_number_snapshot:
        roll_number_snapshot = student_obj.roll_number

    # Step 3: Resolve MealType (Snacks is extra, not meal)
    if isinstance(meal_type, MealType):
        meal_type_obj = meal_type
    elif isinstance(meal_type, int) or (isinstance(meal_type, str) and meal_type.isdigit()):
        meal_type_obj = MealType.objects.filter(meal_type_id=int(meal_type)).first()
    else:
        meal_type_obj = MealType.objects.filter(code__iexact=str(meal_type).strip()).first()

    if not meal_type_obj:
        return RecordMealResult(
            status="REJECTED",
            code="INVALID_MEAL_TYPE",
            message="Invalid meal type specified.",
            transaction_id=transaction_id,
        )

    if meal_type_obj.code in ["SNACKS", "EVENING_SNACKS"]:
        return RecordMealResult(
            status="REJECTED",
            code="SNACKS_IS_EXTRA",
            message="Evening Snacks is an extra item, not a standard meal [SPEC SRS §14.3].",
            transaction_id=transaction_id,
        )

    # Step 4: MealOccurrence check
    occurrence = MealOccurrence.objects.filter(
        mess=mess_obj, meal_date=meal_date, meal_type=meal_type_obj
    ).first()
    if not occurrence:
        return RecordMealResult(
            status="REJECTED",
            code="MEAL_NOT_SCHEDULED",
            message=f"No meal scheduled for {mess_obj.name} on {meal_date} ({meal_type_obj.code}).",
            transaction_id=transaction_id,
        )
    if occurrence.status == "CANCELLED":
        return RecordMealResult(
            status="CONFLICT",
            code="MEAL_CANCELLED",
            message="Scheduled meal occurrence was cancelled.",
            transaction_id=transaction_id,
        )

    # Step 5: Student assignment on MealDate check
    assignment_on_date = (
        StudentMessAssignment.objects.filter(
            student=student_obj,
            effective_from__lte=meal_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=meal_date))
        .filter(status__in=["ACTIVE", "ENDED"])
        .order_by("-effective_from")
        .first()
    )

    if not assignment_on_date:
        return RecordMealResult(
            status="CONFLICT",
            code="NO_ASSIGNMENT_ON_DATE",
            message="Student had no active mess assignment on MealDate.",
            transaction_id=transaction_id,
        )

    if assignment_on_date.mess_id != mess_obj.mess_id:
        return RecordMealResult(
            status="CONFLICT",
            code="ASSIGNMENT_MISMATCH",
            message="Student was assigned to a different mess on MealDate [SPEC SRS §27, DBDD §11.1].",
            transaction_id=transaction_id,
        )

    # Step 6: Pause check (Owner change D23 / DBDD-AC-27)
    active_pause = MessPause.objects.filter(student=student_obj, status="ACTIVE").first()
    if active_pause:
        p_start = active_pause.effective_start_date or active_pause.requested_start_date
        p_end = active_pause.effective_end_date or active_pause.requested_end_date
        if p_start <= meal_date <= p_end:
            # Meal is accepted, pause is cancelled
            active_pause.status = "CANCELLED"
            active_pause.cancellation_reason = "MEAL_TAKEN"
            active_pause.cancelled_at = clock.now()
            active_pause.save(update_fields=["status", "cancellation_reason", "cancelled_at", "updated_at", "version"])

            record_audit_event(
                event_type="PAUSE_CANCELLED",
                actor_user=recorded_by_user,
                entity_type="MessPause",
                entity_id=active_pause.pause_id,
                reason="MEAL_TAKEN",
                old_values={"status": "ACTIVE"},
                new_values={"status": "CANCELLED", "cancellation_reason": "MEAL_TAKEN"},
                correlation_id=correlation_id,
            )

    # Step 7: Billing Period lock check (DEC-05)
    # Note: A late meal is accepted and recorded; it does not change a locked bill (handled at billing generation)
    # So we proceed normally.

    # Step 8: Price snapshot lookup (DEC-16)
    price = get_meal_rate(mess_obj, meal_date)
    if price is None:
        price = Decimal("0.0000")

    txn_ts = transaction_timestamp or clock.now()

    # Step 9: Savepoint insertion for duplicate and concurrency safety [DBDD §18.2]
    # Check if duplicate slot already exists before attempting insert
    existing_by_slot = MealConsumption.objects.filter(
        student=student_obj, meal_date=meal_date, meal_type=meal_type_obj
    ).first()
    if existing_by_slot:
        return RecordMealResult(
            status="DUPLICATE",
            meal_consumption=existing_by_slot,
            code="DUPLICATE",
            message="Student has already consumed a meal for this date and slot [Invariant 4].",
            price=Decimal("0.0000"),
            transaction_id=transaction_id,
        )

    try:
        with transaction.atomic():
            meal = MealConsumption.objects.create(
                transaction_id=transaction_id,
                student=student_obj,
                roll_number_snapshot=roll_number_snapshot,
                mess=mess_obj,
                meal_type=meal_type_obj,
                meal_date=meal_date,
                meal_occurrence=occurrence,
                price_at_transaction=price,
                transaction_timestamp=txn_ts,
                verification_method=verification_method,
                verification_result=verification_result,
                device_registration=device_registration,
                recorded_by_user=recorded_by_user,
                source=source,
                sync_status="SYNCHRONIZED",
                accepted_at=clock.now(),
            )

            # Audit record inside the same database transaction [SPEC SDD §77]
            record_audit_event(
                event_type="MEAL_RECORDED",
                actor_user=recorded_by_user,
                entity_type="MealConsumption",
                entity_id=meal.meal_consumption_id,
                new_values={
                    "student_id": student_obj.student_id,
                    "roll_number": student_obj.roll_number,
                    "mess_id": mess_obj.mess_id,
                    "meal_type": meal_type_obj.code,
                    "meal_date": str(meal_date),
                    "price": str(price),
                    "transaction_id": str(transaction_id),
                },
                correlation_id=correlation_id,
            )

        return RecordMealResult(
            status="SYNCHRONIZED",
            meal_consumption=meal,
            code="SYNCHRONIZED",
            message="Meal recorded successfully.",
            price=price,
            transaction_id=transaction_id,
        )
    except IntegrityError:
        # Case A: Same transaction id arrived concurrently
        dup_tx = MealConsumption.objects.filter(transaction_id=transaction_id).first()
        if dup_tx:
            return RecordMealResult(
                status="IDEMPOTENT_SUCCESS",
                meal_consumption=dup_tx,
                code="IDEMPOTENT_SUCCESS",
                message="Idempotent replay of existing transaction.",
                price=dup_tx.price_at_transaction,
                transaction_id=transaction_id,
            )

        # Case B: Another transaction already claimed this (student, date, meal_type) slot
        dup_slot = MealConsumption.objects.filter(
            student=student_obj, meal_date=meal_date, meal_type=meal_type_obj
        ).first()
        if dup_slot:
            return RecordMealResult(
                status="DUPLICATE",
                meal_consumption=dup_slot,
                code="DUPLICATE",
                message="Student has already consumed a meal for this date and slot [Invariant 4].",
                price=Decimal("0.0000"),
                transaction_id=transaction_id,
            )
        return RecordMealResult(
            status="CONFLICT",
            code="INTEGRITY_CONFLICT",
            message="Unique constraint violation during meal recording.",
            transaction_id=transaction_id,
        )
        raise


# ---------------------------------------------------------------------------
# 2. record_extra command [SPEC SRS §14.3, SRS-AC-8, DEC-05]
# ---------------------------------------------------------------------------

@transaction.atomic
def record_extra(
    *,
    transaction_id: uuid.UUID | str,
    student: Student | int,
    extra_item: ExtraItem | int,
    quantity: int,
    mess: Mess | int,
    recorded_by_user: User,
    transaction_timestamp: datetime | None = None,
    device_registration: DeviceRegistration | None = None,
    source: str = "SCAN_CONFIRMATION",
    correlation_id: str = "",
) -> RecordExtraResult:
    """
    Executes extra item acceptance rules:
    - Active extra item.
    - Item's hostel equals student's hostel on transaction IST date.
    - Quantity is a positive whole number (> 0).
    - Unit price looked up for transaction date; total = quantity * unit_price.
    - Late extra for a LOCKED billing period becomes CONFLICT (DEC-05).
    - Savepoint & idempotency handling.
    """
    if isinstance(transaction_id, str):
        transaction_id = uuid.UUID(transaction_id)

    # Idempotency check
    existing_by_txn = ExtraTransaction.objects.filter(transaction_id=transaction_id).first()
    if existing_by_txn:
        return RecordExtraResult(
            status="IDEMPOTENT_SUCCESS",
            extra_transaction=existing_by_txn,
            code="IDEMPOTENT_SUCCESS",
            message="Extra transaction already processed successfully.",
            unit_price=existing_by_txn.unit_price_at_transaction,
            total_amount=existing_by_txn.total_amount,
            transaction_id=transaction_id,
        )

    # Quantity validation: Must be an integer > 0
    if not isinstance(quantity, int) or quantity <= 0:
        return RecordExtraResult(
            status="REJECTED",
            code="INVALID_QUANTITY",
            message="Extra quantity must be a positive whole number (> 0).",
            transaction_id=transaction_id,
        )

    # Resolve mess
    if isinstance(mess, int):
        mess_obj = Mess.objects.filter(mess_id=mess).first()
        if not mess_obj:
            return RecordExtraResult(
                status="REJECTED",
                code="MESS_NOT_FOUND",
                message=f"Mess ID {mess} not found.",
                transaction_id=transaction_id,
            )
    else:
        mess_obj = mess

    # Caller scope check
    role = get_user_role(recorded_by_user)
    if role == "MESS_MANAGER":
        manager_mess = get_manager_scope(recorded_by_user)
        if not manager_mess or manager_mess.mess_id != mess_obj.mess_id:
            return RecordExtraResult(
                status="REJECTED",
                code="MESS_SCOPE_MISMATCH",
                message="Manager is not assigned to this mess.",
                transaction_id=transaction_id,
            )
        if device_registration and device_registration.session_status != "ACTIVE":
            return RecordExtraResult(
                status="REJECTED",
                code="DEVICE_NOT_ACTIVE",
                message="Device session is not active.",
                transaction_id=transaction_id,
            )
    elif role == "SUPER_ADMIN" or getattr(recorded_by_user, "is_superuser", False):
        pass
    else:
        return RecordExtraResult(
            status="REJECTED",
            code="UNAUTHORIZED_ROLE",
            message="Only Mess Managers and Super Admins may record extras.",
            transaction_id=transaction_id,
        )

    # Resolve student
    if isinstance(student, int):
        student_obj = Student.objects.filter(student_id=student).select_related("hostel").first()
    else:
        student_obj = student

    if not student_obj or student_obj.status != "ACTIVE":
        return RecordExtraResult(
            status="REJECTED",
            code="STUDENT_INACTIVE",
            message="Student not found or inactive.",
            transaction_id=transaction_id,
        )

    # Resolve ExtraItem
    if isinstance(extra_item, int):
        item_obj = ExtraItem.objects.filter(extra_item_id=extra_item).select_related("hostel").first()
    else:
        item_obj = extra_item

    if not item_obj:
        return RecordExtraResult(
            status="REJECTED",
            code="EXTRA_ITEM_NOT_FOUND",
            message="Extra item not found.",
            transaction_id=transaction_id,
        )

    if item_obj.status != "ACTIVE":
        return RecordExtraResult(
            status="REJECTED",
            code="EXTRA_ITEM_INACTIVE",
            message="Extra item is inactive.",
            transaction_id=transaction_id,
        )

    txn_ts = transaction_timestamp or clock.now()
    # Transaction IST date
    ist_date = txn_ts.astimezone(IST).date()

    # Hostel check: Item's hostel must equal student's hostel on transaction IST date
    if item_obj.hostel_id != student_obj.hostel_id:
        return RecordExtraResult(
            status="REJECTED",
            code="HOSTEL_MISMATCH",
            message="Extra item does not belong to the student's assigned hostel [SRS-AC-8].",
            transaction_id=transaction_id,
        )

    # Billing period locked check: A late extra for a locked period is CONFLICT (DEC-05)
    billing_period = BillingPeriod.objects.filter(year=ist_date.year, month=ist_date.month).first()
    if billing_period and billing_period.status == "LOCKED":
        return RecordExtraResult(
            status="CONFLICT",
            code="BILLING_PERIOD_LOCKED",
            message="Billing period for this date is locked; extra submitted as conflict [DEC-05].",
            transaction_id=transaction_id,
        )

    # Unit price lookup
    unit_price = get_extra_price(item_obj, ist_date)
    if unit_price is None:
        return RecordExtraResult(
            status="REJECTED",
            code="NO_PRICE_FOUND",
            message=f"No active price found for extra item on {ist_date}.",
            transaction_id=transaction_id,
        )

    total_amount = Decimal(quantity) * unit_price

    try:
        with transaction.atomic():
            extra_tx = ExtraTransaction.objects.create(
                transaction_id=transaction_id,
                student=student_obj,
                hostel=student_obj.hostel,
                mess=mess_obj,
                extra_item=item_obj,
                quantity=quantity,
                unit_price_at_transaction=unit_price,
                total_amount=total_amount,
                transaction_timestamp=txn_ts,
                recorded_by_user=recorded_by_user,
                device_registration=device_registration,
                source=source,
                sync_status="SYNCHRONIZED",
                accepted_at=clock.now(),
            )

            record_audit_event(
                event_type="EXTRA_RECORDED",
                actor_user=recorded_by_user,
                entity_type="ExtraTransaction",
                entity_id=extra_tx.extra_transaction_id,
                new_values={
                    "student_id": student_obj.student_id,
                    "extra_item_id": item_obj.extra_item_id,
                    "quantity": quantity,
                    "unit_price": str(unit_price),
                    "total_amount": str(total_amount),
                    "transaction_id": str(transaction_id),
                },
                correlation_id=correlation_id,
            )

        return RecordExtraResult(
            status="SYNCHRONIZED",
            extra_transaction=extra_tx,
            code="SYNCHRONIZED",
            message="Extra transaction recorded successfully.",
            unit_price=unit_price,
            total_amount=total_amount,
            transaction_id=transaction_id,
        )
    except IntegrityError:
        dup = ExtraTransaction.objects.filter(transaction_id=transaction_id).first()
        if dup:
            return RecordExtraResult(
                status="IDEMPOTENT_SUCCESS",
                extra_transaction=dup,
                code="IDEMPOTENT_SUCCESS",
                message="Idempotent replay of existing transaction.",
                unit_price=dup.unit_price_at_transaction,
                total_amount=dup.total_amount,
                transaction_id=transaction_id,
            )
        raise


# ---------------------------------------------------------------------------
# 3. apply_attendance_correction [SPEC SRS §32, DEC-12, DEC-22, D12]
# ---------------------------------------------------------------------------

@transaction.atomic
def apply_attendance_correction(
    *,
    correction_transaction_id: uuid.UUID | str,
    student_id: int,
    meal_date: date,
    meal_type: MealType | str | int,
    action: str,  # "ADD_MISSING" or "REMOVE_INCORRECT"
    reason: str,
    actor: User,
    correlation_id: str = "",
) -> AttendanceCorrection:
    """
    Online attendance correction service [SPEC SRS §32, DEC-12, DEC-22, Owner change D12].
    - Who may correct: Super Admin for all, Hostel Clerk for own hostel, Mess Manager for own mess; else 404.
    - Required: reason (min 5 chars).
    - Within correction window (default 48 hours after MealDate per attendance.correction_window_hours).
    - Billing period not locked.
    - Idempotent by correction_transaction_id.
    - ADD_MISSING: on empty slot creates MealConsumption (Source CORRECTION) + correction; on removed slot reinstates.
    - REMOVE_INCORRECT: needs effective row, creates correction row only.
    - Audits ATTENDANCE_CORRECTED.
    """
    if isinstance(correction_transaction_id, str):
        correction_transaction_id = uuid.UUID(correction_transaction_id)

    # Idempotency
    existing = AttendanceCorrection.objects.filter(
        correction_transaction_id=correction_transaction_id
    ).first()
    if existing:
        return existing

    # 1. Reason validation (min 5 characters)
    if not reason or len(reason.strip()) < 5:
        raise ValidationError(
            code="REASON_REQUIRED",
            message="Correction reason is required and must be at least 5 characters.",
        )

    # 2. Action validation
    if action not in ["ADD_MISSING", "REMOVE_INCORRECT"]:
        raise ValidationError(
            code="INVALID_ACTION",
            message=f"Action must be 'ADD_MISSING' or 'REMOVE_INCORRECT', got '{action}'.",
        )

    # 3. Student & Assignment lookup
    student = Student.objects.filter(student_id=student_id).select_related("user", "hostel").first()
    if not student:
        raise NotFoundError("Student not found.")

    # Find assignment covering meal_date
    assignment = (
        StudentMessAssignment.objects.filter(
            student=student,
            effective_from__lte=meal_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=meal_date))
        .filter(status__in=["ACTIVE", "ENDED"])
        .order_by("-effective_from")
        .first()
    )
    if not assignment:
        raise NotFoundError("Student had no active mess assignment on MealDate.")

    target_mess = assignment.mess
    target_hostel = assignment.hostel or student.hostel

    # 4. Scope & Permission Check (Owner change D12, CONFLICT-11)
    # Super Admin: any student. Hostel Clerk: own hostel. Mess Manager: own mess. Anyone else: 404!
    role = get_user_role(actor)
    if role == "SUPER_ADMIN" or getattr(actor, "is_superuser", False):
        pass
    elif role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_scope(actor)
        if not clerk_hostel or clerk_hostel.hostel_id != target_hostel.hostel_id:
            raise NotFoundError("Student does not belong to clerk's assigned hostel [D12].")
    elif role == "MESS_MANAGER":
        manager_mess = get_manager_scope(actor)
        if not manager_mess or manager_mess.mess_id != target_mess.mess_id:
            raise NotFoundError("Student was not assigned to manager's mess on MealDate [D12].")
    else:
        raise NotFoundError("Not authorized to submit attendance corrections [D12].")

    # 5. Billing Period Locked Check (DEC-05)
    billing_period = BillingPeriod.objects.filter(year=meal_date.year, month=meal_date.month).first()
    if billing_period and billing_period.status == "LOCKED":
        raise ValidationError(
            code="BILLING_PERIOD_LOCKED",
            message="Billing period for this meal date is locked; corrections are prohibited [DEC-05].",
        )

    # 6. Correction window check (default 48h after MealDate)
    window_hours = get_int_setting("attendance.correction_window_hours", default=48)
    # MealDate ends at 23:59:59 IST; deadline is + window_hours
    meal_date_end_ist = datetime.combine(meal_date, time(23, 59, 59), tzinfo=IST)
    deadline_utc = meal_date_end_ist + timedelta(hours=window_hours)

    if clock.now() > deadline_utc:
        raise ValidationError(
            code="CORRECTION_PERIOD_EXPIRED",
            message=f"Correction window of {window_hours} hours after MealDate has expired [DEC-11].",
        )

    # Resolve meal_type
    if isinstance(meal_type, MealType):
        meal_type_obj = meal_type
    elif isinstance(meal_type, int) or (isinstance(meal_type, str) and meal_type.isdigit()):
        meal_type_obj = MealType.objects.filter(meal_type_id=int(meal_type)).first()
    else:
        meal_type_obj = MealType.objects.filter(code__iexact=str(meal_type).strip()).first()

    if not meal_type_obj:
        raise ValidationError(code="INVALID_MEAL_TYPE", message="Invalid meal type specified.")

    now = clock.now()

    # Find existing MealConsumption for (student, meal_date, meal_type)
    existing_meal = MealConsumption.objects.filter(
        student=student, meal_date=meal_date, meal_type=meal_type_obj
    ).first()

    # Determine current effective attendance state
    is_currently_effective = False
    if existing_meal:
        latest_corr = (
            AttendanceCorrection.objects.filter(
                student=student, meal_date=meal_date, meal_type=meal_type_obj, status="APPLIED"
            )
            .order_by("-requested_at", "-correction_id")
            .first()
        )
        if latest_corr is None:
            is_currently_effective = True
        else:
            is_currently_effective = (latest_corr.action != "REMOVE_INCORRECT")

    # 7. Apply Action
    if action == "REMOVE_INCORRECT":
        if not is_currently_effective or not existing_meal:
            raise ValidationError(
                code="NO_EFFECTIVE_MEAL",
                message="Cannot remove attendance: no effective meal consumption found for this slot.",
            )

        correction = AttendanceCorrection.objects.create(
            correction_transaction_id=correction_transaction_id,
            student=student,
            mess=existing_meal.mess,
            meal_date=meal_date,
            meal_type=meal_type_obj,
            action="REMOVE_INCORRECT",
            original_meal_consumption=existing_meal,
            requested_at=now,
            applied_at=now,
            reason=reason.strip(),
            actor_user=actor,
            status="APPLIED",
        )

        record_audit_event(
            event_type="ATTENDANCE_CORRECTED",
            actor_user=actor,
            entity_type="MealConsumption",
            entity_id=existing_meal.meal_consumption_id,
            reason=reason.strip(),
            old_values={"effective_attendance": True},
            new_values={"effective_attendance": False, "action": "REMOVE_INCORRECT"},
            correlation_id=correlation_id,
        )
        return correction

    else:  # ADD_MISSING
        if is_currently_effective:
            raise ValidationError(
                code="ALREADY_EFFECTIVE",
                message="Meal attendance is already recorded and effective for this slot.",
            )

        if existing_meal:
            # Row exists (was previously removed); reinstate via new ADD_MISSING correction
            correction = AttendanceCorrection.objects.create(
                correction_transaction_id=correction_transaction_id,
                student=student,
                mess=existing_meal.mess,
                meal_date=meal_date,
                meal_type=meal_type_obj,
                action="ADD_MISSING",
                original_meal_consumption=existing_meal,
                requested_at=now,
                applied_at=now,
                reason=reason.strip(),
                actor_user=actor,
                status="APPLIED",
            )

            record_audit_event(
                event_type="ATTENDANCE_CORRECTED",
                actor_user=actor,
                entity_type="MealConsumption",
                entity_id=existing_meal.meal_consumption_id,
                reason=reason.strip(),
                old_values={"effective_attendance": False},
                new_values={"effective_attendance": True, "action": "ADD_MISSING"},
                correlation_id=correlation_id,
            )
            return correction
        else:
            # Empty slot: insert new MealConsumption (Source CORRECTION) and correction row
            price = get_meal_rate(target_mess, meal_date) or Decimal("0.0000")
            occurrence = MealOccurrence.objects.filter(
                mess=target_mess, meal_date=meal_date, meal_type=meal_type_obj
            ).first()

            new_meal = MealConsumption.objects.create(
                transaction_id=uuid.uuid4(),
                student=student,
                roll_number_snapshot=student.roll_number,
                mess=target_mess,
                meal_type=meal_type_obj,
                meal_date=meal_date,
                meal_occurrence=occurrence,
                price_at_transaction=price,
                transaction_timestamp=now,
                verification_method="MANUAL_CORRECTION",
                verification_result="NOT_APPLICABLE",
                recorded_by_user=actor,
                source="CORRECTION",
                sync_status="SYNCHRONIZED",
                accepted_at=now,
            )

            correction = AttendanceCorrection.objects.create(
                correction_transaction_id=correction_transaction_id,
                student=student,
                mess=target_mess,
                meal_date=meal_date,
                meal_type=meal_type_obj,
                action="ADD_MISSING",
                original_meal_consumption=new_meal,
                requested_at=now,
                applied_at=now,
                reason=reason.strip(),
                actor_user=actor,
                status="APPLIED",
            )

            record_audit_event(
                event_type="ATTENDANCE_CORRECTED",
                actor_user=actor,
                entity_type="MealConsumption",
                entity_id=new_meal.meal_consumption_id,
                reason=reason.strip(),
                old_values={"effective_attendance": False},
                new_values={"effective_attendance": True, "action": "ADD_MISSING", "price": str(price)},
                correlation_id=correlation_id,
            )
            return correction
