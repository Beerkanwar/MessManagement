from django.urls import path
from apps.pause.views import pause_list_stub_view

urlpatterns = [
    path("pauses", pause_list_stub_view, name="pauses_list"),
]
