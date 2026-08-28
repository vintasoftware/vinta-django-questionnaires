"""The authoring API the React editor talks to.

Three things, kept apart from the response API on purpose: reading a version as
an editable document, writing one back, and forking one into a new draft.  Plus
the catalog, which is what makes the editor's dropdowns possible.

Who may author is a method, the way it is over in ``views``, and the default is
the careful one: staff only.  Unlike responding, authoring is not something an
anonymous visitor ever does by accident.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.catalog import editor_catalog
from vinta_django_questionnaires.definition import (
    DefinitionError,
    apply_definition,
    definition_document,
)
from vinta_django_questionnaires.editing import Acknowledgement
from vinta_django_questionnaires.models import (
    Questionnaire,
    QuestionnaireResponse,
    QuestionnaireVersion,
    get_global_scope,
)
from vinta_django_questionnaires.models_registry import get_scope_model
from vinta_django_questionnaires.reporting import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    columns_for,
    csv_rows,
    default_columns,
    response_queryset,
    rows_for,
    select_columns,
)
from vinta_django_questionnaires.scoping import ScopeFilter
from vinta_django_questionnaires.submissions import SubmissionError
from vinta_django_questionnaires.versioning import new_version_from
from vinta_django_questionnaires.views import ApiView

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


class AuthoringAccessMixin:
    """Who may read and change a questionnaire's definition, and whose.

    The scope comes from the URL rather than from anything ambient.  A project
    that wants a tenant boundary on these endpoints wraps the URLconf::

        path(
            "api/authoring/scopes/<slug:scope_key>/",
            include("vinta_django_questionnaires.editor_urls"),
        )

    and Django hands the capture to every view underneath.  Included without a
    prefix -- which is what a single-tenant installation does -- no scope
    arrives and every scope is in view.

    Naming the scope in the path is what turns "did this view remember to
    filter?" into "did this request pass the check?".  The second is a question
    with one answer, in one place: :meth:`check_scope_access`.
    """

    #: Django puts every URL capture here, whether or not a handler names it.
    kwargs: dict[str, Any]

    def check_access(self, request: HttpRequest) -> None:
        if not request.user.is_staff:
            raise PermissionDenied(_("You may not edit questionnaires."))

    def get_scope_key(self, request: HttpRequest) -> str:
        """The scope this request is about, or ``""`` for "every scope"."""
        return str(self.kwargs.get("scope_key") or "")

    def check_scope_access(self, request: HttpRequest, scope_key: str) -> None:
        """Whether this user may act inside *scope_key*.

        Open by default, because reaching here already means
        :meth:`check_access` was satisfied -- staff, who see every tenant.  A
        project that lets a tenant's own people author their questionnaires
        overrides both: ``check_access`` to admit them, and this to pin them to
        their own scope.
        """

    def get_scopes(self, request: HttpRequest) -> ScopeFilter:
        """The scopes whose **responses** this request may read.

        No global fallback: a response always belongs to somebody, so asking
        for one tenant's responses must never turn up another's -- or the
        installation's, which has none of its own.
        """
        key = self.get_scope_key(request)
        if not key:
            return ScopeFilter.everything()
        self.check_scope_access(request, key)
        return ScopeFilter.only(key)

    def get_definition_scopes(self, request: HttpRequest) -> ScopeFilter:
        """The scopes whose **questionnaires** this request may use.

        Global included, unlike :meth:`get_scopes`: a questionnaire the whole
        installation shares is one every tenant can author against and answer.
        """
        key = self.get_scope_key(request)
        if not key:
            return ScopeFilter.everything()
        self.check_scope_access(request, key)
        return ScopeFilter.only(key, include_global=True)

    def get_questionnaire_queryset(self, request: HttpRequest) -> QuerySet[Questionnaire]:
        return self.get_definition_scopes(request).apply(
            Questionnaire.objects.all(), field="scope__scope_key"
        )

    def get_version_queryset(self, request: HttpRequest) -> QuerySet[QuestionnaireVersion]:
        return self.get_definition_scopes(request).apply(
            QuestionnaireVersion.objects.select_related("questionnaire"),
            field="questionnaire__scope__scope_key",
        )

    def get_version(
        self, request: HttpRequest, questionnaire_key: str, version: int
    ) -> QuestionnaireVersion:
        """One version, resolved most-specific-first.

        A key is unique within a scope, so a tenant that has made its own
        ``intake`` and the installation-wide ``intake`` are both candidates.
        The tenant's own wins -- which is what lets a tenant override a shared
        questionnaire without the installation having to anticipate it.
        """
        self.check_access(request)
        candidates = self.get_version_queryset(request).filter(
            questionnaire__key=questionnaire_key, version=version
        )
        key = self.get_scope_key(request)
        if key:
            own = candidates.filter(questionnaire__scope__scope_key=key).first()
            if own is not None:
                return own
        found = candidates.first()
        if found is None:
            raise Http404(_("No questionnaire version matches that."))
        return found

    def get_questionnaire(self, request: HttpRequest, questionnaire_key: str) -> Questionnaire:
        """One questionnaire by key, resolved the same way as a version."""
        candidates = self.get_questionnaire_queryset(request).filter(key=questionnaire_key)
        key = self.get_scope_key(request)
        if key:
            own = candidates.filter(scope__scope_key=key).first()
            if own is not None:
                return own
        found = candidates.first()
        if found is None:
            raise Http404(_("No questionnaire matches that."))
        return found

    def get_target_scope(self, request: HttpRequest) -> Any:
        """Where something created through this request lands.

        The scope the URL named, or the global one -- so a single-tenant
        installation, which names no scope, goes on behaving as it always did.
        """
        key = self.get_scope_key(request)
        if not key:
            return get_global_scope()
        self.check_scope_access(request, key)
        model = get_scope_model()
        scope = model._default_manager.filter(scope_key=key).first()
        if scope is None:
            raise Http404(_("No such scope."))
        return scope

    def get_acknowledgement(
        self, request: HttpRequest, payload: dict[str, Any]
    ) -> Acknowledgement:
        """The box someone ticked to say they know what this edit does.

        Absent or unticked, it is still an acknowledgement object -- a falsy
        one, which the edit gate refuses just as it refuses none at all.
        """
        node = payload.get("acknowledgement")
        node = node if isinstance(node, dict) else {}
        return Acknowledgement(
            understood=bool(node.get("understood")),
            user=request.user if request.user.is_authenticated else None,
            reason=str(node.get("reason") or ""),
        )


class EditorCatalogView(AuthoringAccessMixin, ApiView):
    """``GET /editor/catalog/`` -- the types, validators and widgets there are."""

    def get(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        self.check_access(request)
        return JsonResponse(editor_catalog(scopes=self.get_definition_scopes(request)))


class VersionListView(AuthoringAccessMixin, ApiView):
    """``GET /editor/versions/`` -- what there is to edit."""

    def get(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        self.check_access(request)
        questionnaires = (
            self.get_questionnaire_queryset(request)
            .select_related("scope")
            .prefetch_related("versions")
        )
        return JsonResponse(
            {
                "questionnaires": [
                    {
                        "key": questionnaire.key,
                        "name": questionnaire.name,
                        "isActive": questionnaire.is_active,
                        # Which scope a questionnaire lives in, so a client
                        # never has to guess -- and so a tenant can tell its
                        # own "intake" from the shared one.
                        "scope": questionnaire.scope.scope_key,
                        "isGlobal": not questionnaire.scope.scope_key,
                        "versions": [
                            {
                                "version": version.version,
                                "title": version.title,
                                "status": version.status,
                                "responseCount": version.responses.count(),
                            }
                            for version in questionnaire.versions.all()
                        ],
                    }
                    for questionnaire in questionnaires
                ]
            }
        )


class VersionDefinitionView(AuthoringAccessMixin, ApiView):
    """``GET|PUT /editor/questionnaires/<key>/versions/<n>/``.

    ``PUT`` takes ``{"document": {...}, "acknowledgement": {...}}`` and either
    applies all of it or none of it.  A document the server will not take comes
    back as 422 with one entry per node that would not go, addressed the way the
    editor addresses its own state.
    """

    def get(
        self, request: HttpRequest, questionnaire_key: str, version: int, **kwargs: Any
    ) -> HttpResponse:
        questionnaire_version = self.get_version(request, questionnaire_key, version)
        return JsonResponse({"document": definition_document(questionnaire_version)})

    def put(
        self, request: HttpRequest, questionnaire_key: str, version: int, **kwargs: Any
    ) -> HttpResponse:
        questionnaire_version = self.get_version(request, questionnaire_key, version)
        payload = self.body(request)
        document = payload.get("document")
        if not isinstance(document, dict):
            raise SubmissionError(_("Send the document to apply."))
        try:
            apply_definition(
                questionnaire_version,
                document,
                acknowledgement=self.get_acknowledgement(request, payload),
            )
        except DefinitionError as error:
            return JsonResponse(error.as_dict(), status=422)
        questionnaire_version.refresh_from_db()
        return JsonResponse({"document": definition_document(questionnaire_version)})

    def delete(
        self, request: HttpRequest, questionnaire_key: str, version: int, **kwargs: Any
    ) -> HttpResponse:
        """Drop a draft. Refused once the version has been answered.

        Deleting a version someone filled in is not an edit anyone should be
        able to make by clicking once -- and the responses point at it, so the
        database would refuse anyway.
        """
        questionnaire_version = self.get_version(request, questionnaire_key, version)
        answered = questionnaire_version.responses.count()
        if answered:
            raise SubmissionError(
                _("%(count)s response(s) have been given to this version.") % {"count": answered}
            )
        questionnaire_version.delete()
        return JsonResponse({}, status=204)


class VersionForkView(AuthoringAccessMixin, ApiView):
    """``POST /editor/questionnaires/<key>/versions/<n>/fork/`` -- a new draft.

    The ordinary answer to "this version already has responses": copy it, change
    the copy, publish that.
    """

    def post(
        self, request: HttpRequest, questionnaire_key: str, version: int, **kwargs: Any
    ) -> HttpResponse:
        questionnaire_version = self.get_version(request, questionnaire_key, version)
        payload = self.body(request)
        overrides: dict[str, Any] = {}
        if payload.get("title"):
            overrides["title"] = str(payload["title"])
        draft = new_version_from(questionnaire_version, **overrides)
        return JsonResponse({"document": definition_document(draft)}, status=201)


class QuestionnaireCollectionView(AuthoringAccessMixin, ApiView):
    """``POST /editor/questionnaires/`` -- a new questionnaire and its first draft.

    A questionnaire with no version is not something anyone can do anything
    with, so one comes with the other.
    """

    def post(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        self.check_access(request)
        payload = self.body(request)
        key = str(payload.get("key") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not key:
            raise SubmissionError(_("A questionnaire needs a key."))
        scope = self.get_target_scope(request)
        if Questionnaire.objects.filter(scope=scope, key=key).exists():
            raise SubmissionError(_("A questionnaire with that key already exists here."))
        questionnaire = Questionnaire.objects.create(scope=scope, key=key, name=name or key)
        version = QuestionnaireVersion.objects.create(
            questionnaire=questionnaire,
            version=1,
            title=str(payload.get("title") or name or key),
            description=str(payload.get("description") or ""),
        )
        return JsonResponse({"document": definition_document(version)}, status=201)


class QuestionnaireDetailView(AuthoringAccessMixin, ApiView):
    """``DELETE /editor/questionnaires/<key>/`` -- drop the whole thing.

    Refused while any of its versions has responses.  Deleting a questionnaire
    someone has answered is not an edit anyone should be able to make by
    clicking once; fork, or archive it by making it inactive.
    """

    def delete(self, request: HttpRequest, questionnaire_key: str, **kwargs: Any) -> HttpResponse:
        self.check_access(request)
        questionnaire = self.get_questionnaire(request, questionnaire_key)
        answered = QuestionnaireResponse.objects.filter(
            questionnaire_version__questionnaire=questionnaire
        ).count()
        if answered:
            raise SubmissionError(
                _("%(count)s response(s) have been given to this questionnaire.")
                % {"count": answered}
            )
        questionnaire.delete()
        return JsonResponse({}, status=204)


class ResponseListView(AuthoringAccessMixin, ApiView):
    """``GET /editor/responses/`` -- responses as a table, a page at a time.

    Filtered by ``questionnaire``, ``version``, ``status`` and ``search``; the
    columns come back with the rows, so a client does not have to know what a
    questionnaire asks to render it.
    """

    def get(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        self.check_access(request)
        version = self.get_filtered_version(request)
        available = columns_for(version)
        requested = [key for key in request.GET.get("columns", "").split(",") if key]
        columns = select_columns(available, requested)

        queryset = response_queryset(
            scopes=self.get_scopes(request),
            questionnaire=request.GET.get("questionnaire", ""),
            version=self.get_version_number(request),
            status=request.GET.get("status", ""),
            search=request.GET.get("search", ""),
        )
        total = queryset.count()
        size = self.get_page_size(request)
        number = max(1, self.get_int(request, "page") or 1)
        start = (number - 1) * size
        rows = list(queryset[start : start + size])

        return JsonResponse(
            {
                "columns": [column.as_dict() for column in available],
                "selectedColumns": [column.key for column in columns],
                "defaultColumns": default_columns(version),
                "results": rows_for(rows, columns),
                "page": number,
                "pageSize": size,
                "total": total,
                "totalPages": max(1, -(-total // size)),
            }
        )

    # -- request reading ---------------------------------------------------
    def get_int(self, request: HttpRequest, name: str) -> int | None:
        raw = request.GET.get(name)
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError as exc:
            raise SubmissionError(_("%(name)s must be a number.") % {"name": name}) from exc

    def get_page_size(self, request: HttpRequest) -> int:
        requested = self.get_int(request, "pageSize") or DEFAULT_PAGE_SIZE
        return max(1, min(requested, MAX_PAGE_SIZE))

    def get_version_number(self, request: HttpRequest) -> int | None:
        return self.get_int(request, "version")

    def get_filtered_version(self, request: HttpRequest) -> QuestionnaireVersion | None:
        """The version the columns come from: the filtered one, or the latest.

        Asking for a table across every questionnaire at once cannot have
        answer columns -- different questionnaires ask different things -- so
        it gets the metadata ones only.
        """
        key = request.GET.get("questionnaire", "")
        if not key:
            return None
        number = self.get_version_number(request)
        # Through the mixin, so the columns can only ever come from a
        # questionnaire this request is allowed to see.
        versions = self.get_version_queryset(request).filter(questionnaire__key=key)
        scope_key = self.get_scope_key(request)
        if scope_key:
            versions = versions.filter(questionnaire__scope__scope_key=scope_key)
        if number is not None:
            return versions.filter(version=number).first()
        return versions.order_by("-version").first()


class ResponseExportView(ResponseListView):
    """``GET /editor/responses/export/`` -- the same table, as CSV.

    Streamed, because an export of everything is exactly the request that is
    large, and the columns are the ones asked for, so what is downloaded is
    what was on screen.
    """

    filename = "questionnaire-responses.csv"

    def get(self, request: HttpRequest, **kwargs: Any) -> StreamingHttpResponse:  # type: ignore[override]
        self.check_access(request)
        version = self.get_filtered_version(request)
        requested = [key for key in request.GET.get("columns", "").split(",") if key]
        columns = select_columns(columns_for(version), requested)
        queryset = response_queryset(
            scopes=self.get_scopes(request),
            questionnaire=request.GET.get("questionnaire", ""),
            version=self.get_version_number(request),
            status=request.GET.get("status", ""),
            search=request.GET.get("search", ""),
        )
        streamed = StreamingHttpResponse(
            csv_rows(queryset, columns), content_type="text/csv; charset=utf-8"
        )
        streamed["Content-Disposition"] = f'attachment; filename="{self.get_filename(request)}"'
        return streamed

    def get_filename(self, request: HttpRequest) -> str:
        key = request.GET.get("questionnaire", "")
        return f"{key}-responses.csv" if key else self.filename


__all__ = [
    "AuthoringAccessMixin",
    "EditorCatalogView",
    "QuestionnaireCollectionView",
    "QuestionnaireDetailView",
    "ResponseExportView",
    "ResponseListView",
    "VersionDefinitionView",
    "VersionForkView",
    "VersionListView",
]
