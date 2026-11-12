"""URL patterns for reports [SPEC SDD §64, ImplementationGuide Phase 12]."""
from django.urls import path

from apps.reports import views

urlpatterns = [
    path("reports", views.report_catalog_view, name="report_catalog"),
    path("reports/<str:report_id>", views.report_detail_view, name="report_detail"),
]
