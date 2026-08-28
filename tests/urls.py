"""URLs for the test project, so the admin's own system checks have something to bind."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("questionnaires/", include("vinta_django_questionnaires.urls")),
    path("authoring/", include("vinta_django_questionnaires.editor_urls")),
    # The multi-tenant shape: the project chooses the prefix, and Django hands
    # the capture to every view underneath.  Mounted alongside the unprefixed
    # one so the suite can exercise both without a second URLconf.
    path(
        "t/<slug:scope_key>/questionnaires/",
        include(
            ("vinta_django_questionnaires.urls", "scoped-responses"), namespace="scoped-responses"
        ),
    ),
    path(
        "t/<slug:scope_key>/authoring/",
        include(
            ("vinta_django_questionnaires.editor_urls", "scoped-authoring"),
            namespace="scoped-authoring",
        ),
    ),
]
