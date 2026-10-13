"""
Billing, policies, bills, bill lines, adjustments, and prepaid balance models matching SPEC DBDD §8.
Implements:
- Semester (institutional prepaid accounting period)
- BillingPeriod (monthly lifecycle: OPEN -> BILL_GENERATED -> REVIEWED -> LOCKED)
- BillingPolicy (effective-dated minimum diet count per mess)
- Bill (financial snapshot; formula: MAX(MinimumDietCount, MealCount) * CommonDietRate + Extras + Adjustments [C01])
- BillLine (calculation detail lines)
- BillAdjustment (insert-only FEE and FINE additions [C01])
- BalanceAccount (unique Student + Semester, allows negative balance [DBDD §8, Invariant 25])
- BalanceLedgerEntry (insert-only source of truth)
Triggers for locked-bill guards and insert-only tables are added via migrations.
"""
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel, VersionedModel, InsertOnlyModel


class Semester(VersionedModel):
    """
    Institutional semester period for prepaid opening balance [SPEC DBDD §8].
    Lightweight period; not an academic curriculum model.
    """
    STATUS_CHOICES = [
        ("UPCOMING", "Upcoming"),
        ("ACTIVE", "Active"),
        ("COMPLETED", "Completed"),
        ("ARCHIVED", "Archived"),
    ]

    semester_id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=50, unique=True, help_text="e.g. 'AUTUMN-2026'")
    name = models.CharField(max_length=100, help_text="e.g. 'Autumn Semester 2026-27'")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="UPCOMING")

    class Meta:
        db_table = "billing_semester"
        verbose_name = "Semester"
        verbose_name_plural = "Semesters"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["UPCOMING", "ACTIVE", "COMPLETED", "ARCHIVED"]),
                name="billing_semester_status_check",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="billing_semester_dates_check",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class BillingPeriod(VersionedModel):
    """
    Monthly billing period and lifecycle [SPEC DBDD §8.2].
    OPEN -> BILL_GENERATED -> REVIEWED -> LOCKED.
    Unlocking requires Super Admin authorization, a reason, and writes an AuditLog [DBDD-AC-23].
    """
    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("BILL_GENERATED", "Bill Generated"),
        ("REVIEWED", "Reviewed"),
        ("LOCKED", "Locked"),
    ]

    billing_period_id = models.AutoField(primary_key=True)
    year = models.IntegerField(help_text="Calendar year (e.g. 2026)")
    month = models.IntegerField(help_text="Calendar month (1-12)")
    period_start = models.DateField(help_text="First date of month")
    period_end = models.DateField(help_text="Last date of month")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="OPEN")
    opened_at = models.DateTimeField(auto_now_add=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="locked_billing_periods"
    )
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="unlocked_billing_periods"
    )
    unlock_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "billing_billing_period"
        verbose_name = "Billing Period"
        verbose_name_plural = "Billing Periods"
        constraints = [
            models.UniqueConstraint(
                fields=["year", "month"],
                name="uq_billing_period_year_month",
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1, month__lte=12),
                name="billing_period_month_check",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["OPEN", "BILL_GENERATED", "REVIEWED", "LOCKED"]),
                name="billing_period_status_check",
            ),
        ]

    def __str__(self):
        return f"{self.year}-{self.month:02d} ({self.status})"


class BillingPolicy(TimeStampedModel):
    """
    Effective-dated minimum diet rule per mess [SPEC DBDD §8].
    ExclusionConstraint on (mess, daterange) added via RunSQL.
    """
    billing_policy_id = models.AutoField(primary_key=True)
    mess = models.ForeignKey(
        "mess.Mess", on_delete=models.PROTECT, related_name="billing_policies"
    )
    minimum_diet_count = models.IntegerField(
        help_text="Base minimum diet count for students in this mess [DBDD §8]"
    )
    effective_from = models.DateField(help_text="Start date of policy (inclusive)")
    effective_to = models.DateField(
        null=True, blank=True,
        help_text="End date of policy (inclusive, null=open-ended)"
    )
    policy_version = models.IntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_billing_policies"
    )

    class Meta:
        db_table = "billing_billing_policy"
        verbose_name = "Billing Policy"
        verbose_name_plural = "Billing Policies"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minimum_diet_count__gte=0),
                name="billing_policy_min_diet_non_neg",
            ),
        ]
        indexes = [
            models.Index(fields=["mess", "effective_from"], name="idx_billing_policy_mess_eff"),
        ]

    def __str__(self):
        return f"Mess {self.mess_id} MinDiets: {self.minimum_diet_count} (from {self.effective_from})"


