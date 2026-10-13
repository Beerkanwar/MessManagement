"""
Initial migration for feedback app: Feedback [SPEC DBDD §10].
Enforces:
- UniqueConstraint: (student, calendar_year, calendar_month) [Invariant 6, DBDD-AC-29]
- Insert-only trigger guard [Invariant 12]
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
            name="Feedback",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("feedback_id", models.AutoField(primary_key=True, serialize=False)),
                ("calendar_year", models.IntegerField(help_text="Calendar year")),
                ("calendar_month", models.IntegerField(help_text="Calendar month (1-12)")),
                ("food_quality_rating", models.IntegerField(help_text="Rating from 1 (poor) to 5 (excellent)")),
                ("taste_rating", models.IntegerField(help_text="Rating from 1 (poor) to 5 (excellent)")),
                ("comments", models.TextField(blank=True, default="")),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="feedbacks", to="mess.mess")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="feedbacks", to="hostel.student")),
            ],
            options={
                "verbose_name": "Feedback",
                "verbose_name_plural": "Feedbacks",
                "db_table": "feedback_feedback",
            },
        ),
        migrations.AddIndex(
            model_name="feedback",
            index=models.Index(fields=["mess", "calendar_year", "calendar_month"], name="idx_feedback_mess_year_month"),
        ),
        migrations.AddConstraint(
            model_name="feedback",
            constraint=models.UniqueConstraint(fields=["student", "calendar_year", "calendar_month"], name="uq_feedback_student_year_month"),
        ),
        migrations.AddConstraint(
            model_name="feedback",
            constraint=models.CheckConstraint(condition=models.Q(calendar_month__gte=1, calendar_month__lte=12), name="feedback_month_check"),
        ),
        migrations.AddConstraint(
            model_name="feedback",
            constraint=models.CheckConstraint(condition=models.Q(food_quality_rating__gte=1, food_quality_rating__lte=5), name="feedback_food_quality_check"),
        ),
        migrations.AddConstraint(
            model_name="feedback",
            constraint=models.CheckConstraint(condition=models.Q(taste_rating__gte=1, taste_rating__lte=5), name="feedback_taste_rating_check"),
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION trg_prevent_update_or_delete_feedback()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Table feedback_feedback is insert-only. UPDATE and DELETE operations are forbidden.';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_guard_feedback
            BEFORE UPDATE OR DELETE ON feedback_feedback
            FOR EACH ROW
            EXECUTE FUNCTION trg_prevent_update_or_delete_feedback();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_guard_feedback ON feedback_feedback;
            DROP FUNCTION IF EXISTS trg_prevent_update_or_delete_feedback();
            """,
        ),
    ]
