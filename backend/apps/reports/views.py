"""Views for reports endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Reports Catalog",
    description="Lists available institutional reports per user role [DEC-15].",
    tags=["reports"],
    responses={200: OpenApiResponse(description="Reports list")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_list_stub_view(request):
    return Response({"message": "Reports shell stub"}, status=status.HTTP_200_OK)
