"""
Views for Mess, Managers, Meal Occurrences, Rates, and Extras — Phase 5.
"""
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardPageNumberPagination
from apps.core.permissions import IsHostelClerk, IsMessManager, IsSuperAdmin
from apps.hostel.models import Hostel, StudentMessAssignment
from apps.identity.selectors import get_clerk_hostel, get_manager_mess, get_user_role
from apps.mess.models import (
    ExtraItem,
    ExtraPrice,
    MealOccurrence,
    MealRate,
    MealType,
    Mess,
    MessManagerAssignment,
)
from apps.mess.serializers import (
    ExtraItemCreateSerializer,
    ExtraItemDeactivateSerializer,
    ExtraItemSerializer,
    ExtraItemUpdateSerializer,
    ExtraPriceCreateSerializer,
    ExtraPriceSerializer,
    MealOccurrenceCancelSerializer,
    MealOccurrenceSerializer,
    MealRateCreateSerializer,
    MealRateSerializer,
    MealTypeSerializer,
    MessCreateSerializer,
    MessDeactivateSerializer,
    MessManagerAssignmentSerializer,
    MessManagerCreateSerializer,
    MessManagerReassignSerializer,
    MessSerializer,
    MessUpdateSerializer,
)
from apps.mess.services import (
    add_extra_price,
    add_meal_rate,
    cancel_meal_occurrence,
    create_extra_item,
    create_mess,
    create_mess_manager,
    deactivate_extra_item,
    deactivate_mess,
    deactivate_mess_manager,
    list_extra_prices,
    list_meal_rates,
    list_meal_types,
    reassign_mess_manager,
    update_extra_item,
    update_mess,
)


# ---------------------------------------------------------------------------
# 1. Mess Master Endpoints
# ---------------------------------------------------------------------------


