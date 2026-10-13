"""Views for admin/config endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="Get System Settings",
    description="Lists institutional configuration parameters [SPEC SDD §151, DEC-11].",
    tags=["admin"],
    responses={200: OpenApiResponse(description="System settings dictionary")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_settings_stub_view(request):
    return Response({"message": "Admin settings stub"}, status=status.HTTP_200_OK)
