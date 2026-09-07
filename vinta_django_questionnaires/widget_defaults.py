"""The widget set the package ships, and what each one's props are.

A widget is a row: a key, the JSON Schema its props must satisfy, and which
question types it can render.  Nothing here is required -- a project can define
its own set and never touch this one -- but every installation needs *some* set
before a question can name a widget, and inventing one from scratch is a poor
first task.

The keys are the ones the TypeScript client registers a component for, so
installing these makes a questionnaire render with no front-end work at all,
and a project replaces any of them by registering its own component under the
same key.

Installed with ``manage.py install_default_widgets``; the constant is public so
a project can start from it and edit rather than copy it out of the docs.
"""

from __future__ import annotations

from typing import Any, TypedDict

from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.question_types import QuestionType


class WidgetSpec(TypedDict, total=False):
    """One widget, and the question types it renders."""

    key: str
    name: Any
    description: Any
    props_schema: dict[str, Any]
    default_props: dict[str, Any]
    #: ``(question type, is the default for it)`` pairs.
    question_types: list[tuple[str, bool]]


def _schema(**properties: Any) -> dict[str, Any]:
    """An object schema that accepts exactly *properties* and nothing else.

    Closed on purpose: a prop the component does not read is a typo far more
    often than an extension, and a widget's props are checked on every save,
    which is the cheapest place to find one.
    """
    return {"type": "object", "properties": properties, "additionalProperties": False}


_TEXTISH = _schema(
    placeholder={"type": "string"},
    type={"enum": ["text", "email", "url", "tel"]},
    autoComplete={"type": "string"},
)

_NUMERIC = _schema(
    prefix={"type": "string"},
    suffix={"type": "string"},
    step={"type": "number"},
    min={"type": "number"},
    max={"type": "number"},
)

_RANGE = _schema(startLabel={"type": "string"}, endLabel={"type": "string"})

_REPEATER = _schema(addLabel={"type": "string"}, maxEntries={"type": "integer", "minimum": 1})


#: The widgets ``install_default_widgets`` creates.
DEFAULT_WIDGETS: list[WidgetSpec] = [
    {
        "key": "input",
        "name": _("Text field"),
        "description": _("A single line of text."),
        "props_schema": _TEXTISH,
        "question_types": [(QuestionType.FREE_TEXT, True), (QuestionType.URL, True)],
    },
    {
        "key": "textarea",
        "name": _("Text area"),
        "description": _("Several lines of text."),
        "props_schema": _schema(
            rows={"type": "integer", "minimum": 2, "maximum": 20},
            placeholder={"type": "string"},
        ),
        "default_props": {"rows": 4},
        "question_types": [(QuestionType.FREE_TEXT, False)],
    },
    {
        "key": "number-input",
        "name": _("Number field"),
        "description": _("A number, with an optional prefix and step."),
        "props_schema": _NUMERIC,
        "question_types": [
            (QuestionType.NUMBER, True),
            (QuestionType.YEAR, True),
            (QuestionType.TIME_DURATION, True),
        ],
    },
    {
        "key": "radio-group",
        "name": _("Radio group"),
        "description": _("Every choice on screen, one of them picked."),
        "props_schema": _schema(orientation={"enum": ["vertical", "horizontal"]}),
        "default_props": {"orientation": "vertical"},
        "question_types": [(QuestionType.SINGLE_CHOICE, True)],
    },
    {
        "key": "checkbox-group",
        "name": _("Checkbox group"),
        "description": _("Every choice on screen, any number of them picked."),
        "props_schema": _schema(columns={"type": "integer", "minimum": 1, "maximum": 4}),
        "default_props": {"columns": 1},
        "question_types": [(QuestionType.MULTIPLE_CHOICE, True)],
    },
    {
        "key": "select",
        "name": _("Dropdown"),
        "description": _("One choice, from a list that stays closed until opened."),
        "props_schema": _schema(placeholder={"type": "string"}),
        "question_types": [
            (QuestionType.SINGLE_SELECT, True),
            (QuestionType.SINGLE_CHOICE, False),
        ],
    },
    {
        "key": "multi-select",
        "name": _("Multiple dropdown"),
        "description": _("Any number of choices, from a list."),
        "props_schema": _schema(placeholder={"type": "string"}),
        "question_types": [
            (QuestionType.MULTI_SELECT, True),
            (QuestionType.MULTIPLE_CHOICE, False),
        ],
    },
    {
        "key": "date-input",
        "name": _("Date field"),
        "description": _("A date, a month or a moment, by the question's type."),
        "props_schema": _schema(),
        "question_types": [
            (QuestionType.DATE, True),
            (QuestionType.DATE_TIME, True),
            (QuestionType.MONTH, True),
        ],
    },
    {
        "key": "time-input",
        "name": _("Time field"),
        "description": _("A time of day."),
        "props_schema": _schema(),
        "question_types": [(QuestionType.TIME, True)],
    },
    {
        "key": "date-range",
        "name": _("Date range"),
        "description": _("Two dates, a start and an end."),
        "props_schema": _RANGE,
        "question_types": [
            (QuestionType.DATE_RANGE, True),
            (QuestionType.DATE_TIME_RANGE, True),
        ],
    },
    {
        "key": "number-range",
        "name": _("Number range"),
        "description": _("Two numbers, a low and a high."),
        "props_schema": _RANGE,
        "question_types": [(QuestionType.NUMBER_RANGE, True)],
    },
    {
        "key": "file-upload",
        "name": _("File field"),
        "description": _("One file, or several, by the question's type."),
        "props_schema": _schema(accept={"type": "string"}),
        "question_types": [
            (QuestionType.SINGLE_FILE, True),
            (QuestionType.MULTIPLE_FILES, True),
        ],
    },
    {
        "key": "matrix",
        "name": _("Matrix"),
        "description": _("A grid of checkboxes: the rows against the columns."),
        "props_schema": _schema(),
        "question_types": [(QuestionType.BINARY_MATRIX, True)],
    },
    {
        "key": "item-list",
        "name": _("List of items"),
        "description": _("The item type's own widget, repeated."),
        "props_schema": _REPEATER,
        "question_types": [(QuestionType.ITEM_LIST, True)],
    },
    {
        "key": "sub-questionnaire",
        "name": _("Nested questionnaire"),
        "description": _("Another questionnaire's questions, inline."),
        "props_schema": _schema(),
        "question_types": [(QuestionType.SUB_QUESTIONNAIRE, True)],
    },
    {
        "key": "repeatable-group",
        "name": _("Repeatable group"),
        "description": _("Another questionnaire's questions, once per entry."),
        "props_schema": _REPEATER,
        "question_types": [(QuestionType.SUB_QUESTIONNAIRE_LIST, True)],
    },
]


__all__ = ["DEFAULT_WIDGETS", "WidgetSpec"]
