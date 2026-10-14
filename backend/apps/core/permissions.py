"""
Base permission classes and role-based access helpers.
Enforces authorization hierarchy across API routing shells.
"""
from typing import Any
from rest_framework.permissions import BasePermission
from rest_framework.request import Request


from apps.identity.selectors import get_user_role


class IsSuperAdmin(BasePermission):
    """Allows access only to Super Admin users."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, "is_superuser", False):
            return True
        return get_user_role(request.user) == "SUPER_ADMIN"


class IsHostelClerk(BasePermission):
    """Allows access to Hostel Clerk users."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        role = get_user_role(request.user)
        return role == "HOSTEL_CLERK" or getattr(request.user, "is_superuser", False)


class IsMessManager(BasePermission):
    """Allows access to Mess Manager users."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        role = get_user_role(request.user)
        return role == "MESS_MANAGER" or getattr(request.user, "is_superuser", False)


class IsStudent(BasePermission):
    """Allows access to Student users."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return get_user_role(request.user) == "STUDENT"
