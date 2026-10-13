"""
Migration adding ExtraItem and ExtraPrice to mess app [SPEC DBDD §5].
Depends on hostel.0001_initial to resolve circular dependency.
ExclusionConstraint on mess_extra_price enforced via RunSQL.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mess", "0001_initial"),
        ("hostel", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExtraItem",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("extra_item_id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Item display name (e.g. 'Egg Curry')", max_length=255)),
                ("normalized_name", models.CharField(help_text="Trimmed and uppercase for uniqueness check [REC]", max_length=255)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")], default="ACTIVE", max_length=20)),
                ("hostel", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="extra_items", to="hostel.hostel")),
            ],
            options={
                "verbose_name": "Extra Item",
                "verbose_name_plural": "Extra Items",
                "db_table": "mess_extra_item",
            },
        ),
        migrations.CreateModel(
            name="ExtraPrice",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("extra_price_id", models.AutoField(primary_key=True, serialize=False)),
                ("unit_price", models.DecimalField(decimal_places=4, max_digits=19)),
                ("effective_from", models.DateField(help_text="Start date of price (inclusive)")),
                ("effective_to", models.DateField(blank=True, help_text="End date of price (inclusive, null=open-ended)", null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_extra_prices", to=settings.AUTH_USER_MODEL)),
                ("extra_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="prices", to="mess.extraitem")),
            ],
            options={
                "verbose_name": "Extra Price",
                "verbose_name_plural": "Extra Prices",
                "db_table": "mess_extra_price",
            },
        ),
        migrations.AddConstraint(
            model_name="extraitem",
            constraint=models.UniqueConstraint(fields=["hostel", "normalized_name"], name="uq_mess_extra_item_hostel_norm_name"),
        ),
        migrations.AddConstraint(
            model_name="extraitem",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "INACTIVE"]), name="mess_extra_item_status_check"),
        ),
        migrations.AddIndex(
            model_name="extraprice",
            index=models.Index(fields=["extra_item", "effective_from"], name="idx_mess_extra_price_item_eff"),
        ),
        migrations.AddConstraint(
            model_name="extraprice",
            constraint=models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="mess_extra_price_non_neg_check"),
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE mess_extra_price
            ADD CONSTRAINT excl_mess_extra_price_overlap
            EXCLUDE USING gist (
                extra_item_id WITH =,
                daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[)') WITH &&
            );
            """,
            reverse_sql="""
            ALTER TABLE mess_extra_price
            DROP CONSTRAINT IF EXISTS excl_mess_extra_price_overlap;
            """,
        ),
    ]
