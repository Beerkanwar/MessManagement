"""
Serializers for Mess, Managers, Meal Occurrences, Rates, and Extras — Phase 5.
"""
from decimal import Decimal
from rest_framework import serializers

from apps.core.clock import clock
from apps.mess.models import (
    ExtraItem,
    ExtraPrice,
    MealOccurrence,
    MealRate,
    MealType,
    Mess,
    MessManagerAssignment,
)
from apps.mess.services import get_extra_price


# ---------------------------------------------------------------------------
# Mess Master Serializers
# ---------------------------------------------------------------------------


class MessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mess
        fields = [
            "mess_id",
            "code",
            "name",
            "status",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["mess_id", "created_at", "updated_at"]


class MessCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20, help_text="Short unique mess identifier (e.g. 'M1')")
    name = serializers.CharField(max_length=255, help_text="Mess hall display name")


class MessUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, help_text="Updated display name")
    version = serializers.IntegerField(help_text="Optimistic concurrency version counter")


class MessDeactivateSerializer(serializers.Serializer):
    version = serializers.IntegerField(help_text="Optimistic concurrency version counter")


# ---------------------------------------------------------------------------
# Mess Manager Serializers
# ---------------------------------------------------------------------------


class MessManagerCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Staff institutional email")
    full_name = serializers.CharField(max_length=255)
    mess_code = serializers.CharField(max_length=20)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class MessManagerReassignSerializer(serializers.Serializer):
    new_mess_code = serializers.CharField(max_length=20, help_text="Target mess code")


class MessManagerAssignmentSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.user_id", read_only=True)
    email = serializers.EmailField(source="user.normalized_email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    mess = serializers.SerializerMethodField()

    class Meta:
        model = MessManagerAssignment
        fields = [
            "assignment_id",
            "user_id",
            "email",
            "full_name",
            "phone_number",
            "mess",
            "is_active",
            "assigned_at",
            "deactivated_at",
            "version",
        ]

    def get_mess(self, obj) -> dict[str, object]:
        return {
            "id": obj.mess.mess_id,
            "code": obj.mess.code,
            "name": obj.mess.name,
        }


# ---------------------------------------------------------------------------
# Meal Types & Occurrences Serializers
# ---------------------------------------------------------------------------


class MealTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealType
        fields = [
            "meal_type_id",
            "code",
            "name",
            "sequence_no",
            "is_fixed",
            "is_active",
        ]


class MealOccurrenceSerializer(serializers.ModelSerializer):
    mess_id = serializers.IntegerField(source="mess.mess_id", read_only=True)
    mess_code = serializers.CharField(source="mess.code", read_only=True)
    mess_name = serializers.CharField(source="mess.name", read_only=True)
    meal_type_id = serializers.IntegerField(source="meal_type.meal_type_id", read_only=True)
    meal_type_code = serializers.CharField(source="meal_type.code", read_only=True)
    meal_type_name = serializers.CharField(source="meal_type.name", read_only=True)

    class Meta:
        model = MealOccurrence
        fields = [
            "meal_occurrence_id",
            "mess_id",
            "mess_code",
            "mess_name",
            "meal_type_id",
            "meal_type_code",
            "meal_type_name",
            "meal_date",
            "status",
            "configuration_version",
            "created_at",
            "updated_at",
        ]


class MealOccurrenceCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(
        min_length=5, max_length=500,
        help_text="Required explanation for cancelling scheduled occurrence",
    )


# ---------------------------------------------------------------------------
# Common Meal Rate Serializers
# ---------------------------------------------------------------------------


class MealRateSerializer(serializers.ModelSerializer):
    mess_code = serializers.CharField(source="mess.code", read_only=True)

    class Meta:
        model = MealRate
        fields = [
            "meal_rate_id",
            "mess_id",
            "mess_code",
            "rate",
            "effective_from",
            "effective_to",
            "created_by_id",
            "created_at",
        ]


class MealRateCreateSerializer(serializers.Serializer):
    rate = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=Decimal("0.0001"))
    effective_from = serializers.DateField(help_text="Start date (inclusive, must be >= today)")
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_effective_from(self, value):
        from apps.core.clock import clock
        if value < clock.today():
            raise serializers.ValidationError("Effective from date cannot be in the past.")
        return value


# ---------------------------------------------------------------------------
# Extra Items & Prices Serializers
# ---------------------------------------------------------------------------


class ExtraPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtraPrice
        fields = [
            "extra_price_id",
            "extra_item_id",
            "unit_price",
            "effective_from",
            "effective_to",
            "created_by_id",
            "created_at",
        ]


class ExtraPriceCreateSerializer(serializers.Serializer):
    unit_price = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=Decimal("0.0000"))
    effective_from = serializers.DateField(help_text="Start date (inclusive, must be >= today)")
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_effective_from(self, value):
        from apps.core.clock import clock
        if value < clock.today():
            raise serializers.ValidationError("Effective from date cannot be in the past.")
        return value


class ExtraItemSerializer(serializers.ModelSerializer):
    hostel_code = serializers.CharField(source="hostel.code", read_only=True)
    hostel_name = serializers.CharField(source="hostel.name", read_only=True)
    current_price = serializers.SerializerMethodField()

    class Meta:
        model = ExtraItem
        fields = [
            "extra_item_id",
            "name",
            "normalized_name",
            "hostel_id",
            "hostel_code",
            "hostel_name",
            "status",
            "version",
            "current_price",
            "created_at",
            "updated_at",
        ]

    def get_current_price(self, obj) -> str | None:
        today = clock.today()
        if "prices" in getattr(obj, "_prefetched_objects_cache", {}):
            covering = [
                price
                for price in obj.prices.all()
                if price.effective_from <= today
                and (price.effective_to is None or price.effective_to > today)
            ]
            price = (
                max(covering, key=lambda row: row.effective_from).unit_price
                if covering
                else None
            )
        else:
            price = get_extra_price(obj, today)
        return str(price) if price is not None else None


class ExtraItemCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, help_text="Item display name (e.g. 'Egg Curry')")
    hostel_code = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default="",
        help_text="Hostel code (required for Super Admin, inferred for Clerk)",
    )
    initial_price = serializers.DecimalField(
        max_digits=19, decimal_places=4, required=False, min_value=Decimal("0.0000"),
        help_text="Optional starting unit price",
    )
    effective_from = serializers.DateField(
        required=False,
        help_text="Optional effective start date for initial price (default today)",
    )


class ExtraItemUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    version = serializers.IntegerField(help_text="Optimistic concurrency version counter")


class ExtraItemDeactivateSerializer(serializers.Serializer):
    version = serializers.IntegerField(help_text="Optimistic concurrency version counter")
