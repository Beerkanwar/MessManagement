"""
Initial migration for hostel app: Hostel, Student, StudentMessAssignment, HostelClerkAssignment,
StudentVerification, StudentImportBatch, StudentImportError [SPEC DBDD §4].
Enforces:
- ExclusionConstraint on active student mess assignments
- Insert-only trigger guard on StudentVerification [Invariant 12]
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_btree_gist"),
        ("identity", "0001_initial"),
        ("mess", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Hostel",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("hostel_id", models.AutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(help_text="Short hostel code", max_length=20, unique=True)),
                ("name", models.CharField(help_text="Hostel display name", max_length=255)),
                ("address", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")], default="ACTIVE", max_length=20)),
            ],
            options={
                "verbose_name": "Hostel",
                "verbose_name_plural": "Hostels",
                "db_table": "hostel_hostel",
            },
        ),
        migrations.CreateModel(
            name="Student",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("student_id", models.AutoField(primary_key=True, serialize=False)),
                ("roll_number", models.CharField(max_length=50, unique=True)),
                ("department", models.CharField(blank=True, default="", max_length=255)),
                ("year_of_study", models.IntegerField(blank=True, null=True)),
                ("room_number", models.CharField(blank=True, default="", max_length=50)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")], default="ACTIVE", max_length=20)),
                ("hostel", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="students", to="hostel.hostel")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="student_profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Student",
                "verbose_name_plural": "Students",
                "db_table": "hostel_student",
            },
        ),
        migrations.CreateModel(
            name="StudentImportBatch",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("batch_id", models.AutoField(primary_key=True, serialize=False)),
                ("file_name", models.CharField(max_length=255)),
                ("total_rows", models.IntegerField(default=0)),
                ("successful_rows", models.IntegerField(default=0)),
                ("failed_rows", models.IntegerField(default=0)),
                ("status", models.CharField(choices=[("STAGED", "Staged"), ("VALIDATED", "Validated"), ("COMMITTED", "Committed"), ("FAILED", "Failed"), ("CANCELLED", "Cancelled")], default="STAGED", max_length=20)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("imported_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="import_batches", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Student Import Batch",
                "verbose_name_plural": "Student Import Batches",
                "db_table": "hostel_student_import_batch",
            },
        ),
        migrations.CreateModel(
            name="StudentImportError",
            fields=[
                ("error_id", models.AutoField(primary_key=True, serialize=False)),
                ("row_number", models.IntegerField()),
                ("roll_number", models.CharField(blank=True, default="", max_length=50)),
                ("error_message", models.TextField()),
                ("raw_row_data", models.JSONField(help_text="Raw row content as JSON for debugging")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="errors", to="hostel.studentimportbatch")),
            ],
            options={
                "verbose_name": "Student Import Error",
                "verbose_name_plural": "Student Import Errors",
                "db_table": "hostel_student_import_error",
            },
        ),
        migrations.CreateModel(
            name="StudentMessAssignment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("assignment_id", models.AutoField(primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("PENDING_VERIFICATION", "Pending Verification"), ("ACTIVE", "Active"), ("ENDED", "Ended"), ("REJECTED", "Rejected")], default="PENDING_VERIFICATION", max_length=30)),
                ("effective_from", models.DateField(help_text="Start date of assignment (IST calendar)")),
                ("effective_to", models.DateField(blank=True, help_text="End date of assignment (IST calendar, null=open-ended)", null=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True, default="")),
                ("hostel", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="student_assignments", to="hostel.hostel")),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="student_assignments", to="mess.mess")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mess_assignments", to="hostel.student")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="verified_assignments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Student Mess Assignment",
                "verbose_name_plural": "Student Mess Assignments",
                "db_table": "hostel_student_mess_assignment",
            },
        ),
        migrations.CreateModel(
            name="StudentVerification",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("verification_id", models.AutoField(primary_key=True, serialize=False)),
                ("verification_status", models.CharField(choices=[("VERIFIED", "Verified"), ("REJECTED", "Rejected")], max_length=20)),
                ("verification_notes", models.TextField(blank=True, default="")),
                ("verified_at", models.DateTimeField()),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="verifications", to="hostel.studentmessassignment")),
                ("verified_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="student_verifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Student Verification",
                "verbose_name_plural": "Student Verifications",
                "db_table": "hostel_student_verification",
            },
        ),
        migrations.CreateModel(
            name="HostelClerkAssignment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("clerk_assignment_id", models.AutoField(primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True)),
                ("assigned_at", models.DateTimeField(help_text="When the clerk was assigned")),
                ("deactivated_at", models.DateTimeField(blank=True, null=True)),
                ("hostel", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="clerk_assignments", to="hostel.hostel")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="clerk_assignments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Hostel Clerk Assignment",
                "verbose_name_plural": "Hostel Clerk Assignments",
                "db_table": "hostel_clerk_assignment",
            },
        ),
        migrations.AddConstraint(
            model_name="hostel",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "INACTIVE"]), name="hostel_hostel_status_check"),
        ),
        migrations.AddIndex(
            model_name="student",
            index=models.Index(fields=["roll_number"], name="idx_hostel_student_roll"),
        ),
        migrations.AddConstraint(
            model_name="student",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "INACTIVE"]), name="hostel_student_status_check"),
        ),
        migrations.AddConstraint(
            model_name="studentimportbatch",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["STAGED", "VALIDATED", "COMMITTED", "FAILED", "CANCELLED"]), name="hostel_import_batch_status_check"),
        ),
        migrations.AddIndex(
            model_name="studentmessassignment",
            index=models.Index(fields=["student", "status"], name="idx_hostel_assign_stud_stat"),
        ),
        migrations.AddIndex(
            model_name="studentmessassignment",
            index=models.Index(fields=["mess", "status"], name="idx_hostel_assign_mess_status"),
        ),
        migrations.AddConstraint(
            model_name="studentmessassignment",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["PENDING_VERIFICATION", "ACTIVE", "ENDED", "REJECTED"]), name="hostel_assignment_status_check"),
        ),
        migrations.AddConstraint(
            model_name="studentverification",
            constraint=models.CheckConstraint(condition=models.Q(verification_status__in=["VERIFIED", "REJECTED"]), name="hostel_verification_status_check"),
        ),
        migrations.AddConstraint(
            model_name="hostelclerkassignment",
            constraint=models.UniqueConstraint(condition=models.Q(is_active=True), fields=["user"], name="uq_hostel_clerk_one_active_per_user"),
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE hostel_student_mess_assignment
            ADD CONSTRAINT excl_hostel_student_mess_assignment_overlap
            EXCLUDE USING gist (
                student_id WITH =,
                daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
            ) WHERE (status = 'ACTIVE');
            """,
            reverse_sql="""
            ALTER TABLE hostel_student_mess_assignment
            DROP CONSTRAINT IF EXISTS excl_hostel_student_mess_assignment_overlap;
            """,
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION trg_prevent_update_or_delete_student_verification()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Table hostel_student_verification is insert-only. UPDATE and DELETE operations are forbidden.';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_guard_hostel_student_verification
            BEFORE UPDATE OR DELETE ON hostel_student_verification
            FOR EACH ROW
            EXECUTE FUNCTION trg_prevent_update_or_delete_student_verification();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_guard_hostel_student_verification ON hostel_student_verification;
            DROP FUNCTION IF EXISTS trg_prevent_update_or_delete_student_verification();
            """,
        ),
    ]
