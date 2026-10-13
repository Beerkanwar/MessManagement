from django.urls import path
from apps.qr.views import qr_secret_stub_view

urlpatterns = [
    path("secret", qr_secret_stub_view, name="qr_secret"),
]