class Bill(VersionedModel):
    """
    Generated monthly student bill [SPEC DBDD §8, Invariant 7].
    Owner change C01:
    FinalBillAmount = MAX(BilledMinimumDietCount, MealCount) * CommonDietRate + ExtraCharges + Adjustments
    Locked bills cannot be silently modified [DBDD §8.3, DBDD-AC-22].
    """
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("FINAL", "Final"),
        ("LOCKED", "Locked"),
    ]

    bill_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        "hostel.Student", on_delete=models.PROTECT, related_name="bills"
    )
    mess = models.ForeignKey(
        "mess.Mess", on_delete=models.PROTECT, related_name="bills"
    )
    billing_period = models.ForeignKey(
        BillingPeriod, on_delete=models.PROTECT, related_name="bills"
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.PROTECT, null=True, blank=True, related_name="bills"
    )
    meal_component_amount = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="MAX(minimum_diet_count_snapshot, actual_meal_count) * common_diet_rate_snapshot [C01]"
    )
    extra_charges_amount = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="Sum of extra transactions in period"
    )
    adjustment_amount = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Sum of FEE and FINE adjustments (non-negative additions only) [C01]"
    )
    final_amount = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="meal_component_amount + extra_charges_amount + adjustment_amount [C01]"
    )
    common_diet_rate_snapshot = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="Rate snapshot at generation [DBDD §8.1]"
    )
    minimum_diet_count_snapshot = models.IntegerField(
        help_text="Billed minimum count after pause deduction [DEC-04]"
    )
    actual_meal_count = models.IntegerField(
        default=0,
        help_text="Count of qualifying meals consumed in period [C01]"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    generated_at = models.DateTimeField()
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_bill"
        verbose_name = "Bill"
        verbose_name_plural = "Bills"
        constraints = [
            # Invariant 7: A student cannot have two bills for same mess and billing period
            models.UniqueConstraint(
                fields=["student", "mess", "billing_period"],
                name="uq_billing_bill_student_mess_period",
            ),
            # C01: final = meal + extras + adjustments
            models.CheckConstraint(
                condition=models.Q(final_amount=models.F("meal_component_amount") + models.F("extra_charges_amount") + models.F("adjustment_amount")),
                name="billing_bill_final_amount_calc_check",
            ),
            # C01: adjustments are additions only, amount >= 0
            models.CheckConstraint(
                condition=models.Q(adjustment_amount__gte=0),
                name="billing_bill_adjustment_amount_non_neg",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["DRAFT", "FINAL", "LOCKED"]),
                name="billing_bill_status_check",
            ),
        ]
        indexes = [
            models.Index(fields=["billing_period", "mess"], name="idx_billing_bill_period_mess"),
            models.Index(fields=["student", "-billing_period"], name="idx_bill_student_period"),
        ]

    def __str__(self):
        return f"Bill {self.bill_id} - Student {self.student_id} ({self.final_amount})"


class BillLine(models.Model):
    """
    Detailed calculation line preserving bill derivation without modifying transactions [SPEC DBDD §8].
    """
    LINE_TYPE_CHOICES = [
        ("MINIMUM_DIET", "Minimum Diet"),
        ("EXTRA", "Extra"),
        ("ADJUSTMENT", "Adjustment"),
    ]

    bill_line_id = models.AutoField(primary_key=True)
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="lines")
    line_type = models.CharField(max_length=30, choices=LINE_TYPE_CHOICES)
    source_entity_type = models.CharField(max_length=50, blank=True, default="")
    source_entity_id = models.CharField(max_length=50, blank=True, default="")
    description = models.TextField()
    quantity = models.IntegerField(default=1)
    unit_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    calculation_order = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_bill_line"
        verbose_name = "Bill Line"
        verbose_name_plural = "Bill Lines"
        ordering = ["bill", "calculation_order"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(line_type__in=["MINIMUM_DIET", "EXTRA", "ADJUSTMENT"]),
                name="billing_bill_line_type_check",
            ),
        ]

    def __str__(self):
        return f"Bill {self.bill_id} Line: {self.description} ({self.amount})"


