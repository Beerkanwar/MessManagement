"""Views for billing endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Billing Periods",
    description="Lists billing periods and their lifecycle states [SPEC DBDD §8].",
    tags=["billing"],
    responses={200: OpenApiResponse(description="List of billing periods")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_periods_stub_view(request):
    return Response({"message": "Billing shell stub"}, status=status.HTTP_200_OK)
