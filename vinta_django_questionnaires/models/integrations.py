"""What happens to a response once it has been given.

Two things a project almost always wants and would otherwise write by hand for
every questionnaire: put the answers into its own models, and tell another
system about them.  Both are configured rather than coded, and both read the
answers the same way conditions do -- through JMESPath, one expression per
field -- so there is one language for "where in this response is that value".

Neither is allowed to break a submission.  A mapping that will not apply or a
webhook that will not deliver is recorded and the response still stands: the
respondent has done their part, and an integration failing is not their
problem.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.conditions import validate_condition
from vinta_django_questionnaires.models.base import BaseModel, ConditionalMixin
from vinta_django_questionnaires.models.questionnaires import Questionnaire, QuestionnaireVersion

if TYPE_CHECKING:
    from django.db.models import Model

#: `{name}` in a URL template, which `url_params` has to have an expression for.
URL_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

#: The one-key object that marks a JMESPath expression inside a template tree.
EXPRESSION_KEY = "$jmespath"


class IntegrationTrigger(models.TextChoices):
    """When an integration runs."""

    ON_COMPLETION = "on_completion", _("When the response is complete")
    ON_PAGE_SUBMIT = "on_page_submit", _("Every time a page is pushed")


class MappingOperation(models.TextChoices):
    INSERT = "insert", _("Insert a new record")
    UPDATE = "update", _("Update the record it finds")
    UPSERT = "upsert", _("Update the record it finds, or insert one")


class FieldRole(models.TextChoices):
    """What one mapped field is for."""

    VALUE = "value", _("Written to the record")
    LOOKUP = "lookup", _("Used to find the record to update")


class IntegrationBase(ConditionalMixin, BaseModel):
    """What a mapping and a webhook have in common: when, and whether."""

    key = models.SlugField(_("key"), max_length=100, unique=True)
    name = models.CharField(_("name"), max_length=255)
    questionnaire = models.ForeignKey(
        Questionnaire,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name=_("questionnaire"),
    )
    questionnaire_version = models.ForeignKey(
        QuestionnaireVersion,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        null=True,
        blank=True,
        verbose_name=_("questionnaire version"),
        help_text=_("Pin a version, or leave empty to run for every version of it."),
    )
    trigger = models.CharField(
        _("trigger"),
        max_length=20,
        choices=IntegrationTrigger.choices,
        default=IntegrationTrigger.ON_COMPLETION,
    )
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.name or self.key

    def clean(self) -> None:
        super().clean()
        pinned = self.questionnaire_version if self.questionnaire_version_id else None
        if pinned is not None and pinned.questionnaire_id != self.questionnaire_id:
            raise ValidationError(
                {"questionnaire_version": _("That version belongs to another questionnaire.")}
            )

    def applies_to(self, version: QuestionnaireVersion) -> bool:
        """Whether this runs for responses to *version*."""
        if not self.is_active or self.questionnaire_id != version.questionnaire_id:
            return False
        return self.questionnaire_version_id is None or self.questionnaire_version_id == version.pk


class ResponseMapping(IntegrationBase):
    """Answers to a row of one of the project's own models.

    The target is named through the content type framework, so this package
    does not have to know anything about the model it writes to.  Which field
    takes which answer is one JMESPath expression per field, and what to do
    with the result -- insert, update, or either -- is the operation.
    """

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="questionnaire_mappings",
        verbose_name=_("target model"),
    )
    operation = models.CharField(
        _("operation"),
        max_length=10,
        choices=MappingOperation.choices,
        default=MappingOperation.INSERT,
    )
    defaults = models.JSONField(
        _("defaults"),
        default=dict,
        blank=True,
        help_text=_(
            "Written alongside the mapped fields when a record is created. "
            "A mapped field with a value of its own wins."
        ),
    )
    update_defaults = models.BooleanField(
        _("apply defaults on update"),
        default=False,
        help_text=_("Whether the defaults are also written when an existing record is updated."),
    )
    skip_when_lookup_is_empty = models.BooleanField(
        _("skip when the lookup is empty"),
        default=True,
        help_text=_(
            "A lookup expression that resolves to nothing usually means the answer was not "
            "given. Skip rather than match every record."
        ),
    )

    class Meta:
        verbose_name = _("response mapping")
        verbose_name_plural = _("response mappings")
        ordering = ["questionnaire", "order", "pk"]

    @property
    def model(self) -> type[Model] | None:
        """The target model, or ``None`` when its app is no longer installed."""
        return self.content_type.model_class()

    @property
    def creates(self) -> bool:
        return self.operation in {MappingOperation.INSERT, MappingOperation.UPSERT}

    @property
    def updates(self) -> bool:
        return self.operation in {MappingOperation.UPDATE, MappingOperation.UPSERT}

    def clean(self) -> None:
        super().clean()
        errors: dict[str, Any] = {}
        if not isinstance(self.defaults, dict):
            errors["defaults"] = _("The defaults must be an object.")
        if self.content_type_id is not None and self.model is None:
            errors["content_type"] = _("That model is not installed.")
        # Children only exist once there is a row to hang them off, so the
        # rule about needing a lookup is checked from then on.
        if (
            self.pk is not None
            and self.updates
            and not self.fields.filter(role=FieldRole.LOOKUP).exists()
        ):
            errors["operation"] = _(
                "An update needs at least one lookup field to say which record to update."
            )
        if (
            self.pk is not None
            and not self.updates
            and self.fields.filter(role=FieldRole.LOOKUP).exists()
        ):
            errors["operation"] = _("An insert has nothing to look up.")
        if errors:
            raise ValidationError(errors)

    def lookup_fields(self) -> models.QuerySet[MappingField]:
        return self.fields.filter(role=FieldRole.LOOKUP)

    def value_fields(self) -> models.QuerySet[MappingField]:
        return self.fields.filter(role=FieldRole.VALUE)


class MappingField(BaseModel):
    """One field of the target, and the expression that fills it."""

    mapping = models.ForeignKey(
        ResponseMapping,
        on_delete=models.CASCADE,
        related_name="fields",
        verbose_name=_("mapping"),
    )
    role = models.CharField(
        _("role"), max_length=10, choices=FieldRole.choices, default=FieldRole.VALUE
    )
    target_field = models.CharField(
        _("target field"),
        max_length=255,
        help_text=_("A field of the target model. Use `field__lookup` for a lookup field."),
    )
    expression = models.TextField(
        _("expression"),
        help_text=_("JMESPath, evaluated against the response document."),
    )
    is_required = models.BooleanField(
        _("is required"),
        default=False,
        help_text=_("Whether the whole mapping is abandoned when this resolves to nothing."),
    )
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("mapping field")
        verbose_name_plural = _("mapping fields")
        ordering = ["mapping", "role", "order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["mapping", "role", "target_field"],
                name="unique_target_field_per_mapping_role",
            )
        ]

    def __str__(self) -> str:
        return f"{self.target_field} = {self.expression}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, Any] = {}
        try:
            validate_condition(self.expression)
        except ValidationError as exc:
            errors["expression"] = exc
        if not self.expression.strip():
            errors["expression"] = _("An expression is required.")
        if self.mapping_id is not None:
            model = self.mapping.model
            # A lookup may be spelled `owner__email`; only the first part has
            # to be a field of the model itself.
            root = self.target_field.split("__", 1)[0]
            if model is not None and root:
                try:
                    model._meta.get_field(root)
                except FieldDoesNotExist:
                    errors["target_field"] = _("%(model)s has no field %(field)s.") % {
                        "model": model._meta.label,
                        "field": root,
                    }
            if self.role == FieldRole.LOOKUP and not self.mapping.updates:
                errors["role"] = _("Only an update or an upsert looks a record up.")
        if errors:
            raise ValidationError(errors)


class HttpMethodChoices(models.TextChoices):
    GET = "GET", "GET"
    POST = "POST", "POST"
    PUT = "PUT", "PUT"
    PATCH = "PATCH", "PATCH"
    DELETE = "DELETE", "DELETE"


class ResponseWebhook(IntegrationBase):
    """Tell another system that a response happened.

    The URL, the headers and the body are all templates over the same response
    document.  A URL takes `{name}` placeholders filled from ``url_params``;
    headers and body are JSON, in which ``{"$jmespath": "answers.email"}``
    anywhere in the tree is replaced by what that expression resolves to.
    """

    method = models.CharField(
        _("method"),
        max_length=10,
        choices=HttpMethodChoices.choices,
        default=HttpMethodChoices.POST,
    )
    url_template = models.CharField(
        _("URL template"),
        max_length=500,
        help_text=_("May hold {placeholders}, each of which needs a URL parameter below."),
    )
    url_params = models.JSONField(
        _("URL parameters"),
        default=dict,
        blank=True,
        help_text=_("Maps each placeholder in the URL to the JMESPath expression that fills it."),
    )
    headers = models.JSONField(
        _("headers"),
        default=dict,
        blank=True,
        help_text=_(
            'Header name to value. Use {"$jmespath": "..."} for a value from the response.'
        ),
    )
    body = models.JSONField(
        _("body"),
        default=dict,
        blank=True,
        help_text=_('Sent as JSON. Any {"$jmespath": "..."} in it is resolved first.'),
    )
    timeout = models.PositiveSmallIntegerField(
        _("timeout"), default=10, validators=[MinValueValidator(1)], help_text=_("In seconds.")
    )

    class Meta:
        verbose_name = _("response webhook")
        verbose_name_plural = _("response webhooks")
        ordering = ["questionnaire", "order", "pk"]

    @property
    def sends_a_body(self) -> bool:
        return self.method in {
            HttpMethodChoices.POST,
            HttpMethodChoices.PUT,
            HttpMethodChoices.PATCH,
        }

    def placeholders(self) -> set[str]:
        return set(URL_PLACEHOLDER.findall(self.url_template))

    def clean(self) -> None:
        super().clean()
        errors: dict[str, Any] = {}
        if not isinstance(self.url_params, dict):
            errors["url_params"] = _("The URL parameters must be an object.")
        else:
            missing = sorted(self.placeholders() - set(self.url_params))
            if missing:
                errors["url_params"] = _("The URL has no expression for: %(names)s.") % {
                    "names": ", ".join(missing)
                }
            unused = sorted(set(self.url_params) - self.placeholders())
            if unused:
                errors["url_params"] = _("The URL has no placeholder for: %(names)s.") % {
                    "names": ", ".join(unused)
                }
            for name, expression in (self.url_params or {}).items():
                try:
                    validate_condition(str(expression))
                except ValidationError as exc:
                    errors[f"url_params.{name}"] = exc
        for field_name in ("headers", "body"):
            value = getattr(self, field_name)
            if not isinstance(value, dict):
                errors[field_name] = _("This must be an object.")
                continue
            try:
                validate_template(value)
            except ValidationError as exc:
                errors[field_name] = exc
        if errors:
            raise ValidationError(errors)


def validate_template(node: Any) -> None:
    """Raise ``ValidationError`` unless every expression in *node* compiles."""
    if isinstance(node, dict):
        if EXPRESSION_KEY in node:
            if len(node) != 1:
                raise ValidationError(
                    _("%(key)s must be the only key of the object it is in.")
                    % {"key": EXPRESSION_KEY}
                )
            validate_condition(str(node[EXPRESSION_KEY]))
            return
        for value in node.values():
            validate_template(value)
    elif isinstance(node, list):
        for value in node:
            validate_template(value)


class DeliveryStatus(models.TextChoices):
    SUCCEEDED = "succeeded", _("Succeeded")
    FAILED = "failed", _("Failed")
    SKIPPED = "skipped", _("Skipped")


class WebhookDelivery(BaseModel):
    """What was sent, and what came back.

    A webhook nobody can see the outcome of is not something anyone can run in
    production, so every attempt is written down -- including the ones that
    never left, because the URL would not build or the condition did not hold.
    """

    webhook = models.ForeignKey(
        ResponseWebhook,
        on_delete=models.CASCADE,
        related_name="deliveries",
        verbose_name=_("webhook"),
    )
    response = models.ForeignKey(
        "vinta_django_questionnaires.QuestionnaireResponse",
        on_delete=models.CASCADE,
        related_name="webhook_deliveries",
        verbose_name=_("questionnaire response"),
    )
    status = models.CharField(_("status"), max_length=10, choices=DeliveryStatus.choices)
    method = models.CharField(_("method"), max_length=10, blank=True, default="")
    url = models.CharField(_("URL"), max_length=1000, blank=True, default="")
    request_body = models.JSONField(_("request body"), default=dict, blank=True)
    status_code = models.PositiveSmallIntegerField(_("status code"), null=True, blank=True)
    response_body = models.TextField(_("response body"), blank=True, default="")
    error = models.TextField(_("error"), blank=True, default="")

    class Meta:
        verbose_name = _("webhook delivery")
        verbose_name_plural = _("webhook deliveries")
        ordering = ["-created_at", "pk"]
        indexes = [models.Index(fields=["webhook", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.status} {self.method} {self.url}".strip()


class MappingRun(BaseModel):
    """What one mapping did to one response.

    The record a mapping wrote is reachable from here, which is what makes an
    upsert that went to the wrong row -- or an insert that ran twice --
    something anyone can look at afterwards.
    """

    mapping = models.ForeignKey(
        ResponseMapping,
        on_delete=models.CASCADE,
        related_name="runs",
        verbose_name=_("mapping"),
    )
    response = models.ForeignKey(
        "vinta_django_questionnaires.QuestionnaireResponse",
        on_delete=models.CASCADE,
        related_name="mapping_runs",
        verbose_name=_("questionnaire response"),
    )
    status = models.CharField(_("status"), max_length=10, choices=DeliveryStatus.choices)
    action = models.CharField(_("action"), max_length=20, blank=True, default="")
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("model")
    )
    object_id = models.CharField(_("object id"), max_length=255, blank=True, default="")
    target = GenericForeignKey("content_type", "object_id")
    values = models.JSONField(_("values"), default=dict, blank=True)
    error = models.TextField(_("error"), blank=True, default="")

    class Meta:
        verbose_name = _("mapping run")
        verbose_name_plural = _("mapping runs")
        ordering = ["-created_at", "pk"]
        indexes = [models.Index(fields=["mapping", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.status} {self.action} {self.object_id}".strip()
