"""A small JSON API for filling in a response, a page at a time.

These views are opt-in: include ``vinta_django_questionnaires.urls`` where you
want them.  Every decision a project owns -- who may open a response, who may
see it, whether an anonymous respondent is allowed -- is a method to override
rather than a setting, and the defaults are the careful ones: authenticated
users, each seeing only their own responses.

The work itself lives in ``submissions``; these views only translate JSON into
that and back.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseBase, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views import View

from vinta_django_questionnaires.models import (
    Page,
    Questionnaire,
    QuestionnaireResponse,
    QuestionnaireVersion,
    ResponseStatus,
    ValueSet,
    VersionStatus,
)
from vinta_django_questionnaires.plan import questionnaire_plan
from vinta_django_questionnaires.submissions import (
    EditingNotAllowed,
    PageNotApplicable,
    PageNotSkippable,
    PageValidationError,
    RespondingClosed,
    SubmissionError,
    skip_page,
    start_response,
    submit_page,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from vinta_django_questionnaires.models import PageResponse

#: What each submission problem means over HTTP.
STATUS_CODES: dict[type[SubmissionError], int] = {
    PageValidationError: 422,
    PageNotApplicable: 409,
    PageNotSkippable: 409,
    EditingNotAllowed: 409,
    RespondingClosed: 409,
}


def status_for(error: SubmissionError) -> int:
    """The status of the most specific rule that matches, 400 otherwise."""
    for error_class, status in STATUS_CODES.items():
        if isinstance(error, error_class):
            return status
    return 400


def serialize_response(
    response: QuestionnaireResponse, *, include_plan: bool = False
) -> dict[str, Any]:
    version = response.questionnaire_version
    is_completed = response.status == ResponseStatus.COMPLETED
    payload: dict[str, Any] = {
        "id": str(response.uuid),
        "questionnaire": version.questionnaire.key,
        "version": version.version,
        "status": response.status,
        "answers": response.answers,
        "progress": response.progress(),
        "policy": {
            "editPolicy": version.edit_policy,
            "canRespond": version.is_open_for_responses,
            "canEdit": version.allows_editing(response_is_completed=is_completed),
            "responsesDueAt": (
                version.responses_due_at.isoformat() if version.responses_due_at else None
            ),
            "editsDueAt": version.edits_due_at.isoformat() if version.edits_due_at else None,
        },
    }
    if include_plan:
        payload["plan"] = questionnaire_plan(version)
    return payload


def serialize_page_response(page_response: PageResponse) -> dict[str, Any]:
    return {
        "page": page_response.page.key,
        "status": page_response.status,
        "skipReason": page_response.skip_reason or None,
        "submittedAt": (
            page_response.submitted_at.isoformat() if page_response.submitted_at else None
        ),
    }


class ApiView(View):
    """JSON in, JSON out, with submission problems mapped to status codes."""

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        try:
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied as exc:
            return self.error(str(exc) or str(_("Not allowed.")), status=403)
        except PageValidationError as exc:
            return JsonResponse({"errors": exc.validation.as_dict()}, status=422)
        except SubmissionError as exc:
            return self.error(str(exc), status=status_for(exc))

    def body(self, request: HttpRequest) -> dict[str, Any]:
        if not request.body:
            return {}
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError as exc:
            raise SubmissionError(_("The request body is not valid JSON.")) from exc
        if not isinstance(payload, dict):
            raise SubmissionError(_("The request body must be an object."))
        return payload

    def error(self, message: str, *, status: int) -> JsonResponse:
        return JsonResponse({"detail": str(message)}, status=status)


class ResponseAccessMixin:
    """Who may open and see responses.  Override for anonymous respondents."""

    def check_access(self, request: HttpRequest) -> None:
        if not request.user.is_authenticated:
            raise PermissionDenied(_("Sign in to fill in a questionnaire."))

    def get_respondent(self, request: HttpRequest) -> Any:
        return request.user if request.user.is_authenticated else None

    def get_response_queryset(self, request: HttpRequest) -> QuerySet[QuestionnaireResponse]:
        return QuestionnaireResponse.objects.filter(
            respondent=self.get_respondent(request)
        ).select_related("questionnaire_version__questionnaire")

    def get_response(self, request: HttpRequest, response_uuid: Any) -> QuestionnaireResponse:
        self.check_access(request)
        return get_object_or_404(self.get_response_queryset(request), uuid=response_uuid)

    def get_page(self, response: QuestionnaireResponse, page_key: str) -> Page:
        return get_object_or_404(response.questionnaire_version.pages, key=page_key)


class ResponseCreateView(ResponseAccessMixin, ApiView):
    """``POST /responses/`` -- open a response for a questionnaire.

    Body: ``{"questionnaire": "intake", "version": 2, "context": {}}``.  Without
    a version, the latest published one is used.
    """

    def get_version(self, request: HttpRequest, payload: dict[str, Any]) -> QuestionnaireVersion:
        key = str(payload.get("questionnaire") or "")
        if not key:
            raise SubmissionError(_("Say which questionnaire to answer."))
        questionnaire = get_object_or_404(Questionnaire, key=key, is_active=True)
        requested = payload.get("version")
        if requested is not None:
            return get_object_or_404(
                questionnaire.versions, version=requested, status=VersionStatus.PUBLISHED
            )
        version = questionnaire.latest_published_version
        if version is None:
            raise SubmissionError(_("This questionnaire has no published version."))
        return version

    def get_external_id(self, request: HttpRequest, payload: dict[str, Any]) -> str:
        """How a respondent who is not a user of this system is identified."""
        return str(payload.get("externalId") or "")

    def post(self, request: HttpRequest) -> HttpResponse:
        self.check_access(request)
        payload = self.body(request)
        context = payload.get("context") or {}
        if not isinstance(context, dict):
            raise SubmissionError(_("The context must be an object."))
        response = start_response(
            self.get_version(request, payload),
            respondent=self.get_respondent(request),
            external_id=self.get_external_id(request, payload),
            context=context,
        )
        return JsonResponse(serialize_response(response, include_plan=True), status=201)


class ResponseDetailView(ResponseAccessMixin, ApiView):
    """``GET /responses/<id>/`` -- where the respondent is, and what to render."""

    def get(self, request: HttpRequest, response_uuid: Any) -> HttpResponse:
        response = self.get_response(request, response_uuid)
        include_plan = request.GET.get("plan", "1") not in {"0", "false"}
        return JsonResponse(serialize_response(response, include_plan=include_plan))


class PageSubmitView(ResponseAccessMixin, ApiView):
    """``POST /responses/<id>/pages/<key>/`` -- push one page's answers.

    Body: ``{"answers": {"email": "hugo@vinta.com.br"}}``.  A page that does
    not validate is rejected whole, with the issues keyed by question.
    """

    def post(self, request: HttpRequest, response_uuid: Any, page_key: str) -> HttpResponse:
        response = self.get_response(request, response_uuid)
        page = self.get_page(response, page_key)
        answers = self.body(request).get("answers", {})
        if not isinstance(answers, dict):
            raise SubmissionError(_("The answers must be an object."))
        page_response = submit_page(response, page, answers)
        return JsonResponse(
            {
                "page": serialize_page_response(page_response),
                "response": serialize_response(response),
            }
        )


class ValueSetOptionsView(ResponseAccessMixin, ApiView):
    """``GET /value-sets/<key>/options/`` -- what a select should offer.

    Static and model-backed sets are resolved here.  An endpoint-backed one
    cannot be, so what comes back is the endpoint to call and the paths to read
    the options out of its reply.
    """

    def get(self, request: HttpRequest, key: str) -> HttpResponse:
        self.check_access(request)
        value_set = get_object_or_404(ValueSet, key=key)
        if value_set.is_resolved_by_the_client:
            return JsonResponse(
                {
                    "key": value_set.key,
                    "source": value_set.source,
                    "endpoint": value_set.endpoint_descriptor(),
                }
            )
        return JsonResponse(
            {
                "key": value_set.key,
                "source": value_set.source,
                "options": value_set.iter_options(),
            }
        )


class PageSkipView(ResponseAccessMixin, ApiView):
    """``POST /responses/<id>/pages/<key>/skip/`` -- leave a page for later."""

    def post(self, request: HttpRequest, response_uuid: Any, page_key: str) -> HttpResponse:
        response = self.get_response(request, response_uuid)
        page = self.get_page(response, page_key)
        page_response = skip_page(response, page)
        return JsonResponse(
            {
                "page": serialize_page_response(page_response),
                "response": serialize_response(response),
            }
        )


__all__ = [
    "ApiView",
    "PageSkipView",
    "PageSubmitView",
    "ResponseAccessMixin",
    "ResponseCreateView",
    "ResponseDetailView",
    "ValueSetOptionsView",
    "serialize_page_response",
    "serialize_response",
    "status_for",
]
