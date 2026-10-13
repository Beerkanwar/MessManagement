"""Views for attendance endpoint group."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Attendance Records",
    description="Lists effective student meal attendance [SPEC SDD §64].",
    tags=["attendance"],
    responses={200: OpenApiResponse(description="List of attendance records")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_list_stub_view(request):
    return Response({"message": "Attendance shell stub"}, status=status.HTTP_200_OK)
