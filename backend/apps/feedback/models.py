"""
Feedback models matching SPEC DBDD §10.
Implements:
- Feedback (insert-only, unique student + year + month [Invariant 6], ratings 1-5)
"""
from django.db import models
from django.db.models import TextField
from django.db.models.functions import Length

from apps.core.models import InsertOnlyModel

# Length is a database function but not a registered lookup by default; the
# feedback comment cap needs it in a CheckConstraint.
TextField.register_lookup(Length)


class Feedback(InsertOnlyModel):
    """
    Monthly student mess feedback [SPEC DBDD §10, Invariant 6, DBDD-AC-29].
    Feedback is not anonymous and is associated with the student's mess at submission time.
    Immutable after submission (InsertOnlyModel + database trigger guard).
    """
    feedback_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        "hostel.Student", on_delete=models.PROTECT, related_name="feedbacks"
    )
    mess = models.ForeignKey(
        "mess.Mess", on_delete=models.PROTECT, related_name="feedbacks"
    )
    calendar_year = models.IntegerField(help_text="Calendar year")
    calendar_month = models.IntegerField(help_text="Calendar month (1-12)")
    food_quality_rating = models.IntegerField(
        help_text="Rating from 1 (poor) to 5 (excellent)"
    )
    taste_rating = models.IntegerField(
        help_text="Rating from 1 (poor) to 5 (excellent)"
    )
    comments = models.TextField(
        blank=True, default="", max_length=1000,
        help_text="Optional free-text comments (plain text, up to 1,000 characters)",
    )

    class Meta:
        db_table = "feedback_feedback"
        verbose_name = "Feedback"
        verbose_name_plural = "Feedbacks"
        constraints = [
            # Invariant 6: A student cannot have two feedback records in the same calendar month
            models.UniqueConstraint(
                fields=["student", "calendar_year", "calendar_month"],
                name="uq_feedback_student_year_month",
            ),
            models.CheckConstraint(
                condition=models.Q(calendar_month__gte=1, calendar_month__lte=12),
                name="feedback_month_check",
            ),
            models.CheckConstraint(
                condition=models.Q(food_quality_rating__gte=1, food_quality_rating__lte=5),
                name="feedback_food_quality_check",
            ),
            models.CheckConstraint(
                condition=models.Q(taste_rating__gte=1, taste_rating__lte=5),
                name="feedback_taste_rating_check",
            ),
            models.CheckConstraint(
                condition=models.Q(comments__length__lte=1000),
                name="feedback_comments_length_check",
            ),
        ]
        indexes = [
            models.Index(fields=["mess", "calendar_year", "calendar_month"], name="idx_feedback_mess_year_month"),
        ]

    def __str__(self):
        return f"Feedback from Student {self.student_id} for {self.calendar_year}/{self.calendar_month:02d}"
