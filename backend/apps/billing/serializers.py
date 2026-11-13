"""
Serializers for the billing and prepaid balance endpoint group
[SPEC DBDD §8, ImplementationGuide Phase 10].

All monetary values travel as decimal strings with four decimals; DRF's
DecimalField is configured by default to coerce to string, so no float ever
reaches the wire.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.billing.models import (
    BalanceAccount,
    BalanceLedgerEntry,
    Bill,
    BillAdjustment,
    BillLine,
    BillingPeriod,
    BillingPolicy,
    Semester,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class SemesterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Semester
        fields = [
            "semester_id",
            "code",
            "name",
            "start_date",
            "end_date",
            "status",
            "version",
        ]


class SemesterCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    status = serializers.ChoiceField(
        choices=[choice[0] for choice in Semester.STATUS_CHOICES],
        required=False,
        default="UPCOMING",
    )


class BillingPolicySerializer(serializers.ModelSerializer):
    mess_code = serializers.CharField(source="mess.code", read_only=True)

    class Meta:
        model = BillingPolicy
        fields = [
            "billing_policy_id",
            "mess_id",
            "mess_code",
            "minimum_diet_count",
            "effective_from",
            "effective_to",
            "policy_version",
        ]


class BillingPolicyCreateSerializer(serializers.Serializer):
    mess_id = serializers.IntegerField(min_value=1)
    minimum_diet_count = serializers.IntegerField(min_value=0)
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)


class BillingPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingPeriod
        fields = [
            "billing_period_id",
            "year",
            "month",
            "period_start",
            "period_end",
            "status",
            "opened_at",
            "generated_at",
            "reviewed_at",
            "locked_at",
            "locked_by",
            "unlocked_at",
            "unlocked_by",
            "unlock_reason",
            "version",
        ]


class BillingPeriodUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)


class UnlockPeriodSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------


class BillLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillLine
        fields = [
            "bill_line_id",
            "line_type",
            "source_entity_type",
            "source_entity_id",
            "description",
            "quantity",
            "unit_rate",
            "amount",
            "calculation_order",
        ]


class BillAdjustmentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = BillAdjustment
        fields = [
            "adjustment_id",
            "amount",
            "adjustment_type",
            "reason",
            "created_by",
            "created_by_name",
            "created_at",
        ]


class BillAdjustmentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    adjustment_type = serializers.ChoiceField(
        choices=[choice[0] for choice in BillAdjustment.ADJUSTMENT_TYPE_CHOICES]
    )
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class BillSerializer(serializers.ModelSerializer):
    student_roll_number = serializers.CharField(
        source="student.roll_number", read_only=True
    )
    student_name = serializers.CharField(
        source="student.user.full_name", read_only=True
    )
    hostel_id = serializers.IntegerField(source="student.hostel_id", read_only=True)
    mess_code = serializers.CharField(source="mess.code", read_only=True)
    semester_code = serializers.CharField(
        source="semester.code", read_only=True, allow_null=True
    )
    period_year = serializers.IntegerField(
        source="billing_period.year", read_only=True
    )
    period_month = serializers.IntegerField(
        source="billing_period.month", read_only=True
    )
    period_status = serializers.CharField(
        source="billing_period.status", read_only=True
    )
    lines = BillLineSerializer(many=True, read_only=True)
    adjustments = BillAdjustmentSerializer(many=True, read_only=True)

    class Meta:
        model = Bill
        fields = [
            "bill_id",
            "student_id",
            "student_roll_number",
            "student_name",
            "hostel_id",
            "mess_id",
            "mess_code",
            "billing_period_id",
            "period_year",
            "period_month",
            "period_status",
            "semester_id",
            "semester_code",
            "meal_component_amount",
            "extra_charges_amount",
            "adjustment_amount",
            "final_amount",
            "common_diet_rate_snapshot",
            "minimum_diet_count_snapshot",
            "actual_meal_count",
            "status",
            "generated_at",
            "locked_at",
            "lines",
            "adjustments",
            "version",
        ]


# ---------------------------------------------------------------------------
# Prepaid balances
# ---------------------------------------------------------------------------


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = BalanceLedgerEntry
        fields = [
            "ledger_entry_id",
            "entry_type",
            "amount",
            "reference_type",
            "reference_id",
            "effective_date",
            "description",
            "created_by",
            "created_at",
        ]


class BalanceSerializer(serializers.ModelSerializer):
    student_roll_number = serializers.CharField(
        source="student.roll_number", read_only=True
    )
    student_name = serializers.CharField(
        source="student.user.full_name", read_only=True
    )
    semester_code = serializers.CharField(source="semester.code", read_only=True)
    credits_total = serializers.SerializerMethodField()
    charges_total = serializers.SerializerMethodField()
    entries = serializers.SerializerMethodField()

    class Meta:
        model = BalanceAccount
        fields = [
            "balance_account_id",
            "student_id",
            "student_roll_number",
            "student_name",
            "semester_id",
            "semester_code",
            "opening_balance",
            "credits_total",
            "charges_total",
            "current_balance",
            "last_calculated_at",
            "entries",
            "version",
        ]

    @staticmethod
    def _entries(account: BalanceAccount):
        entries = getattr(account, "_serialized_ledger_entries", None)
        if entries is None:
            entries = list(account.ledger_entries.all())
            if "ledger_entries" not in getattr(account, "_prefetched_objects_cache", {}):
                entries.sort(key=lambda entry: entry.ledger_entry_id)
            account._serialized_ledger_entries = entries
        return entries

    def get_credits_total(self, account: BalanceAccount) -> str:
        total = sum(
            (
                entry.amount
                for entry in self._entries(account)
                if entry.entry_type == "CREDIT"
            ),
            Decimal("0"),
        )
        return str(total)

    def get_charges_total(self, account: BalanceAccount) -> str:
        total = sum(
            (
                entry.amount
                for entry in self._entries(account)
                if entry.entry_type == "BILL_CHARGE"
            ),
            Decimal("0"),
        )
        return str(total)

    def get_entries(self, account: BalanceAccount) -> list:
        return LedgerEntrySerializer(self._entries(account), many=True).data


class OpeningBalanceSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    semester_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")


class CreditSerializer(serializers.Serializer):
    semester_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    reference = serializers.CharField(allow_blank=False, trim_whitespace=True)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class OpeningBalanceImportSerializer(serializers.Serializer):
    semester_id = serializers.IntegerField(min_value=1)
    file = serializers.FileField()
