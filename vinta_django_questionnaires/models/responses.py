"""What a respondent fills in.

A response is filled a page at a time.  Each page the client pushes becomes a
``PageResponse``, so the pages that exist -- and the order they are in -- are
what says where in the form the respondent is.  A page that was not filled
still gets a record, saying why: the respondent skipped it to come back later,
or its condition did not hold.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models.base import BaseModel
from vinta_django_questionnaires.models.questionnaires import QuestionnaireVersion
from vinta_django_questionnaires.models.questions import Question
from vinta_django_questionnaires.models.scopes import ScopedModel
from vinta_django_questionnaires.models.structure import Page

if TYPE_CHECKING:
    from collections.abc import Iterator


class ResponseStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", _("In progress")
    COMPLETED = "completed", _("Completed")
    ABANDONED = "abandoned", _("Abandoned")


class PageResponseStatus(models.TextChoices):
    COMPLETED = "completed", _("Completed")
    SKIPPED = "skipped", _("Skipped")


class SkipReason(models.TextChoices):
    MANUAL_ACTION = "manual_action", _("Skipped by the respondent")
    FALSE_CONDITION = "false_condition", _("Condition did not hold")


class QuestionnaireResponse(ScopedModel, BaseModel):
    """One respondent's pass through one version of a questionnaire.

    The scope is the response's own, not the questionnaire's: a global
    questionnaire -- one the whole installation shares -- collects answers
    that each belong to the tenant whose respondent gave them.
    """

    uuid = models.UUIDField(_("UUID"), default=uuid.uuid4, unique=True, editable=False)
    questionnaire_version = models.ForeignKey(
        QuestionnaireVersion,
        on_delete=models.PROTECT,
        related_name="responses",
        verbose_name=_("questionnaire version"),
    )
    respondent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="questionnaire_responses",
        null=True,
        blank=True,
        verbose_name=_("respondent"),
    )
    external_id = models.CharField(
        _("external id"),
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Identifies a respondent that is not a user of this system."),
    )
    #: The scope as a string, copied from the foreign key at insert.  This is
    #: what every listing filters on, and what a future partition would key on:
    #: both want a value on the row rather than one reached through a join.
    scope_key = models.CharField(_("scope key"), max_length=255, blank=True, default="")
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ResponseStatus.choices,
        default=ResponseStatus.IN_PROGRESS,
    )
    context = models.JSONField(
        _("context"),
        default=dict,
        blank=True,
        help_text=_(
            "Data conditions may read alongside the answers, such as the respondent's role. "
            "An answer with the same key wins."
        ),
    )
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("questionnaire response")
        verbose_name_plural = _("questionnaire responses")
        ordering = ["-created_at", "pk"]
        indexes = [
            # Every scoped read of this table is "the most recent responses in
            # one scope", so the index leads with the key and supplies the
            # ordering.  It keys on the denormalized copy rather than the
            # foreign key so that no join is needed to use it.
            models.Index(F("scope_key"), F("created_at").desc(), name="response_scope_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.questionnaire_version_id and self.questionnaire_version} / {self.uuid}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Stamp the scope, once.

        A response takes the questionnaire's scope unless it was given one --
        which is what makes a global questionnaire usable by every tenant.  The
        ``scope_key`` copy is written on insert and never again: the scope
        cannot move, so the copy cannot drift.
        """
        # See ``ScopedModel.save`` for why this is a ``getattr``.
        if getattr(self, "scope_id", None) is None and self.questionnaire_version_id:
            self.scope_id = self.questionnaire_version.questionnaire.scope_id
        if self._state.adding or not self.scope_key:
            self.scope_key = self.scope.scope_key
        super().save(*args, **kwargs)

    # -- answers -----------------------------------------------------------
    @property
    def answers(self) -> dict[str, Any]:
        """Every answer that currently counts, keyed by question key.

        Answers on a page that no longer applies are left in the database but
        kept out of here, so a condition cannot be held true by an answer to a
        question the respondent is no longer being asked.
        """
        stored = (
            Answer.objects.filter(
                response=self, page_response__status=PageResponseStatus.COMPLETED
            )
            .select_related("question")
            .order_by("question__section__page__order", "question__order")
        )
        return {answer.question.key: answer.value for answer in stored}

    @property
    def condition_document(self) -> dict[str, Any]:
        """What conditions and predicates are evaluated against."""
        return {**self.context, **self.answers}

    # -- progress ----------------------------------------------------------
    @property
    def page_responses_by_page(self) -> dict[int, PageResponse]:
        return {entry.page_id: entry for entry in self.page_responses.all()}

    def ordered_pages(self) -> list[Page]:
        return list(self.questionnaire_version.pages.all())

    def applicable_pages(self, document: dict[str, Any] | None = None) -> list[Page]:
        answers = self.condition_document if document is None else document
        return [page for page in self.ordered_pages() if page.is_applicable(answers)]

    def pending_pages(self) -> list[Page]:
        """The pages still waiting on the respondent, in order.

        A page manually skipped is still pending: skipping it means "later",
        not "never".  A page skipped because its condition did not hold is not.
        """
        recorded = self.page_responses_by_page
        pending = []
        for page in self.applicable_pages():
            entry = recorded.get(page.pk)
            if entry is None or entry.is_manually_skipped:
                pending.append(page)
        return pending

    @property
    def current_page(self) -> Page | None:
        """The page the respondent is on: the first one still pending."""
        pending = self.pending_pages()
        return pending[0] if pending else None

    @property
    def is_complete(self) -> bool:
        return not self.pending_pages()

    def progress(self) -> dict[str, Any]:
        """A summary of where this response stands, for the client."""
        recorded = self.page_responses_by_page
        completed: list[str] = []
        skipped: list[dict[str, str]] = []
        for page in self.ordered_pages():
            entry = recorded.get(page.pk)
            if entry is None:
                continue
            if entry.status == PageResponseStatus.COMPLETED:
                completed.append(page.key)
            else:
                skipped.append({"page": page.key, "reason": entry.skip_reason})
        current = self.current_page
        return {
            "completed": completed,
            "skipped": skipped,
            "pending": [page.key for page in self.pending_pages()],
            "current": current.key if current else None,
            "isComplete": self.is_complete,
        }

    def mark_completed(self) -> None:
        self.status = ResponseStatus.COMPLETED
        self.completed_at = self.completed_at or timezone.now()
        self.save()

    def reopen(self) -> None:
        self.status = ResponseStatus.IN_PROGRESS
        self.completed_at = None
        self.save()

    def refresh_completion(self, *, complete: bool = True) -> None:
        """Bring the status in line with what is recorded.

        Editing a response can make it incomplete again -- a changed answer
        can bring a page back into play -- so this goes both ways.
        """
        if self.is_complete:
            if complete and self.status != ResponseStatus.COMPLETED:
                self.mark_completed()
        elif self.status == ResponseStatus.COMPLETED:
            self.reopen()

    def iter_applicable_questions(self) -> Iterator[Question]:
        yield from self.questionnaire_version.iter_applicable_questions(self.condition_document)


