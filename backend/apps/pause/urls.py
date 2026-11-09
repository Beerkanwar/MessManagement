from django.urls import path

from apps.pause import views

urlpatterns = [
    # Student submits and lists their own pauses [SPEC DBDD §7, DEC-06]
    path("pauses", views.pause_collection_view, name="pause_collection"),
    # Legacy submission alias retained for existing clients
    path("pauses/request", views.pause_request_view, name="pause_request"),
    # Current pause state (SCHEDULED or ACTIVE)
    path("pauses/current", views.pause_current_view, name="pause_current"),
    # Cancel a SCHEDULED or ACTIVE pause
    path("pauses/<int:pause_id>/cancel", views.pause_cancel_view, name="pause_cancel"),
]
