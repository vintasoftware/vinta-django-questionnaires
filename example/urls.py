"""URLs for the example project: the admin, the API, and the demo front end's API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.urls import include, path

if TYPE_CHECKING:
    from django.urls import URLPattern, URLResolver

from example.api import (
    BootstrapView,
    DemoEditorCatalogView,
    DemoPageSkipView,
    DemoPageSubmitView,
    DemoQuestionnaireCollectionView,
    DemoQuestionnaireDetailView,
    DemoResponseCreateView,
    DemoResponseDetailView,
    DemoResponseExportView,
    DemoResponseListView,
    DemoValueSetOptionsView,
    DemoVersionDefinitionView,
    DemoVersionForkView,
    DemoVersionListView,
    SessionView,
)

# The package's own API, with its careful defaults: a signed-in respondent, who
# sees only their own responses.
urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("api/questionnaires/", include("vinta_django_questionnaires.urls")),
    path("api/authoring/", include("vinta_django_questionnaires.editor_urls")),
]

# The same API with the access hooks overridden, which is what the React demo
# under demo/ talks to.  DEBUG only -- see example/api.py.
demo_response = "demo-api/responses/<uuid:response_uuid>/"
urlpatterns += [
    path("demo-api/bootstrap/", BootstrapView.as_view(), name="demo-bootstrap"),
    path("demo-api/responses/", DemoResponseCreateView.as_view(), name="demo-response-create"),
    path(demo_response, DemoResponseDetailView.as_view(), name="demo-response-detail"),
    path(
        demo_response + "pages/<slug:page_key>/",
        DemoPageSubmitView.as_view(),
        name="demo-page-submit",
    ),
    path(
        demo_response + "pages/<slug:page_key>/skip/",
        DemoPageSkipView.as_view(),
        name="demo-page-skip",
    ),
    path(
        "demo-api/value-sets/<slug:key>/options/",
        DemoValueSetOptionsView.as_view(),
        name="demo-value-set-options",
    ),
]

# The authoring API, which is what the demo's editor talks to.  Unlike the
# response API above it is *not* relaxed: it is staff only, the way the package
# ships it, and the demo signs in with the same credentials as the admin.
demo_authoring = "demo-api/authoring/"
demo_questionnaire = demo_authoring + "questionnaires/<slug:questionnaire_key>/"
demo_version = demo_questionnaire + "versions/<int:version>/"
urlpatterns += [
    path("demo-api/auth/session/", SessionView.as_view(), name="demo-session"),
    path(demo_authoring + "catalog/", DemoEditorCatalogView.as_view(), name="demo-catalog"),
    path(
        demo_authoring + "questionnaires/",
        DemoVersionListView.as_view(),
        name="demo-version-list",
    ),
    path(
        demo_authoring + "questionnaires/new/",
        DemoQuestionnaireCollectionView.as_view(),
        name="demo-questionnaire-create",
    ),
    path(
        demo_questionnaire,
        DemoQuestionnaireDetailView.as_view(),
        name="demo-questionnaire-detail",
    ),
    path(demo_version, DemoVersionDefinitionView.as_view(), name="demo-version-definition"),
    path(demo_version + "fork/", DemoVersionForkView.as_view(), name="demo-version-fork"),
    path(
        demo_authoring + "responses/",
        DemoResponseListView.as_view(),
        name="demo-response-list",
    ),
    path(
        demo_authoring + "responses/export/",
        DemoResponseExportView.as_view(),
        name="demo-response-export",
    ),
]
