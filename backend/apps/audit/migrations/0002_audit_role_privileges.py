"""
Audit table privilege hardening [ImplementationGuide Phase 13, DBDD-AC-33].

The application login is left with INSERT and SELECT only on the audit table.
The append-only trigger from 0001 remains the second guard. A superuser
(deployment owner) bypasses privilege checks, so the production migration role
must run this as a non-superuser owner or the deployment must use a dedicated
least-privilege application role (see docs/runbook.md).
"""
from django.db import migrations


FORWARD_SQL = """
DO $$
DECLARE
    app_role text := current_user;
BEGIN
    EXECUTE format(
        'REVOKE UPDATE, DELETE ON TABLE audit_audit_log FROM %I',
        app_role
    );
END
$$;
"""

REVERSE_SQL = """
DO $$
DECLARE
    app_role text := current_user;
BEGIN
    EXECUTE format(
        'GRANT UPDATE, DELETE ON TABLE audit_audit_log TO %I',
        app_role
    );
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
