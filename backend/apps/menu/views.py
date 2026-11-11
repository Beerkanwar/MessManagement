"""
Views for the menu endpoint group
[SPEC DBDD §9, SRS §22, App Flow §3.4, ImplementationGuide Phase 11].

Business rules live in services.py and selectors.py; these views only handle
HTTP concerns, thin validation and the role gate.

Endpoint map:
- /menus                       Clerk (own hostel), Super Admin: list and create a month
- /menus/{id}                  Clerk (own hostel), Super Admin: month structure
- /menus/{id}/meals            Clerk (own hostel), Super Admin: replace one meal's items
- /menus/{id}/publish          Clerk (own hostel), Super Admin: DRAFT -> PUBLISHED
- /menus/{id}/copy-previous    Clerk (own hostel), Super Admin: weekday pattern [REC]
- /menus/food-items            Clerk, Super Admin: master list and add
- /menus/food-items/{id}       Super Admin: rename / edit
- /menus/food-items/{id}/deactivate  Super Admin: deactivate
- /menus/current               Student: current (and already-published next) menu
"""
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import PermissionDeniedError, ValidationError
from apps.core.pagination import StandardPageNumberPagination
from apps.identity.selectors import get_user_role
from apps.menu import selectors as menu_selectors
from apps.menu import services as menu_services
from apps.menu.serializers import (
    CurrentMenuSerializer,
    FoodItemCreateSerializer,
    FoodItemDeactivateSerializer,
    FoodItemSerializer,
    FoodItemUpdateSerializer,
    MenuCreateSerializer,
    MenuMealSetSerializer,
    MenuPublishResultSerializer,
    MenuPublishSerializer,
    MenuSerializer,
    MenuStructureSerializer,
    MenuCopyPreviousSerializer,
)

MENU_AUTHOR_ROLES = ("SUPER_ADMIN", "HOSTEL_CLERK")


def _require_menu_author(user) -> str:
    """Menu authoring is reserved for Hostel Clerks and the Super Admin."""
    role = "SUPER_ADMIN" if menu_selectors.is_super_admin(user) else get_user_role(user)
    if role not in MENU_AUTHOR_ROLES:
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="Menu authoring is limited to hostel clerks and the Super Admin.",
        )
    return role


def _require_student(user) -> str:
    role = get_user_role(user)
    if role != "STUDENT":
        raise PermissionDeniedError(
            code="PERMISSION_DENIED",
            message="The current-menu view is limited to students.",
        )
    return role


def _int_param(request, name: str) -> int | None:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError(
            code="VALIDATION_ERROR",
            message=f"Query parameter '{name}' must be an integer.",
        )


def _paginate(request, queryset, serializer_class):
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(serializer_class(page, many=True).data)
    return Response(serializer_class(queryset, many=True).data)


# ---------------------------------------------------------------------------
# Food-item master
# ---------------------------------------------------------------------------


