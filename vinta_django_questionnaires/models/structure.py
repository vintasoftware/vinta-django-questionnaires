"""The two layers between a questionnaire version and its questions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models.base import MARKDOWN_HELP, BaseModel, ConditionalMixin
from vinta_django_questionnaires.models.editing import VersionScopedModel
from vinta_django_questionnaires.models.layout import LayerMixin
from vinta_django_questionnaires.models.questionnaires import QuestionnaireVersion

if TYPE_CHECKING:
    from vinta_django_questionnaires.models.questions import Question


class SectionState(models.TextChoices):
    OPEN = "open", _("Open")
    CLOSED = "closed", _("Closed")


class Page(LayerMixin, ConditionalMixin, VersionScopedModel, BaseModel):
    """A page of a questionnaire version."""

    layer_field: ClassVar[str] = "page"

    questionnaire_version = models.ForeignKey(
        QuestionnaireVersion,
        on_delete=models.CASCADE,
        related_name="pages",
        verbose_name=_("questionnaire version"),
    )
    key = models.SlugField(_("key"), max_length=100, help_text=_("Unique within the version."))
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(
        _("description"), blank=True, default="", help_text=MARKDOWN_HELP
    )
    conclusion = models.TextField(_("conclusion"), blank=True, default="", help_text=MARKDOWN_HELP)
    is_skippable = models.BooleanField(
        _("is skippable"),
        default=False,
        help_text=_("Whether the respondent may leave this page for later and move on."),
    )
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("page")
        verbose_name_plural = _("pages")
        ordering = ["questionnaire_version", "order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["questionnaire_version", "key"], name="unique_page_key_per_version"
            )
        ]

    def __str__(self) -> str:
        return self.title or self.key

    # -- layout ------------------------------------------------------------
    def get_parent_layer(self) -> LayerMixin | None:
        return self.questionnaire_version if self.questionnaire_version_id else None

    def get_questionnaire_version(self) -> QuestionnaireVersion:
        return self.questionnaire_version

    def get_edited_version(self) -> QuestionnaireVersion | None:
        return self.questionnaire_version if self.questionnaire_version_id else None

    # -- run time ----------------------------------------------------------
    def applicable_sections(self, answers: Any) -> list[Section]:
        return [section for section in self.sections.all() if section.is_applicable(answers)]


class Section(LayerMixin, ConditionalMixin, VersionScopedModel, BaseModel):
    """A group of questions inside a page."""

    layer_field: ClassVar[str] = "section"

    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="sections",
        verbose_name=_("page"),
    )
    key = models.SlugField(_("key"), max_length=100, help_text=_("Unique within the page."))
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(
        _("description"), blank=True, default="", help_text=MARKDOWN_HELP
    )
    conclusion = models.TextField(_("conclusion"), blank=True, default="", help_text=MARKDOWN_HELP)
    default_state = models.CharField(
        _("default state"),
        max_length=10,
        choices=SectionState.choices,
        default=SectionState.OPEN,
    )
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("section")
        verbose_name_plural = _("sections")
        ordering = ["page", "order", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["page", "key"], name="unique_section_key_per_page")
        ]

    def __str__(self) -> str:
        return self.title or self.key

    # -- layout ------------------------------------------------------------
    def get_parent_layer(self) -> LayerMixin | None:
        return self.page if self.page_id else None

    def get_questionnaire_version(self) -> QuestionnaireVersion:
        return self.page.questionnaire_version

    def get_edited_version(self) -> QuestionnaireVersion | None:
        return self.page.questionnaire_version if self.page_id else None

    # -- run time ----------------------------------------------------------
    def applicable_questions(self, answers: Any) -> list[Question]:
        return [question for question in self.questions.all() if question.is_applicable(answers)]
