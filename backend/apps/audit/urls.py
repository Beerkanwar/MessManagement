from django.urls import path
from apps.audit.views import audit_events_stub_view

urlpatterns = [
    path("events", audit_events_stub_view, name="audit_events_list"),
]
