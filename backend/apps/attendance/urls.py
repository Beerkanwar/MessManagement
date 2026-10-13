from django.urls import path
from apps.attendance.views import attendance_list_stub_view

urlpatterns = [
    path("attendance", attendance_list_stub_view, name="attendance_list"),
]
