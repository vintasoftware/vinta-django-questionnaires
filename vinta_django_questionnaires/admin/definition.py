"""The admin for a questionnaire's definition.

The shape of it follows what someone actually does: they open a questionnaire
to see its versions, open a version to work on it, and work on it in one place.
So the version's change form carries the version's own settings -- title,
status, the deadlines, the breakpoints -- and everything below it lives on the
structure editor one click away.

Pages, sections and questions still have their own admin registered, because
sometimes what you have is a link to a question and no idea which questionnaire
it is on. They are just not the road anyone is meant to walk down.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import TooManyFieldsSent
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _, ngettext

from vinta_django_questionnaires.admin.editing import (
    AcknowledgedEditAdminMixin,
    AcknowledgedEditInlineMixin,
)
from vinta_django_questionnaires.admin.structure import StructureEditor
from vinta_django_questionnaires.models import (
    LayerColumns,
    Page,
    Question,
    QuestionChoice,
    Questionnaire,
    QuestionnaireVersion,
    QuestionnaireWidget,
    QuestionValidator,
    Section,
    ValueSet,
    ValueSetOption,
    VersionStatus,
    WidgetQuestionType,
    WindowSizeRange,
)
from vinta_django_questionnaires.versioning import new_version_from

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse


def _link(url: str, label: Any) -> str:
    return format_html('<a class="vqa-link" href="{}">{}</a>', url, label)


class QuestionnaireAssets:
    """The stylesheet, for an admin whose columns render `vqa-` markup.

    The structure editor and the response table link it from their own
    templates. A changelist has no template of ours, so the shortcut links in
    `list_display` would otherwise be unstyled -- which is what they were until
    someone looked at a changelist.
    """

    class Media:
        css = {"all": ["vinta_django_questionnaires/admin.css"]}


# ------------------------------------------------------------- questionnaires


class QuestionnaireVersionInline(admin.TabularInline):
    """The versions of a questionnaire, as a way in rather than a form.

    Everything here is read-only on purpose: a version is edited on its own
    page, and a row of inputs squeezed into a list is how people change the
    wrong version's status by accident.
    """

    model = QuestionnaireVersion
    extra = 0
    can_delete = False
    fields = ("version", "title", "status", "responses", "edit")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    @admin.display(description=_("responses"))
    def responses(self, instance: QuestionnaireVersion) -> int:
        return instance.responses.count()

    @admin.display(description=_("edit"))
    def edit(self, instance: QuestionnaireVersion) -> str:
        return format_html_join(
            " ",
            "{}",
            [
                (_link(_version_url(instance, "structure"), _("Structure")),),
                (_link(_version_url(instance, "change"), _("Settings")),),
                (_link(_responses_url(instance), _("Responses")),),
            ],
        )


class QuestionnaireAdmin(QuestionnaireAssets, admin.ModelAdmin):
    """A questionnaire is a key with versions; this is mostly a way to its versions."""

    list_display = (
        "key",
        "name",
        "scope",
        "is_active",
        "version_count",
        "response_count",
        "shortcuts",
    )
    # ``RelatedOnlyFieldListFilter`` rather than a bare "scope": it offers
    # only the scopes that actually have questionnaires, which is the
    # difference between a usable control and one listing every tenant.
    list_filter = (("scope", admin.RelatedOnlyFieldListFilter), "is_active")
    search_fields = ("key", "name")
    inlines = [QuestionnaireVersionInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Questionnaire]:
        queryset: QuerySet[Questionnaire] = (
            super()
            .get_queryset(request)
            .annotate(
                _versions=Count("versions", distinct=True),
                _responses=Count("versions__responses", distinct=True),
            )
        )
        return queryset

    @admin.display(description=_("versions"), ordering="_versions")
    def version_count(self, instance: Questionnaire) -> int:
        return int(instance._versions)  # type: ignore[attr-defined]

    @admin.display(description=_("responses"), ordering="_responses")
    def response_count(self, instance: Questionnaire) -> int:
        return int(instance._responses)  # type: ignore[attr-defined]

    @admin.display(description=_("go to"))
    def shortcuts(self, instance: Questionnaire) -> str:
        latest = instance.latest_version
        if latest is None:
            return format_html('<span class="vqa-quiet">{}</span>', _("no versions yet"))
        return format_html_join(
            " ",
            "{}",
            [
                (_link(_version_url(latest, "structure"), _("Latest structure")),),
                (
                    _link(
                        f"{_responses_url(latest)}?questionnaire={instance.key}",
                        _("Responses"),
                    ),
                ),
            ],
        )

    def response_change(self, request: HttpRequest, obj: Questionnaire) -> HttpResponse:
        if "_new_version" in request.POST:
            latest = obj.latest_version
            draft = (
                new_version_from(latest)
                if latest is not None
                else QuestionnaireVersion.objects.create(
                    questionnaire=obj, version=1, title=obj.name or obj.key
                )
            )
            self.message_user(
                request,
                _("Started %(version)s. Its structure is empty until you fill it in.")
                % {"version": draft},
                messages.SUCCESS,
            )
            return HttpResponseRedirect(_version_url(draft, "structure"))
        return super().response_change(request, obj)

    def render_change_form(
        self,
        request: HttpRequest,
        context: dict[str, Any],
        add: bool = False,
        change: bool = False,
        form_url: str = "",
        obj: Any = None,
    ) -> HttpResponse:
        context["show_new_version"] = obj is not None
        return super().render_change_form(request, context, add, change, form_url, obj)

    change_form_template = "admin/vinta_django_questionnaires/questionnaire_change_form.html"


class WindowSizeRangeInline(admin.TabularInline):
    model = WindowSizeRange
    extra = 0
    fields = ("order", "key", "label", "min_width", "max_width")


class VersionColumnsInline(admin.TabularInline):
    """What the version's own grid is, per breakpoint. Pages inherit it."""

    model = LayerColumns
    fk_name = "questionnaire_version"
    extra = 0
    fields = ("window_size_range", "columns")
    verbose_name = _("columns of the questionnaire's grid")
    verbose_name_plural = _("columns of the questionnaire's grid")


