"""
OpenAPI contract gate tests [ImplementationGuide Phase 13].

The /api/v1 contract is frozen at the Phase 13 release. Additive changes are
allowed; anything that removes or narrows what a client already relies on must
fail the gate.
"""
from copy import deepcopy
import subprocess
import sys
from pathlib import Path

from scripts.check_schema_contract import compare_breaking


def minimal_schema(*, paths=None, components=None):
    return {
        "openapi": "3.0.3",
        "info": {"title": "Test", "version": "1.0.0"},
        "paths": paths or {},
        "components": {"schemas": components or {}},
    }


def list_operation(schema_ref: str):
    return {
        "get": {
            "responses": {
                "200": {
                    "description": "ok",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "array",
                                "items": {"$ref": f"#/components/schemas/{schema_ref}"},
                            }
                        }
                    },
                }
            }
        }
    }


def create_operation(schema_ref: str):
    return {
        "post": {
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{schema_ref}"}
                    }
                },
            },
            "responses": {"201": {"description": "created"}},
        }
    }


def test_additive_changes_are_allowed():
    base = minimal_schema(
        paths={"/v1/items": list_operation("Item")},
        components={
            "Item": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
            }
        },
    )
    head = deepcopy(base)
    head["paths"]["/v1/items/new"] = list_operation("Item")
    head["paths"]["/v1/items"]["post"] = create_operation("ItemNew")
    head["components"]["schemas"]["Item"]["properties"]["note"] = {"type": "string"}
    head["components"]["schemas"]["Item"]["properties"]["status"] = {
        "type": "string",
        "enum": ["ACTIVE", "INACTIVE"],
    }
    head["components"]["schemas"]["ItemNew"] = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }

    assert compare_breaking(base, head) == []


def test_removed_path_is_breaking():
    base = minimal_schema(paths={"/v1/items": list_operation("Item")})
    head = minimal_schema(paths={})
    assert compare_breaking(base, head) == ["removed path /v1/items"]


def test_removed_method_is_breaking():
    base = minimal_schema(
        paths={"/v1/items": {**list_operation("Item"), **create_operation("Item")}}
    )
    head = minimal_schema(paths={"/v1/items": list_operation("Item")})
    assert compare_breaking(base, head) == ["removed method POST /v1/items"]


def test_removed_response_property_is_breaking():
    base = minimal_schema(
        paths={"/v1/items": list_operation("Item")},
        components={
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
            }
        },
    )
    head = deepcopy(base)
    del head["components"]["schemas"]["Item"]["properties"]["name"]

    assert compare_breaking(base, head) == ["schema Item: removed property name"]


def test_property_type_change_is_breaking():
    base = minimal_schema(
        paths={"/v1/items": list_operation("Item")},
        components={
            "Item": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
            }
        },
    )
    head = deepcopy(base)
    head["components"]["schemas"]["Item"]["properties"]["id"] = {"type": "string"}

    assert compare_breaking(base, head) == [
        "schema Item.id: type changed 'integer' -> 'string'"
    ]


def test_new_required_request_field_is_breaking():
    base = minimal_schema(
        paths={"/v1/items": create_operation("ItemCreate")},
        components={
            "ItemCreate": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            }
        },
    )
    head = deepcopy(base)
    head["components"]["schemas"]["ItemCreate"]["properties"]["hostel_id"] = {
        "type": "integer"
    }
    head["components"]["schemas"]["ItemCreate"]["required"].append("hostel_id")

    assert compare_breaking(base, head) == [
        "schema ItemCreate: new required request field hostel_id"
    ]


def test_new_required_response_field_is_not_breaking():
    base = minimal_schema(
        paths={"/v1/items": list_operation("Item")},
        components={
            "Item": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            }
        },
    )
    head = deepcopy(base)
    head["components"]["schemas"]["Item"]["properties"]["name"] = {"type": "string"}
    head["components"]["schemas"]["Item"]["required"].append("name")

    assert compare_breaking(base, head) == []


def test_removed_enum_value_is_breaking():
    base = minimal_schema(
        paths={"/v1/items": list_operation("Item")},
        components={
            "Item": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["ACTIVE", "INACTIVE"]}
                },
            }
        },
    )
    head = deepcopy(base)
    head["components"]["schemas"]["Item"]["properties"]["status"]["enum"] = ["ACTIVE"]

    assert compare_breaking(base, head) == [
        "schema Item.status: removed enum values ['INACTIVE']"
    ]


def test_removed_required_parameter_is_breaking():
    base = minimal_schema(
        paths={
            "/v1/items": {
                "get": {
                    "parameters": [
                        {"in": "query", "name": "from", "required": True}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    )
    head = deepcopy(base)
    head["paths"]["/v1/items"]["get"]["parameters"] = []

    assert compare_breaking(base, head) == [
        "GET /v1/items: removed required parameter from"
    ]


def test_new_required_parameter_is_breaking():
    base = minimal_schema(
        paths={
            "/v1/items": {
                "get": {
                    "parameters": [],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    )
    head = deepcopy(base)
    head["paths"]["/v1/items"]["get"]["parameters"] = [
        {"in": "query", "name": "from", "required": True}
    ]

    assert compare_breaking(base, head) == [
        "GET /v1/items: new required parameter from"
    ]


def test_committed_schema_matches_code():
    """Drift gate: the committed contract is exactly what the code generates."""
    backend = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "scripts/check_schema_contract.py"],
        cwd=backend,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
