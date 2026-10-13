"""
Feedback models matching SPEC DBDD §10.
Implements:
- Feedback (insert-only, unique student + year + month [Invariant 6], ratings 1-5)
"""
from django.db import models
from apps.core.models import InsertOnlyModel


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
    comments = models.TextField(blank=True, default="")

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
        ]
        indexes = [
            models.Index(fields=["mess", "calendar_year", "calendar_month"], name="idx_feedback_mess_year_month"),
        ]

    def __str__(self):
        return f"Feedback from Student {self.student_id} for {self.calendar_year}/{self.calendar_month:02d}"
