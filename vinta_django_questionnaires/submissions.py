"""Filling in a response, one page at a time.

Everything the HTTP layer does goes through here, so the same rules apply to a
management command, a bulk import or a test: a page is validated on its own,
against the answers already recorded plus the ones being pushed, and what
happened to it is written down -- filled, or skipped and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models import (
    Answer,
    EditPolicy,
    IntegrationTrigger,
    PageResponse,
    PageResponseStatus,
    QuestionnaireResponse,
    ResponseStatus,
    SkipReason,
)

if TYPE_CHECKING:
    from vinta_django_questionnaires.models import Page, Question, QuestionnaireVersion
    from vinta_django_questionnaires.validators import ValidationIssue

#: How many times condition skips are recomputed before giving up.  Recording a
#: skip drops that page's answers from the document, which can flip the next
#: page, so this settles rather than passes once.
MAX_SKIP_PASSES = 10


class SubmissionError(Exception):
    """Something about the submission itself is wrong."""


class RespondingClosed(SubmissionError):
    """The deadline to answer has passed."""

    def __init__(self, version: QuestionnaireVersion) -> None:
        super().__init__(_("This questionnaire stopped accepting responses."))
        self.version = version


class EditingNotAllowed(SubmissionError):
    """The version does not let a recorded answer be changed."""

    def __init__(self, message: Any = None) -> None:
        super().__init__(message or _("This questionnaire does not allow answers to be changed."))


class ResponseAlreadyCompleted(EditingNotAllowed):
    """The response was handed in, and this version only allows edits before that."""

    def __init__(self) -> None:
        super().__init__(_("This response is already completed."))


class EditingClosed(EditingNotAllowed):
    """The deadline to change an answer has passed."""

    def __init__(self) -> None:
        super().__init__(_("This questionnaire stopped accepting edits."))


class PageNotApplicable(SubmissionError):
    def __init__(self, page: Page) -> None:
        super().__init__(_("The condition of page %(page)s does not hold.") % {"page": page.key})
        self.page = page


class PageNotSkippable(SubmissionError):
    def __init__(self, page: Page) -> None:
        super().__init__(_("Page %(page)s cannot be skipped.") % {"page": page.key})
        self.page = page


@dataclass(frozen=True)
class PageValidation:
    """The outcome of validating one page's payload."""

    issues: dict[str, list[ValidationIssue]] = field(default_factory=dict)
    cleaned: dict[str, Any] = field(default_factory=dict)
    questions: list[Question] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, list[dict[str, Any]]]:
        """The issues in the shape the client's own issues already have."""
        return {
            key: [
                {
                    "validator": issue.validator,
                    "errorKey": issue.error_key,
                    "message": issue.message,
                }
                for issue in issues
            ]
            for key, issues in self.issues.items()
        }


class PageValidationError(SubmissionError):
    def __init__(self, validation: PageValidation) -> None:
        super().__init__(_("This page has answers that need fixing."))
        self.validation = validation


def check_can_respond(version: QuestionnaireVersion) -> None:
    """Raise unless a page may still be answered on this version."""
    if not version.is_open_for_responses:
        raise RespondingClosed(version)


def check_can_edit(version: QuestionnaireVersion, *, response_is_completed: bool) -> None:
    """Raise unless an answer already recorded may still be changed.

    The two deadlines are independent: a version can stop taking new answers
    while still letting the answers it has be corrected, and the other way
    around.
    """
    if not version.is_open_for_edits:
        if version.edit_policy == EditPolicy.NEVER:
            raise EditingNotAllowed
        raise EditingClosed
    if response_is_completed and version.edit_policy != EditPolicy.ALWAYS:
        raise ResponseAlreadyCompleted


