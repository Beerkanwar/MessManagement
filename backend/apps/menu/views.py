"""Views for menus endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Menus",
    description="Lists published and draft menus [SPEC DBDD §9].",
    tags=["menus"],
    responses={200: OpenApiResponse(description="List of menus")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def menu_list_stub_view(request):
    return Response({"message": "Menu shell stub"}, status=status.HTTP_200_OK)
