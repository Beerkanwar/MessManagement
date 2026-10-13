from django.urls import path
from apps.hostel.views import hostel_list_stub_view, student_list_stub_view

urlpatterns = [
    path("hostels", hostel_list_stub_view, name="hostels_list"),
    path("students", student_list_stub_view, name="students_list"),
]
