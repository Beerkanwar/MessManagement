"""Views for feedback endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Feedback",
    description="Lists submitted student mess feedback [SPEC DBDD §10].",
    tags=["feedback"],
    responses={200: OpenApiResponse(description="List of feedback records")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def feedback_list_stub_view(request):
    return Response({"message": "Feedback shell stub"}, status=status.HTTP_200_OK)
