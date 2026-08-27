"""URLs for the response API.

Include them where you want them::

    (path("api/questionnaires/", include("vinta_django_questionnaires.urls")),)
"""

from __future__ import annotations

from django.urls import path

from vinta_django_questionnaires.views import (
    PageSkipView,
    PageSubmitView,
    ResponseCreateView,
    ResponseDetailView,
    ValueSetOptionsView,
)

app_name = "questionnaires"

urlpatterns = [
    path("responses/", ResponseCreateView.as_view(), name="response-create"),
    path("responses/<uuid:response_uuid>/", ResponseDetailView.as_view(), name="response-detail"),
    path(
        "responses/<uuid:response_uuid>/pages/<slug:page_key>/",
        PageSubmitView.as_view(),
        name="page-submit",
    ),
    path(
        "responses/<uuid:response_uuid>/pages/<slug:page_key>/skip/",
        PageSkipView.as_view(),
        name="page-skip",
    ),
    path(
        "value-sets/<slug:key>/options/",
        ValueSetOptionsView.as_view(),
        name="value-set-options",
    ),
]
