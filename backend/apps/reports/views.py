"""
Views for the reports endpoint group [SPEC SDD §64, ImplementationGuide Phase 12].

Endpoint map:
- GET /reports                 catalog of reports the caller may run
- GET /reports/{id}            run a report (JSON paginated, or CSV/XLSX/PDF)

The views are deliberately thin: role checks, parameter validation, query
orchestration and auditing live in ``services.py``.
"""
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.reports import services
from apps.reports.serializers import (
    ReportCatalogResponseSerializer,
    ReportJsonResponseSerializer,
)


REPORT_QUERY_PARAMETERS = [
    OpenApiParameter(
        name="from",
        type=OpenApiTypes.DATE,
        location=OpenApiParameter.QUERY,
        required=True,
        description="First date of the report range (inclusive, ISO YYYY-MM-DD).",
    ),
    OpenApiParameter(
        name="to",
        type=OpenApiTypes.DATE,
        location=OpenApiParameter.QUERY,
        required=True,
        description="Last date of the report range (inclusive, ISO YYYY-MM-DD).",
    ),
    OpenApiParameter(
        name="format",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        enum=["json", "csv", "xlsx", "pdf"],
        description="Response format. JSON is paginated; file exports stream the full result.",
    ),
    OpenApiParameter(
        name="hostel",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Optional hostel id filter (scope still applies).",
    ),
    OpenApiParameter(
        name="mess",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Optional mess id filter (scope still applies).",
    ),
    OpenApiParameter(
        name="student",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Optional student id filter.",
    ),
    OpenApiParameter(
        name="meal_type",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Meal type code or id (BREAKFAST, LUNCH, EVENING_SNACKS, DINNER).",
    ),
    OpenApiParameter(
        name="extra_item",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Optional extra item id filter.",
    ),
    OpenApiParameter(
        name="page",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="JSON page number (default 1).",
    ),
    OpenApiParameter(
        name="page_size",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="JSON page size (default 50, maximum 200).",
    ),
]


@extend_schema(
    summary="List Reports Catalog",
    operation_id="reports_catalog",
    description=(
        "Lists the reports the authenticated caller may run, with their columns, "
        "supported filters and export formats. Students are refused entirely [DEC-15]."
    ),
    tags=["reports"],
    responses={200: ReportCatalogResponseSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_catalog_view(request):
    return Response({"reports": services.list_reports(request.user)})


@extend_schema(
    summary="Run or Export a Report",
    operation_id="reports_run",
    description=(
        "Runs one report for the required inclusive date range. JSON responses are "
        "paginated and include totals/groups. CSV, XLSX and PDF responses export the "
        "full result (capped at 100,000 rows for CSV/XLSX and 5,000 for PDF) and write "
        "a REPORT_EXPORTED audit event."
    ),
    tags=["reports"],
    parameters=[
        OpenApiParameter(
            name="id",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
            description="Report id from GET /reports.",
        ),
        *REPORT_QUERY_PARAMETERS,
    ],
    responses={
        200: OpenApiResponse(
            response=ReportJsonResponseSerializer,
            description="Paginated JSON report, or a CSV/XLSX/PDF attachment.",
        ),
        400: OpenApiResponse(description="Invalid range, filter, format or export row cap."),
        403: OpenApiResponse(description="Role is not permitted to run this report."),
        404: OpenApiResponse(description="Unknown report id."),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_detail_view(request, report_id: str):
    role, definition = services.get_authorized_report(request.user, report_id)
    fmt = services.parse_format(request.query_params)
    ctx = services.build_context(
        request.user,
        role,
        request.query_params,
        correlation_id=getattr(request, "correlation_id", ""),
    )

    if fmt == "json":
        return services.paginate_report(definition, ctx, request=request)

    result = services.build_export(definition, ctx, fmt)
    response = HttpResponse(result.content, content_type=result.content_type)
    response["Content-Disposition"] = f'attachment; filename="{result.filename}"'
    response["Content-Length"] = str(len(result.content))
    return response
