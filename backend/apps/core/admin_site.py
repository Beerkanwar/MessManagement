"""
Bounded Django admin site [ImplementationGuide Phase 13].

The admin is a second sign-in path that uses the same accounts and password
rules as the API. Access is limited to ACTIVE Super Admin accounts; staff status
is derived from the role instead of being trusted from a separate flag. The URL
path is environment-configurable and sessions expire after one hour.
"""
from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.identity.selectors import get_user_role


class SuperAdminAuthenticationForm(AdminAuthenticationForm):
    """Reject every account that is not an ACTIVE Super Admin."""

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )
        if get_user_role(user) != "SUPER_ADMIN":
            raise ValidationError(
                _("Only active Super Admin accounts may sign in to the admin site."),
                code="not_super_admin",
            )


class MessAdminSite(AdminSite):
    """AdminSite whose permission is the SUPER_ADMIN role, not ``is_staff``."""

    login_form = SuperAdminAuthenticationForm
    site_header = "Hostel Mess Administration"
    site_title = "Hostel Mess Administration"
    index_title = "Master data and support"
    session_seconds = 60 * 60

    def has_permission(self, request):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        return get_user_role(user) == "SUPER_ADMIN"

    def login(self, request, extra_context=None):
        response = super().login(request, extra_context=extra_context)
        if self.has_permission(request):
            request.session.set_expiry(self.session_seconds)
            # Staff status is derived from the role, never entered by hand.
            if not request.user.is_staff:
                request.user.is_staff = True
                request.user.save(update_fields=["is_staff"])
        return response

    def each_context(self, request):
        context = super().each_context(request)
        context["site_url"] = "/"
        return context


admin_site = MessAdminSite(name="mess-admin")
