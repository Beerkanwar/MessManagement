"""
Migration creating StudentSecret model in identity app [SPEC DBDD §13, CONFLICT-09].
Depends on hostel.0001_initial to resolve circular dependency.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0002_phase2_models"),
        ("hostel", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentSecret",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("student_secret_id", models.AutoField(primary_key=True, serialize=False)),
                ("secret_version", models.IntegerField(help_text="Monotonically increasing version for rotation")),
                ("encrypted_secret", models.BinaryField(help_text="AES-GCM encrypted secret key material")),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("RETIRED", "Retired")], default="ACTIVE", max_length=20)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="secrets", to="hostel.student")),
            ],
            options={
                "verbose_name": "Student Secret",
                "verbose_name_plural": "Student Secrets",
                "db_table": "identity_student_secret",
            },
        ),
        migrations.AddConstraint(
            model_name="studentsecret",
            constraint=models.UniqueConstraint(fields=["student", "secret_version"], name="uq_identity_student_secret_version"),
        ),
        migrations.AddConstraint(
            model_name="studentsecret",
            constraint=models.UniqueConstraint(condition=models.Q(status="ACTIVE"), fields=["student"], name="uq_identity_student_secret_one_active"),
        ),
        migrations.AddConstraint(
            model_name="studentsecret",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "RETIRED"]), name="identity_student_secret_status_check"),
        ),
    ]