class BillAdjustment(InsertOnlyModel):
    """
    Append-only and auditable bill adjustment [SPEC DBDD §8, Invariant 12].
    Owner change C01: Adjustments are non-negative additions only (types FEE and FINE, amount > 0).
    Nothing reduces a bill.
    """
    ADJUSTMENT_TYPE_CHOICES = [
        ("FEE", "Fee"),
        ("FINE", "Fine"),
    ]

    adjustment_id = models.AutoField(primary_key=True)
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="adjustments")
    amount = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="Adjustment amount, strictly > 0 [C01]"
    )
    adjustment_type = models.CharField(
        max_length=20, choices=ADJUSTMENT_TYPE_CHOICES,
        help_text="FEE or FINE only; additions only [C01]"
    )
    reason = models.TextField(help_text="Mandatory reason for fee or fine")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_bill_adjustments"
    )

    class Meta:
        db_table = "billing_bill_adjustment"
        verbose_name = "Bill Adjustment"
        verbose_name_plural = "Bill Adjustments"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="billing_bill_adjustment_amount_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(adjustment_type__in=["FEE", "FINE"]),
                name="billing_bill_adjustment_type_check",
            ),
        ]

    def __str__(self):
        return f"{self.adjustment_type} ₹{self.amount} on Bill {self.bill_id}"


class BalanceAccount(VersionedModel):
    """
    Prepaid student balance account per semester [SPEC DBDD §8, Invariant 8].
    Cached balance is derived from immutable ledger entries.
    Negative balance is representable and does not block attendance [Invariant 25].
    """
    balance_account_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        "hostel.Student", on_delete=models.PROTECT, related_name="balance_accounts"
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.PROTECT, related_name="balance_accounts"
    )
    opening_balance = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    current_balance = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        help_text="Derived cached balance, may be negative [DBDD §8, Invariant 25]"
    )
    last_calculated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_balance_account"
        verbose_name = "Balance Account"
        verbose_name_plural = "Balance Accounts"
        constraints = [
            # Invariant 8: A student cannot have two prepaid BalanceAccounts for the same Semester
            models.UniqueConstraint(
                fields=["student", "semester"],
                name="uq_billing_balance_account_student_sem",
            ),
        ]

    def __str__(self):
        return f"Balance for student {self.student_id} in {self.semester_id}: ₹{self.current_balance}"


class BalanceLedgerEntry(InsertOnlyModel):
    """
    Append-only source of truth for student balance [SPEC DBDD §8, Invariant 12].
    Credits and charges are represented explicitly.
    EntryType: OPENING, CREDIT, BILL_CHARGE, BILL_REVERSAL [DEC-02].
    """
    ENTRY_TYPE_CHOICES = [
        ("OPENING", "Opening Balance"),
        ("CREDIT", "Credit"),
        ("BILL_CHARGE", "Bill Charge"),
        ("BILL_REVERSAL", "Bill Reversal"),
    ]

    ledger_entry_id = models.AutoField(primary_key=True)
    balance_account = models.ForeignKey(
        BalanceAccount, on_delete=models.PROTECT, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=30, choices=ENTRY_TYPE_CHOICES)
    amount = models.DecimalField(
        max_digits=19, decimal_places=4,
        help_text="Signed amount: positive for credits, negative for charges"
    )
    reference_type = models.CharField(max_length=50, blank=True, default="")
    reference_id = models.CharField(max_length=50, blank=True, default="")
    effective_date = models.DateField()
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_ledger_entries"
    )

    class Meta:
        db_table = "billing_balance_ledger_entry"
        verbose_name = "Balance Ledger Entry"
        verbose_name_plural = "Balance Ledger Entries"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(entry_type__in=["OPENING", "CREDIT", "BILL_CHARGE", "BILL_REVERSAL"]),
                name="billing_ledger_entry_type_check",
            ),
        ]
        indexes = [
            models.Index(fields=["balance_account", "effective_date", "ledger_entry_id"], name="idx_billing_ledger_acct_eff_id"),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount} for Account {self.balance_account_id}"
