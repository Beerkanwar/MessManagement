from django.urls import path
from apps.billing.views import billing_periods_stub_view

urlpatterns = [
    path("periods", billing_periods_stub_view, name="billing_periods_list"),
]