class QuestionnaireVersionAdmin(QuestionnaireAssets, admin.ModelAdmin):
    """A version's own settings. What is *in* it is on the structure editor."""

    list_display = (
        "__str__",
        "title",
        "status",
        "edit_policy",
        "response_count",
        "question_count",
        "shortcuts",
    )
    list_filter = (
        ("questionnaire__scope", admin.RelatedOnlyFieldListFilter),
        "status",
        "edit_policy",
        "questionnaire",
    )
    search_fields = ("questionnaire__key", "questionnaire__name", "title")
    autocomplete_fields = ("questionnaire",)
    inlines = [WindowSizeRangeInline, VersionColumnsInline]
    actions = ["publish", "fork"]
    change_form_template = "admin/vinta_django_questionnaires/version_change_form.html"

    fieldsets = (
        (None, {"fields": ("questionnaire", "version", "title", "description")}),
        (
            _("What it accepts"),
            {
                "fields": (
                    "status",
                    "published_at",
                    "edit_policy",
                    "responses_due_at",
                    "edits_due_at",
                ),
                "description": _(
                    "Answering a page with nothing recorded and editing one that already has "
                    "answers are separate acts, each with its own deadline."
                ),
            },
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet[QuestionnaireVersion]:
        queryset: QuerySet[QuestionnaireVersion] = (
            super()
            .get_queryset(request)
            .select_related("questionnaire")
            .annotate(_responses=Count("responses", distinct=True))
        )
        return queryset

    @admin.display(description=_("responses"), ordering="_responses")
    def response_count(self, instance: QuestionnaireVersion) -> int:
        return int(instance._responses)  # type: ignore[attr-defined]

    @admin.display(description=_("questions"))
    def question_count(self, instance: QuestionnaireVersion) -> int:
        return sum(1 for _question in instance.iter_questions())

    @admin.display(description=_("go to"))
    def shortcuts(self, instance: QuestionnaireVersion) -> str:
        return format_html_join(
            " ",
            "{}",
            [
                (_link(_version_url(instance, "structure"), _("Structure")),),
                (
                    _link(
                        f"{_responses_url(instance)}?questionnaire="
                        f"{instance.questionnaire.key}&version={instance.version}",
                        _("Responses"),
                    ),
                ),
            ],
        )

    # -- the structure editor ---------------------------------------------
    def get_urls(self) -> list[URLPattern]:
        own = [
            path(
                "<path:object_id>/structure/",
                self.admin_site.admin_view(self.structure_view),
                name="vinta_django_questionnaires_questionnaireversion_structure",
            )
        ]
        return own + super().get_urls()

    def structure_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """Every page, section, question, choice and validator, on one form."""
        version = get_object_or_404(
            QuestionnaireVersion.objects.select_related("questionnaire"), pk=object_id
        )
        if not self.has_change_permission(request, version):
            return self.structure_denied(request)

        if request.method == "POST":
            try:
                editor = StructureEditor(version, request.POST)
            except TooManyFieldsSent:
                return self.structure_too_large(request, version)
            if editor.is_valid(user=request.user):
                editor.save(user=request.user)
                self.message_user(request, _("Saved the structure."), messages.SUCCESS)
                if "_continue" in request.POST:
                    return HttpResponseRedirect(request.get_full_path())
                return HttpResponseRedirect(_version_url(version, "change"))
            self.message_user(
                request,
                _("Nothing was saved: %(count)s thing(s) need fixing.")
                % {"count": len(editor.errors())},
                messages.ERROR,
            )
        else:
            editor = StructureEditor(version)

        context = {
            **self.admin_site.each_context(request),
            "title": _("Structure of %(version)s") % {"version": version},
            "opts": self.model._meta,
            "original": version,
            "version": version,
            "editor": editor,
            "response_count": version.responses.count(),
            "settings_url": _version_url(version, "change"),
            "responses_url": (
                f"{_responses_url(version)}?questionnaire={version.questionnaire.key}"
                f"&version={version.version}"
            ),
            "has_view_permission": True,
            "has_change_permission": True,
        }
        return TemplateResponse(
            request, "admin/vinta_django_questionnaires/structure.html", context
        )

    def structure_too_large(
        self, request: HttpRequest, version: QuestionnaireVersion
    ) -> HttpResponse:
        """Django refused the POST for having too many inputs in it.

        Editing a whole questionnaire at once means posting a whole
        questionnaire at once, and Django's default cap is a thousand fields.
        Nothing is wrong with the questionnaire, so this says what to raise
        rather than showing a traceback.
        """
        needed = StructureEditor(version).field_count
        context = {
            **self.admin_site.each_context(request),
            "title": _("That was too big to post"),
            "opts": self.model._meta,
            "needed": needed,
            "suggested": max(2000, needed * 2),
            "current": getattr(settings, "DATA_UPLOAD_MAX_NUMBER_FIELDS", 1000),
            "settings_url": _version_url(version, "change"),
        }
        return TemplateResponse(
            request, "admin/vinta_django_questionnaires/too_large.html", context, status=400
        )

    def structure_denied(self, request: HttpRequest) -> HttpResponse:
        return render(
            request,
            "admin/vinta_django_questionnaires/denied.html",
            {**self.admin_site.each_context(request), "title": _("Not allowed")},
            status=403,
        )

    # -- actions -----------------------------------------------------------
    @admin.action(description=_("Publish the selected versions"))
    def publish(self, request: HttpRequest, queryset: QuerySet[QuestionnaireVersion]) -> None:
        published = 0
        for version in queryset.exclude(status=VersionStatus.PUBLISHED):
            version.publish()
            published += 1
        self.message_user(
            request,
            ngettext("Published %(count)d version.", "Published %(count)d versions.", published)
            % {"count": published},
            messages.SUCCESS if published else messages.WARNING,
        )

    @admin.action(description=_("Fork the selected versions into new drafts"))
    def fork(self, request: HttpRequest, queryset: QuerySet[QuestionnaireVersion]) -> None:
        drafts = [new_version_from(version) for version in queryset]
        if len(drafts) == 1:
            self.message_user(
                request, _("Started %(version)s.") % {"version": drafts[0]}, messages.SUCCESS
            )
            return
        self.message_user(
            request,
            ngettext("Started %(count)d draft.", "Started %(count)d drafts.", len(drafts))
            % {"count": len(drafts)},
            messages.SUCCESS,
        )


# ------------------------------------------------------- the tree, on its own


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    fields = ("order", "key", "title", "default_state", "condition")
    show_change_link = True


class PageAdmin(QuestionnaireAssets, AcknowledgedEditAdminMixin, admin.ModelAdmin):
    list_display = ("key", "title", "questionnaire_version", "order", "is_skippable", "structure")
    list_filter = ("questionnaire_version", "is_skippable")
    search_fields = ("key", "title")
    inlines = [SectionInline]

    @admin.display(description=_("edit in place"))
    def structure(self, instance: Page) -> str:
        return _link(_version_url(instance.questionnaire_version, "structure"), _("Structure"))


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ("order", "key", "title", "question_type", "condition")
    show_change_link = True


class SectionAdmin(AcknowledgedEditAdminMixin, admin.ModelAdmin):
    list_display = ("key", "title", "page", "order", "default_state")
    list_filter = ("page__questionnaire_version",)
    search_fields = ("key", "title")
    inlines = [QuestionInline]


class QuestionChoiceInline(AcknowledgedEditInlineMixin, admin.TabularInline):
    model = QuestionChoice
    extra = 0
    fields = ("order", "axis", "value", "label", "is_active")


class QuestionValidatorInline(AcknowledgedEditInlineMixin, admin.TabularInline):
    model = QuestionValidator
    extra = 0
    fields = ("order", "validator", "params", "message_overrides", "is_enabled")


class QuestionAdmin(AcknowledgedEditAdminMixin, admin.ModelAdmin):
    list_display = ("key", "title", "question_type", "section", "order")
    list_filter = ("question_type", "section__page__questionnaire_version")
    search_fields = ("key", "title")
    inlines = [QuestionChoiceInline, QuestionValidatorInline]


# ------------------------------------------ what a question is rendered with


class WidgetQuestionTypeInline(admin.TabularInline):
    model = WidgetQuestionType
    extra = 0


class QuestionnaireWidgetAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "types", "is_active")
    list_filter = ("is_active",)
    search_fields = ("key", "name")
    inlines = [WidgetQuestionTypeInline]

    @admin.display(description=_("renders"))
    def types(self, instance: QuestionnaireWidget) -> str:
        supports = instance.question_type_supports.all()
        return (
            ", ".join(
                f"{support.question_type}*" if support.is_default else support.question_type
                for support in supports
            )
            or "—"
        )


class ValueSetOptionInline(admin.TabularInline):
    model = ValueSetOption
    extra = 0


class QuestionnaireScopeAdmin(admin.ModelAdmin):
    """The tenant boundary itself.

    Only registered when this installation uses the scope model this package
    ships: a project that swapped it has its own model, in its own app, and
    wants its own admin for it.
    """

    list_display = ("__str__", "scope_type", "scope_key", "label")
    list_filter = ("scope_type",)
    search_fields = ("scope_key", "label")
    readonly_fields = ("scope_key",)

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        """``scope_key`` is derived, and moving a scope orphans its responses.

        The key is built from the columns beside it on every save, so offering
        it as a field would be offering a value that gets overwritten.
        """
        return self.readonly_fields


class ValueSetAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "scope", "source", "option_count")
    list_filter = (("scope", admin.RelatedOnlyFieldListFilter), "source")
    search_fields = ("key", "name")
    inlines = [ValueSetOptionInline]

    @admin.display(description=_("options"))
    def option_count(self, instance: ValueSet) -> str:
        if instance.is_resolved_by_the_client:
            return str(_("from an endpoint"))
        return str(len(instance.iter_options()))


# ------------------------------------------------------------------- helpers


def _version_url(version: QuestionnaireVersion, view: str) -> str:
    return reverse(
        f"admin:vinta_django_questionnaires_questionnaireversion_{view}", args=[version.pk]
    )


def _responses_url(_version: QuestionnaireVersion | None = None) -> str:
    return reverse("admin:vinta_django_questionnaires_questionnaireresponse_table")


__all__ = [
    "PageAdmin",
    "QuestionAdmin",
    "QuestionnaireAdmin",
    "QuestionnaireAssets",
    "QuestionnaireVersionAdmin",
    "QuestionnaireWidgetAdmin",
    "SectionAdmin",
    "ValueSetAdmin",
]
