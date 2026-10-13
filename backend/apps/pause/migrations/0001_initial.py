"""
Initial migration for pause app: MessPause, MessPauseMealSlot [SPEC DBDD §7].
Enforces:
- UniqueConstraint: at most one SCHEDULED or ACTIVE pause per student
- UniqueConstraint: (pause, slot_sequence) on MessPauseMealSlot
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_btree_gist"),
        ("hostel", "0001_initial"),
        ("mess", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MessPause",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("pause_id", models.AutoField(primary_key=True, serialize=False)),
                ("requested_start_date", models.DateField(help_text="Requested start date (IST calendar)")),
                ("requested_end_date", models.DateField(help_text="Requested end date (IST calendar)")),
                ("effective_start_date", models.DateField(blank=True, help_text="Calculated date of the first slot after third qualifying slot [DEC-06]", null=True)),
                ("effective_end_date", models.DateField(blank=True, help_text="Effective end date, equals requested_end_date unchanged [DBDD §7, DBDD-AC-27]", null=True)),
                ("activation_meal_date", models.DateField(blank=True, help_text="Date on which pause transitioned to ACTIVE", null=True)),
                ("status", models.CharField(choices=[("SCHEDULED", "Scheduled"), ("ACTIVE", "Active"), ("CANCELLED", "Cancelled"), ("COMPLETED", "Completed")], default="SCHEDULED", max_length=20)),
                ("requested_at", models.DateTimeField(help_text="When student submitted the request (UTC)")),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("cancellation_reason", models.TextField(blank=True, default="")),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pauses", to="mess.mess")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pauses", to="hostel.student")),
            ],
            options={
                "verbose_name": "Mess Pause",
                "verbose_name_plural": "Mess Pauses",
                "db_table": "pause_mess_pause",
            },
        ),
        migrations.CreateModel(
            name="MessPauseMealSlot",
            fields=[
                ("pause_slot_id", models.AutoField(primary_key=True, serialize=False)),
                ("slot_sequence", models.IntegerField(help_text="Sequence index: 1, 2, 3...")),
                ("qualifies_for_activation", models.BooleanField(default=True, help_text="True for Breakfast, Lunch, Dinner; False for Evening Snacks [DBDD §7]")),
                ("slot_date", models.DateField()),
                ("consumed_for_activation", models.BooleanField(default=False, help_text="True once this slot's end time has passed")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("meal_occurrence", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pause_slots", to="mess.mealoccurrence")),
                ("pause", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="meal_slots", to="pause.messpause")),
            ],
            options={
                "verbose_name": "Mess Pause Meal Slot",
                "verbose_name_plural": "Mess Pause Meal Slots",
                "db_table": "pause_mess_pause_meal_slot",
                "ordering": ["pause", "slot_sequence"],
            },
        ),
        migrations.AddIndex(
            model_name="messpause",
            index=models.Index(fields=["student", "status"], name="idx_pause_student_status"),
        ),
        migrations.AddIndex(
            model_name="messpause",
            index=models.Index(fields=["mess", "status"], name="idx_pause_mess_status"),
        ),
        migrations.AddConstraint(
            model_name="messpause",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["SCHEDULED", "ACTIVE", "CANCELLED", "COMPLETED"]), name="pause_mess_pause_status_check"),
        ),
        migrations.AddConstraint(
            model_name="messpause",
            constraint=models.UniqueConstraint(condition=models.Q(status__in=["SCHEDULED", "ACTIVE"]), fields=["student"], name="uq_pause_one_active_or_sched_per_student"),
        ),
        migrations.AddConstraint(
            model_name="messpausemealslot",
            constraint=models.UniqueConstraint(fields=["pause", "slot_sequence"], name="uq_pause_meal_slot_seq"),
        ),
    ]
