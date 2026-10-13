#!/usr/bin/env python
"""
Exports OpenAPI schema to docs/openapi/schema.yaml.
Enforces byte-identical deterministic schema output for client contract verification [SPEC SDD §64].
"""
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django
django.setup()

from django.core.management import call_command


def export_schema():
    target_dir = BASE_DIR.parent / "docs" / "openapi"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "schema.yaml"

    print(f"Exporting OpenAPI schema to {target_file}...")
    call_command("spectacular", file=str(target_file), validate=True)
    print("Schema exported successfully.")


if __name__ == "__main__":
    export_schema()
