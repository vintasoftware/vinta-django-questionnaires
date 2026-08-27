"""Responses as a table: what the columns are, and what goes in the cells.

A questionnaire's answers are a tree keyed by question, and a table is flat, so
something has to decide what the columns are.  That is the version: one column
per question it asks, in the order it asks them, plus the handful of things
about a response itself that anyone reading a table wants -- who, when, how far
they got.

The same column list drives the JSON listing and the CSV export, so what
someone sees on screen and what they download cannot drift apart.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models import (
    Answer,
    PageResponseStatus,
    QuestionnaireResponse,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from django.db.models import QuerySet
    from django.utils.functional import Promise

    from vinta_django_questionnaires.models import QuestionnaireVersion

#: How many rows a page of the listing holds unless asked otherwise.
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class Column:
    """One column of the table."""

    key: str
    #: Lazy where it is a translation of this package's own, plain where it is
    #: a question's title.
    label: str | Promise
    #: ``meta`` for something about the response, ``answer`` for a question.
    group: str
    #: Where the question sits, for grouping the column picker.
    page: str = ""
    section: str = ""
    question_type: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": str(self.label),
            "group": self.group,
            "page": self.page,
            "section": self.section,
            "questionType": self.question_type,
        }


#: The columns every response has, whatever it was answering.
META_COLUMNS: tuple[Column, ...] = (
    Column(key="id", label=_("Response"), group="meta"),
    Column(key="questionnaire", label=_("Questionnaire"), group="meta"),
    Column(key="version", label=_("Version"), group="meta"),
    Column(key="status", label=_("Status"), group="meta"),
    Column(key="respondent", label=_("Respondent"), group="meta"),
    Column(key="external_id", label=_("External id"), group="meta"),
    Column(key="progress", label=_("Pages answered"), group="meta"),
    Column(key="created_at", label=_("Started"), group="meta"),
    Column(key="completed_at", label=_("Completed"), group="meta"),
)

#: What the table shows before anyone picks anything.
DEFAULT_META_COLUMNS = ("id", "status", "respondent", "created_at", "completed_at")


def answer_columns(version: QuestionnaireVersion) -> list[Column]:
    """One column per question the version asks, in the order it asks them."""
    columns: list[Column] = []
    for page in version.pages.all():
        for section in page.sections.all():
            for question in section.questions.all():
                columns.append(
                    Column(
                        key=question.key,
                        label=question.title or question.key,
                        group="answer",
                        page=page.title or page.key,
                        section=section.title or section.key,
                        question_type=question.question_type,
                    )
                )
    return columns


def columns_for(version: QuestionnaireVersion | None) -> list[Column]:
    """Every column available for *version*, metadata first."""
    return [*META_COLUMNS, *(answer_columns(version) if version is not None else [])]


def default_columns(version: QuestionnaireVersion | None, *, answers: int = 8) -> list[str]:
    """A sensible first view: the useful metadata and the first few questions."""
    keys = list(DEFAULT_META_COLUMNS)
    if version is not None:
        keys.extend(column.key for column in answer_columns(version)[:answers])
    return keys


# ------------------------------------------------------------------- reading


def response_queryset(
    *,
    questionnaire: str = "",
    version: int | None = None,
    status: str = "",
    search: str = "",
) -> QuerySet[QuestionnaireResponse]:
    """The responses matching a filter, newest first."""
    queryset = QuestionnaireResponse.objects.select_related(
        "questionnaire_version__questionnaire", "respondent"
    ).prefetch_related("page_responses", "questionnaire_version__pages")
    if questionnaire:
        queryset = queryset.filter(questionnaire_version__questionnaire__key=questionnaire)
    if version is not None:
        queryset = queryset.filter(questionnaire_version__version=version)
    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(
            Q(external_id__icontains=search) | Q(respondent__username__icontains=search)
        )
    return queryset.order_by("-created_at", "-pk")


def answers_for(responses: Sequence[QuestionnaireResponse]) -> dict[int, dict[str, Any]]:
    """Every response's answers, in one query rather than one each.

    ``QuestionnaireResponse.answers`` is right and convenient and would run a
    query per row; a table of fifty rows is exactly where that matters.
    """
    if not responses:
        return {}
    rows = (
        Answer.objects.filter(
            response__in=responses, page_response__status=PageResponseStatus.COMPLETED
        )
        .select_related("question")
        .order_by("question__section__page__order", "question__order")
    )
    collected: dict[int, dict[str, Any]] = {response.pk: {} for response in responses}
    for answer in rows:
        collected.setdefault(answer.response_id, {})[answer.question.key] = answer.value
    return collected


def pages_answered(response: QuestionnaireResponse) -> str:
    """How far through the response got, as `answered/total`.

    Deliberately not ``response.progress()``, which is right and costs a walk
    over every condition: a table of fifty rows would pay for it fifty times.
    This counts what is recorded, off the prefetched rows, and says so in the
    column's label.
    """
    answered = sum(
        1
        for entry in response.page_responses.all()
        if entry.status == PageResponseStatus.COMPLETED
    )
    return f"{answered}/{len(response.questionnaire_version.pages.all())}"


def row_for(
    response: QuestionnaireResponse, answers: dict[str, Any], columns: Sequence[Column]
) -> dict[str, Any]:
    """One response as a mapping of column key to value."""
    meta: dict[str, Any] = {
        "id": str(response.uuid),
        "questionnaire": response.questionnaire_version.questionnaire.key,
        "version": response.questionnaire_version.version,
        "status": response.status,
        "respondent": _respondent_name(response),
        "external_id": response.external_id,
        "progress": pages_answered(response),
        "created_at": response.created_at.isoformat() if response.created_at else None,
        "completed_at": response.completed_at.isoformat() if response.completed_at else None,
    }
    return {
        column.key: (meta.get(column.key) if column.group == "meta" else answers.get(column.key))
        for column in columns
    }


def _respondent_name(response: QuestionnaireResponse) -> str:
    user = response.respondent if response.respondent_id else None
    return user.get_username() if user is not None else ""


def rows_for(
    responses: Sequence[QuestionnaireResponse], columns: Sequence[Column]
) -> list[dict[str, Any]]:
    collected = answers_for(responses)
    return [row_for(response, collected.get(response.pk, {}), columns) for response in responses]


def select_columns(available: Sequence[Column], requested: Iterable[str] | None) -> list[Column]:
    """The requested columns, in the order asked for, ignoring unknown ones."""
    requested = list(requested or [])
    if not requested:
        return list(available)
    by_key = {column.key: column for column in available}
    return [by_key[key] for key in requested if key in by_key]


# --------------------------------------------------------------------- CSV


def as_cell(value: Any) -> str:
    """One value as a string a spreadsheet can hold.

    A matrix answer or a list of files has no flat form, so it goes in as the
    JSON it already is rather than as ``[object Object]``.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, list) and all(isinstance(entry, (str, int, float)) for entry in value):
        return ", ".join(str(entry) for entry in value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def csv_rows(
    queryset: QuerySet[QuestionnaireResponse],
    columns: Sequence[Column],
    *,
    chunk_size: int = 200,
) -> Iterator[str]:
    """The whole export, a line at a time, so a big one does not sit in memory."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def flush() -> str:
        value = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return value

    writer.writerow([str(column.label) for column in columns])
    yield flush()

    batch: list[QuestionnaireResponse] = []
    for response in queryset.iterator(chunk_size=chunk_size):
        batch.append(response)
        if len(batch) >= chunk_size:
            for row in rows_for(batch, columns):
                writer.writerow([as_cell(row.get(column.key)) for column in columns])
            batch = []
            yield flush()
    if batch:
        for row in rows_for(batch, columns):
            writer.writerow([as_cell(row.get(column.key)) for column in columns])
        yield flush()


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "META_COLUMNS",
    "Column",
    "answer_columns",
    "as_cell",
    "columns_for",
    "csv_rows",
    "default_columns",
    "pages_answered",
    "response_queryset",
    "rows_for",
    "select_columns",
]
