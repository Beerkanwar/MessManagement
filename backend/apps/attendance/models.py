"""
Attendance, consumption, extras transactions, and correction models matching SPEC DBDD §6.
Implements:
- MealConsumption (with transaction snapshot prices, unique student/date/type, transaction_id)
- ExtraTransaction (with quantity > 0, total_amount = quantity * unit_price check)
- AttendanceCorrection (insert-only model preserving original consumption)
Price immutability and insert-only triggers are enforced via migrations.
"""
from django.conf import settings
from django.db import models
from apps.core.models import InsertOnlyModel


class MealConsumption(models.Model):
    """
    Central meal consumption record [SPEC DBDD §6].
    PriceAtTransaction is an immutable financial snapshot [DBDD §5.2, Invariant 11].
    One student + one MealDate + one MealType = at most one meal consumption [Invariant 4].
    """
    VERIFICATION_METHOD_CHOICES = [
        ("QR_HMAC_SHA256", "QR HMAC-SHA256"),
        ("MANUAL_CORRECTION", "Manual Correction"),
    ]
    VERIFICATION_RESULT_CHOICES = [
        ("SUCCESS", "Success"),
        ("NOT_APPLICABLE", "Not Applicable"),
    ]
    SOURCE_CHOICES = [
        ("QR", "QR"),
        ("CORRECTION", "Correction"),
        ("SYNC_RESOLUTION", "Sync Resolution"),
    ]
    SYNC_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SYNCHRONIZED", "Synchronized"),
        ("IDEMPOTENT_SUCCESS", "Idempotent Success"),
        ("DUPLICATE", "Duplicate"),
        ("REJECTED", "Rejected"),
        ("CONFLICT", "Conflict"),
    ]

    meal_consumption_id = models.AutoField(primary_key=True)
    transaction_id = models.UUIDField(
        unique=True,
        help_text="Stable GUID assigned before local persistence [DBDD §6.1, Invariant 5]"
    )
    student = models.ForeignKey(
        "hostel.Student", on_delete=models.PROTECT, related_name="meal_consumptions"
    )
    roll_number_snapshot = models.CharField(
        max_length=50, help_text="Denormalized roll number snapshot at scan time"
    )
    mess = models.ForeignKey(
        "mess.Mess", on_delete=models.PROTECT, related_name="meal_consumptions"
    )
    meal_type = models.ForeignKey(
        "mess.MealType", on_delete=models.PROTECT, related_name="meal_consumptions"
    )
    meal_date = models.DateField(
        help_text="Scheduled date of the meal (IST calendar) [DEC-01, DBDD §5.1]"
    )
    meal_occurrence = models.ForeignKey(
        "mess.MealOccurrence", on_delete=models.PROTECT,
        null=True, blank=True, related_name="consumptions"
    )
    price_at_transaction = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="Immutable rate snapshot at transaction time [DBDD §5.2]"
    )
    transaction_timestamp = models.DateTimeField(
        help_text="Timestamp when scan occurred on client (UTC)"
    )
    verification_method = models.CharField(
        max_length=50, choices=VERIFICATION_METHOD_CHOICES, default="QR_HMAC_SHA256"
    )
    verification_result = models.CharField(
        max_length=50, choices=VERIFICATION_RESULT_CHOICES, default="SUCCESS"
    )
    device_registration = models.ForeignKey(
        "identity.DeviceRegistration", on_delete=models.PROTECT,
        null=True, blank=True, related_name="meal_consumptions"
    )
    recorded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_meals"
    )
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default="QR")
    sync_status = models.CharField(
        max_length=30, choices=SYNC_STATUS_CHOICES, default="SYNCHRONIZED"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "attendance_meal_consumption"
        verbose_name = "Meal Consumption"
        verbose_name_plural = "Meal Consumptions"
        constraints = [
            # Invariant 4: One student cannot have two meal records for same date + meal type
            models.UniqueConstraint(
                fields=["student", "meal_date", "meal_type"],
                name="uq_attendance_student_date_meal_type",
            ),
            models.CheckConstraint(
                condition=models.Q(price_at_transaction__gte=0),
                name="attendance_meal_price_non_neg_check",
            ),
        ]
        indexes = [
            models.Index(fields=["mess", "meal_date", "meal_type"], name="idx_att_meal_mess_date_type"),
            models.Index(fields=["student", "-meal_date"], name="idx_att_meal_student_date"),
            models.Index(fields=["transaction_id"], name="idx_att_meal_txn_id"),
        ]

    def __str__(self):
        return f"{self.roll_number_snapshot} - {self.meal_date} {self.meal_type_id} ({self.transaction_id})"


class ExtraTransaction(models.Model):
    """
    Extra food item purchase transaction [SPEC DBDD §6].
    Monetary values are snapshots [Invariant 11].
    TotalAmount = Quantity * UnitPriceAtTransaction.
    """
    SOURCE_CHOICES = [
        ("SCAN_CONFIRMATION", "Scan Confirmation"),
        ("MANUAL", "Manual"),
        ("SYNC_RESOLUTION", "Sync Resolution"),
    ]
    SYNC_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SYNCHRONIZED", "Synchronized"),
        ("IDEMPOTENT_SUCCESS", "Idempotent Success"),
        ("DUPLICATE", "Duplicate"),
        ("REJECTED", "Rejected"),
        ("CONFLICT", "Conflict"),
    ]

    extra_transaction_id = models.AutoField(primary_key=True)
    transaction_id = models.UUIDField(
        unique=True,
        help_text="Stable GUID assigned before local persistence [DBDD §6.1, Invariant 5]"
    )
    student = models.ForeignKey(
        "hostel.Student", on_delete=models.PROTECT, related_name="extra_transactions"
    )
    hostel = models.ForeignKey(
        "hostel.Hostel", on_delete=models.PROTECT, related_name="extra_transactions"
    )
    mess = models.ForeignKey(
        "mess.Mess", on_delete=models.PROTECT, related_name="extra_transactions"
    )
    extra_item = models.ForeignKey(
        "mess.ExtraItem", on_delete=models.PROTECT, related_name="transactions"
    )
    quantity = models.IntegerField(help_text="Units consumed, must be > 0")
    unit_price_at_transaction = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="Price snapshot at transaction time [DBDD §5.2]"
    )
    total_amount = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="Quantity * unit_price_at_transaction"
    )
    transaction_timestamp = models.DateTimeField()
    recorded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_extras"
    )
    device_registration = models.ForeignKey(
        "identity.DeviceRegistration", on_delete=models.PROTECT,
        null=True, blank=True, related_name="extra_transactions"
    )
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default="SCAN_CONFIRMATION")
    sync_status = models.CharField(
        max_length=30, choices=SYNC_STATUS_CHOICES, default="SYNCHRONIZED"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "attendance_extra_transaction"
        verbose_name = "Extra Transaction"
        verbose_name_plural = "Extra Transactions"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="attendance_extra_quantity_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price_at_transaction__gte=0),
                name="attendance_extra_unit_price_non_neg",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount=models.F("quantity") * models.F("unit_price_at_transaction")),
                name="attendance_extra_total_amount_check",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "-transaction_timestamp"], name="idx_att_extra_student_time"),
            models.Index(fields=["mess", "-transaction_timestamp"], name="idx_att_extra_mess_time"),
            models.Index(fields=["transaction_id"], name="idx_att_extra_txn_id"),
        ]

    def __str__(self):
        return f"Extra {self.extra_item_id} x{self.quantity} for student {self.student_id} ({self.total_amount})"