@extend_schema(
    summary="List or Create Messes",
    description="Lists messes (scoped) or creates a new mess hall (Super Admin only) [SPEC SDD §64].",
    tags=["messes"],
    request=MessCreateSerializer,
    responses={
        200: MessSerializer(many=True),
        201: MessSerializer,
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def mess_list_create_view(request):
    """List messes or create a new mess hall."""
    if request.method == "GET":
        role = get_user_role(request.user)
        qs = Mess.objects.all().order_by("code")

        if role != "SUPER_ADMIN" and not getattr(request.user, "is_superuser", False):
            # Non-superadmins only see active messes
            qs = qs.filter(status="ACTIVE")

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(code__icontains=search)

        paginator = StandardPageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = MessSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # POST: Super Admin only
    if not (getattr(request.user, "is_superuser", False) or get_user_role(request.user) == "SUPER_ADMIN"):
        raise PermissionDenied("Only Super Admin can create messes.")

    serializer = MessCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    mess = create_mess(
        code=serializer.validated_data["code"],
        name=serializer.validated_data["name"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(MessSerializer(mess).data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Get or Update Mess",
    description="Retrieve details or update display name with optimistic locking (Super Admin).",
    tags=["messes"],
    request=MessUpdateSerializer,
    responses={200: MessSerializer},
)
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def mess_detail_update_view(request, mess_id: int):
    """Retrieve or update a mess hall."""
    mess = Mess.objects.filter(mess_id=mess_id).first()
    if not mess:
        return Response({"code": "OBJECT_NOT_FOUND", "message": "Mess not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(MessSerializer(mess).data, status=status.HTTP_200_OK)

    # PUT: Super Admin only
    if not (getattr(request.user, "is_superuser", False) or get_user_role(request.user) == "SUPER_ADMIN"):
        raise PermissionDenied("Only Super Admin can update messes.")

    serializer = MessUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    updated = update_mess(
        mess_id=mess_id,
        name=serializer.validated_data["name"],
        version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(MessSerializer(updated).data, status=status.HTTP_200_OK)


@extend_schema(
    summary="Deactivate Mess",
    description="Deactivate a mess hall (Super Admin only). Refused if active assignments exist.",
    tags=["messes"],
    request=MessDeactivateSerializer,
    responses={200: MessSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def mess_deactivate_view(request, mess_id: int):
    """Deactivate a mess hall."""
    serializer = MessDeactivateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    mess = deactivate_mess(
        mess_id=mess_id,
        version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(MessSerializer(mess).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 2. Mess Manager Accounts Endpoints
# ---------------------------------------------------------------------------


@extend_schema(
    summary="List or Create Mess Managers",
    description="Super Admin management of Mess Manager accounts and assignments [DEC-21].",
    tags=["admin"],
    request=MessManagerCreateSerializer,
    responses={
        200: MessManagerAssignmentSerializer(many=True),
        201: OpenApiResponse(description="Mess Manager created"),
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def mess_manager_list_create_view(request):
    """List or create Mess Managers."""
    if request.method == "GET":
        qs = (
            MessManagerAssignment.objects
            .select_related("user", "mess")
            .order_by("-is_active", "mess__code")
        )

        is_active = request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")

        mess_id = request.query_params.get("mess_id")
        if mess_id:
            qs = qs.filter(mess_id=mess_id)

        paginator = StandardPageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = MessManagerAssignmentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = MessManagerCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = create_mess_manager(
        email=serializer.validated_data["email"],
        full_name=serializer.validated_data["full_name"],
        mess_code=serializer.validated_data["mess_code"],
        phone_number=serializer.validated_data.get("phone_number", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Reassign Mess Manager",
    description="Reassigns a Mess Manager to a different mess (Super Admin only) [DEC-21].",
    tags=["admin"],
    request=MessManagerReassignSerializer,
    responses={200: OpenApiResponse(description="Mess Manager reassigned")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def mess_manager_reassign_view(request, user_id: int):
    """Reassign a Mess Manager to another mess."""
    serializer = MessManagerReassignSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    result = reassign_mess_manager(
        user_id=user_id,
        new_mess_code=serializer.validated_data["new_mess_code"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    summary="Deactivate Mess Manager",
    description="Deactivates a Mess Manager's assignment.",
    tags=["admin"],
    request=None,
    responses={200: OpenApiResponse(description="Mess Manager deactivated")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def mess_manager_deactivate_view(request, user_id: int):
    """Deactivate a Mess Manager's assignment."""
    result = deactivate_mess_manager(
        user_id=user_id,
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(result, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 3. Meal Types & Occurrences Endpoints
# ---------------------------------------------------------------------------


@extend_schema(
    summary="List Meal Types",
    description="Lists fixed meal types (Breakfast, Lunch, Evening Snacks, Dinner) [SPEC DBDD §1].",
    tags=["meals"],
    responses={200: MealTypeSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def meal_types_view(request):
    """Read-only listing of seeded meal types."""
    meal_types = list_meal_types()
    serializer = MealTypeSerializer(meal_types, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    summary="List Meal Occurrences",
    description="Lists scheduled meal occurrences scoped by role.",
    tags=["meals"],
    responses={200: MealOccurrenceSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def meal_occurrences_list_view(request):
    """List scheduled meal occurrences with scoped authorization."""
    role = get_user_role(request.user)
    qs = (
        MealOccurrence.objects
        .select_related("mess", "meal_type")
        .order_by("meal_date", "meal_type__sequence_no")
    )

    if role == "MESS_MANAGER":
        manager_mess = get_manager_mess(request.user)
        if not manager_mess:
            return Response({"code": "STATE_CONFLICT", "message": "No active mess assigned."}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(mess=manager_mess)

    elif role == "STUDENT":
        today = clock.today()
        assignment = StudentMessAssignment.objects.filter(
            student__user=request.user,
            status="ACTIVE",
            effective_from__lte=today,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=today)
        ).first()
        if assignment:
            qs = qs.filter(mess_id=assignment.mess_id)
        else:
            qs = qs.none()

    # Query param filters
    mess_id = request.query_params.get("mess_id")
    if mess_id:
        if role == "MESS_MANAGER":
            manager_mess = get_manager_mess(request.user)
            if str(manager_mess.mess_id) != str(mess_id):
                return Response({"code": "OBJECT_NOT_FOUND", "message": "Mess out of scope."}, status=status.HTTP_404_NOT_FOUND)
        qs = qs.filter(mess_id=mess_id)

    from_date = request.query_params.get("from_date")
    if from_date:
        qs = qs.filter(meal_date__gte=from_date)

    to_date = request.query_params.get("to_date")
    if to_date:
        qs = qs.filter(meal_date__lte=to_date)

    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter.upper())

    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = MealOccurrenceSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    summary="Cancel Meal Occurrence",
    description="Super Admin cancels a scheduled meal occurrence with reason [SPEC DBDD §5].",
    tags=["meals"],
    request=MealOccurrenceCancelSerializer,
    responses={200: MealOccurrenceSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def meal_occurrence_cancel_view(request, occurrence_id: int):
    """Cancel a scheduled meal occurrence."""
    serializer = MealOccurrenceCancelSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    occurrence = cancel_meal_occurrence(
        occurrence_id=occurrence_id,
        reason=serializer.validated_data["reason"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(MealOccurrenceSerializer(occurrence).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 4. Common Meal Rate Endpoints
# ---------------------------------------------------------------------------


@extend_schema(
    summary="List or Create Meal Rates",
    description="Super Admin creates new rate version; Super Admin or assigned Manager reads rate history.",
    tags=["messes"],
    request=MealRateCreateSerializer,
    responses={
        200: MealRateSerializer(many=True),
        201: MealRateSerializer,
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def meal_rates_list_create_view(request, mess_id: int):
    """List or create meal rates for a mess."""
    mess = Mess.objects.filter(mess_id=mess_id).first()
    if not mess:
        return Response({"code": "OBJECT_NOT_FOUND", "message": "Mess not found."}, status=status.HTTP_404_NOT_FOUND)

    role = get_user_role(request.user)

    if request.method == "GET":
        # Super Admin or Manager of own mess
        is_sa = role == "SUPER_ADMIN" or getattr(request.user, "is_superuser", False)
        if not is_sa:
            if role != "MESS_MANAGER":
                raise PermissionDenied("You do not have permission to view meal rates.")
            manager_mess = get_manager_mess(request.user)
            if not manager_mess or manager_mess.mess_id != mess_id:
                return Response({"code": "OBJECT_NOT_FOUND", "message": "Mess out of scope."}, status=status.HTTP_404_NOT_FOUND)

        rates = list_meal_rates(mess_id)
        serializer = MealRateSerializer(rates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # POST: Super Admin only
    if not (getattr(request.user, "is_superuser", False) or role == "SUPER_ADMIN"):
        raise PermissionDenied("Only Super Admin can update meal rates.")

    serializer = MealRateCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    new_rate = add_meal_rate(
        mess_id=mess_id,
        rate=serializer.validated_data["rate"],
        effective_from=serializer.validated_data["effective_from"],
        reason=serializer.validated_data.get("reason", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(MealRateSerializer(new_rate).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# 5. Extra Items & Prices Endpoints
# ---------------------------------------------------------------------------


@extend_schema(
    summary="List or Create Extra Items",
    description="Clerk (own hostel) or Super Admin creates/manages extra items; Manager reads scoped items.",
    tags=["extras"],
    request=ExtraItemCreateSerializer,
    responses={
        200: ExtraItemSerializer(many=True),
        201: ExtraItemSerializer,
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def extra_items_list_create_view(request):
    """List or create extra items."""
    role = get_user_role(request.user)

    if request.method == "GET":
        qs = (
            ExtraItem.objects
            .select_related("hostel")
            .prefetch_related("prices")
            .order_by("hostel__code", "name")
        )

        if role == "HOSTEL_CLERK":
            clerk_hostel = get_clerk_hostel(request.user)
            if not clerk_hostel:
                return Response({"code": "STATE_CONFLICT", "message": "No active hostel assigned."}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(hostel=clerk_hostel)

        elif role == "MESS_MANAGER":
            manager_mess = get_manager_mess(request.user)
            if not manager_mess:
                return Response({"code": "STATE_CONFLICT", "message": "No active mess assigned."}, status=status.HTTP_400_BAD_REQUEST)
            # Hostels of students assigned to manager's mess
            hostel_ids = (
                StudentMessAssignment.objects
                .filter(mess=manager_mess, status="ACTIVE")
                .values_list("hostel_id", flat=True)
                .distinct()
            )
            qs = qs.filter(hostel_id__in=hostel_ids, status="ACTIVE")

        elif role == "STUDENT":
            today = clock.today()
            assignment = StudentMessAssignment.objects.filter(
                student__user=request.user,
                status="ACTIVE",
                effective_from__lte=today,
            ).filter(
                Q(effective_to__isnull=True) | Q(effective_to__gt=today)
            ).first()
            if assignment:
                qs = qs.filter(hostel_id=assignment.hostel_id, status="ACTIVE")
            else:
                qs = qs.none()

        # Query filters
        hostel_id = request.query_params.get("hostel_id")
        if hostel_id:
            if role == "HOSTEL_CLERK":
                clerk_hostel = get_clerk_hostel(request.user)
                if str(clerk_hostel.hostel_id) != str(hostel_id):
                    return Response({"code": "OBJECT_NOT_FOUND", "message": "Hostel out of scope."}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(hostel_id=hostel_id)

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        paginator = StandardPageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ExtraItemSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # POST: Super Admin or Clerk (own hostel)
    is_sa = role == "SUPER_ADMIN" or getattr(request.user, "is_superuser", False)
    if not (is_sa or role == "HOSTEL_CLERK"):
        raise PermissionDenied("Only Super Admin or Hostel Clerk can create extra items.")

    serializer = ExtraItemCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_hostel(request.user)
        if not clerk_hostel:
            return Response({"code": "STATE_CONFLICT", "message": "No active hostel assignment."}, status=status.HTTP_400_BAD_REQUEST)
        hostel_id = clerk_hostel.hostel_id
    else:
        # Super Admin: hostel_code required
        hostel_code = serializer.validated_data.get("hostel_code", "").strip().upper()
        if not hostel_code:
            return Response({"code": "VALIDATION_ERROR", "message": "Hostel code is required for Super Admin."}, status=status.HTTP_400_BAD_REQUEST)
        hostel = Hostel.objects.filter(code=hostel_code).first()
        if not hostel:
            return Response({"code": "OBJECT_NOT_FOUND", "message": f"Hostel '{hostel_code}' not found."}, status=status.HTTP_404_NOT_FOUND)
        hostel_id = hostel.hostel_id

    item = create_extra_item(
        name=serializer.validated_data["name"],
        hostel_id=hostel_id,
        initial_price=serializer.validated_data.get("initial_price"),
        effective_from=serializer.validated_data.get("effective_from"),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(ExtraItemSerializer(item).data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Get or Update Extra Item",
    description="Retrieve extra item details or update its display name with optimistic locking.",
    tags=["extras"],
    request=ExtraItemUpdateSerializer,
    responses={200: ExtraItemSerializer},
)
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def extra_item_detail_update_view(request, item_id: int):
    """Retrieve or update an extra item."""
    item = ExtraItem.objects.select_related("hostel").filter(extra_item_id=item_id).first()
    if not item:
        return Response({"code": "OBJECT_NOT_FOUND", "message": "Extra item not found."}, status=status.HTTP_404_NOT_FOUND)

    role = get_user_role(request.user)
    is_sa = role == "SUPER_ADMIN" or getattr(request.user, "is_superuser", False)

    if request.method == "GET":
        if not is_sa and role == "HOSTEL_CLERK":
            clerk_hostel = get_clerk_hostel(request.user)
            if not clerk_hostel or clerk_hostel.hostel_id != item.hostel_id:
                return Response({"code": "OBJECT_NOT_FOUND", "message": "Extra item out of scope."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ExtraItemSerializer(item).data, status=status.HTTP_200_OK)

    # PUT: Clerk (own hostel) or Super Admin
    if not (is_sa or role == "HOSTEL_CLERK"):
        raise PermissionDenied("Only Super Admin or Hostel Clerk can update extra items.")

    if not is_sa and role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_hostel(request.user)
        if not clerk_hostel or clerk_hostel.hostel_id != item.hostel_id:
            return Response({"code": "OBJECT_NOT_FOUND", "message": "Extra item out of scope."}, status=status.HTTP_404_NOT_FOUND)

    serializer = ExtraItemUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    updated = update_extra_item(
        extra_item_id=item_id,
        name=serializer.validated_data["name"],
        version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(ExtraItemSerializer(updated).data, status=status.HTTP_200_OK)


@extend_schema(
    summary="Deactivate Extra Item",
    description="Deactivate an extra item (Clerk own hostel or Super Admin).",
    tags=["extras"],
    request=ExtraItemDeactivateSerializer,
    responses={200: ExtraItemSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def extra_item_deactivate_view(request, item_id: int):
    """Deactivate an extra item."""
    item = ExtraItem.objects.filter(extra_item_id=item_id).first()
    if not item:
        return Response({"code": "OBJECT_NOT_FOUND", "message": "Extra item not found."}, status=status.HTTP_404_NOT_FOUND)

    role = get_user_role(request.user)
    is_sa = role == "SUPER_ADMIN" or getattr(request.user, "is_superuser", False)

    if not (is_sa or role == "HOSTEL_CLERK"):
        raise PermissionDenied("Only Super Admin or Hostel Clerk can deactivate extra items.")

    if not is_sa and role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_hostel(request.user)
        if not clerk_hostel or clerk_hostel.hostel_id != item.hostel_id:
            return Response({"code": "OBJECT_NOT_FOUND", "message": "Extra item out of scope."}, status=status.HTTP_404_NOT_FOUND)

    serializer = ExtraItemDeactivateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    deactivated = deactivate_extra_item(
        extra_item_id=item_id,
        version=serializer.validated_data["version"],
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(ExtraItemSerializer(deactivated).data, status=status.HTTP_200_OK)


@extend_schema(
    summary="List or Create Extra Prices",
    description="List price versions or add a new effective-dated price version.",
    tags=["extras"],
    request=ExtraPriceCreateSerializer,
    responses={
        200: ExtraPriceSerializer(many=True),
        201: ExtraPriceSerializer,
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def extra_prices_list_create_view(request, item_id: int):
    """List or create effective-dated prices for an extra item."""
    item = ExtraItem.objects.filter(extra_item_id=item_id).first()
    if not item:
        return Response({"code": "OBJECT_NOT_FOUND", "message": "Extra item not found."}, status=status.HTTP_404_NOT_FOUND)

    role = get_user_role(request.user)
    is_sa = role == "SUPER_ADMIN" or getattr(request.user, "is_superuser", False)

    if request.method == "GET":
        if not is_sa and role == "HOSTEL_CLERK":
            clerk_hostel = get_clerk_hostel(request.user)
            if not clerk_hostel or clerk_hostel.hostel_id != item.hostel_id:
                return Response({"code": "OBJECT_NOT_FOUND", "message": "Extra item out of scope."}, status=status.HTTP_404_NOT_FOUND)

        prices = list_extra_prices(item_id)
        serializer = ExtraPriceSerializer(prices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # POST: Super Admin or Clerk (own hostel)
    if not (is_sa or role == "HOSTEL_CLERK"):
        raise PermissionDenied("Only Super Admin or Hostel Clerk can add prices.")

    if not is_sa and role == "HOSTEL_CLERK":
        clerk_hostel = get_clerk_hostel(request.user)
        if not clerk_hostel or clerk_hostel.hostel_id != item.hostel_id:
            return Response({"code": "OBJECT_NOT_FOUND", "message": "Extra item out of scope."}, status=status.HTTP_404_NOT_FOUND)

    serializer = ExtraPriceCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    new_price = add_extra_price(
        extra_item_id=item_id,
        unit_price=serializer.validated_data["unit_price"],
        effective_from=serializer.validated_data["effective_from"],
        reason=serializer.validated_data.get("reason", ""),
        actor=request.user,
        correlation_id=getattr(request, "correlation_id", ""),
    )
    return Response(ExtraPriceSerializer(new_price).data, status=status.HTTP_201_CREATED)
