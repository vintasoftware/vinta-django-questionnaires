"""Responses as a table in the admin, and the CSV of the same thing.

The admin changelist can show a response's metadata but not its answers: they
are rows in another table, keyed by a question the changelist has never heard
of.  So this is the same table the React demo renders, served from the admin --
one column per question the version asks, the reader picking which ones, and an
export that takes exactly the columns on screen.

It reuses `reporting`, so the admin, the API and the demo cannot drift: there
is one definition of what a column is and what goes in it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.http import StreamingHttpResponse
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models import (
    QuestionnaireResponse,
    QuestionnaireVersion,
    ResponseStatus,
)
from vinta_django_questionnaires.reporting import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Column,
    as_cell,
    columns_for,
    csv_rows,
    default_columns,
    response_queryset,
    rows_for,
    select_columns,
)
from vinta_django_questionnaires.scoping import GLOBAL_SCOPE_KEY, ScopeFilter

#: What the scope control writes for the installation's own scope, whose key
#: is "" and so cannot be told from "no selection" in a query string.
GLOBAL_CHOICE = "-"

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


#: The query parameter each control writes into the URL, so a filtered table is
#: a link someone can send to a colleague.
SCOPE = "scope"
#: A primary key, not a key.  A questionnaire key is unique only within a
#: scope, and this table spans every scope, so two tenants' "intake" would
#: otherwise select as one and merge their answers under one set of columns.
QUESTIONNAIRE = "questionnaire"
VERSION = "version"
STATUS = "status"
SEARCH = "search"
COLUMNS = "columns"
PAGE = "p"
PAGE_SIZE = "size"


class ResponseTable:
    """One page of the table, and everything the template needs to draw it."""

    def __init__(self, request: HttpRequest) -> None:
        self.request = request
        # Staff see every scope; this narrows what is on screen rather than
        # deciding what may be seen.  "" is every scope, "" cannot be a tenant
        # key, and the global scope is reached with the explicit sentinel.
        self.scope_key = request.GET.get(SCOPE, "")
        self.questionnaire_pk = _as_int(request.GET.get(QUESTIONNAIRE))
        self.version_number = _as_int(request.GET.get(VERSION))
        self.status = request.GET.get(STATUS, "")
        self.search = request.GET.get(SEARCH, "").strip()
        self.version = self._version()
        self.available = columns_for(self.version)
        self.selected = self._selected()
        self.page_size = min(
            max(_as_int(request.GET.get(PAGE_SIZE)) or DEFAULT_PAGE_SIZE, 1), MAX_PAGE_SIZE
        )
        self.number = max(_as_int(request.GET.get(PAGE)) or 1, 1)
        self.queryset = self._queryset()
        self.total = self.queryset.count()

    # -- what to show ------------------------------------------------------
    def _version(self) -> QuestionnaireVersion | None:
        """The version the answer columns come from.

        Without one there is nothing sensible to put in them: two
        questionnaires do not ask the same questions, so a table across all of
        them gets the metadata columns only.
        """
        if self.questionnaire_pk is None:
            return None
        versions = QuestionnaireVersion.objects.filter(questionnaire_id=self.questionnaire_pk)
        if self.version_number is not None:
            return versions.filter(version=self.version_number).first()
        return versions.order_by("-version").first()

    def _selected(self) -> list[Column]:
        asked = [key for key in self.request.GET.get(COLUMNS, "").split(",") if key]
        return select_columns(self.available, asked or default_columns(self.version))

    @property
    def scopes(self) -> ScopeFilter:
        """What the scope control is asking for.

        Staff may see everything, so no selection means exactly that.  Picking
        one narrows to it, and :data:`GLOBAL_CHOICE` reaches the installation's
        own scope, whose key is the empty string and so cannot be spelled in a
        query parameter any other way.
        """
        if not self.scope_key:
            return ScopeFilter.everything()
        if self.scope_key == GLOBAL_CHOICE:
            return ScopeFilter.only(GLOBAL_SCOPE_KEY)
        return ScopeFilter.only(self.scope_key)

    def _queryset(self) -> QuerySet[QuestionnaireResponse]:
        return response_queryset(
            scopes=self.scopes,
            questionnaire_pk=self.questionnaire_pk,
            version=self.version_number,
            status=self.status,
            search=self.search,
        )

    # -- the page ----------------------------------------------------------
    @property
    def total_pages(self) -> int:
        return max(1, -(-self.total // self.page_size))

    def rows(self) -> list[dict[str, Any]]:
        start = (self.number - 1) * self.page_size
        return rows_for(list(self.queryset[start : start + self.page_size]), self.selected)

    def cells(self) -> list[dict[str, Any]]:
        """Each row as a list of already-rendered cells, in column order."""
        keys = [column.key for column in self.selected]
        return [
            {"id": row.get("id"), "cells": [as_cell(row.get(key)) for key in keys]}
            for row in self.rows()
        ]

    # -- the controls ------------------------------------------------------
    def scopes_available(self) -> list[dict[str, Any]]:
        """Every scope that has a response, so the control has no dead entries."""
        from vinta_django_questionnaires.models_registry import get_scope_model

        used = set(
            QuestionnaireResponse.objects.order_by().values_list("scope_key", flat=True).distinct()
        )
        entries: list[dict[str, Any]] = []
        if GLOBAL_SCOPE_KEY in used:
            entries.append(
                {
                    "value": GLOBAL_CHOICE,
                    "label": str(_("The whole installation")),
                    "selected": self.scope_key == GLOBAL_CHOICE,
                }
            )
        # The model is swappable, so it is only ever ``type[Model]`` here;
        # the columns below are the ones ``AbstractQuestionnaireScope``
        # guarantees whatever a project put underneath it.
        scopes: Any = get_scope_model()._default_manager.filter(
            scope_key__in=used - {GLOBAL_SCOPE_KEY}
        )
        entries.extend(
            {
                "value": scope.scope_key,
                "label": str(scope),
                "selected": scope.scope_key == self.scope_key,
            }
            for scope in scopes
        )
        return entries

    def questionnaires(self) -> list[dict[str, Any]]:
        """The questionnaires to choose from, told apart by scope.

        Selected by primary key rather than by key, and labelled with the scope
        alongside, so that two tenants each having an "intake" is legible at the
        point of choosing rather than a surprise afterwards.
        """
        from vinta_django_questionnaires.models import Questionnaire

        return [
            {
                "key": entry.pk,
                "name": self._questionnaire_label(entry),
                "selected": entry.pk == self.questionnaire_pk,
            }
            for entry in self.scopes.apply(
                Questionnaire.objects.select_related("scope"), field="scope__scope_key"
            )
        ]

    @staticmethod
    def _questionnaire_label(questionnaire: Any) -> str:
        scope = questionnaire.scope
        return f"{questionnaire} - {scope}" if scope.scope_key else str(questionnaire)

    def versions(self) -> list[dict[str, Any]]:
        if self.questionnaire_pk is None:
            return []
        return [
            {
                "version": entry.version,
                "label": f"v{entry.version} ({entry.status})",
                "selected": entry.version == self.version_number,
            }
            for entry in QuestionnaireVersion.objects.filter(
                questionnaire_id=self.questionnaire_pk
            ).order_by("version")
        ]

    def statuses(self) -> list[dict[str, Any]]:
        return [
            {"value": value, "label": str(label), "selected": value == self.status}
            for value, label in ResponseStatus.choices
        ]

    def column_groups(self) -> list[dict[str, Any]]:
        """The picker, grouped the way someone thinks about it: page by page."""
        chosen = {column.key for column in self.selected}
        groups: dict[str, list[dict[str, Any]]] = {}
        for column in self.available:
            title = (
                str(_("The response"))
                if column.group == "meta"
                else (column.page or str(_("Questions")))
            )
            groups.setdefault(title, []).append(
                {
                    "key": column.key,
                    "label": str(column.label),
                    "section": column.section,
                    "checked": column.key in chosen,
                }
            )
        return [{"title": title, "columns": entries} for title, entries in groups.items()]

    def query(self, **overrides: Any) -> str:
        """This table's URL with a few parameters changed, for the links."""
        params = self.request.GET.copy()
        for name, value in overrides.items():
            if value in (None, ""):
                params.pop(name, None)
            else:
                params[name] = str(value)
        return params.urlencode()

    @property
    def export_query(self) -> str:
        return self.query(**{COLUMNS: ",".join(column.key for column in self.selected)})

    @property
    def previous_query(self) -> str:
        return self.query(**{PAGE: self.number - 1})

    @property
    def next_query(self) -> str:
        return self.query(**{PAGE: self.number + 1})

    @property
    def has_previous(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.total_pages


def export(table: ResponseTable) -> StreamingHttpResponse:
    """The table as CSV, streamed, with the columns that were on screen."""
    name = f"{table.version.questionnaire.key}-responses.csv" if table.version else "responses.csv"
    response = StreamingHttpResponse(
        csv_rows(table.queryset, table.selected), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


def export_queryset(
    queryset: QuerySet[QuestionnaireResponse], version: QuestionnaireVersion | None = None
) -> StreamingHttpResponse:
    """The CSV of an arbitrary selection, for the changelist action."""
    if version is None:
        versions = {response.questionnaire_version_id for response in queryset}
        version = (
            QuestionnaireVersion.objects.filter(pk=versions.pop()).first()
            if len(versions) == 1
            else None
        )
    columns = columns_for(version)
    response = StreamingHttpResponse(
        csv_rows(queryset, columns), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = 'attachment; filename="responses.csv"'
    return response


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["GLOBAL_CHOICE", "ResponseTable", "export", "export_queryset"]
