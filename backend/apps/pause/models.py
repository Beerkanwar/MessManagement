"""
Mess pause models matching SPEC DBDD §7.
Implements:
- MessPause (status lifecycle: SCHEDULED -> ACTIVE -> COMPLETED, or CANCELLED)
- MessPauseMealSlot (qualifying scheduled meal slots for three-slot activation delay)
"""
from django.db import models
from apps.core.models import VersionedModel


class MessPause(VersionedModel):
    """
    Mess pause request and lifecycle tracking [SPEC DBDD §7].
    Pause becomes effective only after next three qualifying scheduled meal slots pass [DEC-06].
    Breakfast, Lunch, Dinner qualify; Snacks do not count.
    Owner change D23: A meal taken during ACTIVE pause automatically cancels remaining pause.
    """
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("ACTIVE", "Active"),
        ("CANCELLED", "Cancelled"),
        ("COMPLETED", "Completed"),
    ]

    pause_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        "hostel.Student", on_delete=models.PROTECT, related_name="pauses"
    )
    mess = models.ForeignKey(
        "mess.Mess", on_delete=models.PROTECT, related_name="pauses"
    )
    requested_start_date = models.DateField(help_text="Requested start date (IST calendar)")
    requested_end_date = models.DateField(help_text="Requested end date (IST calendar)")
    effective_start_date = models.DateField(
        null=True, blank=True,
        help_text="Calculated date of the first slot after third qualifying slot [DEC-06]"
    )
    effective_end_date = models.DateField(
        null=True, blank=True,
        help_text="Effective end date, equals requested_end_date unchanged [DBDD §7, DBDD-AC-27]"
    )
    activation_meal_date = models.DateField(
        null=True, blank=True,
        help_text="Date on which pause transitioned to ACTIVE"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="SCHEDULED"
    )
    requested_at = models.DateTimeField(help_text="When student submitted the request (UTC)")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pause_mess_pause"
        verbose_name = "Mess Pause"
        verbose_name_plural = "Mess Pauses"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["SCHEDULED", "ACTIVE", "CANCELLED", "COMPLETED"]),
                name="pause_mess_pause_status_check",
            ),
            # Partial unique: at most one SCHEDULED or ACTIVE pause per student [REC]
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(status__in=["SCHEDULED", "ACTIVE"]),
                name="uq_pause_one_active_or_sched_per_student",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "status"], name="idx_pause_student_status"),
            models.Index(fields=["mess", "status"], name="idx_pause_mess_status"),
        ]

    def __str__(self):
        return f"Pause {self.pause_id} for student {self.student_id} ({self.status})"


class MessPauseMealSlot(models.Model):
    """
    Qualifying meal occurrences tracked for pause activation delay [SPEC DBDD §7].
    Snacks have qualifies_for_activation = False.
    """
    pause_slot_id = models.AutoField(primary_key=True)
    pause = models.ForeignKey(
        MessPause, on_delete=models.PROTECT, related_name="meal_slots"
    )
    meal_occurrence = models.ForeignKey(
        "mess.MealOccurrence", on_delete=models.PROTECT, related_name="pause_slots"
    )
    slot_sequence = models.IntegerField(help_text="Sequence index: 1, 2, 3...")
    qualifies_for_activation = models.BooleanField(
        default=True,
        help_text="True for Breakfast, Lunch, Dinner; False for Evening Snacks [DBDD §7]"
    )
    slot_date = models.DateField()
    consumed_for_activation = models.BooleanField(
        default=False,
        help_text="True once this slot's end time has passed"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pause_mess_pause_meal_slot"
        verbose_name = "Mess Pause Meal Slot"
        verbose_name_plural = "Mess Pause Meal Slots"
        ordering = ["pause", "slot_sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["pause", "slot_sequence"],
                name="uq_pause_meal_slot_seq",
            ),
        ]

    def __str__(self):
        return f"Pause {self.pause_id} Slot {self.slot_sequence} ({self.slot_date})"
