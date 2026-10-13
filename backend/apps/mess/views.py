"""Views for mess, meals, and extras endpoint groups."""
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@extend_schema(
    summary="List Messes",
    description="Lists all institutional dining mess halls [SPEC SDD §64].",
    tags=["messes"],
    responses={200: OpenApiResponse(description="List of messes")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mess_list_stub_view(request):
    return Response({"message": "Mess shell stub"}, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Meal Types",
    description="Lists fixed meal types (Breakfast, Lunch, Evening Snacks, Dinner) [SPEC DBDD §1].",
    tags=["meals"],
    responses={200: OpenApiResponse(description="List of meal types")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def meal_types_stub_view(request):
    return Response({"message": "Meal types stub"}, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Extra Items",
    description="Lists available extras and prices [SPEC SDD §64].",
    tags=["extras"],
    responses={200: OpenApiResponse(description="List of extra items")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def extras_list_stub_view(request):
    return Response({"message": "Extras shell stub"}, status=status.HTTP_200_OK)
