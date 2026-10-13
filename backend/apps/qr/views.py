"""Views for QR endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="Get Student QR Secret",
    description="Returns the active rolling QR secret key for the authenticated student [SPEC SDD §19].",
    tags=["qr"],
    responses={200: OpenApiResponse(description="QR secret payload")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def qr_secret_stub_view(request):
    return Response({"message": "QR secret shell stub"}, status=status.HTTP_200_OK)
