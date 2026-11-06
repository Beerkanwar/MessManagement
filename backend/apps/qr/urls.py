"""
URL routes for QR module [SPEC SDD §64, ImplementationGuide Phase 6].
"""
from django.urls import path
from apps.qr import views

urlpatterns = [
    path("secret", views.qr_secret_view, name="qr_secret"),
    path("rotate", views.qr_rotate_view, name="qr_rotate"),
]