@extend_schema(
    methods=["GET"],
    summary="List Food Items",
    description=(
        "Lists the global reusable food-item master [SPEC DBDD §9]. "
        "Available to menu authors (Hostel Clerk and Super Admin)."
    ),
    tags=["menus"],
    responses={200: FoodItemSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    summary="Create Food Item",
    description=(
        "A Clerk or Super Admin adds a food item. Names are unique after "
        "trimming and upper-casing [SPEC DBDD §9]."
    ),
    tags=["menus"],
    request=FoodItemCreateSerializer,
    responses={
        201: FoodItemSerializer,
        409: OpenApiResponse(description="Duplicate normalized name"),
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def food_item_collection_view(request):
    _require_menu_author(request.user)
    if request.method == "POST":
        serializer = FoodItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        food_item = menu_services.create_food_item(
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
            **serializer.validated_data,
        )
        return Response(FoodItemSerializer(food_item).data, status=status.HTTP_201_CREATED)

    status_value = request.query_params.get("status") or None
    return _paginate(
        request, menu_selectors.list_food_items(status_value=status_value), FoodItemSerializer
    )


@extend_schema(
    summary="Update Food Item",
    description=(
        "Super Admin renames a shared food item or edits its description. "
        "Clerks may only add or pick items because one item is shared by every "
        "hostel's menu [REC]."
    ),
    tags=["menus"],
    request=FoodItemUpdateSerializer,
    responses={
        200: FoodItemSerializer,
        403: OpenApiResponse(description="Only the Super Admin may rename"),
        404: OpenApiResponse(description="Not found"),
        409: OpenApiResponse(description="Stale version or duplicate name"),
    },
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def food_item_detail_view(request, food_item_id: int):
    _require_menu_author(request.user)
    serializer = FoodItemUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    food_item = menu_services.update_food_item(
        food_item_id=food_item_id,
        name=data.get("name"),
        description=data.get("description"),
        expected_version=data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(FoodItemSerializer(food_item).data)


@extend_schema(
    summary="Deactivate Food Item",
    description=(
        "Super Admin deactivates a shared food item. Items are never hard-deleted "
        "because historical menus reference them."
    ),
    tags=["menus"],
    request=FoodItemDeactivateSerializer,
    responses={
        200: FoodItemSerializer,
        403: OpenApiResponse(description="Only the Super Admin may deactivate"),
        404: OpenApiResponse(description="Not found"),
        409: OpenApiResponse(description="Stale version"),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def food_item_deactivate_view(request, food_item_id: int):
    _require_menu_author(request.user)
    serializer = FoodItemDeactivateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    food_item = menu_services.deactivate_food_item(
        food_item_id=food_item_id,
        expected_version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(FoodItemSerializer(food_item).data)


# ---------------------------------------------------------------------------
# Current published menu (Student)
# ---------------------------------------------------------------------------


@extend_schema(
    summary="Current Published Menu",
    description=(
        "Returns the published menu of the student's hostel from today's ACTIVE "
        "assignment for the current IST month, and the next month when already "
        "published, shaped as Month -> Date -> Meal -> Items [SRS §22]. Earlier "
        "months are never exposed."
    ),
    tags=["menus"],
    responses={
        200: CurrentMenuSerializer,
        403: OpenApiResponse(description="Students only"),
        404: OpenApiResponse(description="No student profile or active assignment"),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_menu_view(request):
    _require_student(request.user)
    return Response(CurrentMenuSerializer(menu_selectors.get_current_student_menu(request.user)).data)


# ---------------------------------------------------------------------------
# Monthly menus
# ---------------------------------------------------------------------------


@extend_schema(
    methods=["GET"],
    summary="List Menus",
    description=(
        "Lists monthly menus. A Hostel Clerk sees only their own hostel; the "
        "Super Admin sees every hostel. Students use /menus/current."
    ),
    tags=["menus"],
    responses={200: MenuSerializer(many=True), 403: OpenApiResponse(description="Permission denied")},
)
@extend_schema(
    methods=["POST"],
    summary="Create Monthly Menu",
    description=(
        "Creates an empty DRAFT menu for one hostel and calendar month. The "
        "combination of hostel, year and month is unique [SPEC DBDD §9]."
    ),
    tags=["menus"],
    request=MenuCreateSerializer,
    responses={
        201: MenuStructureSerializer,
        404: OpenApiResponse(description="Hostel not found or out of scope"),
        409: OpenApiResponse(description="Menu already exists"),
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def menu_collection_view(request):
    _require_menu_author(request.user)
    if request.method == "POST":
        serializer = MenuCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        menu = menu_services.create_menu(
            hostel_id=data["hostel_id"],
            year=data["year"],
            month=data["month"],
            actor=request.user,
            correlation_id=getattr(request, "correlation_id", ""),
        )
        return Response(
            MenuStructureSerializer(menu_selectors.build_menu_structure(menu_selectors.menu_with_meals(menu))).data,
            status=status.HTTP_201_CREATED,
        )

    menus = menu_selectors.list_menus_scoped(
        request.user,
        hostel_id=_int_param(request, "hostel_id"),
        year=_int_param(request, "year"),
        month=_int_param(request, "month"),
        status_value=request.query_params.get("status") or None,
    )
    return _paginate(request, menus, MenuSerializer)


@extend_schema(
    summary="Menu Detail",
    description=(
        "Returns one menu shaped as Month -> Date -> Meal -> Items. Out-of-scope "
        "menus return 404 so their existence is not revealed."
    ),
    tags=["menus"],
    responses={
        200: MenuStructureSerializer,
        404: OpenApiResponse(description="Not found or out of scope"),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def menu_detail_view(request, menu_id: int):
    _require_menu_author(request.user)
    menu = menu_selectors.get_menu_scoped(request.user, menu_id)
    menu = menu_selectors.menu_with_meals(menu)
    return Response(MenuStructureSerializer(menu_selectors.build_menu_structure(menu)).data)


@extend_schema(
    summary="Replace Menu Meal Items",
    description=(
        "Sets the complete item list of one (date, meal type) in one call. An "
        "empty list clears the meal. Dates must fall inside the menu's month. "
        "The database forbids the same food item twice in one MenuMeal "
        "[DBDD-AC-30]. Changes to a PUBLISHED menu are audited as MENU_REVISED."
    ),
    tags=["menus"],
    request=MenuMealSetSerializer,
    responses={
        200: MenuStructureSerializer,
        400: OpenApiResponse(description="Validation error"),
        404: OpenApiResponse(description="Not found or out of scope"),
        409: OpenApiResponse(description="Stale version"),
    },
)
@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def menu_meal_view(request, menu_id: int):
    _require_menu_author(request.user)
    serializer = MenuMealSetSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    menu = menu_services.set_menu_meal(
        menu_id=menu_id,
        menu_date=data["menu_date"],
        meal_type_code=data["meal_type_code"],
        items=data["items"],
        expected_version=data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(MenuStructureSerializer(menu_selectors.build_menu_structure(menu)).data)


@extend_schema(
    summary="Publish Menu",
    description=(
        "DRAFT -> PUBLISHED. Sets PublishedAt and PublishedBy and audits "
        "MENU_PUBLISHED. Dates with no items are returned as warnings but do not "
        "block publication because the specifications do not require full coverage."
    ),
    tags=["menus"],
    request=MenuPublishSerializer,
    responses={
        200: MenuPublishResultSerializer,
        404: OpenApiResponse(description="Not found or out of scope"),
        409: OpenApiResponse(description="Already published or stale version"),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def menu_publish_view(request, menu_id: int):
    _require_menu_author(request.user)
    serializer = MenuPublishSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    menu, warnings = menu_services.publish_menu(
        menu_id=menu_id,
        expected_version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(
        MenuPublishResultSerializer(
            {
                "menu": menu_selectors.build_menu_structure(menu),
                "warnings": warnings,
            }
        ).data
    )


@extend_schema(
    summary="Copy Previous Month Pattern",
    description=(
        "Populates a DRAFT menu from the previous month's weekday pattern [REC]. "
        "The first previous-month date for each weekday supplies that weekday's meals."
    ),
    tags=["menus"],
    request=MenuCopyPreviousSerializer,
    responses={
        200: MenuStructureSerializer,
        404: OpenApiResponse(description="No previous menu, or out of scope"),
        409: OpenApiResponse(description="Not a draft or stale version"),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def menu_copy_previous_view(request, menu_id: int):
    _require_menu_author(request.user)
    serializer = MenuCopyPreviousSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    menu = menu_services.copy_previous_month_pattern(
        menu_id=menu_id,
        expected_version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(MenuStructureSerializer(menu_selectors.build_menu_structure(menu)).data)