class PageResponse(BaseModel):
    """What happened to one page of one response: filled, or skipped and why."""

    response = models.ForeignKey(
        QuestionnaireResponse,
        on_delete=models.CASCADE,
        related_name="page_responses",
        verbose_name=_("response"),
    )
    page = models.ForeignKey(
        Page,
        on_delete=models.PROTECT,
        related_name="responses",
        verbose_name=_("page"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=PageResponseStatus.choices,
        default=PageResponseStatus.COMPLETED,
    )
    skip_reason = models.CharField(
        _("skip reason"), max_length=20, choices=SkipReason.choices, blank=True, default=""
    )
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("page response")
        verbose_name_plural = _("page responses")
        ordering = ["response", "page__order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["response", "page"], name="unique_page_response_per_response"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=PageResponseStatus.COMPLETED, skip_reason="")
                    | (Q(status=PageResponseStatus.SKIPPED) & ~Q(skip_reason=""))
                ),
                name="page_response_skip_reason_matches_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.page_id}: {self.status}"

    @property
    def is_skipped(self) -> bool:
        return self.status == PageResponseStatus.SKIPPED

    @property
    def is_manually_skipped(self) -> bool:
        return self.is_skipped and self.skip_reason == SkipReason.MANUAL_ACTION

    def clean(self) -> None:
        super().clean()
        if self.status == PageResponseStatus.SKIPPED and not self.skip_reason:
            raise ValidationError({"skip_reason": _("Say why the page was skipped.")})
        if self.status == PageResponseStatus.COMPLETED and self.skip_reason:
            raise ValidationError({"skip_reason": _("A completed page was not skipped.")})
        if not self.response_id or not self.page_id:
            return
        if self.page.questionnaire_version_id != self.response.questionnaire_version_id:
            raise ValidationError(
                {"page": _("This page belongs to another questionnaire version.")}
            )


class Answer(BaseModel):
    """One question's answer, stored as the JSON document validation works on.

    The value is kept in the shape the validation layer reads -- a string, a
    list, a range object, a nested answer set for a sub-questionnaire -- so
    what is stored and what conditions are evaluated against are the same
    thing.
    """

    response = models.ForeignKey(
        QuestionnaireResponse,
        on_delete=models.CASCADE,
        # Not "answers": that name belongs to the property returning the answer
        # document, which is what the rest of the app reads.
        related_name="answer_records",
        verbose_name=_("response"),
    )
    page_response = models.ForeignKey(
        PageResponse,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name=_("page response"),
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="answers",
        verbose_name=_("question"),
    )
    value = models.JSONField(_("value"), null=True, blank=True)

    class Meta:
        verbose_name = _("answer")
        verbose_name_plural = _("answers")
        ordering = ["response", "question__order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["response", "question"], name="unique_answer_per_response_and_question"
            )
        ]

    def __str__(self) -> str:
        return f"{self.question_id}: {self.value!r}"

    def save(self, *args: Any, validate: bool = True, **kwargs: Any) -> None:
        if not self.response_id and self.page_response_id:
            self.response_id = self.page_response.response_id
        super().save(*args, validate=validate, **kwargs)

    def clean(self) -> None:
        super().clean()
        if not self.page_response_id or not self.question_id:
            return
        if self.question.section.page_id != self.page_response.page_id:
            raise ValidationError({"question": _("This question is not on the answered page.")})
        if self.response_id and self.response_id != self.page_response.response_id:
            raise ValidationError({"response": _("This answer belongs to another response.")})
