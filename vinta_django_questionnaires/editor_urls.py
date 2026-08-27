"""URLs for the authoring API.

Kept separate from the response API, because they are not for the same people::

    (path("api/questionnaires/", include("vinta_django_questionnaires.urls")),)
    (path("api/authoring/", include("vinta_django_questionnaires.editor_urls")),)

The React editor under ``client/`` takes the second of those as its base URL.
"""

from __future__ import annotations

from django.urls import path

from vinta_django_questionnaires.editor_views import (
    EditorCatalogView,
    QuestionnaireCollectionView,
    QuestionnaireDetailView,
    ResponseExportView,
    ResponseListView,
    VersionDefinitionView,
    VersionForkView,
    VersionListView,
)

app_name = "questionnaires-authoring"

QUESTIONNAIRE = "questionnaires/<slug:questionnaire_key>/"
VERSION = QUESTIONNAIRE + "versions/<int:version>/"

urlpatterns = [
    path("catalog/", EditorCatalogView.as_view(), name="catalog"),
    path("questionnaires/", VersionListView.as_view(), name="questionnaire-list"),
    path(
        "questionnaires/new/",
        QuestionnaireCollectionView.as_view(),
        name="questionnaire-create",
    ),
    path(QUESTIONNAIRE, QuestionnaireDetailView.as_view(), name="questionnaire-detail"),
    path(VERSION, VersionDefinitionView.as_view(), name="version-definition"),
    path(VERSION + "fork/", VersionForkView.as_view(), name="version-fork"),
    path("responses/", ResponseListView.as_view(), name="response-list"),
    path("responses/export/", ResponseExportView.as_view(), name="response-export"),
]
