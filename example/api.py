"""The response API as the demo front end uses it.

The package's own views want a signed-in respondent, each seeing only their own
responses.  A public demo has no sign-in, so this is the worked example of
overriding those hooks: here, a response is keyed on the browser session
instead of a user.

It refuses to run with ``DEBUG`` off.  Letting anonymous people open responses
is a decision a project makes deliberately, not one a dependency should make
easy to arrive at by accident.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from vinta_django_questionnaires.editor_views import (
    EditorCatalogView,
    QuestionnaireCollectionView,
    QuestionnaireDetailView,
    ResponseExportView,
    ResponseListView,
    VersionDefinitionView,
    VersionForkView,
    VersionListView,
)
from vinta_django_questionnaires.models import Questionnaire, QuestionnaireResponse
from vinta_django_questionnaires.views import (
    ApiView,
    PageSkipView,
    PageSubmitView,
    ResponseAccessMixin,
    ResponseCreateView,
    ResponseDetailView,
    ValueSetOptionsView,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse


class SessionRespondentMixin(ResponseAccessMixin):
    """Identifies a respondent by their browser session rather than a login."""

    def check_access(self, request: HttpRequest) -> None:
        if not settings.DEBUG:
            raise PermissionDenied("The demo API only runs with DEBUG on.")

    def get_respondent(self, request: HttpRequest) -> Any:
        return request.user if request.user.is_authenticated else None

    def get_external_id(self, request: HttpRequest, payload: dict[str, Any]) -> str:
        return self.session_id(request)

    def get_response_queryset(self, request: HttpRequest) -> QuerySet[QuestionnaireResponse]:
        return QuestionnaireResponse.objects.filter(
            external_id=self.session_id(request)
        ).select_related("questionnaire_version__questionnaire")

    def session_id(self, request: HttpRequest) -> str:
        if not request.session.session_key:
            request.session.save()
        return f"session:{request.session.session_key}"


class DemoResponseCreateView(SessionRespondentMixin, ResponseCreateView):
    pass


class DemoResponseDetailView(SessionRespondentMixin, ResponseDetailView):
    pass


class DemoPageSubmitView(SessionRespondentMixin, PageSubmitView):
    pass


class DemoPageSkipView(SessionRespondentMixin, PageSkipView):
    pass


class DemoValueSetOptionsView(SessionRespondentMixin, ValueSetOptionsView):
    pass


@method_decorator(ensure_csrf_cookie, name="dispatch")
class BootstrapView(SessionRespondentMixin, ApiView):
    """What the front end asks for first: the questionnaires, and a CSRF cookie."""

    def get(self, request: HttpRequest) -> HttpResponse:
        self.check_access(request)
        self.session_id(request)
        return JsonResponse(
            {
                "questionnaires": [
                    {
                        "key": questionnaire.key,
                        "name": str(questionnaire),
                        "version": version.version,
                        "title": version.title,
                        "description": version.description,
                    }
                    for questionnaire in Questionnaire.objects.filter(is_active=True)
                    if (version := questionnaire.latest_published_version) is not None
                ]
            }
        )


# -- signing in ------------------------------------------------------------
#
# Filling a questionnaire in needs no account; authoring one does.  So the demo
# has a sign-in that hands out the ordinary Django session, and the authoring
# endpoints below are the package's own -- staff only, unrelaxed.  The admin
# credentials work because they are the same credentials.


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(ApiView):
    """``GET|POST|DELETE /demo-api/auth/session/`` -- who is signed in.

    ``GET`` says, ``POST`` signs in, ``DELETE`` signs out.  It is a session
    cookie rather than a token because that is what the Django admin already
    hands the same user.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        return JsonResponse(self.identity(request))

    def post(self, request: HttpRequest) -> HttpResponse:
        payload = self.body(request)
        user = authenticate(
            request,
            username=str(payload.get("username") or ""),
            password=str(payload.get("password") or ""),
        )
        if user is None:
            return self.error("That username and password did not match.", status=401)
        if not user.is_active:
            return self.error("That account is not active.", status=403)
        login(request, user)
        return JsonResponse(self.identity(request))

    def delete(self, request: HttpRequest) -> HttpResponse:
        logout(request)
        return JsonResponse(self.identity(request))

    def identity(self, request: HttpRequest) -> dict[str, Any]:
        user = request.user
        if not user.is_authenticated:
            return {"isAuthenticated": False, "isStaff": False, "username": ""}
        return {
            "isAuthenticated": True,
            "isStaff": bool(user.is_staff),
            "username": user.get_username(),
        }


# -- authoring -------------------------------------------------------------
#
# These are the package's views unchanged.  What the demo adds is the CSRF
# cookie above and a sign-in page in front of them; the access rule --
# `request.user.is_staff` -- is the package's own default.


class DemoEditorCatalogView(EditorCatalogView):
    pass


class DemoVersionListView(VersionListView):
    pass


class DemoVersionDefinitionView(VersionDefinitionView):
    pass


class DemoVersionForkView(VersionForkView):
    pass


class DemoQuestionnaireCollectionView(QuestionnaireCollectionView):
    pass


class DemoQuestionnaireDetailView(QuestionnaireDetailView):
    pass


class DemoResponseListView(ResponseListView):
    pass


class DemoResponseExportView(ResponseExportView):
    pass
