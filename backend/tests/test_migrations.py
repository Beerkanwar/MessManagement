"""
Tests for migration cleanliness and pending model changes.
Checkpoint:
- makemigrations --check reports no pending changes.
"""
from io import StringIO
import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db
def test_makemigrations_check():
    """
    Checkpoint: makemigrations --check passes cleanly with no pending model changes.
    """
    out = StringIO()
    call_command("makemigrations", check=True, dry_run=True, stdout=out)


@pytest.mark.django_db(transaction=True)
def test_all_migrations_are_reversible():
    """
    Every migration must support both directions.

    The database is migrated to its latest state, reversed to zero, and then
    re-applied. A migration without a workable reverse (``RunSQL`` without
    ``reverse_sql``, a destructive ``RunPython``, or a broken dependency) fails
    here instead of surfacing during a production rollback.
    """
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    leaves = executor.loader.graph.leaf_nodes()

    executor.migrate(leaves)
    try:
        executor.loader.build_graph()
        zero_targets = [
            (app_label, None) for app_label in executor.loader.migrated_apps
        ]
        executor.migrate(zero_targets)

        executor.loader.build_graph()
        remaining = set(executor.loader.applied_migrations)
        assert remaining == set(), (
            f"Migrations left applied after reversing: {remaining}"
        )

        executor.loader.build_graph()
        executor.migrate(leaves)

        executor.loader.build_graph()
        applied = set(executor.loader.applied_migrations)
        missing = [leaf for leaf in leaves if leaf not in applied]
        assert missing == [], f"Leaf migrations not re-applied: {missing}"
    finally:
        # Never leave the shared test database reversed, even when the
        # reversibility assertion fails and the suite must keep running.
        executor.loader.build_graph()
        executor.migrate(leaves)