class AttendanceCorrection(InsertOnlyModel):
    """
    Append-only correction for attendance [SPEC DBDD §6, Invariant 12].
    Action: ADD_MISSING or REMOVE_INCORRECT.
    Original MealConsumption record is preserved; removal is represented
    as a state/correction outcome rather than destructive deletion.
    """
    ACTION_CHOICES = [
        ("ADD_MISSING", "Add Missing"),
        ("REMOVE_INCORRECT", "Remove Incorrect"),
    ]
    STATUS_CHOICES = [
        ("APPLIED", "Applied"),
        ("REJECTED", "Rejected"),
    ]

    correction_id = models.AutoField(primary_key=True)
    correction_transaction_id = models.UUIDField(unique=True)
    student = models.ForeignKey(
        "hostel.Student", on_delete=models.PROTECT, related_name="attendance_corrections"
    )
    mess = models.ForeignKey(
        "mess.Mess", on_delete=models.PROTECT, related_name="attendance_corrections"
    )
    meal_date = models.DateField(help_text="MealDate corrected")
    meal_type = models.ForeignKey(
        "mess.MealType", on_delete=models.PROTECT, related_name="attendance_corrections"
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    original_meal_consumption = models.ForeignKey(
        MealConsumption, on_delete=models.PROTECT,
        null=True, blank=True, related_name="corrections"
    )
    requested_at = models.DateTimeField()
    applied_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(help_text="Mandatory reason (min 5 chars) [DEC-12, D12]")
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applied_corrections"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="APPLIED")
    source_transaction_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "attendance_attendance_correction"
        verbose_name = "Attendance Correction"
        verbose_name_plural = "Attendance Corrections"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(action__in=["ADD_MISSING", "REMOVE_INCORRECT"]),
                name="attendance_correction_action_check",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["APPLIED", "REJECTED"]),
                name="attendance_correction_status_check",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "meal_date", "meal_type"], name="idx_att_corr_student_meal"),
            models.Index(fields=["correction_transaction_id"], name="idx_att_corr_txn_id"),
        ]

    def __str__(self):
        return f"{self.action} on {self.meal_date} for student {self.student_id}"
