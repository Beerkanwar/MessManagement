"""
URL patterns for monthly student feedback [SPEC SDD §64, ImplementationGuide Phase 11].
"""
from django.urls import path

from apps.feedback import views

urlpatterns = [
    path("feedback", views.feedback_submit_view, name="feedback_submit"),
    path("feedback/current", views.feedback_current_view, name="feedback_current"),
]
