"""
Mess, meal occurrences, pricing, and extras models matching SPEC DBDD §5.
Implements:
- Mess master
- MessManagerAssignment (with DEC-21 single active manager per mess constraint)
- MealType (fixed seeded types)
- MealOccurrence
- MealRate (common mess rate with non-overlapping effective dates)
- ExtraItem (hostel-scoped with normalized_name)
- ExtraPrice (effective-dated non-overlapping item prices)
"""
from django.conf import settings
from django.db import models
from django.utils import timezone as django_tz
from apps.core.models import TimeStampedModel, VersionedModel


class Mess(VersionedModel):
    """Mess hall master data [SPEC DBDD §5]. Deactivated, never deleted [DBDD §17]."""
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    mess_id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True, help_text="Short mess identifier")
    name = models.CharField(max_length=255, help_text="Mess hall display name")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        db_table = "mess_mess"
        verbose_name = "Mess"
        verbose_name_plural = "Messes"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "INACTIVE"]),
                name="mess_mess_status_check",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class MessManagerAssignment(VersionedModel):
    """
    Mess manager assignment [SPEC DBDD §5].
    Filtered unique: one active mess assignment per user.
    DEC-21: exactly one active manager per mess.
    """
    assignment_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mess_manager_assignments"
    )
    mess = models.ForeignKey(Mess, on_delete=models.PROTECT, related_name="manager_assignments")
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(help_text="When the manager was assigned")
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mess_manager_assignment"
        verbose_name = "Mess Manager Assignment"
        verbose_name_plural = "Mess Manager Assignments"
        constraints = [
            # One active mess per manager
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="uq_mess_manager_one_active_per_user",
            ),
            # DEC-21: Exactly one active manager per mess
            models.UniqueConstraint(
                fields=["mess"],
                condition=models.Q(is_active=True),
                name="uq_mess_one_active_manager",
            ),
        ]

    def __str__(self):
        return f"Manager {self.user_id} -> Mess {self.mess_id} (active={self.is_active})"


class MealType(models.Model):
    """
    Fixed meal types [SPEC DBDD §5].
    Seeded: BREAKFAST (1), LUNCH (2), EVENING_SNACKS (3), DINNER (4).
    """
    meal_type_id = models.AutoField(primary_key=True)
    code = models.CharField(
        max_length=50, unique=True,
        help_text="BREAKFAST, LUNCH, EVENING_SNACKS, DINNER"
    )
    name = models.CharField(max_length=100)
    sequence_no = models.IntegerField(help_text="Display/chronological ordering: 1, 2, 3, 4")
    is_fixed = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "mess_meal_type"
        verbose_name = "Meal Type"
        verbose_name_plural = "Meal Types"
        ordering = ["sequence_no"]

    def __str__(self):
        return self.name


class MealOccurrence(VersionedModel):
    """
    Scheduled meal occurrence for a mess on a specific date [SPEC DBDD §5].
    MealDate semantics: scheduled date of the meal, not sync/upload date (DEC-01, DEC-07).
    """
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("CANCELLED", "Cancelled"),
    ]

    meal_occurrence_id = models.AutoField(primary_key=True)
    mess = models.ForeignKey(Mess, on_delete=models.PROTECT, related_name="meal_occurrences")
    meal_type = models.ForeignKey(MealType, on_delete=models.PROTECT, related_name="occurrences")
    meal_date = models.DateField(help_text="Scheduled calendar date (IST)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="SCHEDULED")
    configuration_version = models.BigIntegerField(
        default=1, help_text="Tracks menu/time configuration changes"
    )

    class Meta:
        db_table = "mess_meal_occurrence"
        verbose_name = "Meal Occurrence"
        verbose_name_plural = "Meal Occurrences"
        constraints = [
            models.UniqueConstraint(
                fields=["mess", "meal_date", "meal_type"],
                name="uq_mess_occurrence_mess_date_type",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["SCHEDULED", "CANCELLED"]),
                name="mess_occurrence_status_check",
            ),
        ]
        indexes = [
            models.Index(fields=["mess", "meal_date"], name="idx_mess_occ_mess_date"),
        ]

    def __str__(self):
        return f"{self.mess.code} - {self.meal_date} - {self.meal_type.code} ({self.status})"


class MealRate(TimeStampedModel):
    """
    Common mess rate for Breakfast, Lunch, and Dinner [SPEC DBDD §5].
    Effective-dated and non-overlapping per Mess.
    ExclusionConstraint on (mess, daterange) added via RunSQL.
    """
    meal_rate_id = models.AutoField(primary_key=True)
    mess = models.ForeignKey(Mess, on_delete=models.PROTECT, related_name="meal_rates")
    rate = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="Common diet rate per meal [DEC-04]"
    )
    effective_from = models.DateField(help_text="Start date of rate (inclusive)")
    effective_to = models.DateField(
        null=True, blank=True,
        help_text="End date of rate (inclusive, null=open-ended)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_meal_rates"
    )

    class Meta:
        db_table = "mess_meal_rate"
        verbose_name = "Meal Rate"
        verbose_name_plural = "Meal Rates"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rate__gt=0),
                name="mess_meal_rate_positive_check",
            ),
        ]
        indexes = [
            models.Index(fields=["mess", "effective_from"], name="idx_mess_rate_mess_eff"),
        ]

    def __str__(self):
        return f"Mess {self.mess_id} Rate: {self.rate} (from {self.effective_from})"


class ExtraItem(VersionedModel):
    """
    Hostel-scoped reusable extra item master [SPEC DBDD §5].
    Price is NOT stored here; it is effective-dated in ExtraPrice [CONFLICT-06].
    """
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    extra_item_id = models.AutoField(primary_key=True)
    hostel = models.ForeignKey("hostel.Hostel", on_delete=models.PROTECT, related_name="extra_items")
    name = models.CharField(max_length=255, help_text="Item display name (e.g. 'Egg Curry')")
    normalized_name = models.CharField(
        max_length=255, help_text="Trimmed and uppercase for uniqueness check [REC]"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        db_table = "mess_extra_item"
        verbose_name = "Extra Item"
        verbose_name_plural = "Extra Items"
        constraints = [
            models.UniqueConstraint(
                fields=["hostel", "normalized_name"],
                name="uq_mess_extra_item_hostel_norm_name",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "INACTIVE"]),
                name="mess_extra_item_status_check",
            ),
        ]

    def __str__(self):
        return f"{self.name} (Hostel {self.hostel_id})"


class ExtraPrice(TimeStampedModel):
    """
    Effective-dated pricing for extra items [SPEC DBDD §5, CONFLICT-06].
    ExclusionConstraint on (extra_item, daterange) added via RunSQL.
    """
    extra_price_id = models.AutoField(primary_key=True)
    extra_item = models.ForeignKey(ExtraItem, on_delete=models.PROTECT, related_name="prices")
    unit_price = models.DecimalField(max_digits=19, decimal_places=4)
    effective_from = models.DateField(help_text="Start date of price (inclusive)")
    effective_to = models.DateField(
        null=True, blank=True,
        help_text="End date of price (inclusive, null=open-ended)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_extra_prices"
    )

    class Meta:
        db_table = "mess_extra_price"
        verbose_name = "Extra Price"
        verbose_name_plural = "Extra Prices"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="mess_extra_price_non_neg_check",
            ),
        ]
        indexes = [
            models.Index(fields=["extra_item", "effective_from"], name="idx_mess_extra_price_item_eff"),
        ]

    def __str__(self):
        return f"Item {self.extra_item_id} Price: {self.unit_price} (from {self.effective_from})"
