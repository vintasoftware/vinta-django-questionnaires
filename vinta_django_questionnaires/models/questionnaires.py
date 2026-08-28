"""Questionnaires and their versions.

``Questionnaire`` is the stable identity -- the key other systems reference.
Everything that can change between revisions lives on ``QuestionnaireVersion``,
so a published version is a frozen definition that answers can keep pointing at
while the next draft is written.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models.base import MARKDOWN_HELP, BaseModel
from vinta_django_questionnaires.models.layout import LayerMixin
from vinta_django_questionnaires.models.scopes import ScopedModel

if TYPE_CHECKING:
    from collections.abc import Iterator

    from vinta_django_questionnaires.models.questions import Question
    from vinta_django_questionnaires.models.structure import Page


class VersionStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")


class EditPolicy(models.TextChoices):
    """Whether a respondent may change an answer they already recorded.

    The distinction the two middle cases draw is between going back a page
    while still filling the questionnaire in, and coming back to a response
    that was already handed in.
    """

    NEVER = "never", _("Never: a page is final once it is recorded")
    UNTIL_COMPLETED = (
        "until_completed",
        _("Until completed: pages can be revised while the response is in progress"),
    )
    ALWAYS = "always", _("Always: a completed response can still be changed")


class Questionnaire(ScopedModel, BaseModel):
    """The identity a questionnaire keeps across every version of it."""

    key = models.SlugField(
        _("key"),
        max_length=100,
        help_text=_("Stable identifier, shared by every version. Unique within a scope."),
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Internal name. The title shown to respondents lives on each version."),
    )
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("questionnaire")
        verbose_name_plural = _("questionnaires")
        ordering = ["key"]
        constraints: ClassVar = [
            # Per scope, not globally: two tenants may each have an "intake".
            models.UniqueConstraint(
                fields=["scope", "key"], name="unique_questionnaire_key_per_scope"
            ),
        ]

    def __str__(self) -> str:
        return self.name or self.key

    @property
    def latest_version(self) -> QuestionnaireVersion | None:
        return self.versions.order_by("-version").first()

    @property
    def latest_published_version(self) -> QuestionnaireVersion | None:
        return self.versions.filter(status=VersionStatus.PUBLISHED).order_by("-version").first()

    def next_version_number(self) -> int:
        highest = self.versions.aggregate(highest=models.Max("version"))["highest"]
        return (highest or 0) + 1


class QuestionnaireVersion(LayerMixin, BaseModel):
    """One revision of a questionnaire: its content, layout and pages."""

    layer_field: ClassVar[str] = "questionnaire_version"

    questionnaire = models.ForeignKey(
        Questionnaire,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("questionnaire"),
    )
    version = models.PositiveIntegerField(_("version"), default=1)
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(
        _("description"), blank=True, default="", help_text=MARKDOWN_HELP
    )
    status = models.CharField(
        _("status"), max_length=20, choices=VersionStatus.choices, default=VersionStatus.DRAFT
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    edit_policy = models.CharField(
        _("edit policy"),
        max_length=20,
        choices=EditPolicy.choices,
        default=EditPolicy.UNTIL_COMPLETED,
    )
    responses_due_at = models.DateTimeField(
        _("responses due at"),
        null=True,
        blank=True,
        help_text=_("After this moment no page can be answered. Empty means no deadline."),
    )
    edits_due_at = models.DateTimeField(
        _("edits due at"),
        null=True,
        blank=True,
        help_text=_(
            "After this moment no recorded answer can be changed. Empty means no deadline."
        ),
    )

    class Meta:
        verbose_name = _("questionnaire version")
        verbose_name_plural = _("questionnaire versions")
        ordering = ["questionnaire", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["questionnaire", "version"], name="unique_version_per_questionnaire"
            )
        ]

    def __str__(self) -> str:
        key = self.questionnaire.key if self.questionnaire_id else "?"
        return f"{key} v{self.version}"

    # -- layout ------------------------------------------------------------
    def get_questionnaire_version(self) -> QuestionnaireVersion:
        return self

    # -- lifecycle ---------------------------------------------------------
    @property
    def is_published(self) -> bool:
        return self.status == VersionStatus.PUBLISHED

    def clean(self) -> None:
        super().clean()
        if self.edit_policy == EditPolicy.NEVER and self.edits_due_at is not None:
            raise ValidationError(
                {"edits_due_at": _("A version that never allows edits has no edit deadline.")}
            )

    # -- what is still allowed ---------------------------------------------
    @property
    def is_open_for_responses(self) -> bool:
        """Whether pages can still be answered.

        Only about the deadline: whether the version is one that should be
        offered at all is what its status says.
        """
        return self.responses_due_at is None or timezone.now() <= self.responses_due_at

    @property
    def is_open_for_edits(self) -> bool:
        """Whether a recorded answer can still be changed."""
        if self.edit_policy == EditPolicy.NEVER:
            return False
        return self.edits_due_at is None or timezone.now() <= self.edits_due_at

    @property
    def accepts_responses(self) -> bool:
        """Whether a new response should be offered at all."""
        return self.is_published and self.is_open_for_responses

    def allows_editing(self, *, response_is_completed: bool) -> bool:
        """Whether this version lets a respondent change what they recorded."""
        if not self.is_open_for_edits:
            return False
        if response_is_completed:
            return self.edit_policy == EditPolicy.ALWAYS
        return True

    def publish(self, **kwargs: Any) -> None:
        self.status = VersionStatus.PUBLISHED
        self.published_at = self.published_at or timezone.now()
        self.save(**kwargs)

    @property
    def content_fingerprint(self) -> str:
        """A digest of everything this version asks, in order."""
        from vinta_django_questionnaires.fingerprints import version_fingerprint

        return version_fingerprint(self)

    def iter_questions(self) -> Iterator[Question]:
        """Every question of this version, in the order it is asked."""
        for page in self.pages.all():
            for section in page.sections.all():
                yield from section.questions.all()

    # -- run time ----------------------------------------------------------
    def applicable_pages(self, answers: Any) -> list[Page]:
        """The pages whose condition holds for *answers*."""
        return [page for page in self.pages.all() if page.is_applicable(answers)]

    def iter_applicable_questions(self, answers: Any) -> Iterator[Question]:
        """Every question that should be validated and saved for *answers*.

        A question only counts when its own condition holds *and* the section
        and page above it hold too.
        """
        for page in self.applicable_pages(answers):
            for section in page.applicable_sections(answers):
                yield from section.applicable_questions(answers)
