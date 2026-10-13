"""
Root URL configuration for Hostel Mess Management System.
Enforces SPEC SDD §64 (/api/v1/ versioned prefix) and SPEC SDD §105 (unversioned health probes).
"""
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from apps.core.views.health import health_live_view, health_ready_view

# API v1 versioned endpoints
v1_patterns = [
    # OpenAPI Schema & Interactive Documentation
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # Endpoint Groups matching SDD §64
    path("", include("apps.identity.urls")),
    path("", include("apps.hostel.urls")),
    path("", include("apps.mess.urls")),
    path("", include("apps.attendance.urls")),
    path("", include("apps.pause.urls")),
    path("", include("apps.billing.urls")),
    path("", include("apps.menu.urls")),
    path("", include("apps.feedback.urls")),
    path("", include("apps.sync.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.audit.urls")),
    path("admin/", include("apps.config.urls")),
    path("qr/", include("apps.qr.urls")),
]

urlpatterns = [
    # Health checks outside versioned prefix [SPEC SDD §105]
    path("health/live", health_live_view, name="health_live"),
    path("health/ready", health_ready_view, name="health_ready"),

    # Central API v1 routing shell [SPEC SDD §64]
    path("api/v1/", include(v1_patterns)),
]
