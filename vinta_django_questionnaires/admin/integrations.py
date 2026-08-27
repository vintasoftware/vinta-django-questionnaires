"""The admin for what a response sets off.

A mapping is only readable next to its fields -- "email comes from
`answers.email`" is the whole thing -- so they are inline, split by what they
are for: the ones that fill the record in, and the ones that find it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.admin.responses import ReadOnlyAdmin
from vinta_django_questionnaires.models import (
    FieldRole,
    MappingField,
    MappingRun,
    WebhookDelivery,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


class MappingFieldInline(admin.TabularInline):
    model = MappingField
    extra = 1
    fields = ("order", "target_field", "expression", "is_required")

    #: Which half of the mapping this inline is for. Set by the two below.
    role: str = ""

    def get_queryset(self, request: HttpRequest) -> QuerySet[MappingField]:
        queryset: QuerySet[MappingField] = super().get_queryset(request)
        return queryset.filter(role=self.role)

    def get_formset(self, request: HttpRequest, obj: Any = None, **kwargs: Any) -> Any:
        formset = super().get_formset(request, obj, **kwargs)
        role = self.role

        class RoleFormSet(formset):  # type: ignore[valid-type]
            def save_new(self, form: Any, commit: bool = True) -> Any:
                form.instance.role = role
                return super().save_new(form, commit)

        return RoleFormSet


class ValueFieldInline(MappingFieldInline):
    role = FieldRole.VALUE
    verbose_name = _("mapped field")
    verbose_name_plural = _("fields written to the record")


class LookupFieldInline(MappingFieldInline):
    role = FieldRole.LOOKUP
    verbose_name = _("lookup field")
    verbose_name_plural = _("fields that find the record to update")


class ResponseMappingAdmin(admin.ModelAdmin):
    """Answers into one of the project's own models."""

    list_display = (
        "key",
        "name",
        "questionnaire",
        "content_type",
        "operation",
        "trigger",
        "is_active",
    )
    list_filter = ("operation", "trigger", "is_active", "questionnaire")
    search_fields = ("key", "name")
    inlines = [ValueFieldInline, LookupFieldInline]
    fieldsets = (
        (None, {"fields": ("key", "name", "is_active", "order")}),
        (
            _("When it runs"),
            {
                "fields": ("questionnaire", "questionnaire_version", "trigger", "condition"),
                "description": _(
                    "Leave the version empty to run for every version of the questionnaire."
                ),
            },
        ),
        (
            _("What it writes"),
            {
                "fields": (
                    "content_type",
                    "operation",
                    "defaults",
                    "update_defaults",
                    "skip_when_lookup_is_empty",
                ),
                "description": _(
                    "An insert needs no lookup fields; an update and an upsert need at least "
                    "one. Every expression below is JMESPath over the response."
                ),
            },
        ),
    )


class ResponseWebhookAdmin(admin.ModelAdmin):
    """Telling another system that a response happened."""

    list_display = (
        "key",
        "name",
        "questionnaire",
        "method",
        "url_template",
        "trigger",
        "is_active",
    )
    list_filter = ("method", "trigger", "is_active", "questionnaire")
    search_fields = ("key", "name", "url_template")
    fieldsets = (
        (None, {"fields": ("key", "name", "is_active", "order")}),
        (
            _("When it runs"),
            {"fields": ("questionnaire", "questionnaire_version", "trigger", "condition")},
        ),
        (
            _("What it sends"),
            {
                "fields": ("method", "url_template", "url_params", "headers", "body", "timeout"),
                "description": _(
                    "Every {placeholder} in the URL needs an expression in the parameters. "
                    'In the headers and the body, {"$jmespath": "..."} anywhere in the JSON is '
                    "replaced by what that expression resolves to; everything else is a literal."
                ),
            },
        ),
    )


class MappingRunAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "mapping", "response_link", "status", "action", "object_id")
    list_filter = ("status", "action", "mapping")
    search_fields = ("object_id", "error")
    date_hierarchy = "created_at"

    @admin.display(description=_("response"))
    def response_link(self, instance: MappingRun) -> str:
        return _response_link(instance.response_id, instance.response.uuid)


class WebhookDeliveryAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "webhook", "response_link", "status", "status_code", "url")
    list_filter = ("status", "webhook")
    search_fields = ("url", "error")
    date_hierarchy = "created_at"

    @admin.display(description=_("response"))
    def response_link(self, instance: WebhookDelivery) -> str:
        return _response_link(instance.response_id, instance.response.uuid)


def _response_link(pk: Any, label: Any) -> str:
    url = reverse("admin:vinta_django_questionnaires_questionnaireresponse_change", args=[pk])
    return format_html('<a href="{}">{}</a>', url, label)


__all__ = [
    "MappingRunAdmin",
    "ResponseMappingAdmin",
    "ResponseWebhookAdmin",
    "WebhookDeliveryAdmin",
]
