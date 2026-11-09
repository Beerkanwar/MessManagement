"""
Serializers for mess pause API [SPEC DBDD §7, SDD §64].
"""
from rest_framework import serializers

from apps.pause.models import MessPause, MessPauseMealSlot


class PauseMealSlotSerializer(serializers.ModelSerializer):
    """Serializer for pause activation slot traceability."""

    meal_date = serializers.DateField(source="slot_date", read_only=True)
    meal_type_code = serializers.CharField(
        source="meal_occurrence.meal_type.code", read_only=True
    )
    meal_type_name = serializers.CharField(
        source="meal_occurrence.meal_type.name", read_only=True
    )

    class Meta:
        model = MessPauseMealSlot
        fields = [
            "pause_slot_id",
            "slot_sequence",
            "meal_date",
            "meal_type_code",
            "meal_type_name",
            "qualifies_for_activation",
            "consumed_for_activation",
        ]


class PauseRequestSerializer(serializers.Serializer):
    """Request schema for POST /api/v1/pauses [SPEC SDD §64, DBDD §7]."""

    mess_id = serializers.IntegerField(required=True, help_text="Target mess ID")
    requested_start_date = serializers.DateField(
        required=True, help_text="Requested start date (IST calendar)"
    )
    requested_end_date = serializers.DateField(
        required=True, help_text="Requested end date (IST calendar)"
    )

    def validate(self, attrs):
        if attrs["requested_end_date"] < attrs["requested_start_date"]:
            raise serializers.ValidationError(
                {
                    "requested_end_date": (
                        "Requested end date must be on or after the requested start date."
                    )
                }
            )
        return attrs


class PauseResponseSerializer(serializers.ModelSerializer):
    """Response schema for pause records [SPEC SDD §64, DBDD §7]."""

    meal_slots = PauseMealSlotSerializer(many=True, read_only=True)
    slots_remaining = serializers.SerializerMethodField()

    class Meta:
        model = MessPause
        fields = [
            "pause_id",
            "student_id",
            "mess_id",
            "requested_start_date",
            "requested_end_date",
            "effective_start_date",
            "effective_end_date",
            "activation_meal_date",
            "status",
            "requested_at",
            "cancelled_at",
            "completed_at",
            "cancellation_reason",
            "meal_slots",
            "slots_remaining",
        ]

    def get_slots_remaining(self, obj: MessPause) -> int:
        from apps.pause.services import ACTIVATION_SLOT_COUNT

        consumed = MessPauseMealSlot.objects.filter(
            pause=obj,
            qualifies_for_activation=True,
            consumed_for_activation=True,
        ).count()
        return max(0, ACTIVATION_SLOT_COUNT - consumed)


class PauseCancelSerializer(serializers.Serializer):
    """Request schema for POST /api/v1/pauses/<id>/cancel [SPEC SDD §64, DBDD §7]."""

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Optional cancellation reason",
    )
