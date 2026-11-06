"""
Views for admin configuration and version policy endpoints — Phase 5.
"""
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.config.serializers import (
    ApplicationVersionPolicyCreateSerializer,
    ApplicationVersionPolicySerializer,
    ApplicationVersionPolicyUpdateSerializer,
    SystemSettingSerializer,
    SystemSettingUpdateSerializer,
)
from apps.config.services import (
    create_or_update_version_policy,
    delete_version_policy,
    list_system_settings,
    list_version_policies,
    update_setting,
    update_version_policy_by_id,
)
from apps.core.permissions import IsSuperAdmin


@extend_schema(
    summary="Get or Update System Settings",
    description="Super Admin management of institutional configuration parameters [SPEC SDD §151, DEC-11].",
    tags=["admin"],
    request=SystemSettingUpdateSerializer,
    responses={
        200: OpenApiResponse(description="List of settings or updated setting"),
        201: OpenApiResponse(description="Setting created/updated"),
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def settings_list_update_view(request):
    """List or update institutional SystemSettings."""
    if request.method == "GET":
        settings_data = list_system_settings(mask_sensitive=True)
        return Response(settings_data, status=status.HTTP_200_OK)

    serializer = SystemSettingUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    setting = update_setting(
        key=serializer.validated_data["key"],
        value=serializer.validated_data["value"],
        reason=serializer.validated_data.get("reason", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )

    val = "******" if setting.is_sensitive else setting.value
    return Response({
        "setting_id": setting.setting_id,
        "key": setting.key,
        "value": val,
        "data_type": setting.data_type,
        "description": setting.description,
        "is_sensitive": setting.is_sensitive,
        "effective_from": setting.effective_from,
        "version": setting.version,
    }, status=status.HTTP_200_OK)


@extend_schema(
    summary="List or Create Application Version Policies",
    description="Manage client application version policies (SUPPORTED, DEPRECATED, BLOCKED) [DEC-18].",
    tags=["admin"],
    request=ApplicationVersionPolicyCreateSerializer,
    responses={
        200: ApplicationVersionPolicySerializer(many=True),
        201: ApplicationVersionPolicySerializer,
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def app_version_policy_list_create_view(request):
    """List or create/update ApplicationVersionPolicy rows."""
    if request.method == "GET":
        policies = list_version_policies()
        serializer = ApplicationVersionPolicySerializer(policies, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer = ApplicationVersionPolicyCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    policy = create_or_update_version_policy(
        platform=serializer.validated_data["platform"],
        app_version=serializer.validated_data["app_version"],
        status=serializer.validated_data["status"],
        force_update_message=serializer.validated_data.get("force_update_message", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(
        ApplicationVersionPolicySerializer(policy).data,
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    summary="Get, Update, or Delete Version Policy",
    description="Retrieve, update or delete a specific application version policy by id.",
    tags=["admin"],
    request=ApplicationVersionPolicyUpdateSerializer,
    responses={
        200: ApplicationVersionPolicySerializer,
        204: OpenApiResponse(description="Policy deleted"),
    },
)
@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def app_version_policy_detail_view(request, policy_id: int):
    """Retrieve, update, or delete version policy."""
    if request.method == "GET":
        from apps.config.models import ApplicationVersionPolicy
        from apps.core.exceptions import NotFoundError
        policy = ApplicationVersionPolicy.objects.filter(policy_id=policy_id).first()
        if not policy:
            raise NotFoundError(code="OBJECT_NOT_FOUND", message="Policy not found.")
        return Response(ApplicationVersionPolicySerializer(policy).data)

    if request.method == "PUT":
        serializer = ApplicationVersionPolicyUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        policy = update_version_policy_by_id(
            policy_id=policy_id,
            status=serializer.validated_data["status"],
            force_update_message=serializer.validated_data.get("force_update_message", ""),
            version=serializer.validated_data["version"],
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )
        return Response(ApplicationVersionPolicySerializer(policy).data)

    # DELETE
    delete_version_policy(
        policy_id=policy_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(status=status.HTTP_204_NO_CONTENT)