def start_response(
    version: QuestionnaireVersion,
    *,
    respondent: Any = None,
    external_id: str = "",
    context: dict[str, Any] | None = None,
) -> QuestionnaireResponse:
    """Open a response, and record the pages its context already rules out."""
    check_can_respond(version)
    response = QuestionnaireResponse.objects.create(
        questionnaire_version=version,
        respondent=respondent,
        external_id=external_id,
        context=context or {},
    )
    sync_condition_skips(response)
    return response


def validate_page(
    response: QuestionnaireResponse,
    page: Page,
    payload: dict[str, Any],
    *,
    document: dict[str, Any] | None = None,
) -> PageValidation:
    """Run the validator chains of every question this page is asking.

    Sections and questions carry conditions of their own, so what gets
    validated is decided against the answers as they will be once this page
    lands -- not as they were before it.

    Each validator receives the response and the page under ``context.extra``,
    which is what a server-only validator needs to look at anything wider than
    the answer in front of it.
    """
    answers = document if document is not None else submission_document(response, payload)
    issues: dict[str, list[ValidationIssue]] = {}
    cleaned: dict[str, Any] = {}
    questions: list[Question] = []
    for section in page.sections.all():
        if not section.is_applicable(answers):
            continue
        for question in section.questions.all():
            if not question.is_applicable(answers):
                continue
            questions.append(question)
            value = payload.get(question.key)
            context = question.run_validators(
                value, answers=answers, extra={"response": response, "page": page}
            )
            if context.issues:
                issues[question.key] = context.issues
            cleaned[question.key] = context.outcomes[-1].value if context.outcomes else value
    return PageValidation(issues=issues, cleaned=cleaned, questions=questions)


def submission_document(
    response: QuestionnaireResponse, payload: dict[str, Any]
) -> dict[str, Any]:
    """The answers as they will stand once *payload* is recorded."""
    return {**response.condition_document, **payload}


@transaction.atomic
def submit_page(
    response: QuestionnaireResponse,
    page: Page,
    payload: dict[str, Any],
    *,
    complete_when_done: bool = True,
) -> PageResponse:
    """Validate and record one page.

    Raises ``PageValidationError`` with the issues per question key, and
    nothing is written.  Keys in *payload* that this page is not asking about
    are ignored.

    Whether this counts as answering or as editing depends on what is already
    recorded: a page with no answers yet is answered, a page that already has
    them is edited, and the two have their own deadlines.
    """
    _check_page_belongs(response, page)
    _check_window(response, page)
    document = submission_document(response, payload)
    if not page.is_applicable(document):
        raise PageNotApplicable(page)

    validation = validate_page(response, page, payload, document=document)
    if not validation.is_valid:
        raise PageValidationError(validation)

    page_response, _created = PageResponse.objects.update_or_create(
        response=response,
        page=page,
        defaults={
            "status": PageResponseStatus.COMPLETED,
            "skip_reason": "",
            "submitted_at": timezone.now(),
        },
    )
    answered = []
    for question in validation.questions:
        answer, _ = Answer.objects.update_or_create(
            response=response,
            question=question,
            defaults={"page_response": page_response, "value": validation.cleaned[question.key]},
        )
        answered.append(answer.pk)
    # A question this page stopped asking -- its condition no longer holds --
    # keeps no answer behind to hold a later condition true.
    Answer.objects.filter(page_response=page_response).exclude(pk__in=answered).delete()

    sync_condition_skips(response)
    was_complete = response.status == ResponseStatus.COMPLETED
    response.refresh_completion(complete=complete_when_done)
    _run_integrations(response, became_complete=not was_complete)
    return page_response


@transaction.atomic
def skip_page(response: QuestionnaireResponse, page: Page) -> PageResponse:
    """Put a page off for later, at the respondent's request."""
    _check_page_belongs(response, page)
    _check_window(response, page)
    if not page.is_skippable:
        raise PageNotSkippable(page)
    if not page.is_applicable(response.condition_document):
        raise PageNotApplicable(page)

    page_response, _created = PageResponse.objects.update_or_create(
        response=response,
        page=page,
        defaults={
            "status": PageResponseStatus.SKIPPED,
            "skip_reason": SkipReason.MANUAL_ACTION,
            "submitted_at": None,
        },
    )
    return page_response


