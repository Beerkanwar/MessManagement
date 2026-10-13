"""
Initial migration for mess app: Mess, MessManagerAssignment, MealType, MealOccurrence, MealRate [SPEC DBDD §5].
ExclusionConstraint on mess_meal_rate date ranges enforced via RunSQL.
ExtraItem and ExtraPrice are in 0002 to resolve circular dependency with hostel.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_btree_gist"),
        ("identity", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MealType",
            fields=[
                ("meal_type_id", models.AutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(help_text="BREAKFAST, LUNCH, EVENING_SNACKS, DINNER", max_length=50, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("sequence_no", models.IntegerField(help_text="Display/chronological ordering: 1, 2, 3, 4")),
                ("is_fixed", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Meal Type",
                "verbose_name_plural": "Meal Types",
                "db_table": "mess_meal_type",
                "ordering": ["sequence_no"],
            },
        ),
        migrations.CreateModel(
            name="Mess",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("mess_id", models.AutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(help_text="Short mess identifier", max_length=20, unique=True)),
                ("name", models.CharField(help_text="Mess hall display name", max_length=255)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")], default="ACTIVE", max_length=20)),
            ],
            options={
                "verbose_name": "Mess",
                "verbose_name_plural": "Messes",
                "db_table": "mess_mess",
            },
        ),
        migrations.CreateModel(
            name="MealOccurrence",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("meal_occurrence_id", models.AutoField(primary_key=True, serialize=False)),
                ("meal_date", models.DateField(help_text="Scheduled calendar date (IST)")),
                ("status", models.CharField(choices=[("SCHEDULED", "Scheduled"), ("CANCELLED", "Cancelled")], default="SCHEDULED", max_length=20)),
                ("configuration_version", models.BigIntegerField(default=1, help_text="Tracks menu/time configuration changes")),
                ("meal_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="occurrences", to="mess.mealtype")),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="meal_occurrences", to="mess.mess")),
            ],
            options={
                "verbose_name": "Meal Occurrence",
                "verbose_name_plural": "Meal Occurrences",
                "db_table": "mess_meal_occurrence",
            },
        ),
        migrations.CreateModel(
            name="MealRate",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("meal_rate_id", models.AutoField(primary_key=True, serialize=False)),
                ("rate", models.DecimalField(decimal_places=4, help_text="Common diet rate per meal [DEC-04]", max_digits=19)),
                ("effective_from", models.DateField(help_text="Start date of rate (inclusive)")),
                ("effective_to", models.DateField(blank=True, help_text="End date of rate (inclusive, null=open-ended)", null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_meal_rates", to=settings.AUTH_USER_MODEL)),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="meal_rates", to="mess.mess")),
            ],
            options={
                "verbose_name": "Meal Rate",
                "verbose_name_plural": "Meal Rates",
                "db_table": "mess_meal_rate",
            },
        ),
        migrations.CreateModel(
            name="MessManagerAssignment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("assignment_id", models.AutoField(primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True)),
                ("assigned_at", models.DateTimeField(help_text="When the manager was assigned")),
                ("deactivated_at", models.DateTimeField(blank=True, null=True)),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="manager_assignments", to="mess.mess")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mess_manager_assignments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Mess Manager Assignment",
                "verbose_name_plural": "Mess Manager Assignments",
                "db_table": "mess_manager_assignment",
            },
        ),
        migrations.AddConstraint(
            model_name="mess",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "INACTIVE"]), name="mess_mess_status_check"),
        ),
        migrations.AddIndex(
            model_name="mealoccurrence",
            index=models.Index(fields=["mess", "meal_date"], name="idx_mess_occ_mess_date"),
        ),
        migrations.AddConstraint(
            model_name="mealoccurrence",
            constraint=models.UniqueConstraint(fields=["mess", "meal_date", "meal_type"], name="uq_mess_occurrence_mess_date_type"),
        ),
        migrations.AddConstraint(
            model_name="mealoccurrence",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["SCHEDULED", "CANCELLED"]), name="mess_occurrence_status_check"),
        ),
        migrations.AddIndex(
            model_name="mealrate",
            index=models.Index(fields=["mess", "effective_from"], name="idx_mess_rate_mess_eff"),
        ),
        migrations.AddConstraint(
            model_name="mealrate",
            constraint=models.CheckConstraint(condition=models.Q(rate__gt=0), name="mess_meal_rate_positive_check"),
        ),
        migrations.AddConstraint(
            model_name="messmanagerassignment",
            constraint=models.UniqueConstraint(condition=models.Q(is_active=True), fields=["user"], name="uq_mess_manager_one_active_per_user"),
        ),
        migrations.AddConstraint(
            model_name="messmanagerassignment",
            constraint=models.UniqueConstraint(condition=models.Q(is_active=True), fields=["mess"], name="uq_mess_one_active_manager"),
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE mess_meal_rate
            ADD CONSTRAINT excl_mess_meal_rate_overlap
            EXCLUDE USING gist (
                mess_id WITH =,
                daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
            );
            """,
            reverse_sql="""
            ALTER TABLE mess_meal_rate
            DROP CONSTRAINT IF EXISTS excl_mess_meal_rate_overlap;
            """,
        ),
    ]
