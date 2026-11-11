"""
Serializers for the feedback endpoint group
[SPEC DBDD §10, SRS §23, SDD §49, ImplementationGuide Phase 11].

Comments are ordinary text. They are stored and returned verbatim, never
interpreted as markup, so a comment containing HTML is inert data.
"""
from rest_framework import serializers

from apps.feedback.models import Feedback


class FeedbackSubmitSerializer(serializers.Serializer):
    food_quality_rating = serializers.IntegerField(min_value=1, max_value=5)
    taste_rating = serializers.IntegerField(min_value=1, max_value=5)
    comments = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=1000,
        trim_whitespace=False,
    )


class FeedbackSerializer(serializers.ModelSerializer):
    mess_code = serializers.CharField(source="mess.code", read_only=True)
    mess_name = serializers.CharField(source="mess.name", read_only=True)

    class Meta:
        model = Feedback
        fields = [
            "feedback_id",
            "student_id",
            "mess_id",
            "mess_code",
            "mess_name",
            "calendar_year",
            "calendar_month",
            "food_quality_rating",
            "taste_rating",
            "comments",
            "created_at",
        ]


class FeedbackCurrentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(read_only=True)
    calendar_year = serializers.IntegerField(read_only=True)
    calendar_month = serializers.IntegerField(read_only=True)
    submitted = serializers.BooleanField(read_only=True)
    feedback = FeedbackSerializer(read_only=True, allow_null=True)
