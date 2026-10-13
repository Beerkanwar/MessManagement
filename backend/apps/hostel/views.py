"""Views for hostel and student endpoint groups."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Hostels",
    description="Lists all institutional hostels [SPEC SDD §64].",
    tags=["hostels"],
    responses={200: OpenApiResponse(description="List of hostels")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hostel_list_stub_view(request):
    return Response({"message": "Hostel shell stub"}, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Students",
    description="Lists students scoped by user authority [SPEC SDD §64].",
    tags=["students"],
    responses={200: OpenApiResponse(description="List of students")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_list_stub_view(request):
    return Response({"message": "Student shell stub"}, status=status.HTTP_200_OK)
