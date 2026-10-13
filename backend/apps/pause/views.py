"""Views for pauses endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Mess Pauses",
    description="Lists student mess pause records [SPEC SDD §64, DBDD §7].",
    tags=["pauses"],
    responses={200: OpenApiResponse(description="List of mess pauses")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pause_list_stub_view(request):
    return Response({"message": "Pause shell stub"}, status=status.HTTP_200_OK)
