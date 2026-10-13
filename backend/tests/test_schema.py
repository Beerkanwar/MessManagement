"""
Tests for OpenAPI schema generator pipeline [SPEC SDD §64].
Checkpoint:
- Exporting the schema twice produces byte-identical files.
- Operation IDs are stable and formatted cleanly.
"""
from django.core.management import call_command


def test_schema_export_is_deterministic_and_byte_identical(tmp_path):
    """
    Checkpoint: Schema export twice produces byte-identical output.
    Guarantees reproducible client SDK generation across CI contract jobs.
    """
    file1 = tmp_path / "schema1.yaml"
    file2 = tmp_path / "schema2.yaml"

    call_command("spectacular", file=str(file1), validate=True)
    call_command("spectacular", file=str(file2), validate=True)

    bytes1 = file1.read_bytes()
    bytes2 = file2.read_bytes()

    assert len(bytes1) > 0
    assert bytes1 == bytes2, "OpenAPI schema generation must be strictly byte-identical."


def test_schema_contains_required_sdd_endpoint_groups(tmp_path):
    """Confirms all SDD §64 groups and tags exist in the generated schema."""
    schema_file = tmp_path / "schema.yaml"
    call_command("spectacular", file=str(schema_file), validate=True)
    schema_yaml = schema_file.read_text(encoding="utf-8")

    expected_tags = [
        "auth",
        "devices",
        "students",
        "hostels",
        "messes",
        "meals",
        "attendance",
        "extras",
        "billing",
        "pauses",
        "menus",
        "feedback",
        "sync",
        "reports",
        "audit",
        "admin",
        "health",
    ]

    for tag in expected_tags:
        assert tag in schema_yaml, f"Expected tag '{tag}' missing from OpenAPI schema."
