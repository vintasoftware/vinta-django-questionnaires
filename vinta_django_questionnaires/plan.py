"""The validation plan: what the server tells the browser to enforce.

The plan is the wire format between this package and its TypeScript client.
It carries everything needed to rebuild a question's validation as a Zod
schema -- the base type, the checks in order, the resolved messages -- and
nothing about how any of it is rendered.

Messages are resolved here, on the server, with overrides applied and
translations done.  The client never reimplements that precedence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vinta_django_questionnaires.question_types import get_question_type_spec

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from vinta_django_questionnaires.models import (
        Page,
        Question,
        QuestionnaireVersion,
        QuestionValidator,
        Section,
    )

#: Bumped when the shape below changes in a way clients must notice.
PLAN_VERSION = 1

#: How deep sub-questionnaires are expanded before the plan just references them.
MAX_NESTING_DEPTH = 5


def checks_for(bindings: Iterable[QuestionValidator]) -> tuple[list[dict[str, Any]], bool]:
    """The emitted checks of a validator chain, and whether it needs context."""
    checks: list[dict[str, Any]] = []
    uses_context = False
    for binding in bindings:
        validator = binding.build()
        checks.extend(validator.client_checks())
        uses_context = uses_context or validator.reads_context
    return checks, uses_context


def question_plan(
    question: Question,
    *,
    depth: int = 0,
    seen: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    """The plan for one question, expanding what it nests."""
    spec = get_question_type_spec(question.question_type)
    checks, uses_context = checks_for(question.validators.filter(is_enabled=True))
    plan: dict[str, Any] = {
        "key": question.key,
        "type": question.question_type,
        "title": question.title,
        "description": question.description,
        "condition": question.condition,
        "checks": checks,
        "usesContext": uses_context,
        "widget": question.resolved_widget.key if question.resolved_widget else None,
        "widgetProps": question.resolved_widget_props,
        "minimumColumns": question.minimum_column_layout(),
        "requiresBeingFirstInARow": question.requires_being_first_in_a_row,
        "requiresBeingLastInARow": question.requires_being_last_in_a_row,
    }
    if spec.requires_item_type:
        plan["itemType"] = question.item_question_type
    if spec.supports_choices and not spec.uses_matrix_axes:
        plan["choices"] = _choices(question, "option")
    if spec.supports_other_option:
        plan["allowsOther"] = question.allows_other
    if spec.uses_matrix_axes:
        plan["matrix"] = {
            "rows": _choices(question, "row"),
            "columns": _choices(question, "column"),
        }
    value_set = question.value_set if question.value_set_id else None
    if value_set is not None:
        plan["valueSet"] = {
            "key": value_set.key,
            "source": value_set.source,
            "resolvedByTheClient": value_set.is_resolved_by_the_client,
        }
    if spec.requires_sub_questionnaire:
        plan["subQuestionnaire"] = _sub_plan(question, depth=depth, seen=seen)
    return plan


def _choices(question: Question, axis: str) -> list[dict[str, Any]]:
    return [
        {"value": choice.value, "label": choice.label}
        for choice in question.choices.filter(axis=axis, is_active=True)
    ]


def _sub_plan(question: Question, *, depth: int, seen: frozenset[int]) -> dict[str, Any] | None:
    version = question.resolved_sub_questionnaire_version
    if version is None:
        return None
    if depth >= MAX_NESTING_DEPTH or version.pk in seen:
        # Deep or recursive nesting is referenced, not expanded: the client
        # fetches it when the respondent actually opens it.
        return {"ref": {"questionnaire": version.questionnaire.key, "version": version.version}}
    return questionnaire_plan(version, depth=depth + 1, seen=seen | {version.pk})


def section_plan(
    section: Section, *, depth: int = 0, seen: frozenset[int] = frozenset()
) -> dict[str, Any]:
    return {
        "key": section.key,
        "title": section.title,
        "description": section.description,
        "conclusion": section.conclusion,
        "defaultState": section.default_state,
        "condition": section.condition,
        "columns": section.column_layout(),
        "questions": [
            question_plan(question, depth=depth, seen=seen) for question in section.questions.all()
        ],
    }


def page_plan(page: Page, *, depth: int = 0, seen: frozenset[int] = frozenset()) -> dict[str, Any]:
    return {
        "key": page.key,
        "title": page.title,
        "description": page.description,
        "conclusion": page.conclusion,
        "condition": page.condition,
        "isSkippable": page.is_skippable,
        "columns": page.column_layout(),
        "sections": [
            section_plan(section, depth=depth, seen=seen) for section in page.sections.all()
        ],
    }


def questionnaire_plan(
    version: QuestionnaireVersion,
    *,
    depth: int = 0,
    seen: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    """The plan for a whole questionnaire version.

    Conditions travel with it, so the client can decide what to validate the
    same way the server does on save.
    """
    return {
        "planVersion": PLAN_VERSION,
        "questionnaire": version.questionnaire.key,
        "version": version.version,
        "title": version.title,
        "description": version.description,
        "windowSizeRanges": [
            {
                "key": window_size_range.key,
                "label": window_size_range.label,
                "minWidth": window_size_range.min_width,
                "maxWidth": window_size_range.max_width,
            }
            for window_size_range in version.window_size_ranges.all()
        ],
        "columns": version.column_layout(),
        "pages": [
            page_plan(page, depth=depth, seen=seen or frozenset({version.pk}))
            for page in version.pages.all()
        ],
    }


def standalone_plan(
    question_type: str,
    checks: Sequence[dict[str, Any]],
    *,
    key: str = "answer",
    uses_context: bool = False,
    item_type: str = "",
    choices: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A one-question plan, used by the conformance corpus."""
    plan: dict[str, Any] = {
        "key": key,
        "type": question_type,
        "condition": "",
        "checks": list(checks),
        "usesContext": uses_context,
    }
    if item_type:
        plan["itemType"] = item_type
    if choices is not None:
        plan["choices"] = list(choices)
    return plan
