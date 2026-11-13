"""
Audit read API [ImplementationGuide Phase 13, Appendix A].

Super Admin only, read-only, keyset-paginated over the DBDD §15.2 indexes.
Every payload is passed through the sanitizer again on output.
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.audit.selectors import (
    list_audit_events,
    parse_date_param,
    parse_page_size,
)
from apps.audit.serializers import AuditEventPageSerializer, AuditEventSerializer
from apps.core.exceptions import ValidationError
from apps.core.permissions import IsSuperAdmin
from apps.identity.models import User

ALLOWED_QUERY_PARAMS = {
    "actor",
    "actor_id",
    "event_type",
    "entity_type",
    "entity_id",
    "correlation_id",
    "from",
    "to",
    "cursor",
    "limit",
    "page_size",
}


def _parse_actor(request) -> int | None:
    raw = request.query_params.get("actor") or request.query_params.get("actor_id")
    if not raw:
        return None
    if str(raw).isdigit():
        return int(raw)
    user = User.objects.filter(normalized_email=str(raw).strip().lower()).first()
    if user is None:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message="Unknown audit actor.",
        )
    return user.user_id


@extend_schema(
    summary="List Audit Events",
    description=(
        "Read-only, Super Admin audit trail with actor, event, entity, "
        "correlation-id and date filters. Keyset paging via `cursor`."
    ),
    tags=["audit"],
    operation_id="audit_events_list",
    parameters=[
        OpenApiParameter("actor", str, description="Actor user id or email"),
        OpenApiParameter("actor_id", str, description="Actor user id (alias of actor)"),
        OpenApiParameter("event_type", str, description="Exact event code"),
        OpenApiParameter("entity_type", str, description="Target entity model"),
        OpenApiParameter("entity_id", str, description="Target entity id"),
        OpenApiParameter("correlation_id", str, description="Request trace id"),
        OpenApiParameter("from", str, description="IST date (YYYY-MM-DD), inclusive"),
        OpenApiParameter("to", str, description="IST date (YYYY-MM-DD), inclusive"),
        OpenApiParameter("cursor", str, description="Opaque keyset cursor"),
        OpenApiParameter("limit", int, description="Page size (1-100, default 50)"),
        OpenApiParameter("page_size", int, description="Alias of limit"),
    ],
    responses={200: AuditEventPageSerializer},
)
@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def audit_events_list_view(request):
    unknown = set(request.query_params.keys()) - ALLOWED_QUERY_PARAMS
    if unknown:
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Unsupported filter(s): {', '.join(sorted(unknown))}.",
        )

    date_from = (
        parse_date_param(request.query_params["from"], "from")
        if request.query_params.get("from")
        else None
    )
    date_to = (
        parse_date_param(request.query_params["to"], "to")
        if request.query_params.get("to")
        else None
    )
    limit = parse_page_size(
        request.query_params.get("limit") or request.query_params.get("page_size")
    )

    rows, next_cursor, has_more, total = list_audit_events(
        actor_id=_parse_actor(request),
        event_type=request.query_params.get("event_type") or None,
        entity_type=request.query_params.get("entity_type") or None,
        entity_id=request.query_params.get("entity_id") or None,
        correlation_id=request.query_params.get("correlation_id") or None,
        date_from=date_from,
        date_to=date_to,
        cursor=request.query_params.get("cursor") or None,
        limit=limit,
    )

    return Response(
        {
            "count": total,
            "results": AuditEventSerializer(rows, many=True).data,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
        },
        status=status.HTTP_200_OK,
    )
