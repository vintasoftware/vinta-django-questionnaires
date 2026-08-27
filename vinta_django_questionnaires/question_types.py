"""The question types the app knows how to describe, and what each one implies.

The ``QuestionType`` choices are what a ``Question`` stores.  The specs next to
them are what the model validates against: whether a type takes inline choices,
draws its options from a value set, accepts an "other" escape hatch, nests
another questionnaire, and so on.  Keeping that in a table means ``Question``
does not grow a branch per type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.utils.functional import Promise


class QuestionType(models.TextChoices):
    SINGLE_CHOICE = "single_choice", _("Single choice")
    MULTIPLE_CHOICE = "multiple_choice", _("Multiple choice")
    FREE_TEXT = "free_text", _("Free text")
    SINGLE_SELECT = "single_select", _("Single select from a value set")
    MULTI_SELECT = "multi_select", _("Multi select from a value set")
    NUMBER = "number", _("Number")
    NUMBER_RANGE = "number_range", _("Number range")
    TIME = "time", _("Time")
    DATE = "date", _("Date")
    DATE_TIME = "date_time", _("Date and time")
    MONTH = "month", _("Month")
    YEAR = "year", _("Year")
    DATE_RANGE = "date_range", _("Date range")
    DATE_TIME_RANGE = "date_time_range", _("Date and time range")
    TIME_DURATION = "time_duration", _("Time duration")
    URL = "url", _("URL")
    SINGLE_FILE = "single_file", _("Single file")
    MULTIPLE_FILES = "multiple_files", _("Multiple files")
    BINARY_MATRIX = "binary_matrix", _("Binary matrix of selections")
    ITEM_LIST = "item_list", _("List of items")
    SUB_QUESTIONNAIRE = "sub_questionnaire", _("Sub-questionnaire")
    SUB_QUESTIONNAIRE_LIST = "sub_questionnaire_list", _("List of sub-questionnaires")


class AnswerShape(models.TextChoices):
    """The shape of the answer a question type produces."""

    SCALAR = "scalar", _("Single value")
    LIST = "list", _("List of values")
    RANGE = "range", _("Object with a start and an end")
    MATRIX = "matrix", _("Mapping of row key to the list of selected columns")
    FILE = "file", _("File reference")
    FILE_LIST = "file_list", _("List of file references")
    OBJECT = "object", _("Nested answer set")
    OBJECT_LIST = "object_list", _("List of nested answer sets")


@dataclass(frozen=True)
class QuestionTypeSpec:
    """What a question type accepts, checked by ``Question.clean()``."""

    key: str
    answer_shape: str
    supports_choices: bool = False
    supports_value_set: bool = False
    supports_other_option: bool = False
    uses_matrix_axes: bool = False
    requires_item_type: bool = False
    requires_sub_questionnaire: bool = False

    @property
    def label(self) -> Promise | str:
        return QuestionType(self.key).label


def _spec(key: str, answer_shape: str, **kwargs: bool) -> QuestionTypeSpec:
    return QuestionTypeSpec(key=key, answer_shape=answer_shape, **kwargs)


QUESTION_TYPE_SPECS: dict[str, QuestionTypeSpec] = {
    spec.key: spec
    for spec in (
        _spec(
            QuestionType.SINGLE_CHOICE,
            AnswerShape.SCALAR,
            supports_choices=True,
            supports_value_set=True,
            supports_other_option=True,
        ),
        _spec(
            QuestionType.MULTIPLE_CHOICE,
            AnswerShape.LIST,
            supports_choices=True,
            supports_value_set=True,
            supports_other_option=True,
        ),
        _spec(QuestionType.FREE_TEXT, AnswerShape.SCALAR),
        _spec(QuestionType.SINGLE_SELECT, AnswerShape.SCALAR, supports_value_set=True),
        _spec(QuestionType.MULTI_SELECT, AnswerShape.LIST, supports_value_set=True),
        _spec(QuestionType.NUMBER, AnswerShape.SCALAR),
        _spec(QuestionType.NUMBER_RANGE, AnswerShape.RANGE),
        _spec(QuestionType.TIME, AnswerShape.SCALAR),
        _spec(QuestionType.DATE, AnswerShape.SCALAR),
        _spec(QuestionType.DATE_TIME, AnswerShape.SCALAR),
        _spec(QuestionType.MONTH, AnswerShape.SCALAR),
        _spec(QuestionType.YEAR, AnswerShape.SCALAR),
        _spec(QuestionType.DATE_RANGE, AnswerShape.RANGE),
        _spec(QuestionType.DATE_TIME_RANGE, AnswerShape.RANGE),
        _spec(QuestionType.TIME_DURATION, AnswerShape.SCALAR),
        _spec(QuestionType.URL, AnswerShape.SCALAR),
        _spec(QuestionType.SINGLE_FILE, AnswerShape.FILE),
        _spec(QuestionType.MULTIPLE_FILES, AnswerShape.FILE_LIST),
        _spec(
            QuestionType.BINARY_MATRIX,
            AnswerShape.MATRIX,
            supports_choices=True,
            uses_matrix_axes=True,
        ),
        _spec(QuestionType.ITEM_LIST, AnswerShape.LIST, requires_item_type=True),
        _spec(
            QuestionType.SUB_QUESTIONNAIRE,
            AnswerShape.OBJECT,
            requires_sub_questionnaire=True,
        ),
        _spec(
            QuestionType.SUB_QUESTIONNAIRE_LIST,
            AnswerShape.OBJECT_LIST,
            requires_sub_questionnaire=True,
        ),
    )
}

#: Types whose answer is a single value, and which an item list may repeat.
SCALAR_TYPES = frozenset(
    key for key, spec in QUESTION_TYPE_SPECS.items() if spec.answer_shape == AnswerShape.SCALAR
)
TEXTUAL_TYPES = frozenset({QuestionType.FREE_TEXT, QuestionType.URL})
NUMERIC_TYPES = frozenset({QuestionType.NUMBER, QuestionType.YEAR, QuestionType.TIME_DURATION})
TEMPORAL_TYPES = frozenset(
    {
        QuestionType.DATE,
        QuestionType.DATE_TIME,
        QuestionType.TIME,
        QuestionType.MONTH,
    }
)
RANGE_TYPES = frozenset(
    key for key, spec in QUESTION_TYPE_SPECS.items() if spec.answer_shape == AnswerShape.RANGE
)
FILE_TYPES = frozenset({QuestionType.SINGLE_FILE, QuestionType.MULTIPLE_FILES})
MULTI_VALUE_TYPES = frozenset(
    key
    for key, spec in QUESTION_TYPE_SPECS.items()
    if spec.answer_shape in {AnswerShape.LIST, AnswerShape.FILE_LIST, AnswerShape.OBJECT_LIST}
)
CHOICE_TYPES = frozenset(key for key, spec in QUESTION_TYPE_SPECS.items() if spec.supports_choices)
VALUE_SET_TYPES = frozenset(
    key for key, spec in QUESTION_TYPE_SPECS.items() if spec.supports_value_set
)
SUB_QUESTIONNAIRE_TYPES = frozenset(
    key for key, spec in QUESTION_TYPE_SPECS.items() if spec.requires_sub_questionnaire
)


def get_question_type_spec(question_type: str) -> QuestionTypeSpec:
    """Return the spec for *question_type*, raising ``KeyError`` if unknown."""
    return QUESTION_TYPE_SPECS[question_type]
