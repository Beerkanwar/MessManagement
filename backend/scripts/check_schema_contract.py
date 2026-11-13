#!/usr/bin/env python
"""
OpenAPI contract gate [ImplementationGuide Phase 13].

Two checks, both safe to run in CI before deployment:

1. Drift: regenerate the schema and fail if it differs from the committed
   ``docs/openapi/schema.yaml``. A developer who changes a serializer must run
   ``python scripts/export_schema.py`` and commit the result.
2. Breaking change detection: compare the committed schema with a base git ref
   (``origin/main`` on a pull request) and fail when a client-visible contract
   is broken. Additive changes are allowed because the release contract is
   frozen: only new paths, methods, optional request fields, response fields and
   enum values are compatible.

Usage (from ``backend/``):
    python scripts/check_schema_contract.py
    python scripts/check_schema_contract.py --base-ref origin/main
    python scripts/check_schema_contract.py --base-file /tmp/base-schema.yaml
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
COMMITTED_SCHEMA = REPO_ROOT / "docs" / "openapi" / "schema.yaml"

sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


# ---------------------------------------------------------------------------
# Schema loading and generation
# ---------------------------------------------------------------------------


def generate_schema() -> dict[str, Any]:
    """Render the current code as an OpenAPI document."""
    import django

    django.setup()

    from django.core.management import call_command

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "schema.yaml"
        call_command("spectacular", file=str(target), validate=True)
        return yaml.safe_load(target.read_text(encoding="utf-8"))


def load_schema(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} is not an OpenAPI document")
    return data


def load_schema_from_git(ref: str) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{ref}:docs/openapi/schema.yaml"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Could not read docs/openapi/schema.yaml at git ref '{ref}':\n"
            f"{result.stderr.strip()}"
        )
    return yaml.safe_load(result.stdout)


# ---------------------------------------------------------------------------
# Breaking-change analysis
# ---------------------------------------------------------------------------


def _schema_refs(node: Any) -> Iterable[str]:
    """Yield every ``#/components/schemas/<name>`` reference below ``node``."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            yield ref.rsplit("/", 1)[-1]
        for value in node.values():
            yield from _schema_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _schema_refs(value)


def _closure(names: Iterable[str], components: dict[str, Any]) -> set[str]:
    seen: set[str] = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(_schema_refs(components.get(name, {})))
    return seen


def _request_and_response_components(
    document: dict[str, Any],
) -> tuple[set[str], set[str]]:
    components = document.get("components", {}).get("schemas", {})
    request_names: list[str] = []
    response_names: list[str] = []

    for path_item in document.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            request_names.extend(_schema_refs(operation.get("requestBody", {})))
            request_names.extend(
                _schema_refs(operation.get("parameters", []))
            )
            for response in operation.get("responses", {}).values():
                response_names.extend(_schema_refs(response))

    return (
        _closure(request_names, components),
        _closure(response_names, components),
    )


def _properties(schema: dict[str, Any]) -> dict[str, Any]:
    properties = dict(schema.get("properties") or {})
    for part in schema.get("allOf") or []:
        if isinstance(part, dict):
            properties.update(part.get("properties") or {})
    return properties


