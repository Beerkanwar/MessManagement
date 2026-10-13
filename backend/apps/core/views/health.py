"""
Health endpoints outside the versioned prefix.
Enforces SPEC SDD §105:
- /health/live: process liveness
- /health/ready: database reachability and unapplied migrations check
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(
    summary="Process Liveness Probe",
    description="Returns HTTP 200 when the backend web process is up and accepting HTTP traffic.",
    tags=["health"],
    responses={
        200: OpenApiResponse(description="Process is alive"),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_live_view(request):
    """Liveness probe: verifies process is alive."""
    return Response({"status": "ok", "live": True}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Readiness Probe",
    description=(
        "Verifies that the database is reachable and that all database migrations "
        "have been applied. Returns HTTP 503 if the database is unreachable or migrations are pending."
    ),
    tags=["health"],
    responses={
        200: OpenApiResponse(description="Database connected and migrations applied"),
        503: OpenApiResponse(description="Database unreachable or pending migrations"),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready_view(request):
    """
    Readiness probe: verifies PostgreSQL database reachability and confirms
    no pending/unapplied migrations exist.
    """
    # 1. Database reachability check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except Exception as exc:
        return Response(
            {
                "status": "unavailable",
                "ready": False,
                "error": "Database unreachable",
                "detail": str(exc),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # 2. Unapplied migrations check
    try:
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        if plan:
            pending_count = len(plan)
            return Response(
                {
                    "status": "unavailable",
                    "ready": False,
                    "error": "Unapplied migrations pending",
                    "pending_migrations_count": pending_count,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
    except Exception as exc:
        return Response(
            {
                "status": "unavailable",
                "ready": False,
                "error": "Unable to verify migration state",
                "detail": str(exc),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {
            "status": "ok",
            "ready": True,
            "database": "connected",
            "migrations": "applied",
        },
        status=status.HTTP_200_OK,
    )
