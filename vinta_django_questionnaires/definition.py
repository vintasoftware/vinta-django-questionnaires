"""The editable document of a questionnaire version, and how to write it back.

The validation plan is what a *respondent's* browser needs: resolved, flattened,
and lossy on purpose.  This is the other direction -- what an *author* needs to
see and change, in the shape the React editor under ``client/`` reads and sends
back.

Two things it does differently from the plan.  Column counts are the ones each
layer *declares*, not the ones it resolves to, so a round trip does not
materialise inherited values all the way down.  And widgets, value sets and
sub-questionnaires appear as the author set them -- empty where the author left
the default -- with what the server resolved alongside, for display only.

Keys are identity.  A page, section, question or choice is matched to what is
stored by its key, so renaming one is a delete and a create rather than a
rename: answers are keyed by question key, and pretending otherwise would
quietly reattach them to a different question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.editing import acknowledged_edit
from vinta_django_questionnaires.models import (
    LayerColumns,
    Page,
    Question,
    QuestionChoice,
    QuestionMinimumColumns,
    Questionnaire,
    QuestionnaireVersion,
    QuestionnaireWidget,
    QuestionValidator,
    Section,
    ValueSet,
    WindowSizeRange,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from django.db.models import Model

    from vinta_django_questionnaires.editing import Acknowledgement
    from vinta_django_questionnaires.models import LayerMixin

#: Bumped when the shape below changes in a way the editor must notice.
DOCUMENT_VERSION = 1

#: Where a non-field error is reported, matching ``ValidationError.NON_FIELD_ERRORS``.
NON_FIELD = "__all__"


# ---------------------------------------------------------------- reporting


@dataclass(frozen=True)
class DefinitionIssue:
    """One node of the document the server would not accept.

    ``path`` addresses the node the way the editor addresses it --
    ``pages.0.sections.1.questions.2`` -- so a failure lands on the field that
    caused it rather than at the top of the form.
    """

    path: str
    errors: dict[str, list[str]]

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "errors": self.errors}


class DefinitionError(Exception):
    """Raised when a document does not apply.  Nothing is written."""

    def __init__(self, issues: Sequence[DefinitionIssue]) -> None:
        super().__init__(_("The questionnaire definition was not accepted."))
        self.issues = list(issues)

    def as_dict(self) -> dict[str, Any]:
        return {"issues": [issue.as_dict() for issue in self.issues]}


def _messages(error: ValidationError) -> dict[str, list[str]]:
    """A ``ValidationError`` as plain lists of strings, keyed by field."""
    if hasattr(error, "error_dict"):
        return {
            field: [str(message) for message in messages]
            for field, messages in error.message_dict.items()
        }
    return {NON_FIELD: [str(message) for message in error.messages]}


# ------------------------------------------------------------------ reading


def _declared_columns(layer: LayerMixin) -> dict[str, int]:
    """The column counts this layer sets itself, not the ones it inherits."""
    if layer.pk is None or not layer.layer_field:
        return {}
    entries = LayerColumns.objects.filter(**{layer.layer_field: layer}).select_related(
        "window_size_range"
    )
    return {entry.window_size_range.key: entry.columns for entry in entries}


def _choice_document(choice: QuestionChoice) -> dict[str, Any]:
    return {
        "axis": choice.axis,
        "value": choice.value,
        "label": choice.label,
        "extra": dict(choice.extra or {}),
        "isActive": choice.is_active,
    }


def _validator_document(binding: QuestionValidator) -> dict[str, Any]:
    return {
        "validator": binding.validator,
        "params": dict(binding.params or {}),
        "messageOverrides": dict(binding.message_overrides or {}),
        "isEnabled": binding.is_enabled,
    }


def question_document(question: Question) -> dict[str, Any]:
    """One question, as its author configured it."""
    resolved_widget = question.resolved_widget
    widget = question.widget if question.widget_id else None
    value_set = question.value_set if question.value_set_id else None
    nested = question.sub_questionnaire if question.sub_questionnaire_id else None
    pinned = question.sub_questionnaire_version if question.sub_questionnaire_version_id else None
    return {
        "key": question.key,
        "title": question.title,
        "description": question.description,
        "questionType": question.question_type,
        "itemQuestionType": question.item_question_type,
        "condition": question.condition,
        "requiresBeingFirstInARow": question.requires_being_first_in_a_row,
        "requiresBeingLastInARow": question.requires_being_last_in_a_row,
        "minimumColumns": {
            entry.window_size_range.key: entry.minimum_columns
            for entry in question.minimum_columns.select_related("window_size_range")
        },
        "widget": widget.key if widget else None,
        "widgetProps": dict(question.widget_props or {}),
        "allowsOther": question.allows_other,
        "otherLabel": question.other_label,
        "valueSet": value_set.key if value_set else None,
        "subQuestionnaire": nested.key if nested else None,
        "subQuestionnaireVersion": pinned.version if pinned else None,
        "choices": [_choice_document(choice) for choice in question.choices.all()],
        "validators": [_validator_document(binding) for binding in question.validators.all()],
        # Read-only, for the editor to show what the defaults resolved to.
        "resolved": {
            "widget": resolved_widget.key if resolved_widget else None,
            "fingerprint": question.content_fingerprint,
        },
    }


def section_document(section: Section) -> dict[str, Any]:
    return {
        "key": section.key,
        "title": section.title,
        "description": section.description,
        "conclusion": section.conclusion,
        "defaultState": section.default_state,
        "condition": section.condition,
        "columns": _declared_columns(section),
        "questions": [question_document(question) for question in section.questions.all()],
    }


def page_document(page: Page) -> dict[str, Any]:
    return {
        "key": page.key,
        "title": page.title,
        "description": page.description,
        "conclusion": page.conclusion,
        "condition": page.condition,
        "isSkippable": page.is_skippable,
        "columns": _declared_columns(page),
        "sections": [section_document(section) for section in page.sections.all()],
    }


def definition_document(version: QuestionnaireVersion) -> dict[str, Any]:
    """The whole version, as an editable document."""
    response_count = version.responses.count()
    return {
        "documentVersion": DOCUMENT_VERSION,
        "questionnaire": {
            "key": version.questionnaire.key,
            "name": version.questionnaire.name,
        },
        "version": version.version,
        "title": version.title,
        "description": version.description,
        "status": version.status,
        "editPolicy": version.edit_policy,
        "responsesDueAt": (
            version.responses_due_at.isoformat() if version.responses_due_at else None
        ),
        "editsDueAt": version.edits_due_at.isoformat() if version.edits_due_at else None,
        "windowSizeRanges": [
            {
                "key": window_size_range.key,
                "label": window_size_range.label,
                "minWidth": window_size_range.min_width,
                "maxWidth": window_size_range.max_width,
            }
            for window_size_range in version.window_size_ranges.all()
        ],
        "columns": _declared_columns(version),
        "pages": [page_document(page) for page in version.pages.all()],
        # Read-only: what makes an edit here consequential.
        "state": {
            "responseCount": response_count,
            "requiresAcknowledgement": response_count > 0,
            "isPublished": version.is_published,
            "fingerprint": version.content_fingerprint,
        },
    }


# ------------------------------------------------------------------ writing


def _text(node: Any, key: str, default: str = "") -> str:
    value = node.get(key, default)
    return default if value is None else str(value)


def _flag(node: Any, key: str, *, default: bool = False) -> bool:
    return bool(node.get(key, default))


def _nodes(node: Any, key: str) -> list[dict[str, Any]]:
    value = node.get(key) or []
    return [entry for entry in value if isinstance(entry, dict)]


def _mapping(node: Any, key: str) -> dict[str, Any]:
    value = node.get(key)
    return dict(value) if isinstance(value, dict) else {}


@dataclass
class _Applier:
    """Walks a document against what is stored, node by node.

    Every node is validated before it is written, and a node that does not hold
    up is recorded and skipped along with its children, so one bad question does
    not hide the other nine.  Nothing survives the walk unless all of it did:
    the caller runs this inside a transaction it rolls back on any issue.
    """

    version: QuestionnaireVersion
    issues: list[DefinitionIssue] = field(default_factory=list)
    ranges: dict[str, WindowSizeRange] = field(default_factory=dict)

    # -- primitives --------------------------------------------------------
    def fail(self, path: str, errors: dict[str, list[str]]) -> None:
        self.issues.append(DefinitionIssue(path=path, errors=errors))

    def save(self, instance: Model, path: str) -> bool:
        """Write *instance*, recording why if it will not go."""
        try:
            instance.save()
        except ValidationError as exc:
            self.fail(path, _messages(exc))
            return False
        return True

    def remove(self, instances: Iterable[Model], path: str) -> None:
        for instance in instances:
            try:
                instance.delete()
            except ValidationError as exc:
                self.fail(path, _messages(exc))

    def lookup(
        self, model: type[Model], value: Any, *, path: str, field_name: str, **filters: Any
    ) -> Any:
        """Resolve what the document names, reporting what it cannot find."""
        if value in (None, ""):
            return None
        instance = model._default_manager.filter(**filters).first()
        if instance is None:
            label = model._meta.verbose_name
            self.fail(
                path,
                {
                    field_name: [
                        str(
                            _("There is no %(model)s %(value)s.")
                            % {
                                "model": label,
                                "value": value,
                            }
                        )
                    ]
                },
            )
        return instance

    # -- the walk ----------------------------------------------------------
    def run(self, document: dict[str, Any]) -> None:
        self.apply_version(document)
        self.apply_ranges(_nodes(document, "windowSizeRanges"))
        self.apply_columns(self.version, _mapping(document, "columns"), "")
        self.apply_pages(_nodes(document, "pages"))

    def apply_version(self, document: dict[str, Any]) -> None:
        version = self.version
        version.title = _text(document, "title", version.title)
        version.description = _text(document, "description")
        if document.get("status"):
            version.status = str(document["status"])
        if document.get("editPolicy"):
            version.edit_policy = str(document["editPolicy"])
        version.responses_due_at = self.moment(document.get("responsesDueAt"), "responsesDueAt")
        version.edits_due_at = self.moment(document.get("editsDueAt"), "editsDueAt")
        self.save(version, "")

    def moment(self, value: Any, field_name: str) -> Any:
        if not value:
            return None
        parsed = parse_datetime(str(value))
        if parsed is None:
            self.fail("", {field_name: [str(_("This is not a date and time."))]})
        return parsed

    def apply_ranges(self, nodes: list[dict[str, Any]]) -> None:
        stored = {entry.key: entry for entry in self.version.window_size_ranges.all()}
        keys = {_text(node, "key") for node in nodes}
        self.remove(
            (entry for key, entry in stored.items() if key not in keys), "windowSizeRanges"
        )
        for index, node in enumerate(nodes):
            path = f"windowSizeRanges.{index}"
            key = _text(node, "key")
            entry = stored.get(key) or WindowSizeRange(questionnaire_version=self.version, key=key)
            entry.label = _text(node, "label")
            entry.min_width = int(node.get("minWidth") or 0)
            maximum = node.get("maxWidth")
            entry.max_width = int(maximum) if maximum not in (None, "") else None
            entry.order = index
            if self.save(entry, path):
                self.ranges[entry.key] = entry

    def apply_columns(self, layer: LayerMixin, mapping: dict[str, Any], parent: str) -> None:
        """The column counts one layer declares, keyed by window size range."""
        if layer.pk is None:
            return
        path = f"{parent}.columns" if parent else "columns"
        stored = {
            entry.window_size_range.key: entry
            for entry in LayerColumns.objects.filter(**{layer.layer_field: layer}).select_related(
                "window_size_range"
            )
        }
        self.remove((entry for key, entry in stored.items() if key not in mapping), path)
        for key, columns in mapping.items():
            window_size_range = self.ranges.get(key)
            if window_size_range is None:
                self.fail(path, {key: [str(_("There is no window size range with this key."))]})
                continue
            entry = stored.get(key) or LayerColumns(
                window_size_range=window_size_range, **{layer.layer_field: layer}
            )
            entry.columns = int(columns or 0)
            self.save(entry, path)

    def apply_pages(self, nodes: list[dict[str, Any]]) -> None:
        stored = {page.key: page for page in self.version.pages.all()}
        keys = {_text(node, "key") for node in nodes}
        self.remove((page for key, page in stored.items() if key not in keys), "pages")
        for index, node in enumerate(nodes):
            path = f"pages.{index}"
            key = _text(node, "key")
            page = stored.get(key) or Page(questionnaire_version=self.version, key=key)
            page.title = _text(node, "title")
            page.description = _text(node, "description")
            page.conclusion = _text(node, "conclusion")
            page.condition = _text(node, "condition")
            page.is_skippable = _flag(node, "isSkippable")
            page.order = index
            if not self.save(page, path):
                continue
            self.apply_columns(page, _mapping(node, "columns"), path)
            self.apply_sections(page, _nodes(node, "sections"), path)

    def apply_sections(self, page: Page, nodes: list[dict[str, Any]], parent: str) -> None:
        stored = {section.key: section for section in page.sections.all()}
        keys = {_text(node, "key") for node in nodes}
        self.remove(
            (section for key, section in stored.items() if key not in keys), f"{parent}.sections"
        )
        for index, node in enumerate(nodes):
            path = f"{parent}.sections.{index}"
            key = _text(node, "key")
            section = stored.get(key) or Section(page=page, key=key)
            section.title = _text(node, "title")
            section.description = _text(node, "description")
            section.conclusion = _text(node, "conclusion")
            section.condition = _text(node, "condition")
            if node.get("defaultState"):
                section.default_state = str(node["defaultState"])
            section.order = index
            if not self.save(section, path):
                continue
            self.apply_columns(section, _mapping(node, "columns"), path)
            self.apply_questions(section, _nodes(node, "questions"), path)

    def apply_questions(self, section: Section, nodes: list[dict[str, Any]], parent: str) -> None:
        stored = {question.key: question for question in section.questions.all()}
        keys = {_text(node, "key") for node in nodes}
        self.remove(
            (question for key, question in stored.items() if key not in keys),
            f"{parent}.questions",
        )
        for index, node in enumerate(nodes):
            path = f"{parent}.questions.{index}"
            question = stored.get(_text(node, "key"))
            # Choices and validators are checked against the question's *stored*
            # type, so the ones being dropped have to go before the type changes
            # under them -- and the ones being added, after.
            if question is not None:
                self.prune_choices(question, _nodes(node, "choices"), path)
                self.prune_validators(question, _nodes(node, "validators"), path)
            question = question or Question(section=section, key=_text(node, "key"))
            if not self.apply_question_fields(question, node, index, path):
                continue
            self.apply_minimum_columns(question, _mapping(node, "minimumColumns"), path)
            self.apply_choices(question, _nodes(node, "choices"), path)
            self.apply_validators(question, _nodes(node, "validators"), path)

    def apply_question_fields(
        self, question: Question, node: dict[str, Any], index: int, path: str
    ) -> bool:
        question.title = _text(node, "title")
        question.description = _text(node, "description")
        question.question_type = _text(node, "questionType")
        question.item_question_type = _text(node, "itemQuestionType")
        question.condition = _text(node, "condition")
        question.requires_being_first_in_a_row = _flag(node, "requiresBeingFirstInARow")
        question.requires_being_last_in_a_row = _flag(node, "requiresBeingLastInARow")
        question.widget_props = _mapping(node, "widgetProps")
        question.allows_other = _flag(node, "allowsOther")
        question.other_label = _text(node, "otherLabel")
        question.order = index

        before = len(self.issues)
        widget_key = node.get("widget")
        question.widget = self.lookup(
            QuestionnaireWidget, widget_key, path=path, field_name="widget", key=widget_key
        )
        value_set_key = node.get("valueSet")
        question.value_set = self.lookup(
            ValueSet, value_set_key, path=path, field_name="valueSet", key=value_set_key
        )
        sub_key = node.get("subQuestionnaire")
        question.sub_questionnaire = self.lookup(
            Questionnaire, sub_key, path=path, field_name="subQuestionnaire", key=sub_key
        )
        sub_version = node.get("subQuestionnaireVersion")
        question.sub_questionnaire_version = None
        if question.sub_questionnaire_id and sub_version:
            question.sub_questionnaire_version = self.lookup(
                QuestionnaireVersion,
                sub_version,
                path=path,
                field_name="subQuestionnaireVersion",
                questionnaire=question.sub_questionnaire,
                version=sub_version,
            )
        if len(self.issues) != before:
            return False
        return self.save(question, path)

    def apply_minimum_columns(
        self, question: Question, mapping: dict[str, Any], path: str
    ) -> None:
        stored = {
            entry.window_size_range.key: entry
            for entry in question.minimum_columns.select_related("window_size_range")
        }
        self.remove(
            (entry for key, entry in stored.items() if key not in mapping),
            f"{path}.minimumColumns",
        )
        for key, columns in mapping.items():
            window_size_range = self.ranges.get(key)
            if window_size_range is None:
                self.fail(
                    f"{path}.minimumColumns",
                    {key: [str(_("There is no window size range with this key."))]},
                )
                continue
            entry = stored.get(key) or QuestionMinimumColumns(
                question=question, window_size_range=window_size_range
            )
            entry.minimum_columns = int(columns or 0)
            self.save(entry, f"{path}.minimumColumns")

    # -- choices and validators -------------------------------------------
    def prune_choices(self, question: Question, nodes: list[dict[str, Any]], path: str) -> None:
        wanted = {(_text(node, "axis", "option"), _text(node, "value")) for node in nodes}
        self.remove(
            (
                choice
                for choice in question.choices.all()
                if (choice.axis, choice.value) not in wanted
            ),
            f"{path}.choices",
        )

    def apply_choices(self, question: Question, nodes: list[dict[str, Any]], path: str) -> None:
        stored = {(choice.axis, choice.value): choice for choice in question.choices.all()}
        for index, node in enumerate(nodes):
            axis = _text(node, "axis", "option")
            value = _text(node, "value")
            choice = stored.get((axis, value)) or QuestionChoice(
                question=question, axis=axis, value=value
            )
            choice.label = _text(node, "label")
            choice.extra = _mapping(node, "extra")
            choice.is_active = _flag(node, "isActive", default=True)
            choice.order = index
            self.save(choice, f"{path}.choices.{index}")

    def prune_validators(self, question: Question, nodes: list[dict[str, Any]], path: str) -> None:
        # A chain has no key of its own, so a link is matched by position: the
        # tail beyond what the document sends is what goes.
        stored = list(question.validators.all())
        self.remove(stored[len(nodes) :], f"{path}.validators")

    def apply_validators(self, question: Question, nodes: list[dict[str, Any]], path: str) -> None:
        stored = list(question.validators.all())
        for index, node in enumerate(nodes):
            binding = (
                stored[index] if index < len(stored) else QuestionValidator(question=question)
            )
            binding.validator = _text(node, "validator")
            binding.params = _mapping(node, "params")
            binding.message_overrides = _mapping(node, "messageOverrides")
            binding.is_enabled = _flag(node, "isEnabled", default=True)
            binding.order = index
            self.save(binding, f"{path}.validators.{index}")


def apply_definition(
    version: QuestionnaireVersion,
    document: dict[str, Any],
    *,
    acknowledgement: Acknowledgement | None = None,
) -> QuestionnaireVersion:
    """Write *document* onto *version*, or write nothing at all.

    Deleting a page cascades to its sections and questions in the database, so
    what is recorded for it is one acknowledged edit against the page, not one
    per descendant.
    """
    if document.get("documentVersion", DOCUMENT_VERSION) != DOCUMENT_VERSION:
        raise DefinitionError(
            [
                DefinitionIssue(
                    path="",
                    errors={
                        "documentVersion": [
                            str(_("This editor speaks a different document version."))
                        ]
                    },
                )
            ]
        )
    named = document.get("questionnaire")
    key = named.get("key") if isinstance(named, dict) else named
    if key and key != version.questionnaire.key:
        raise DefinitionError(
            [
                DefinitionIssue(
                    path="",
                    errors={
                        "questionnaire": [str(_("This document is for another questionnaire."))]
                    },
                )
            ]
        )

    applier = _Applier(version=version)
    try:
        with transaction.atomic():
            with acknowledged_edit(
                user=acknowledgement.user if acknowledgement else None,
                reason=acknowledgement.reason if acknowledgement else "",
                understood=bool(acknowledgement),
            ):
                applier.run(document)
            if applier.issues:
                raise DefinitionError(applier.issues)
    except DefinitionError:
        version.refresh_from_db()
        raise
    return version


__all__ = [
    "DOCUMENT_VERSION",
    "DefinitionError",
    "DefinitionIssue",
    "apply_definition",
    "definition_document",
    "page_document",
    "question_document",
    "section_document",
]
