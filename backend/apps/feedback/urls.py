from django.urls import path
from apps.feedback.views import feedback_list_stub_view

urlpatterns = [
    path("feedback", feedback_list_stub_view, name="feedback_list"),
]
