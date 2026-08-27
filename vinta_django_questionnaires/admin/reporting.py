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

from vinta_django_questionnaires.models import QuestionnaireVersion, ResponseStatus
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

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest

    from vinta_django_questionnaires.models import QuestionnaireResponse

#: The query parameter each control writes into the URL, so a filtered table is
#: a link someone can send to a colleague.
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
        self.questionnaire = request.GET.get(QUESTIONNAIRE, "")
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
        if not self.questionnaire:
            return None
        versions = QuestionnaireVersion.objects.filter(questionnaire__key=self.questionnaire)
        if self.version_number is not None:
            return versions.filter(version=self.version_number).first()
        return versions.order_by("-version").first()

    def _selected(self) -> list[Column]:
        asked = [key for key in self.request.GET.get(COLUMNS, "").split(",") if key]
        return select_columns(self.available, asked or default_columns(self.version))

    def _queryset(self) -> QuerySet[QuestionnaireResponse]:
        return response_queryset(
            questionnaire=self.questionnaire,
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
    def questionnaires(self) -> list[dict[str, Any]]:
        from vinta_django_questionnaires.models import Questionnaire

        return [
            {"key": entry.key, "name": str(entry), "selected": entry.key == self.questionnaire}
            for entry in Questionnaire.objects.all()
        ]

    def versions(self) -> list[dict[str, Any]]:
        if not self.questionnaire:
            return []
        return [
            {
                "version": entry.version,
                "label": f"v{entry.version} ({entry.status})",
                "selected": entry.version == self.version_number,
            }
            for entry in QuestionnaireVersion.objects.filter(
                questionnaire__key=self.questionnaire
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
    name = f"{table.questionnaire}-responses.csv" if table.questionnaire else "responses.csv"
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


__all__ = ["ResponseTable", "export", "export_queryset"]