def _type_of(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return None
    if "type" in schema:
        return schema["type"]
    for part in schema.get("allOf") or []:
        if isinstance(part, dict) and "type" in part:
            return part["type"]
    if "$ref" in schema:
        return schema["$ref"]
    return None


def _enum_values(schema: Any) -> list[Any]:
    if not isinstance(schema, dict):
        return []
    if "enum" in schema:
        return list(schema["enum"])
    values: list[Any] = []
    for part in schema.get("allOf") or []:
        values.extend(_enum_values(part))
    return values


def compare_breaking(
    base: dict[str, Any], head: dict[str, Any]
) -> list[str]:
    """Return human-readable breaking changes from ``base`` to ``head``."""
    findings: list[str] = []
    base_paths = base.get("paths", {}) or {}
    head_paths = head.get("paths", {}) or {}

    for path, base_item in base_paths.items():
        if path not in head_paths:
            findings.append(f"removed path {path}")
            continue
        head_item = head_paths.get(path) or {}
        if not isinstance(base_item, dict):
            continue
        for method, base_operation in base_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if method not in head_item:
                findings.append(f"removed method {method.upper()} {path}")
                continue
            head_operation = head_item.get(method) or {}
            findings.extend(
                _compare_operation(path, method, base_operation, head_operation)
            )

    base_components = (base.get("components", {}) or {}).get("schemas", {}) or {}
    head_components = (head.get("components", {}) or {}).get("schemas", {}) or {}
    request_components, _ = _request_and_response_components(head)

    for name, base_schema in base_components.items():
        if name not in head_components:
            # A component that is no longer referenced cannot break a client;
            # an unresolved reference is reported by schema validation instead.
            continue
        findings.extend(
            _compare_schema(
                name,
                base_schema,
                head_components[name],
                request_components,
            )
        )

    return findings


def _compare_operation(
    path: str,
    method: str,
    base: Any,
    head: Any,
) -> list[str]:
    findings: list[str] = []
    prefix = f"{method.upper()} {path}"

    if not isinstance(base, dict) or not isinstance(head, dict):
        return findings

    base_params = {
        (p.get("in"), p.get("name")): p
        for p in base.get("parameters", []) or []
        if isinstance(p, dict)
    }
    head_params = {
        (p.get("in"), p.get("name")): p
        for p in head.get("parameters", []) or []
        if isinstance(p, dict)
    }
    for key, base_param in base_params.items():
        if base_param.get("required") and key not in head_params:
            findings.append(f"{prefix}: removed required parameter {key[1]}")
    for key, head_param in head_params.items():
        if head_param.get("required") and key not in base_params:
            findings.append(f"{prefix}: new required parameter {key[1]}")

    base_body = base.get("requestBody") or {}
    head_body = head.get("requestBody") or {}
    if base_body and not base_body.get("required") and head_body.get("required"):
        findings.append(f"{prefix}: request body became required")

    return findings


def _compare_schema(
    name: str,
    base: Any,
    head: Any,
    request_components: set[str],
) -> list[str]:
    findings: list[str] = []
    if not isinstance(base, dict) or not isinstance(head, dict):
        return findings

    base_props = _properties(base)
    head_props = _properties(head)
    head_required = set(head.get("required") or [])

    for prop, base_prop in base_props.items():
        if prop not in head_props:
            findings.append(f"schema {name}: removed property {prop}")
            continue
        head_prop = head_props[prop]
        if _type_of(base_prop) != _type_of(head_prop):
            findings.append(
                f"schema {name}.{prop}: type changed "
                f"{_type_of(base_prop)!r} -> {_type_of(head_prop)!r}"
            )
        removed_enums = [
            value
            for value in _enum_values(base_prop)
            if value not in _enum_values(head_prop)
        ]
        if removed_enums:
            findings.append(
                f"schema {name}.{prop}: removed enum values {removed_enums!r}"
            )

    for prop in head_props:
        if prop in base_props:
            continue
        if prop in head_required and name in request_components:
            findings.append(f"schema {name}: new required request field {prop}")

    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        type=Path,
        default=COMMITTED_SCHEMA,
        help="Committed schema to compare against (default: docs/openapi/schema.yaml).",
    )
    parser.add_argument(
        "--base-ref",
        help="Git ref whose schema is the compatibility baseline (e.g. origin/main).",
    )
    parser.add_argument(
        "--base-file",
        type=Path,
        help="Explicit baseline schema file instead of a git ref.",
    )
    args = parser.parse_args(argv)

    generated = generate_schema()
    committed = load_schema(args.schema)

    if generated != committed:
        print(
            f"Schema drift: {args.schema} is not the current contract.\n"
            "Run `python scripts/export_schema.py` and commit the result.",
            file=sys.stderr,
        )
        return 1

    if args.base_ref and args.base_file:
        parser.error("use either --base-ref or --base-file, not both")

    baseline = None
    if args.base_ref:
        baseline = load_schema_from_git(args.base_ref)
    elif args.base_file:
        baseline = load_schema(args.base_file)

    if baseline is not None:
        findings = compare_breaking(baseline, committed)
        if findings:
            print("Breaking OpenAPI changes detected:", file=sys.stderr)
            for finding in findings:
                print(f"  - {finding}", file=sys.stderr)
            print(
                "The /api/v1 contract is frozen. Make the change additive or "
                "introduce /api/v2.",
                file=sys.stderr,
            )
            return 1

    print("OpenAPI contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
