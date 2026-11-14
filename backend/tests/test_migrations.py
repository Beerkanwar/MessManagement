"""
Tests for migration cleanliness and pending model changes.
Checkpoint:
- makemigrations --check reports no pending changes.
"""
from io import StringIO
import importlib
import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

seed_meal_types_migration = importlib.import_module(
    "apps.mess.migrations.0003_seed_meal_types"
)
MEAL_TYPES = seed_meal_types_migration.MEAL_TYPES
reverse_meal_types = seed_meal_types_migration.reverse_meal_types


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


def test_reverse_meal_types_uses_direct_sql_delete():
    class _ModelMeta:
        db_table = "mess_meal_type"

    class _MealTypeModel:
        _meta = _ModelMeta()

    class _Apps:
        @staticmethod
        def get_model(app_label, model_name):
            assert app_label == "mess"
            assert model_name == "MealType"
            return _MealTypeModel

    class _SchemaEditor:
        sql = None
        params = None

        def execute(self, sql, params=()):
            self.sql = sql
            self.params = list(params)

    schema_editor = _SchemaEditor()
    reverse_meal_types(_Apps(), schema_editor)

    expected_codes = [code for code, *_ in MEAL_TYPES]
    assert schema_editor.params == expected_codes
    assert schema_editor.sql == (
        'DELETE FROM "mess_meal_type" WHERE "code" IN (%s, %s, %s, %s)'
    )
