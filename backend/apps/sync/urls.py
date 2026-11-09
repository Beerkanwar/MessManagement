from django.urls import path
from apps.sync import views

urlpatterns = [
    # Manager Batch Upload matching OpenAPI (/api/v1/upload) and SDD §67 (/api/v1/sync/upload)
    path("upload", views.sync_upload_view, name="sync_upload"),
    path("sync/upload", views.sync_upload_view, name="sync_upload_explicit"),
    path("sync/batches", views.sync_batches_list_view, name="sync_batches_list"),
    path("sync/conflicts", views.sync_conflicts_list_view, name="sync_conflicts_list"),
    path("sync/conflicts/<int:conflict_id>/resolve", views.sync_conflict_resolve_view, name="sync_conflict_resolve"),
]
