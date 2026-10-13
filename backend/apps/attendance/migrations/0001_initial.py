"""
Initial migration for attendance app: MealConsumption, ExtraTransaction, AttendanceCorrection [SPEC DBDD §6].
Enforces:
- Price snapshot immutability triggers on MealConsumption and ExtraTransaction [Invariant 11]
- Insert-only trigger guard on AttendanceCorrection [Invariant 12]
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_btree_gist"),
        ("identity", "0002_phase2_models"),
        ("hostel", "0001_initial"),
        ("mess", "0002_extraitem_extraprice"),
    ]

    operations = [
        migrations.CreateModel(
            name="MealConsumption",
            fields=[
                ("meal_consumption_id", models.AutoField(primary_key=True, serialize=False)),
                ("transaction_id", models.UUIDField(help_text="Stable GUID assigned before local persistence [DBDD §6.1, Invariant 5]", unique=True)),
                ("roll_number_snapshot", models.CharField(help_text="Denormalized roll number snapshot at scan time", max_length=50)),
                ("meal_date", models.DateField(help_text="Scheduled date of the meal (IST calendar) [DEC-01, DBDD §5.1]")),
                ("price_at_transaction", models.DecimalField(decimal_places=4, help_text="Immutable rate snapshot at transaction time [DBDD §5.2]", max_digits=19)),
                ("transaction_timestamp", models.DateTimeField(help_text="Timestamp when scan occurred on client (UTC)")),
                ("verification_method", models.CharField(choices=[("QR_HMAC_SHA256", "QR HMAC-SHA256"), ("MANUAL_CORRECTION", "Manual Correction")], default="QR_HMAC_SHA256", max_length=50)),
                ("verification_result", models.CharField(choices=[("SUCCESS", "Success"), ("NOT_APPLICABLE", "Not Applicable")], default="SUCCESS", max_length=50)),
                ("source", models.CharField(choices=[("QR", "QR"), ("CORRECTION", "Correction"), ("SYNC_RESOLUTION", "Sync Resolution")], default="QR", max_length=30)),
                ("sync_status", models.CharField(choices=[("PENDING", "Pending"), ("SYNCHRONIZED", "Synchronized"), ("IDEMPOTENT_SUCCESS", "Idempotent Success"), ("DUPLICATE", "Duplicate"), ("REJECTED", "Rejected"), ("CONFLICT", "Conflict")], default="SYNCHRONIZED", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("device_registration", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="meal_consumptions", to="identity.deviceregistration")),
                ("meal_occurrence", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="consumptions", to="mess.mealoccurrence")),
                ("meal_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="meal_consumptions", to="mess.mealtype")),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="meal_consumptions", to="mess.mess")),
                ("recorded_by_user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recorded_meals", to=settings.AUTH_USER_MODEL)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="meal_consumptions", to="hostel.student")),
            ],
            options={
                "verbose_name": "Meal Consumption",
                "verbose_name_plural": "Meal Consumptions",
                "db_table": "attendance_meal_consumption",
            },
        ),
        migrations.CreateModel(
            name="ExtraTransaction",
            fields=[
                ("extra_transaction_id", models.AutoField(primary_key=True, serialize=False)),
                ("transaction_id", models.UUIDField(help_text="Stable GUID assigned before local persistence [DBDD §6.1, Invariant 5]", unique=True)),
                ("quantity", models.IntegerField(help_text="Units consumed, must be > 0")),
                ("unit_price_at_transaction", models.DecimalField(decimal_places=4, help_text="Price snapshot at transaction time [DBDD §5.2]", max_digits=19)),
                ("total_amount", models.DecimalField(decimal_places=4, help_text="Quantity * unit_price_at_transaction", max_digits=19)),
                ("transaction_timestamp", models.DateTimeField()),
                ("source", models.CharField(choices=[("SCAN_CONFIRMATION", "Scan Confirmation"), ("MANUAL", "Manual"), ("SYNC_RESOLUTION", "Sync Resolution")], default="SCAN_CONFIRMATION", max_length=30)),
                ("sync_status", models.CharField(choices=[("PENDING", "Pending"), ("SYNCHRONIZED", "Synchronized"), ("IDEMPOTENT_SUCCESS", "Idempotent Success"), ("DUPLICATE", "Duplicate"), ("REJECTED", "Rejected"), ("CONFLICT", "Conflict")], default="SYNCHRONIZED", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("device_registration", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="extra_transactions", to="identity.deviceregistration")),
                ("extra_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="mess.extraitem")),
                ("hostel", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="extra_transactions", to="hostel.hostel")),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="extra_transactions", to="mess.mess")),
                ("recorded_by_user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recorded_extras", to=settings.AUTH_USER_MODEL)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="extra_transactions", to="hostel.student")),
            ],
            options={
                "verbose_name": "Extra Transaction",
                "verbose_name_plural": "Extra Transactions",
                "db_table": "attendance_extra_transaction",
            },
        ),
        migrations.CreateModel(
            name="AttendanceCorrection",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("correction_id", models.AutoField(primary_key=True, serialize=False)),
                ("correction_transaction_id", models.UUIDField(unique=True)),
                ("meal_date", models.DateField(help_text="MealDate corrected")),
                ("action", models.CharField(choices=[("ADD_MISSING", "Add Missing"), ("REMOVE_INCORRECT", "Remove Incorrect")], max_length=30)),
                ("requested_at", models.DateTimeField()),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("reason", models.TextField(help_text="Mandatory reason (min 5 chars) [DEC-12, D12]")),
                ("status", models.CharField(choices=[("APPLIED", "Applied"), ("REJECTED", "Rejected")], default="APPLIED", max_length=20)),
                ("source_transaction_id", models.UUIDField(blank=True, null=True)),
                ("actor_user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applied_corrections", to=settings.AUTH_USER_MODEL)),
                ("meal_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attendance_corrections", to="mess.mealtype")),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attendance_corrections", to="mess.mess")),
                ("original_meal_consumption", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="corrections", to="attendance.mealconsumption")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attendance_corrections", to="hostel.student")),
            ],
            options={
                "verbose_name": "Attendance Correction",
                "verbose_name_plural": "Attendance Corrections",
                "db_table": "attendance_attendance_correction",
            },
        ),
        migrations.AddIndex(
            model_name="mealconsumption",
            index=models.Index(fields=["mess", "meal_date", "meal_type"], name="idx_att_meal_mess_date_type"),
        ),
        migrations.AddIndex(
            model_name="mealconsumption",
            index=models.Index(fields=["student", "-meal_date"], name="idx_att_meal_student_date"),
        ),
        migrations.AddIndex(
            model_name="mealconsumption",
            index=models.Index(fields=["transaction_id"], name="idx_att_meal_txn_id"),
        ),
        migrations.AddConstraint(
            model_name="mealconsumption",
            constraint=models.UniqueConstraint(fields=["student", "meal_date", "meal_type"], name="uq_attendance_student_date_meal_type"),
        ),
        migrations.AddConstraint(
            model_name="mealconsumption",
            constraint=models.CheckConstraint(condition=models.Q(price_at_transaction__gte=0), name="attendance_meal_price_non_neg_check"),
        ),
        migrations.AddIndex(
            model_name="extratransaction",
            index=models.Index(fields=["student", "-transaction_timestamp"], name="idx_att_extra_student_time"),
        ),
        migrations.AddIndex(
            model_name="extratransaction",
            index=models.Index(fields=["mess", "-transaction_timestamp"], name="idx_att_extra_mess_time"),
        ),
        migrations.AddIndex(
            model_name="extratransaction",
            index=models.Index(fields=["transaction_id"], name="idx_att_extra_txn_id"),
        ),
        migrations.AddConstraint(
            model_name="extratransaction",
            constraint=models.CheckConstraint(condition=models.Q(quantity__gt=0), name="attendance_extra_quantity_gt_zero"),
        ),
        migrations.AddConstraint(
            model_name="extratransaction",
            constraint=models.CheckConstraint(condition=models.Q(unit_price_at_transaction__gte=0), name="attendance_extra_unit_price_non_neg"),
        ),
        migrations.AddConstraint(
            model_name="extratransaction",
            constraint=models.CheckConstraint(condition=models.Q(total_amount=models.F("quantity") * models.F("unit_price_at_transaction")), name="attendance_extra_total_amount_check"),
        ),
        migrations.AddIndex(
            model_name="attendancecorrection",
            index=models.Index(fields=["student", "meal_date", "meal_type"], name="idx_att_corr_student_meal"),
        ),
        migrations.AddIndex(
            model_name="attendancecorrection",
            index=models.Index(fields=["correction_transaction_id"], name="idx_att_corr_txn_id"),
        ),
        migrations.AddConstraint(
            model_name="attendancecorrection",
            constraint=models.CheckConstraint(condition=models.Q(action__in=["ADD_MISSING", "REMOVE_INCORRECT"]), name="attendance_correction_action_check"),
        ),
        migrations.AddConstraint(
            model_name="attendancecorrection",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["APPLIED", "REJECTED"]), name="attendance_correction_status_check"),
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION trg_guard_meal_consumption_price_immutability()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.price_at_transaction IS DISTINCT FROM NEW.price_at_transaction THEN
                    RAISE EXCEPTION 'PriceAtTransaction on MealConsumption is an immutable financial snapshot and cannot be modified.';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_meal_consumption_price_immutability
            BEFORE UPDATE ON attendance_meal_consumption
            FOR EACH ROW
            EXECUTE FUNCTION trg_guard_meal_consumption_price_immutability();

            CREATE OR REPLACE FUNCTION trg_guard_extra_transaction_price_immutability()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.unit_price_at_transaction IS DISTINCT FROM NEW.unit_price_at_transaction
                   OR OLD.total_amount IS DISTINCT FROM NEW.total_amount THEN
                    RAISE EXCEPTION 'UnitPriceAtTransaction and TotalAmount on ExtraTransaction are immutable financial snapshots and cannot be modified.';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_extra_transaction_price_immutability
            BEFORE UPDATE ON attendance_extra_transaction
            FOR EACH ROW
            EXECUTE FUNCTION trg_guard_extra_transaction_price_immutability();

            CREATE OR REPLACE FUNCTION trg_prevent_update_or_delete_attendance_correction()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Table attendance_attendance_correction is insert-only. UPDATE and DELETE operations are forbidden.';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_guard_attendance_correction
            BEFORE UPDATE OR DELETE ON attendance_attendance_correction
            FOR EACH ROW
            EXECUTE FUNCTION trg_prevent_update_or_delete_attendance_correction();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_meal_consumption_price_immutability ON attendance_meal_consumption;
            DROP FUNCTION IF EXISTS trg_guard_meal_consumption_price_immutability();

            DROP TRIGGER IF EXISTS trg_extra_transaction_price_immutability ON attendance_extra_transaction;
            DROP FUNCTION IF EXISTS trg_guard_extra_transaction_price_immutability();

            DROP TRIGGER IF EXISTS trg_guard_attendance_correction ON attendance_attendance_correction;
            DROP FUNCTION IF EXISTS trg_prevent_update_or_delete_attendance_correction();
            """,
        ),
    ]
