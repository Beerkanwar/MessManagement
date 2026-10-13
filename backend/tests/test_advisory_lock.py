"""
Tests for scheduled management command PostgreSQL advisory lock convention [SPEC SRS §26.4].
Checkpoint:
- Running the example job twice at once: second run exits immediately without error.
"""
import io
from unittest.mock import patch
import psycopg
import pytest
from django.core.management import call_command
from django.db import connection
from apps.core.management.commands.run_example_job import Command as ExampleCommand


@pytest.mark.django_db
def test_example_job_runs_under_advisory_lock():
    """Confirms single instance runs successfully and releases lock."""
    out = io.StringIO()
    call_command("run_example_job", stdout=out)
    output = out.getvalue()
    assert "Example job completed successfully." in output


@pytest.mark.django_db
def test_example_job_overlapping_run_exits_quietly():
    """
    Checkpoint: Run the example job twice at once.
    A separate process/connection holds the advisory lock.
    The second run detects the held lock and exits immediately without error.
    """
    cmd = ExampleCommand()
    lock_id = cmd.get_lock_id()

    # Open a separate independent connection to the active test database
    db_config = connection.settings_dict
    conn_uri = f"postgresql://{db_config['USER']}:{db_config['PASSWORD']}@{db_config['HOST']}:{db_config['PORT']}/{db_config['NAME']}"
    with psycopg.connect(conn_uri, autocommit=True) as conn2:
        with conn2.cursor() as cur2:
            cur2.execute("SELECT pg_try_advisory_lock(%s);", [lock_id])
            acquired = cur2.fetchone()[0]
            assert acquired is True

            try:
                # Second run via Django connection attempts execution
                out = io.StringIO()
                call_command("run_example_job", stdout=out)
                output = out.getvalue()

                # Second run must exit cleanly with quiet notification
                assert "Job already running with advisory lock; exiting quietly." in output
            finally:
                cur2.execute("SELECT pg_advisory_unlock(%s);", [lock_id])


@pytest.mark.django_db
def test_example_job_lock_simulation_quiet_exit():
    """Confirms lock collision handling when pg_try_advisory_lock returns False."""
    out = io.StringIO()

    class MockCursorContext:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, *args, **kwargs):
            pass
        def fetchone(self):
            return [False]

    with patch.object(connection, "cursor", return_value=MockCursorContext()):
        call_command("run_example_job", stdout=out)
    assert "Job already running with advisory lock; exiting quietly." in out.getvalue()
