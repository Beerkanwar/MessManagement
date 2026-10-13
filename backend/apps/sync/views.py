"""Views for sync endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="Manager Batch Upload",
    description="Synchronizes offline transactions uploaded by Mess Managers [SPEC SDD §67, §68].",
    tags=["sync"],
    request=None,
    responses={200: OpenApiResponse(description="Batch sync results")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_upload_stub_view(request):
    return Response({"message": "Sync shell stub"}, status=status.HTTP_200_OK)
