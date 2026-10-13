"""Views for audit endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Audit Events",
    description="Lists append-only system audit events [SPEC DBDD §12].",
    tags=["audit"],
    responses={200: OpenApiResponse(description="Audit events list")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def audit_events_stub_view(request):
    return Response({"message": "Audit shell stub"}, status=status.HTTP_200_OK)
