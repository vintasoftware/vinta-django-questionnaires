"""What an editor may offer: the question types, validators and widgets there are.

A definition document says a question is a ``single_choice`` rendered by the
``select`` widget and checked by ``min_length``.  For someone to *author* that,
the editor has to know which types exist, which validators apply to each of
them, what params each validator takes and what a widget's props schema is --
none of which is in the document.

That is this: one payload, read once when the editor opens.  It is derived from
the registry and the database rather than written down anywhere, so a validator
another app registers shows up in the editor without this package knowing about
it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vinta_django_questionnaires.models import (
    DEFAULT_COLUMN_COUNT,
    ChoiceAxis,
    EditPolicy,
    Questionnaire,
    QuestionnaireWidget,
    SectionState,
    ValueSet,
    VersionStatus,
)
from vinta_django_questionnaires.question_types import (
    QUESTION_TYPE_SPECS,
    SCALAR_TYPES,
    QuestionType,
)
from vinta_django_questionnaires.validators import registry

if TYPE_CHECKING:
    from vinta_django_questionnaires.validators import BaseValidator

#: Bumped when the shape below changes in a way the editor must notice.
CATALOG_VERSION = 1


def _choices(enum: Any) -> list[dict[str, str]]:
    return [{"value": value, "label": str(label)} for value, label in enum.choices]


def question_type_catalog() -> list[dict[str, Any]]:
    """Every question type, with what it accepts."""
    return [
        {
            "key": key,
            "label": str(QuestionType(key).label),
            "answerShape": spec.answer_shape,
            "supportsChoices": spec.supports_choices,
            "supportsValueSet": spec.supports_value_set,
            "supportsOtherOption": spec.supports_other_option,
            "usesMatrixAxes": spec.uses_matrix_axes,
            "requiresItemType": spec.requires_item_type,
            "requiresSubQuestionnaire": spec.requires_sub_questionnaire,
        }
        for key, spec in QUESTION_TYPE_SPECS.items()
    ]


def validator_catalog() -> list[dict[str, Any]]:
    """Every registered validator, including the ones other apps added."""
    return [_validator_entry(key, validator) for key, validator in registry.items()]


def _validator_entry(key: str, validator: type[BaseValidator]) -> dict[str, Any]:
    return {
        "key": key,
        "label": str(validator.label or key),
        "description": str(validator.__doc__ or "").strip().split("\n")[0],
        "paramsSchema": dict(validator.params_schema),
        "errorKeys": [
            {"key": error_key, "message": str(message)}
            for error_key, message in validator.error_messages.items()
        ],
        # ``None`` means every type, which the editor reads as "no restriction".
        "questionTypes": (
            sorted(validator.supported_question_types)
            if validator.supported_question_types is not None
            else None
        ),
        "clientMode": validator.client.mode,
        "skipWhenEmpty": validator.skip_when_empty,
        "readsContext": validator.reads_context,
    }


def widget_catalog() -> list[dict[str, Any]]:
    """Every active widget, with the props schema its component takes."""
    widgets = QuestionnaireWidget.objects.filter(is_active=True).prefetch_related(
        "question_type_supports"
    )
    return [
        {
            "key": widget.key,
            "name": widget.name,
            "description": widget.description,
            "component": widget.component or widget.key,
            "propsSchema": dict(widget.props_schema or {}),
            "defaultProps": dict(widget.default_props or {}),
            "questionTypes": sorted(
                support.question_type for support in widget.question_type_supports.all()
            ),
            "defaultForQuestionTypes": sorted(
                support.question_type
                for support in widget.question_type_supports.all()
                if support.is_default
            ),
        }
        for widget in widgets
    ]


def value_set_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": value_set.key,
            "name": value_set.name,
            "description": value_set.description,
            "source": value_set.source,
            "resolvedByTheClient": value_set.is_resolved_by_the_client,
        }
        for value_set in ValueSet.objects.all()
    ]


def questionnaire_catalog() -> list[dict[str, Any]]:
    """The questionnaires a question could nest, and their versions."""
    return [
        {
            "key": questionnaire.key,
            "name": questionnaire.name,
            "versions": [
                {
                    "version": version.version,
                    "title": version.title,
                    "status": version.status,
                }
                for version in questionnaire.versions.all()
            ],
        }
        for questionnaire in Questionnaire.objects.filter(is_active=True).prefetch_related(
            "versions"
        )
    ]


def editor_catalog() -> dict[str, Any]:
    """Everything an editor needs to offer choices, in one payload."""
    return {
        "catalogVersion": CATALOG_VERSION,
        "defaultColumnCount": DEFAULT_COLUMN_COUNT,
        "questionTypes": question_type_catalog(),
        "scalarQuestionTypes": sorted(SCALAR_TYPES),
        "validators": validator_catalog(),
        "widgets": widget_catalog(),
        "valueSets": value_set_catalog(),
        "questionnaires": questionnaire_catalog(),
        "choiceAxes": _choices(ChoiceAxis),
        "sectionStates": _choices(SectionState),
        "versionStatuses": _choices(VersionStatus),
        "editPolicies": _choices(EditPolicy),
    }


__all__ = [
    "CATALOG_VERSION",
    "editor_catalog",
    "question_type_catalog",
    "questionnaire_catalog",
    "validator_catalog",
    "value_set_catalog",
    "widget_catalog",
]
