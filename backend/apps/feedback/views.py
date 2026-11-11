"""
Views for the feedback endpoint group
[SPEC DBDD §10, SRS §23, SDD §49, ImplementationGuide Phase 11].

Endpoint map:
- POST /feedback          Student: submit this month's one response
- GET  /feedback/current  Student: whether this month's response exists, read-only

There is deliberately no update or delete endpoint [SDD §49].
"""
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import PermissionDeniedError
from apps.feedback import selectors as feedback_selectors
from apps.feedback import services as feedback_services
from apps.feedback.serializers import (
    FeedbackCurrentSerializer,
    FeedbackSerializer,
    FeedbackSubmitSerializer,
)
from apps.identity.selectors import get_user_role


def _require_student(user) -> None:
    if get_user_role(user) != "STUDENT":
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Feedback is limited to students.",
        )


@extend_schema(
    methods=["POST"],
    summary="Submit Monthly Feedback",
    description=(
        "Records the student's one immutable feedback response for the current "
        "IST month. The mess is taken from the student's ACTIVE assignment and "
        "the year/month from the server clock; the client sends neither. A second "
        "submission in the same month returns 409 FEEDBACK_ALREADY_SUBMITTED "
        "[DBDD-AC-29]."
    ),
    tags=["feedback"],
    request=FeedbackSubmitSerializer,
    responses={
        201: FeedbackSerializer,
        400: OpenApiResponse(description="Rating outside 1-5 or comments too long"),
        404: OpenApiResponse(description="No student profile or active assignment"),
        409: OpenApiResponse(description="Feedback already submitted this month"),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def feedback_submit_view(request):
    _require_student(request.user)
    serializer = FeedbackSubmitSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    feedback = feedback_services.submit_feedback(
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
        **serializer.validated_data,
    )
    return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Current Month Feedback Status",
    description=(
        "Tells the app whether this month's response exists and shows it read-only. "
        "The current month comes from the IST clock [DEC-01]."
    ),
    tags=["feedback"],
    responses={
        200: FeedbackCurrentSerializer,
        404: OpenApiResponse(description="No student profile"),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def feedback_current_view(request):
    _require_student(request.user)
    context = feedback_selectors.get_current_feedback_context(request.user)
    return Response(FeedbackCurrentSerializer(context).data)
