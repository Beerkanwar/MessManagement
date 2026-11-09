"""
Phase 8: install change-version triggers on every row type the Manager receives.

The trigger takes a new value from the shared ``change_version_seq`` on INSERT
and UPDATE, so every write path (services, admin, corrections, cron) advances the
change marker without having to remember to do so
[ImplementationGuide Phase 8, build 6].
"""
from django.db import migrations

TABLES = [
    "hostel_student",
    "hostel_student_mess_assignment",
    "identity_student_secret",
    "mess_meal_occurrence",
    "mess_meal_rate",
    "mess_extra_item",
    "mess_extra_price",
    "pause_mess_pause",
    "attendance_meal_consumption",
    "attendance_extra_transaction",
]


def _backfill_sql() -> str:
    return "\n".join(
        f"UPDATE {table} SET change_version = nextval('change_version_seq');"
        for table in TABLES
    )


def _install_sql() -> str:
    statements = [_backfill_sql()]
    for table in TABLES:
        statements.append(
            f"""
            CREATE TRIGGER trg_{table}_change_version
            BEFORE INSERT OR UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION set_change_version();
            """
        )
    return "\n".join(statements)


def _remove_sql() -> str:
    return "\n".join(
        f"DROP TRIGGER IF EXISTS trg_{table}_change_version ON {table};"
        for table in TABLES
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_change_version"),
        ("hostel", "0002_student_change_version_and_more"),
        ("identity", "0006_studentsecret_change_version"),
        ("mess", "0004_extraitem_change_version_extraprice_change_version_and_more"),
        ("pause", "0002_messpause_change_version"),
        ("attendance", "0002_extratransaction_change_version_and_more"),
        ("sync", "0002_synctransaction_client_payload_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_install_sql(),
            reverse_sql=_remove_sql(),
        ),
    ]
