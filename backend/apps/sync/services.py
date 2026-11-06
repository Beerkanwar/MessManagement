"""
Sync services implementing atomic cursor management [SPEC DBDD §11, ISSUE-24].
"""
from django.db import connection


def advance_change_cursor(cursor_key: str) -> int:
    """
    Atomically advances the change cursor for the given aggregate key
    (e.g. 'mess:<id>:students', 'mess:<id>:secrets', 'mess:<id>:meal_rates').
    Uses a single atomic PostgreSQL UPSERT statement to eliminate race conditions.
    Returns the new monotonically increasing version number.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sync_change_cursor (aggregate_type, current_version, updated_at)
            VALUES (%s, 1, NOW())
            ON CONFLICT (aggregate_type)
            DO UPDATE SET current_version = sync_change_cursor.current_version + 1, updated_at = NOW()
            RETURNING current_version;
            """,
            [cursor_key],
        )
        row = cursor.fetchone()
        return row[0] if row else 1

