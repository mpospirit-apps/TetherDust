"""Root URL routes for the REST API (mounted at /api/)."""

from django.urls import include, path

urlpatterns = [
    path("v1/", include("api.v1.urls")),
    path("internal/", include("api.internal.urls")),  # tdmcp service API (service-token auth)
]
