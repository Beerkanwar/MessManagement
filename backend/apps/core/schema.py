"""
OpenAPI schema utilities for drf-spectacular.
Provides a stable, deterministic operation ID generator so generated TypeScript
client function names remain consistent and human-readable [SPEC SDD §64].
"""
import re
from typing import Any


def custom_operation_id_generator(*args: Any, **kwargs: Any) -> str:
    """
    Produces deterministic, snake_case or camelCase operation IDs from path and method/action.
    Supports both drf-spectacular signature variations:
      generator(endpoint_path, method, auto_schema)
      generator(auto_schema)
    """
    path = ""
    method = "GET"
    action = None

    if len(args) == 1:
        auto_schema = args[0]
        path = getattr(auto_schema, "path", "")
        method = getattr(auto_schema, "method", "GET")
        view = getattr(auto_schema, "view", None)
        if view and hasattr(view, "action") and view.action:
            action = view.action
    elif len(args) >= 2:
        path = str(args[0])
        method = str(args[1])
        if len(args) >= 3 and hasattr(args[2], "view"):
            view = args[2].view
            if hasattr(view, "action") and view.action:
                action = view.action

    # Normalize path: remove leading /api/v1/ or /api/
    clean_path = re.sub(r"^/api/v1/?", "", path)
    clean_path = re.sub(r"^/api/?", "", clean_path)
    clean_path = clean_path.strip("/")

    # Replace parameter templates like {id} with by_id
    clean_path = re.sub(r"\{(\w+)\}", r"by_\1", clean_path)

    # Tokenize path segments
    tokens = [t for t in re.split(r"[/_-]+", clean_path) if t]

    if not tokens:
        tokens = ["root"]

    if action:
        operation_id = f"{'_'.join(tokens)}_{action}"
    else:
        method_lower = method.lower()
        if method_lower == "get":
            # If path ends in parameter, it's retrieve; otherwise list or action
            verb = "read" if ("by_id" in tokens or "by_pk" in tokens) else "list"
        elif method_lower == "post":
            verb = "create"
        elif method_lower in ("put", "patch"):
            verb = "update"
        elif method_lower == "delete":
            verb = "delete"
        else:
            verb = method_lower
        operation_id = f"{'_'.join(tokens)}_{verb}"

    # Clean double underscores and convert to valid identifier
    operation_id = re.sub(r"_+", "_", operation_id).strip("_")
    return operation_id
