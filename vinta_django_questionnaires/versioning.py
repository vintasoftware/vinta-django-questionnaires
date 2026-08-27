"""Making a new version out of an existing one.

Every page, section and question belongs to exactly one version, so a new
version is a deep copy rather than a reference.  That is the point: a version
that has been answered can then never change under those answers, whatever
happens to the next draft.

The copy is cheap -- a large questionnaire is a few hundred small rows -- and
question keys are carried over unchanged, so answers stay comparable from one
version to the next.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from vinta_django_questionnaires.models import QuestionnaireVersion, VersionStatus

if TYPE_CHECKING:
    from django.db.models import Model

    from vinta_django_questionnaires.models import Question, Section, WindowSizeRange


def _copy(instance: Model, **overrides: Any) -> Any:
    """A detached copy of *instance*, ready to be saved as a new row."""
    fields = {
        field.name: getattr(instance, field.attname)
        for field in instance._meta.concrete_fields
        if field.name not in {"id", "created_at", "updated_at"}
    }
    # Foreign keys were read as ids, so hand them back as ids.
    values = {
        (f"{name}_id" if instance._meta.get_field(name).is_relation else name): value
        for name, value in fields.items()
    }
    return type(instance)(**{**values, **overrides})


@transaction.atomic
def new_version_from(
    version: QuestionnaireVersion,
    *,
    version_number: int | None = None,
    status: str = VersionStatus.DRAFT,
    **overrides: Any,
) -> QuestionnaireVersion:
    """Copy *version* into a new draft of the same questionnaire.

    Everything that makes up the definition comes along: window size ranges,
    the column counts every layer sets, pages, sections, questions, their
    choices and their validators.  What a question points *at* -- a widget, a
    value set, a nested questionnaire -- is shared, because those are their own
    records with their own lifecycle.

    Responses stay with the version they were given to.
    """
    draft = _copy(
        version,
        version=version_number or version.questionnaire.next_version_number(),
        status=status,
        published_at=None,
        **overrides,
    )
    draft = _saved_version(draft)

    ranges = {
        original.pk: _saved(_copy(original, questionnaire_version_id=draft.pk))
        for original in version.window_size_ranges.all()
    }
    _copy_layer_columns(version.layer_columns.all(), ranges, questionnaire_version_id=draft.pk)

    for page in version.pages.all():
        new_page = _saved(_copy(page, questionnaire_version_id=draft.pk))
        _copy_layer_columns(page.layer_columns.all(), ranges, page_id=new_page.pk)

        for section in page.sections.all():
            new_section = _saved(_copy(section, page_id=new_page.pk))
            _copy_layer_columns(section.layer_columns.all(), ranges, section_id=new_section.pk)

            for question in section.questions.all():
                _copy_question(question, new_section, ranges)

    return draft


def _saved(instance: Any) -> Any:
    instance.save()
    return instance


def _saved_version(instance: Any) -> QuestionnaireVersion:
    instance.save()
    return instance  # type: ignore[no-any-return]


def _copy_layer_columns(entries: Any, ranges: dict[int, WindowSizeRange], **owner: Any) -> None:
    """Copy a layer's column counts, repointing them at the new version's ranges."""
    for entry in entries:
        overrides: dict[str, Any] = {
            "questionnaire_version_id": None,
            "page_id": None,
            "section_id": None,
            "window_size_range_id": ranges[entry.window_size_range_id].pk,
            **owner,
        }
        _saved(_copy(entry, **overrides))


def _copy_question(
    question: Question, section: Section, ranges: dict[int, WindowSizeRange]
) -> None:
    new_question = _saved(_copy(question, section_id=section.pk))
    for choice in question.choices.all():
        _saved(_copy(choice, question_id=new_question.pk))
    for binding in question.validators.all():
        _saved(_copy(binding, question_id=new_question.pk))
    for minimum in question.minimum_columns.all():
        _saved(
            _copy(
                minimum,
                question_id=new_question.pk,
                window_size_range_id=ranges[minimum.window_size_range_id].pk,
            )
        )


__all__ = ["new_version_from"]