def _run_integrations(response: QuestionnaireResponse, *, became_complete: bool) -> None:
    """Hand the response to its mappings and webhooks, once the page is written.

    They run after the transaction commits, so nothing they do can be rolled
    back by a later failure and nothing they read is uncommitted.  A project
    that would rather run them from a task queue turns
    ``QUESTIONNAIRES_RUN_INTEGRATIONS`` off and calls ``run_integrations``
    itself.
    """
    from vinta_django_questionnaires.integrations import (
        integrations_are_enabled,
        run_integrations,
    )

    if not integrations_are_enabled():
        return
    triggers = [IntegrationTrigger.ON_PAGE_SUBMIT]
    if became_complete and response.status == ResponseStatus.COMPLETED:
        triggers.append(IntegrationTrigger.ON_COMPLETION)
    for trigger in triggers:
        transaction.on_commit(
            lambda trigger=trigger: run_integrations(response, trigger=trigger)  # type: ignore[misc]
        )


def sync_condition_skips(response: QuestionnaireResponse) -> list[PageResponse]:
    """Write down the pages the answers currently rule out, and undo the ones they no longer do.

    Only ``false_condition`` records are ever undone.  A page the respondent
    chose to skip stays skipped until they come back to it -- unless its
    condition stops holding, at which point the reason becomes the honest one.
    """
    touched: list[PageResponse] = []
    for _pass in range(MAX_SKIP_PASSES):
        document = response.condition_document
        recorded = response.page_responses_by_page
        changed = False
        for page in response.ordered_pages():
            entry = recorded.get(page.pk)
            if page.is_applicable(document):
                changed |= _restore(entry, touched)
            else:
                changed |= _rule_out(response, page, entry, touched)
        if not changed:
            break
    return touched


def _rule_out(
    response: QuestionnaireResponse,
    page: Page,
    entry: PageResponse | None,
    touched: list[PageResponse],
) -> bool:
    if entry is None:
        touched.append(
            PageResponse.objects.create(
                response=response,
                page=page,
                status=PageResponseStatus.SKIPPED,
                skip_reason=SkipReason.FALSE_CONDITION,
            )
        )
        return True
    if entry.skip_reason == SkipReason.FALSE_CONDITION:
        return False
    entry.status = PageResponseStatus.SKIPPED
    entry.skip_reason = SkipReason.FALSE_CONDITION
    entry.save()
    touched.append(entry)
    return True


def _restore(entry: PageResponse | None, touched: list[PageResponse]) -> bool:
    if entry is None or entry.skip_reason != SkipReason.FALSE_CONDITION:
        return False
    if entry.answers.exists():
        # The page was filled before its condition stopped holding, and now it
        # holds again: the answers are still there, so it counts as filled.
        entry.status = PageResponseStatus.COMPLETED
        entry.skip_reason = ""
        entry.save()
        touched.append(entry)
    else:
        entry.delete()
    return True


def is_edit(response: QuestionnaireResponse, page: Page) -> bool:
    """Whether writing this page would change something already recorded."""
    if response.status == ResponseStatus.COMPLETED:
        return True
    recorded = response.page_responses_by_page.get(page.pk)
    return recorded is not None and recorded.status == PageResponseStatus.COMPLETED


def _check_window(response: QuestionnaireResponse, page: Page) -> None:
    version = response.questionnaire_version
    if is_edit(response, page):
        check_can_edit(version, response_is_completed=response.status == ResponseStatus.COMPLETED)
    else:
        check_can_respond(version)


def _check_page_belongs(response: QuestionnaireResponse, page: Page) -> None:
    if page.questionnaire_version_id != response.questionnaire_version_id:
        raise SubmissionError(_("This page belongs to another questionnaire version."))
