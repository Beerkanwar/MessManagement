"""
Django admin registrations bounded by Phase 13 rules.

Editable models are the simple master records only. Every other domain model is
registered read-only because its state must change through the domain services.
No model allows deletion: records are deactivated or superseded instead, so
references never dangle [SPEC DBDD §17].
"""
from django.apps import apps as django_apps
from django.contrib import admin

from apps.audit.services import record_audit_event
from apps.config.models import ApplicationVersionPolicy
from apps.core.admin_site import admin_site
from apps.hostel.models import Hostel
from apps.menu.models import FoodItem
from apps.mess.models import Mess

DOMAIN_APP_LABELS = {
    "identity",
    "config",
    "hostel",
    "mess",
    "attendance",
    "pause",
    "billing",
    "menu",
    "feedback",
    "sync",
    "audit",
    "qr",
    "reports",
}

SENSITIVE_EXCLUDES = {
    "identity.user": ("password", "groups", "user_permissions"),
    "identity.refreshtoken": ("token_hash",),
    "identity.passwordresettoken": ("token_hash", "otp_hash"),
    "identity.studentsecret": ("encrypted_secret",),
    "audit.auditlog": ("old_values_json", "new_values_json", "metadata_json"),
}

MAX_AUDIT_VALUE_LENGTH = 500


def _audit_value(value):
    """Keep admin audit payloads inside the sanitizer's string limit."""
    if value is None:
        return ""
    text = str(value)
    if len(text) > MAX_AUDIT_VALUE_LENGTH:
        return text[:MAX_AUDIT_VALUE_LENGTH]
    return text


class BaseBoundedAdmin(admin.ModelAdmin):
    """Common permission surface: viewable, never deletable."""

    def has_module_permission(self, request):
        return admin_site.has_permission(request)

    def has_view_permission(self, request, obj=None):
        return admin_site.has_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(BaseBoundedAdmin):
    """Workflow-owned data: visible for support, impossible to edit here."""

    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class AuditedMasterAdmin(BaseBoundedAdmin):
    """Simple master data: editable, and every save is audited."""

    audited_fields: tuple[str, ...] = ()

    def has_add_permission(self, request):
        return admin_site.has_permission(request)

    def has_change_permission(self, request, obj=None):
        return admin_site.has_permission(request)

    def _snapshot(self, obj):
        return {
            field: _audit_value(getattr(obj, field))
            for field in self.audited_fields
        }

    def save_model(self, request, obj, form, change):
        old_values = None
        if change and obj.pk is not None:
            previous = type(obj)._default_manager.filter(pk=obj.pk).first()
            if previous is not None:
                old_values = self._snapshot(previous)

        super().save_model(request, obj, form, change)

        new_values = self._snapshot(obj)
        action = "edited" if change else "created"
        record_audit_event(
            event_type="MASTER_DATA_CHANGED",
            actor_user=request.user,
            entity_type=type(obj).__name__,
            entity_id=str(obj.pk),
            reason=f"Django admin {action} {type(obj).__name__}",
            old_values=old_values,
            new_values=new_values,
            correlation_id=getattr(request, "correlation_id", ""),
        )


class HostelAdmin(AuditedMasterAdmin):
    list_display = ("code", "name", "status")
    list_filter = ("status",)
    search_fields = ("code", "name")
    audited_fields = ("code", "name", "address", "status")


class MessAdmin(AuditedMasterAdmin):
    list_display = ("code", "name", "status")
    list_filter = ("status",)
    search_fields = ("code", "name")
    audited_fields = ("code", "name", "status")


class FoodItemAdmin(AuditedMasterAdmin):
    list_display = ("name", "normalized_name", "status")
    list_filter = ("status",)
    search_fields = ("name", "normalized_name")
    audited_fields = ("name", "normalized_name", "description", "status")


class ApplicationVersionPolicyAdmin(AuditedMasterAdmin):
    list_display = ("platform", "app_version", "status")
    list_filter = ("platform", "status")
    search_fields = ("app_version",)
    audited_fields = ("platform", "app_version", "status", "force_update_message")


EDITABLE_ADMINS = {
    Hostel: HostelAdmin,
    Mess: MessAdmin,
    FoodItem: FoodItemAdmin,
    ApplicationVersionPolicy: ApplicationVersionPolicyAdmin,
}


def _register_domain_models():
    editable_models = set(EDITABLE_ADMINS)
    for model in django_apps.get_models(include_auto_created=False, include_swapped=False):
        meta = model._meta
        if meta.app_label not in DOMAIN_APP_LABELS:
            continue
        if model in editable_models:
            admin_site.register(model, EDITABLE_ADMINS[model])
            continue

        admin_class = type(
            f"{model.__name__}ReadOnlyAdmin",
            (ReadOnlyAdmin,),
            {
                "exclude": SENSITIVE_EXCLUDES.get(
                    f"{meta.app_label}.{meta.model_name}", ()
                ),
            },
        )
        admin_site.register(model, admin_class)


_register_domain_models()
