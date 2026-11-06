"""
Serializers for attendance, extras, and corrections [SPEC SDD §64, ImplementationGuide Phase 7].
"""
from rest_framework import serializers

from apps.attendance.models import AttendanceCorrection, ExtraTransaction, MealConsumption


class MealConsumptionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    mess_name = serializers.CharField(source="mess.name", read_only=True)
    meal_type_code = serializers.CharField(source="meal_type.code", read_only=True)

    class Meta:
        model = MealConsumption
        fields = [
            "meal_consumption_id",
            "transaction_id",
            "student_id",
            "roll_number_snapshot",
            "student_name",
            "mess_id",
            "mess_name",
            "meal_type_id",
            "meal_type_code",
            "meal_date",
            "price_at_transaction",
            "transaction_timestamp",
            "verification_method",
            "verification_result",
            "source",
            "accepted_at",
        ]


class AttendanceSummarySerializer(serializers.Serializer):
    breakfast_count = serializers.IntegerField()
    lunch_count = serializers.IntegerField()
    dinner_count = serializers.IntegerField()
    total_meals = serializers.IntegerField()
    total_amount = serializers.CharField()
    start_date = serializers.DateField(allow_null=True)
    end_date = serializers.DateField(allow_null=True)


class ExtraTransactionSerializer(serializers.ModelSerializer):
    roll_number = serializers.CharField(source="student.roll_number", read_only=True)
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    extra_item_name = serializers.CharField(source="extra_item.name", read_only=True)

    class Meta:
        model = ExtraTransaction
        fields = [
            "extra_transaction_id",
            "transaction_id",
            "student_id",
            "roll_number",
            "student_name",
            "extra_item_id",
            "extra_item_name",
            "hostel_id",
            "mess_id",
            "quantity",
            "unit_price_at_transaction",
            "total_amount",
            "transaction_timestamp",
            "source",
            "accepted_at",
        ]


class AttendanceCorrectionCreateSerializer(serializers.Serializer):
    correction_transaction_id = serializers.UUIDField(
        required=True,
        help_text="Client-generated idempotent UUID for the correction"
    )
    student_id = serializers.IntegerField(
        required=True,
        help_text="Student ID being corrected"
    )
    meal_date = serializers.DateField(
        required=True,
        help_text="MealDate (IST calendar date) to correct"
    )
    meal_type = serializers.CharField(
        required=True,
        help_text="Meal type code: BREAKFAST, LUNCH, or DINNER"
    )
    action = serializers.ChoiceField(
        choices=["ADD_MISSING", "REMOVE_INCORRECT"],
        required=True,
        help_text="Action to take: ADD_MISSING or REMOVE_INCORRECT"
    )
    reason = serializers.CharField(
        required=True,
        min_length=5,
        max_length=1000,
        help_text="Mandatory operational reason (minimum 5 characters)"
    )


class AttendanceCorrectionSerializer(serializers.ModelSerializer):
    meal_type_code = serializers.CharField(source="meal_type.code", read_only=True)
    actor_email = serializers.CharField(source="actor_user.email", read_only=True)

    class Meta:
        model = AttendanceCorrection
        fields = [
            "correction_id",
            "correction_transaction_id",
            "student_id",
            "mess_id",
            "meal_date",
            "meal_type_id",
            "meal_type_code",
            "action",
            "original_meal_consumption_id",
            "requested_at",
            "applied_at",
            "reason",
            "actor_email",
            "status",
        ]

