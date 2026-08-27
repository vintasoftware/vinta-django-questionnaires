"""What respondents left behind, and what it set off.

A response's own change form is read-only -- an answer is a record of what
somebody said, and quietly correcting one in the admin is not an edit, it is a
forgery. What it does show is everything that happened *because* of it: the
rows a mapping wrote and the webhooks that went out, each with why it did not
if it did not.

The table view is the interesting one, and lives in `reporting`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.http import StreamingHttpResponse  # noqa: TC002  -- returned, not just annotated
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.admin.reporting import ResponseTable, export, export_queryset
from vinta_django_questionnaires.models import (
    Answer,
    MappingRun,
    PageResponse,
    QuestionnaireResponse,
    WebhookDelivery,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse


class ReadOnlyAdmin(admin.ModelAdmin):
    """For the records a person should read, not write."""

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class ReadOnlyInline(admin.TabularInline):
    """Rows to read.

    ``max_num = 0`` as well as the permissions: the admin's own JavaScript
    decides whether to offer "add another" from ``max_num`` alone, so without
    it a read-only inline still invites you to write a page response by hand.
    """

    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class PageResponseInline(ReadOnlyInline):
    model = PageResponse
    fields = ("page", "status", "skip_reason", "submitted_at")
    readonly_fields = fields
    show_change_link = False


class AnswerInline(ReadOnlyInline):
    model = Answer
    fk_name = "response"
    fields = ("question", "value")
    readonly_fields = fields
    show_change_link = False


class MappingRunInline(ReadOnlyInline):
    """What this response wrote into the project's own models."""

    model = MappingRun
    fields = ("created_at", "mapping", "status", "action", "target_link", "error")
    readonly_fields = fields
    show_change_link = False
    verbose_name = _("mapping run")
    verbose_name_plural = _("what this response wrote")

    @admin.display(description=_("record"))
    def target_link(self, instance: MappingRun) -> str:
        target = instance.target
        if target is None:
            return "—"
        meta = type(target)._meta
        try:
            url = reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[target.pk])
        except Exception:
            return str(target)
        return format_html('<a href="{}">{}</a>', url, target)


class WebhookDeliveryInline(ReadOnlyInline):
    """What was sent about this response, and what came back."""

    model = WebhookDelivery
    fields = ("created_at", "webhook", "status", "method", "url", "status_code", "error")
    readonly_fields = fields
    show_change_link = False
    verbose_name = _("webhook delivery")
    verbose_name_plural = _("what this response set off")


class QuestionnaireResponseAdmin(ReadOnlyAdmin):
    """One response. Read-only, with everything it caused underneath it."""

    list_display = (
        "uuid",
        "questionnaire_version",
        "respondent_name",
        "status",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "questionnaire_version__questionnaire", "questionnaire_version")
    search_fields = ("uuid", "external_id", "respondent__username")
    date_hierarchy = "created_at"
    inlines = [PageResponseInline, AnswerInline, MappingRunInline, WebhookDeliveryInline]
    actions = ["export_csv"]
    change_list_template = "admin/vinta_django_questionnaires/response_change_list.html"

    def get_queryset(self, request: HttpRequest) -> QuerySet[QuestionnaireResponse]:
        queryset: QuerySet[QuestionnaireResponse] = (
            super()
            .get_queryset(request)
            .select_related("questionnaire_version__questionnaire", "respondent")
        )
        return queryset

    @admin.display(description=_("respondent"), ordering="respondent__username")
    def respondent_name(self, instance: QuestionnaireResponse) -> str:
        user = instance.respondent if instance.respondent_id else None
        if user is not None:
            return str(user.get_username())
        return instance.external_id or "—"

    @admin.action(description=_("Export the selected responses as CSV"))
    def export_csv(
        self, request: HttpRequest, queryset: QuerySet[QuestionnaireResponse]
    ) -> StreamingHttpResponse:
        return export_queryset(queryset)

    # -- the table ---------------------------------------------------------
    def get_urls(self) -> list[URLPattern]:
        own = [
            path(
                "table/",
                self.admin_site.admin_view(self.table_view),
                name="vinta_django_questionnaires_questionnaireresponse_table",
            ),
            path(
                "table/export/",
                self.admin_site.admin_view(self.export_view),
                name="vinta_django_questionnaires_questionnaireresponse_export",
            ),
        ]
        return own + super().get_urls()

    def table_view(self, request: HttpRequest) -> HttpResponse:
        """The answers themselves, as a table, with the columns the reader picks."""
        table = ResponseTable(request)
        context = {
            **self.admin_site.each_context(request),
            "title": _("Responses"),
            "opts": self.model._meta,
            "table": table,
            "export_url": reverse(
                "admin:vinta_django_questionnaires_questionnaireresponse_export"
            ),
            "changelist_url": reverse(
                "admin:vinta_django_questionnaires_questionnaireresponse_changelist"
            ),
        }
        return TemplateResponse(
            request, "admin/vinta_django_questionnaires/response_table.html", context
        )

    def export_view(self, request: HttpRequest) -> StreamingHttpResponse:
        return export(ResponseTable(request))


class AcknowledgedEditAdmin(ReadOnlyAdmin):
    """Who changed a live definition, when, and what it did to the answers."""

    list_display = (
        "created_at",
        "questionnaire_version",
        "action",
        "target_label",
        "target_key",
        "acknowledged_by",
        "responses_at_edit",
    )
    list_filter = ("action", "questionnaire_version", "acknowledged_by")
    search_fields = ("target_key", "reason")
    date_hierarchy = "created_at"


__all__ = [
    "AcknowledgedEditAdmin",
    "MappingRunInline",
    "QuestionnaireResponseAdmin",
    "ReadOnlyAdmin",
    "WebhookDeliveryInline",
]
