"""Value sets: where select questions get their options from.

A value set is either a static list of options, a queryset over any installed
model -- picked through the content types framework and narrowed with the
filter DSL -- or an endpoint the client calls at run time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.conditions import validate_condition
from vinta_django_questionnaires.filters import (
    compile_filter_expression,
    validate_filter_expression,
)
from vinta_django_questionnaires.models.base import MARKDOWN_HELP, BaseModel
from vinta_django_questionnaires.models.scopes import ScopedModel

if TYPE_CHECKING:
    from django.db.models import QuerySet


class ValueSetSource(models.TextChoices):
    STATIC = "static", _("Static options")
    MODEL = "model", _("Model queryset")
    ENDPOINT = "endpoint", _("Endpoint")


class HttpMethod(models.TextChoices):
    GET = "GET", _("GET")
    POST = "POST", _("POST")


class ValueSet(ScopedModel, BaseModel):
    """A named set of options questions can select from."""

    key = models.SlugField(_("key"), max_length=100)
    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(
        _("description"), blank=True, default="", help_text=MARKDOWN_HELP
    )
    source = models.CharField(
        _("source"), max_length=20, choices=ValueSetSource.choices, default=ValueSetSource.STATIC
    )

    # -- model source ------------------------------------------------------
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="questionnaire_value_sets",
        verbose_name=_("model"),
    )
    filter_expression = models.TextField(
        _("filter expression"),
        blank=True,
        default="",
        help_text=_('Filter DSL, e.g. \'status = "active" and not slug in ["internal"]\'.'),
    )
    value_field = models.CharField(
        _("value field"),
        max_length=100,
        blank=True,
        default="pk",
        help_text=_("Field read for the option value."),
    )
    label_field = models.CharField(
        _("label field"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("Field read for the option label. Empty falls back to str(instance)."),
    )
    ordering = models.CharField(
        _("ordering"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Comma separated field names, '-' prefixed to reverse."),
    )

    # -- endpoint source ---------------------------------------------------
    endpoint_url = models.URLField(_("endpoint URL"), blank=True, default="")
    endpoint_method = models.CharField(
        _("endpoint method"), max_length=10, choices=HttpMethod.choices, default=HttpMethod.GET
    )
    endpoint_headers = models.JSONField(_("endpoint headers"), default=dict, blank=True)
    endpoint_query_params = models.JSONField(_("endpoint query params"), default=dict, blank=True)
    endpoint_results_path = models.CharField(
        _("endpoint results path"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("JMESPath to the list of options in the response body."),
    )
    endpoint_value_path = models.CharField(
        _("endpoint value path"),
        max_length=255,
        blank=True,
        default="value",
        help_text=_("JMESPath to the value inside one result."),
    )
    endpoint_label_path = models.CharField(
        _("endpoint label path"),
        max_length=255,
        blank=True,
        default="label",
        help_text=_("JMESPath to the label inside one result."),
    )

    class Meta:
        verbose_name = _("value set")
        verbose_name_plural = _("value sets")
        ordering = ["key"]
        constraints = [
            # Per scope, like a questionnaire: a tenant may override a
            # shared "countries" list with one of its own.
            models.UniqueConstraint(
                fields=["scope", "key"], name="unique_value_set_key_per_scope"
            ),
        ]

    def __str__(self) -> str:
        return self.name or self.key

    def clean(self) -> None:
        super().clean()
        errors: dict[str, Any] = {}
        if self.source == ValueSetSource.MODEL:
            if self.content_type_id is None:
                errors["content_type"] = _("A model value set needs a model.")
            try:
                validate_filter_expression(self.filter_expression)
            except ValidationError as exc:
                errors["filter_expression"] = exc
        elif self.filter_expression:
            errors["filter_expression"] = _("Only model value sets take a filter expression.")

        if self.source == ValueSetSource.ENDPOINT:
            if not self.endpoint_url:
                errors["endpoint_url"] = _("An endpoint value set needs a URL.")
            for field_name in (
                "endpoint_results_path",
                "endpoint_value_path",
                "endpoint_label_path",
            ):
                try:
                    validate_condition(str(getattr(self, field_name) or ""))
                except ValidationError as exc:
                    errors[field_name] = exc
        elif self.endpoint_url:
            errors["endpoint_url"] = _("Only endpoint value sets take a URL.")

        if errors:
            raise ValidationError(errors)

    def iter_options(self) -> list[dict[str, Any]]:
        """The options this value set offers, for the client to render.

        Static and model-backed sets are resolved here.  An endpoint-backed one
        cannot be: it is the client that calls the endpoint, at the moment it
        needs the options.
        """
        if self.source == ValueSetSource.STATIC:
            return [
                {"value": option.value, "label": option.label, "extra": option.extra}
                for option in self.options.filter(is_active=True)
            ]
        if self.source == ValueSetSource.MODEL:
            return [
                {
                    "value": str(getattr(instance, self.value_field or "pk")),
                    "label": (
                        str(getattr(instance, self.label_field))
                        if self.label_field
                        else str(instance)
                    ),
                    "extra": {},
                }
                for instance in self.get_queryset()
            ]
        return []

    @property
    def is_resolved_by_the_client(self) -> bool:
        return self.source == ValueSetSource.ENDPOINT

    def endpoint_descriptor(self) -> dict[str, Any]:
        """What the client needs in order to fetch the options itself."""
        return {
            "url": self.endpoint_url,
            "method": self.endpoint_method,
            "headers": self.endpoint_headers,
            "queryParams": self.endpoint_query_params,
            "resultsPath": self.endpoint_results_path,
            "valuePath": self.endpoint_value_path,
            "labelPath": self.endpoint_label_path,
        }

    def get_queryset(self) -> QuerySet[Any]:
        """The queryset a model-backed value set draws its options from."""
        content_type = self.content_type if self.content_type_id else None
        if self.source != ValueSetSource.MODEL or content_type is None:
            raise ValueError(f"{self} is not backed by a model.")
        model = content_type.model_class()
        if model is None:
            raise ValueError(f"{content_type} does not resolve to an installed model.")
        queryset = model._default_manager.filter(compile_filter_expression(self.filter_expression))
        if self.ordering:
            queryset = queryset.order_by(*[part.strip() for part in self.ordering.split(",")])
        return queryset


class ValueSetOption(BaseModel):
    """One option of a static value set."""

    value_set = models.ForeignKey(
        ValueSet,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=_("value set"),
    )
    value = models.CharField(_("value"), max_length=255)
    label = models.CharField(_("label"), max_length=255)
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    extra = models.JSONField(_("extra"), default=dict, blank=True)
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("value set option")
        verbose_name_plural = _("value set options")
        ordering = ["value_set", "order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["value_set", "value"], name="unique_option_value_per_value_set"
            )
        ]

    def __str__(self) -> str:
        return self.label or self.value
