"""URL patterns for the audit read API."""
from django.urls import path

from apps.audit.views import audit_events_list_view

urlpatterns = [
    path("audit/events", audit_events_list_view, name="audit_events_list"),
]
