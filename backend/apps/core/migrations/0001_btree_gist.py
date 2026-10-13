"""
Phase 2, Step 0: Create btree_gist extension.
Every ExclusionConstraint depends on this [SPEC DBDD §2.3].
Must be run by the migration role which has DDL rights.
"""
from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS btree_gist;",
            reverse_sql="DROP EXTENSION IF EXISTS btree_gist;",
        ),
    ]
