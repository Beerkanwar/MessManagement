from django.urls import path
from apps.sync.views import sync_upload_stub_view

urlpatterns = [
    path("upload", sync_upload_stub_view, name="sync_upload"),
]
