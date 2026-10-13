from django.urls import path
from apps.reports.views import reports_list_stub_view

urlpatterns = [
    path("reports", reports_list_stub_view, name="reports_list"),
]
