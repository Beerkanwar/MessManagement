"""
Report orchestration, validation and export auditing [ImplementationGuide Phase 12].

HTTP concerns stay in ``views.py``; this module owns:
- role/report access decisions,
- date-range and filter validation,
- JSON pagination vs. full-file export row caps,
- the ``REPORT_EXPORTED`` audit event.

Exports never write report content to audit: only report id, parameters,
format, row count and actor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from apps.audit.services import record_audit_event
from apps.core.clock import clock
from apps.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from apps.core.pagination import StandardPageNumberPagination
from apps.identity.models import User
from apps.identity.selectors import get_clerk_hostel, get_manager_mess

from apps.reports import exporters
from apps.reports.registry import ReportDefinition, get_report, report_catalog
from apps.reports.scope import (
    ROLE_CLERK,
    ROLE_MANAGER,
    ROLE_SUPER_ADMIN,
    ReportContext,
    resolve_role,
)

MAX_RANGE_DAYS = 366
CSV_XLSX_ROW_CAP = 100_000
PDF_ROW_CAP = 5_000
ALLOWED_FORMATS = ("json", "csv", "xlsx", "pdf")
EXPORT_FORMATS = ("csv", "xlsx", "pdf")
REPORT_READER_ROLES = (ROLE_MANAGER, ROLE_CLERK, ROLE_SUPER_ADMIN)

CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@dataclass(frozen=True)
class ExportResult:
    content: bytes
    content_type: str
    filename: str
    row_count: int


# ---------------------------------------------------------------------------
# Access and catalog
# ---------------------------------------------------------------------------


def require_reports_access(user: User) -> str:
    """Students have no Reports entry and are refused entirely [CONFLICT-14]."""
    role = resolve_role(user)
    if role not in REPORT_READER_ROLES:
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Reports are available to Mess Managers, Hostel Clerks and the Super Admin only.",
        )
    return role


def list_reports(user: User) -> list[dict[str, Any]]:
    role = require_reports_access(user)
    return [serialize_catalog_entry(report) for report in report_catalog(role)]


def serialize_catalog_entry(definition: ReportDefinition) -> dict[str, Any]:
    return {
        "id": definition.id,
        "title": definition.title,
        "roles": list(definition.roles),
        "filters": list(definition.supported_filters),
        "formats": list(ALLOWED_FORMATS),
        "columns": [
            {
                "key": column.key,
                "label": column.label,
                "type": column.kind,
                "money": column.money,
            }
            for column in definition.columns
        ],
    }


def get_authorized_report(user: User, report_id: str) -> tuple[str, ReportDefinition]:
    role = require_reports_access(user)
    definition = get_report(report_id)
    if definition is None:
        raise NotFoundError(
            code="OBJECT_NOT_FOUND",
            message=f"Report '{report_id}' does not exist.",
        )
    if not definition.allows(role):
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message=f"You do not have access to the '{definition.title}' report.",
        )
    return role, definition


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


def _parse_date(params: Mapping[str, Any], name: str) -> date:
    raw = params.get(name)
    if raw in (None, ""):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Query parameter '{name}' is required (ISO date, e.g. 2026-08-01).",
        )
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Query parameter '{name}' must be an ISO date (YYYY-MM-DD).",
        )


def _parse_optional_int(params: Mapping[str, Any], name: str) -> int | None:
    raw = params.get(name)
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Query parameter '{name}' must be an integer.",
        )
    if value <= 0:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Query parameter '{name}' must be a positive integer.",
        )
    return value


def _parse_meal_type(params: Mapping[str, Any]) -> str | int | None:
    raw = params.get("meal_type")
    if raw in (None, ""):
        return None
    text = str(raw)
    return int(text) if text.isdigit() else text


def validate_date_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="'from' must be on or before 'to'.",
        )
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=(
                f"Report range exceeds {MAX_RANGE_DAYS} days. "
                "Narrow the date range and try again."
            ),
        )


def parse_format(params: Mapping[str, Any]) -> str:
    raw = params.get("format") or "json"
    value = str(raw).lower()
    if value not in ALLOWED_FORMATS:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=(
                "Query parameter 'format' must be one of: "
                + ", ".join(ALLOWED_FORMATS)
                + "."
            ),
        )
    return value


def build_context(
    user: User, role: str, params: Mapping[str, Any]
) -> ReportContext:
    date_from = _parse_date(params, "from")
    date_to = _parse_date(params, "to")
    validate_date_range(date_from, date_to)

    hostel_id = _parse_optional_int(params, "hostel")
    mess_id = _parse_optional_int(params, "mess")
    student_id = _parse_optional_int(params, "student")
    extra_item_id = _parse_optional_int(params, "extra_item")
    meal_type = _parse_meal_type(params)

    applied: dict[str, Any] = {}
    if hostel_id is not None:
        applied["hostel"] = hostel_id
    if mess_id is not None:
        applied["mess"] = mess_id
    if student_id is not None:
        applied["student"] = student_id
    if extra_item_id is not None:
        applied["extra_item"] = extra_item_id
    if meal_type is not None:
        applied["meal_type"] = meal_type

    return ReportContext(
        user=user,
        role=role,
        date_from=date_from,
        date_to=date_to,
        hostel_id=hostel_id,
        mess_id=mess_id,
        student_id=student_id,
        meal_type=meal_type,
        extra_item_id=extra_item_id,
        applied_filters=applied,
    )


# ---------------------------------------------------------------------------
# Row handling
# ---------------------------------------------------------------------------


def project_row(
    definition: ReportDefinition, raw_row: Any
) -> dict[str, Any]:
    row = definition.row_mapper(raw_row)
    return {column.key: row.get(column.key) for column in definition.columns}


def source_is_materialized(source: Any) -> bool:
    return not hasattr(source, "count")


def count_source(source: Any) -> int:
    if source_is_materialized(source):
        return len(source)
    return int(source.count())


def iter_source(source: Any, *, limit: int | None = None):
    if source_is_materialized(source):
        rows = source if limit is None else source[:limit]
        for row in rows:
            yield row
    else:
        queryset = source if limit is None else source[:limit]
        for row in queryset.iterator():
            yield row


def _build_export_rows(
    definition: ReportDefinition, ctx: ReportContext, *, cap: int
) -> tuple[list[dict[str, Any]], int]:
    source = definition.row_source(ctx)
    row_count = count_source(source)
    if row_count > cap:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=(
                f"Export contains {row_count:,} rows, which exceeds the "
                f"{cap:,}-row limit. Narrow the date range or filters."
            ),
        )
    rows = [
        project_row(definition, row)
        for row in iter_source(source, limit=cap)
    ]
    return rows, row_count


def jsonify(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: jsonify(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, (list, tuple)):
        return [jsonify(item) for item in value]
    return value


def build_json_payload(
    definition: ReportDefinition,
    ctx: ReportContext,
    page_rows: list[Any],
) -> dict[str, Any]:
    return {
        "report": definition.id,
        "title": definition.title,
        "from": ctx.date_from.isoformat(),
        "to": ctx.date_to.isoformat(),
        "results": [
            jsonify(project_row(definition, row)) for row in page_rows
        ],
        "totals": jsonify(definition.totals_func(ctx)),
        "groups": jsonify(definition.groups_func(ctx)),
    }


def paginate_report(
    definition: ReportDefinition,
    ctx: ReportContext,
    *,
    request,
):
    """Builds the paginated JSON screen response, including totals/groups."""
    source = definition.row_source(ctx)
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(source, request) or []
    payload = build_json_payload(definition, ctx, page)
    response = paginator.get_paginated_response(payload["results"])
    response.data.update(
        {key: value for key, value in payload.items() if key != "results"}
    )
    return response


def scope_label(ctx: ReportContext) -> str:
    parts: list[str] = []
    if ctx.role == ROLE_MANAGER:
        mess = get_manager_mess(ctx.user)
        parts.append(f"Mess: {mess.name}" if mess else "Mess: unassigned")
    elif ctx.role == ROLE_CLERK:
        hostel = get_clerk_hostel(ctx.user)
        parts.append(f"Hostel: {hostel.name}" if hostel else "Hostel: unassigned")
    else:
        parts.append("Institution-wide")

    if ctx.hostel_id is not None and ctx.role != ROLE_CLERK:
        parts.append(f"Hostel filter: {ctx.hostel_id}")
    if ctx.mess_id is not None and ctx.role != ROLE_MANAGER:
        parts.append(f"Mess filter: {ctx.mess_id}")
    if ctx.student_id is not None:
        parts.append(f"Student filter: {ctx.student_id}")
    if ctx.meal_type is not None:
        parts.append(f"Meal type filter: {ctx.meal_type}")
    if ctx.extra_item_id is not None:
        parts.append(f"Extra item filter: {ctx.extra_item_id}")
    return "; ".join(parts)


def generated_at_ist() -> str:
    return clock.ist_now().strftime("%Y-%m-%d %H:%M:%S IST")


def export_filename(definition: ReportDefinition, ctx: ReportContext, fmt: str) -> str:
    return (
        f"{definition.id}_{ctx.date_from.isoformat()}_{ctx.date_to.isoformat()}.{fmt}"
    )


def record_export_audit(
    definition: ReportDefinition,
    ctx: ReportContext,
    fmt: str,
    row_count: int,
) -> None:
    metadata = {
        "report_id": definition.id,
        "from": ctx.date_from.isoformat(),
        "to": ctx.date_to.isoformat(),
        "format": fmt,
        "row_count": row_count,
    }
    metadata.update(ctx.applied_filters)
    record_audit_event(
        event_type="REPORT_EXPORTED",
        actor_user=ctx.user,
        entity_type="REPORT",
        entity_id=definition.id,
        metadata=metadata,
    )


def build_export(
    definition: ReportDefinition, ctx: ReportContext, fmt: str
) -> ExportResult:
    cap = PDF_ROW_CAP if fmt == "pdf" else CSV_XLSX_ROW_CAP
    rows, row_count = _build_export_rows(definition, ctx, cap=cap)
    if row_count == 0:
        # The checkpoint requires an empty file with headers, not a totals-only file.
        totals: dict[str, Any] = {}
        groups: list[dict[str, Any]] = []
    else:
        totals = definition.totals_func(ctx)
        groups = definition.groups_func(ctx)

    if fmt == "csv":
        content = exporters.render_csv(definition, rows, totals, groups)
    elif fmt == "xlsx":
        content = exporters.render_xlsx(definition, rows, totals, groups)
    elif fmt == "pdf":
        content = exporters.render_pdf(
            definition,
            rows,
            totals,
            groups,
            scope_label=scope_label(ctx),
            date_from=ctx.date_from,
            date_to=ctx.date_to,
            generated_by=ctx.user.full_name,
            generated_at_ist=generated_at_ist(),
        )
    else:  # pragma: no cover - parse_format guarantees this
        raise ValidationError(
            code="VALIDATION_ERROR", message=f"Unsupported export format '{fmt}'."
        )

    record_export_audit(definition, ctx, fmt, row_count)
    return ExportResult(
        content=content,
        content_type=CONTENT_TYPES[fmt],
        filename=export_filename(definition, ctx, fmt),
        row_count=row_count,
    )
