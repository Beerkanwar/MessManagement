"""
Initial migration for billing app [SPEC DBDD §8, Owner change C01].
Models: Semester, BillingPeriod, BillingPolicy, Bill, BillLine, BillAdjustment,
BalanceAccount, BalanceLedgerEntry.
Enforces:
- ExclusionConstraint on BillingPolicy effective date ranges per mess
- Locked-bill guard triggers on Bill, BillLine, BillAdjustment [DBDD §8.3]
- Insert-only trigger guards on BillAdjustment and BalanceLedgerEntry [Invariant 12]
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_btree_gist"),
        ("identity", "0001_initial"),
        ("hostel", "0001_initial"),
        ("mess", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Semester",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("semester_id", models.AutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(help_text="e.g. 'AUTUMN-2026'", max_length=50, unique=True)),
                ("name", models.CharField(help_text="e.g. 'Autumn Semester 2026-27'", max_length=100)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("status", models.CharField(choices=[("UPCOMING", "Upcoming"), ("ACTIVE", "Active"), ("COMPLETED", "Completed"), ("ARCHIVED", "Archived")], default="UPCOMING", max_length=20)),
            ],
            options={
                "verbose_name": "Semester",
                "verbose_name_plural": "Semesters",
                "db_table": "billing_semester",
            },
        ),
        migrations.CreateModel(
            name="BillingPeriod",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("billing_period_id", models.AutoField(primary_key=True, serialize=False)),
                ("year", models.IntegerField(help_text="Calendar year (e.g. 2026)")),
                ("month", models.IntegerField(help_text="Calendar month (1-12)")),
                ("period_start", models.DateField(help_text="First date of month")),
                ("period_end", models.DateField(help_text="Last date of month")),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("BILL_GENERATED", "Bill Generated"), ("REVIEWED", "Reviewed"), ("LOCKED", "Locked")], default="OPEN", max_length=30)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("generated_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("unlocked_at", models.DateTimeField(blank=True, null=True)),
                ("unlock_reason", models.TextField(blank=True, default="")),
                ("locked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="locked_billing_periods", to=settings.AUTH_USER_MODEL)),
                ("unlocked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="unlocked_billing_periods", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Billing Period",
                "verbose_name_plural": "Billing Periods",
                "db_table": "billing_billing_period",
            },
        ),
        migrations.CreateModel(
            name="BillingPolicy",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("billing_policy_id", models.AutoField(primary_key=True, serialize=False)),
                ("minimum_diet_count", models.IntegerField(help_text="Base minimum diet count for students in this mess [DBDD §8]")),
                ("effective_from", models.DateField(help_text="Start date of policy (inclusive)")),
                ("effective_to", models.DateField(blank=True, help_text="End date of policy (inclusive, null=open-ended)", null=True)),
                ("policy_version", models.IntegerField(default=1)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_billing_policies", to=settings.AUTH_USER_MODEL)),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_policies", to="mess.mess")),
            ],
            options={
                "verbose_name": "Billing Policy",
                "verbose_name_plural": "Billing Policies",
                "db_table": "billing_billing_policy",
            },
        ),
        migrations.CreateModel(
            name="Bill",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("bill_id", models.AutoField(primary_key=True, serialize=False)),
                ("meal_component_amount", models.DecimalField(decimal_places=4, help_text="MAX(minimum_diet_count_snapshot, actual_meal_count) * common_diet_rate_snapshot [C01]", max_digits=19)),
                ("extra_charges_amount", models.DecimalField(decimal_places=4, help_text="Sum of extra transactions in period", max_digits=19)),
                ("adjustment_amount", models.DecimalField(decimal_places=4, default=0, help_text="Sum of FEE and FINE adjustments (non-negative additions only) [C01]", max_digits=19)),
                ("final_amount", models.DecimalField(decimal_places=4, help_text="meal_component_amount + extra_charges_amount + adjustment_amount [C01]", max_digits=19)),
                ("common_diet_rate_snapshot", models.DecimalField(decimal_places=4, help_text="Rate snapshot at generation [DBDD §8.1]", max_digits=19)),
                ("minimum_diet_count_snapshot", models.IntegerField(help_text="Billed minimum count after pause deduction [DEC-04]")),
                ("actual_meal_count", models.IntegerField(default=0, help_text="Count of qualifying meals consumed in period [C01]")),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("FINAL", "Final"), ("LOCKED", "Locked")], default="DRAFT", max_length=20)),
                ("generated_at", models.DateTimeField()),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("billing_period", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bills", to="billing.billingperiod")),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bills", to="mess.mess")),
                ("semester", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="bills", to="billing.semester")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bills", to="hostel.student")),
            ],
            options={
                "verbose_name": "Bill",
                "verbose_name_plural": "Bills",
                "db_table": "billing_bill",
            },
        ),
        migrations.CreateModel(
            name="BillLine",
            fields=[
                ("bill_line_id", models.AutoField(primary_key=True, serialize=False)),
                ("line_type", models.CharField(choices=[("MINIMUM_DIET", "Minimum Diet"), ("EXTRA", "Extra"), ("ADJUSTMENT", "Adjustment")], max_length=30)),
                ("source_entity_type", models.CharField(blank=True, default="", max_length=50)),
                ("source_entity_id", models.CharField(blank=True, default="", max_length=50)),
                ("description", models.TextField()),
                ("quantity", models.IntegerField(default=1)),
                ("unit_rate", models.DecimalField(decimal_places=4, default=0, max_digits=19)),
                ("amount", models.DecimalField(decimal_places=4, max_digits=19)),
                ("calculation_order", models.IntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("bill", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lines", to="billing.bill")),
            ],
            options={
                "verbose_name": "Bill Line",
                "verbose_name_plural": "Bill Lines",
                "db_table": "billing_bill_line",
                "ordering": ["bill", "calculation_order"],
            },
        ),
        migrations.CreateModel(
            name="BillAdjustment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("adjustment_id", models.AutoField(primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=4, help_text="Adjustment amount, strictly > 0 [C01]", max_digits=19)),
                ("adjustment_type", models.CharField(choices=[("FEE", "Fee"), ("FINE", "Fine")], help_text="FEE or FINE only; additions only [C01]", max_length=20)),
                ("reason", models.TextField(help_text="Mandatory reason for fee or fine")),
                ("bill", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="adjustments", to="billing.bill")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_bill_adjustments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Bill Adjustment",
                "verbose_name_plural": "Bill Adjustments",
                "db_table": "billing_bill_adjustment",
            },
        ),
        migrations.CreateModel(
            name="BalanceAccount",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("balance_account_id", models.AutoField(primary_key=True, serialize=False)),
                ("opening_balance", models.DecimalField(decimal_places=4, default=0, max_digits=19)),
                ("current_balance", models.DecimalField(decimal_places=4, default=0, help_text="Derived cached balance, may be negative [DBDD §8, Invariant 25]", max_digits=19)),
                ("last_calculated_at", models.DateTimeField(blank=True, null=True)),
                ("semester", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="balance_accounts", to="billing.semester")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="balance_accounts", to="hostel.student")),
            ],
            options={
                "verbose_name": "Balance Account",
                "verbose_name_plural": "Balance Accounts",
                "db_table": "billing_balance_account",
            },
        ),
        migrations.CreateModel(
            name="BalanceLedgerEntry",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("ledger_entry_id", models.AutoField(primary_key=True, serialize=False)),
                ("entry_type", models.CharField(choices=[("OPENING", "Opening Balance"), ("CREDIT", "Credit"), ("BILL_CHARGE", "Bill Charge"), ("BILL_REVERSAL", "Bill Reversal")], max_length=30)),
                ("amount", models.DecimalField(decimal_places=4, help_text="Signed amount: positive for credits, negative for charges", max_digits=19)),
                ("reference_type", models.CharField(blank=True, default="", max_length=50)),
                ("reference_id", models.CharField(blank=True, default="", max_length=50)),
                ("effective_date", models.DateField()),
                ("description", models.TextField(blank=True, default="")),
                ("balance_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="billing.balanceaccount")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_ledger_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Balance Ledger Entry",
                "verbose_name_plural": "Balance Ledger Entries",
                "db_table": "billing_balance_ledger_entry",
            },
        ),
        migrations.AddConstraint(
            model_name="semester",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["UPCOMING", "ACTIVE", "COMPLETED", "ARCHIVED"]), name="billing_semester_status_check"),
        ),
        migrations.AddConstraint(
            model_name="semester",
            constraint=models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="billing_semester_dates_check"),
        ),
        migrations.AddConstraint(
            model_name="billingperiod",
            constraint=models.UniqueConstraint(fields=["year", "month"], name="uq_billing_period_year_month"),
        ),
        migrations.AddConstraint(
            model_name="billingperiod",
            constraint=models.CheckConstraint(condition=models.Q(month__gte=1, month__lte=12), name="billing_period_month_check"),
        ),
        migrations.AddConstraint(
            model_name="billingperiod",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["OPEN", "BILL_GENERATED", "REVIEWED", "LOCKED"]), name="billing_period_status_check"),
        ),
        migrations.AddIndex(
            model_name="billingpolicy",
            index=models.Index(fields=["mess", "effective_from"], name="idx_billing_policy_mess_eff"),
        ),
        migrations.AddConstraint(
            model_name="billingpolicy",
            constraint=models.CheckConstraint(condition=models.Q(minimum_diet_count__gte=0), name="billing_policy_min_diet_non_neg"),
        ),
        migrations.AddIndex(
            model_name="bill",
            index=models.Index(fields=["billing_period", "mess"], name="idx_billing_bill_period_mess"),
        ),
        migrations.AddIndex(
            model_name="bill",
            index=models.Index(fields=["student", "-billing_period"], name="idx_bill_student_period"),
        ),
        migrations.AddConstraint(
            model_name="bill",
            constraint=models.UniqueConstraint(fields=["student", "mess", "billing_period"], name="uq_billing_bill_student_mess_period"),
        ),
        migrations.AddConstraint(
            model_name="bill",
            constraint=models.CheckConstraint(condition=models.Q(final_amount=models.F("meal_component_amount") + models.F("extra_charges_amount") + models.F("adjustment_amount")), name="billing_bill_final_amount_calc_check"),
        ),
        migrations.AddConstraint(
            model_name="bill",
            constraint=models.CheckConstraint(condition=models.Q(adjustment_amount__gte=0), name="billing_bill_adjustment_amount_non_neg"),
        ),
        migrations.AddConstraint(
            model_name="bill",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "FINAL", "LOCKED"]), name="billing_bill_status_check"),
        ),
        migrations.AddConstraint(
            model_name="billline",
            constraint=models.CheckConstraint(condition=models.Q(line_type__in=["MINIMUM_DIET", "EXTRA", "ADJUSTMENT"]), name="billing_bill_line_type_check"),
        ),
        migrations.AddConstraint(
            model_name="billadjustment",
            constraint=models.CheckConstraint(condition=models.Q(amount__gt=0), name="billing_bill_adjustment_amount_gt_zero"),
        ),
        migrations.AddConstraint(
            model_name="billadjustment",
            constraint=models.CheckConstraint(condition=models.Q(adjustment_type__in=["FEE", "FINE"]), name="billing_bill_adjustment_type_check"),
        ),
        migrations.AddConstraint(
            model_name="balanceaccount",
            constraint=models.UniqueConstraint(fields=["student", "semester"], name="uq_billing_balance_account_student_sem"),
        ),
        migrations.AddIndex(
            model_name="balanceledgerentry",
            index=models.Index(fields=["balance_account", "effective_date", "ledger_entry_id"], name="idx_billing_ledger_acct_eff_id"),
        ),
        migrations.AddConstraint(
            model_name="balanceledgerentry",
            constraint=models.CheckConstraint(condition=models.Q(entry_type__in=["OPENING", "CREDIT", "BILL_CHARGE", "BILL_REVERSAL"]), name="billing_ledger_entry_type_check"),
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_billing_policy
            ADD CONSTRAINT excl_billing_policy_overlap
            EXCLUDE USING gist (
                mess_id WITH =,
                daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
            );
            """,
            reverse_sql="""
            ALTER TABLE billing_billing_policy
            DROP CONSTRAINT IF EXISTS excl_billing_policy_overlap;
            """,
        ),
        migrations.RunSQL(
            sql="""
            -- Locked-Bill Guard Trigger Function for Bill
            CREATE OR REPLACE FUNCTION trg_guard_locked_bill()
            RETURNS TRIGGER AS $$
            DECLARE
                bp_status VARCHAR(30);
                target_bp_id INT;
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    target_bp_id := OLD.billing_period_id;
                ELSE
                    target_bp_id := NEW.billing_period_id;
                END IF;

                SELECT status INTO bp_status FROM billing_billing_period WHERE billing_period_id = target_bp_id;
                IF bp_status = 'LOCKED' THEN
                    RAISE EXCEPTION 'Cannot % Bill because the parent BillingPeriod is LOCKED.', TG_OP;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                ELSE
                    RETURN NEW;
                END IF;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_bill_locked_guard
            BEFORE INSERT OR UPDATE OR DELETE ON billing_bill
            FOR EACH ROW
            EXECUTE FUNCTION trg_guard_locked_bill();

            -- Locked-Bill Guard Trigger Function for BillLine
            CREATE OR REPLACE FUNCTION trg_guard_locked_bill_line()
            RETURNS TRIGGER AS $$
            DECLARE
                bp_status VARCHAR(30);
                target_bill_id INT;
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    target_bill_id := OLD.bill_id;
                ELSE
                    target_bill_id := NEW.bill_id;
                END IF;

                SELECT bp.status INTO bp_status
                FROM billing_bill b
                JOIN billing_billing_period bp ON b.billing_period_id = bp.billing_period_id
                WHERE b.bill_id = target_bill_id;

                IF bp_status = 'LOCKED' THEN
                    RAISE EXCEPTION 'Cannot % BillLine because the parent BillingPeriod is LOCKED.', TG_OP;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                ELSE
                    RETURN NEW;
                END IF;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_bill_line_locked_guard
            BEFORE INSERT OR UPDATE OR DELETE ON billing_bill_line
            FOR EACH ROW
            EXECUTE FUNCTION trg_guard_locked_bill_line();

            -- Locked-Bill Guard Trigger Function for BillAdjustment
            CREATE OR REPLACE FUNCTION trg_guard_locked_bill_adjustment()
            RETURNS TRIGGER AS $$
            DECLARE
                bp_status VARCHAR(30);
                target_bill_id INT;
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    target_bill_id := OLD.bill_id;
                ELSE
                    target_bill_id := NEW.bill_id;
                END IF;

                SELECT bp.status INTO bp_status
                FROM billing_bill b
                JOIN billing_billing_period bp ON b.billing_period_id = bp.billing_period_id
                WHERE b.bill_id = target_bill_id;

                IF bp_status = 'LOCKED' THEN
                    RAISE EXCEPTION 'Cannot % BillAdjustment because the parent BillingPeriod is LOCKED.', TG_OP;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                ELSE
                    RETURN NEW;
                END IF;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_bill_adjustment_locked_guard
            BEFORE INSERT OR UPDATE OR DELETE ON billing_bill_adjustment
            FOR EACH ROW
            EXECUTE FUNCTION trg_guard_locked_bill_adjustment();

            -- Insert-only triggers
            CREATE OR REPLACE FUNCTION trg_prevent_update_or_delete_bill_adjustment()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Table billing_bill_adjustment is insert-only. UPDATE and DELETE operations are forbidden.';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_guard_bill_adjustment
            BEFORE UPDATE OR DELETE ON billing_bill_adjustment
            FOR EACH ROW
            EXECUTE FUNCTION trg_prevent_update_or_delete_bill_adjustment();

            CREATE OR REPLACE FUNCTION trg_prevent_update_or_delete_balance_ledger_entry()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Table billing_balance_ledger_entry is insert-only. UPDATE and DELETE operations are forbidden.';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_guard_balance_ledger_entry
            BEFORE UPDATE OR DELETE ON billing_balance_ledger_entry
            FOR EACH ROW
            EXECUTE FUNCTION trg_prevent_update_or_delete_balance_ledger_entry();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_bill_locked_guard ON billing_bill;
            DROP FUNCTION IF EXISTS trg_guard_locked_bill();

            DROP TRIGGER IF EXISTS trg_bill_line_locked_guard ON billing_bill_line;
            DROP FUNCTION IF EXISTS trg_guard_locked_bill_line();

            DROP TRIGGER IF EXISTS trg_bill_adjustment_locked_guard ON billing_bill_adjustment;
            DROP FUNCTION IF EXISTS trg_guard_locked_bill_adjustment();

            DROP TRIGGER IF EXISTS trg_guard_bill_adjustment ON billing_bill_adjustment;
            DROP FUNCTION IF EXISTS trg_prevent_update_or_delete_bill_adjustment();

            DROP TRIGGER IF EXISTS trg_guard_balance_ledger_entry ON billing_balance_ledger_entry;
            DROP FUNCTION IF EXISTS trg_prevent_update_or_delete_balance_ledger_entry();
            """,
        ),
    ]
