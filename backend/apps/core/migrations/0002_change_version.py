"""
Phase 8: shared change-version sequence and trigger function.

Every row the Manager receives carries a ``change_version`` taken from one
PostgreSQL sequence, so a single opaque cursor can describe the whole download
[ImplementationGuide Phase 8, build 6; DBDD §2.2].
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_btree_gist"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE SEQUENCE IF NOT EXISTS change_version_seq;

            CREATE OR REPLACE FUNCTION set_change_version()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.change_version := nextval('change_version_seq');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            reverse_sql="""
            DROP FUNCTION IF EXISTS set_change_version();
            DROP SEQUENCE IF EXISTS change_version_seq;
            """,
        ),
    ]
