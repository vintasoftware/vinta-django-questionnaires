"""Running the mappings and the webhooks a response triggers.

The document every expression here is evaluated against is the same one
conditions see, with a little more around it::

    {
        "id": "…", "status": "completed", "questionnaire": "intake",
        "version": 2, "respondent": {...}, "context": {...},
        "answers": {"email": "hugo@vinta.com.br", ...},
        # …and every answer at the top level too, so `email` works as well as
        # `answers.email` -- which is what conditions already do.
    }

Nothing in here is allowed to break a submission.  Each mapping and each
webhook is run on its own and its outcome written down; a failure is a record,
not an exception the respondent sees.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.module_loading import import_string

from vinta_django_questionnaires.conditions import compile_condition, evaluate_condition
from vinta_django_questionnaires.models import (
    DeliveryStatus,
    FieldRole,
    IntegrationTrigger,
    MappingOperation,
    MappingRun,
    ResponseMapping,
    ResponseWebhook,
    WebhookDelivery,
)
from vinta_django_questionnaires.models.integrations import EXPRESSION_KEY, URL_PLACEHOLDER

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import Model

    from vinta_django_questionnaires.models import QuestionnaireResponse

logger = logging.getLogger(__name__)

#: Set ``QUESTIONNAIRES_RUN_INTEGRATIONS = False`` to stop the submission layer
#: running these inline -- for a project that hands them to a task queue.
RUN_SETTING = "QUESTIONNAIRES_RUN_INTEGRATIONS"
#: Dotted path to ``send(request: WebhookRequest) -> WebhookResult``.
SENDER_SETTING = "QUESTIONNAIRES_WEBHOOK_SENDER"


# ------------------------------------------------------------------ document


def response_document(response: QuestionnaireResponse) -> dict[str, Any]:
    """What every expression of an integration is evaluated against."""
    answers = response.answers
    version = response.questionnaire_version
    return {
        **answers,
        "answers": answers,
        "context": dict(response.context or {}),
        "id": str(response.uuid),
        "status": response.status,
        "questionnaire": version.questionnaire.key,
        "version": version.version,
        # The tenant this response belongs to, so a URL template can say
        # `{scope}` and a shared questionnaire can still reach the right place.
        "scope": response.scope_key,
        "external_id": response.external_id,
        "respondent": _respondent(response),
        "completed_at": response.completed_at.isoformat() if response.completed_at else None,
        "created_at": response.created_at.isoformat() if response.created_at else None,
    }


def _respondent(response: QuestionnaireResponse) -> dict[str, Any] | None:
    user = response.respondent if response.respondent_id else None
    if user is None:
        return None
    return {
        "id": user.pk,
        "username": user.get_username(),
        "email": getattr(user, "email", ""),
    }


def resolve(expression: str, document: dict[str, Any]) -> Any:
    """Evaluate one expression, returning ``None`` rather than raising."""
    if not expression.strip():
        return None
    return compile_condition(expression).search(document)


def resolve_template(node: Any, document: dict[str, Any]) -> Any:
    """A JSON tree with every ``{"$jmespath": "..."}`` in it evaluated."""
    if isinstance(node, dict):
        if EXPRESSION_KEY in node and len(node) == 1:
            return resolve(str(node[EXPRESSION_KEY]), document)
        return {key: resolve_template(value, document) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve_template(value, document) for value in node]
    return node


# ------------------------------------------------------------------ mappings


@dataclass
class MappingOutcome:
    """What one mapping did."""

    mapping: ResponseMapping
    status: str
    action: str = ""
    target: Any = None
    values: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == DeliveryStatus.SUCCEEDED


def mappings_for(response: QuestionnaireResponse, *, trigger: str) -> list[ResponseMapping]:
    version = response.questionnaire_version
    return [
        mapping
        for mapping in ResponseMapping.objects.filter(
            questionnaire=version.questionnaire, is_active=True, trigger=trigger
        ).select_related("content_type", "scope")
        if mapping.applies_to(version) and mapping.applies_to_scope(response.scope_key)
    ]


def run_mapping(
    mapping: ResponseMapping,
    response: QuestionnaireResponse,
    *,
    document: dict[str, Any] | None = None,
    record: bool = True,
) -> MappingOutcome:
    """Apply one mapping to one response."""
    document = response_document(response) if document is None else document
    outcome = _apply_mapping(mapping, document)
    if record:
        _record_mapping(mapping, response, outcome)
    return outcome


def _apply_mapping(mapping: ResponseMapping, document: dict[str, Any]) -> MappingOutcome:
    if not evaluate_condition(mapping.condition, document):
        return MappingOutcome(mapping=mapping, status=DeliveryStatus.SKIPPED, action="condition")

    model = mapping.model
    if model is None:  # pragma: no cover -- the app was uninstalled since
        return MappingOutcome(
            mapping=mapping, status=DeliveryStatus.FAILED, error="That model is not installed."
        )

    try:
        values, missing = _resolve_fields(mapping.value_fields(), document)
    except Exception as exc:
        return MappingOutcome(mapping=mapping, status=DeliveryStatus.FAILED, error=str(exc))
    if missing:
        return MappingOutcome(
            mapping=mapping,
            status=DeliveryStatus.SKIPPED,
            action="missing_required",
            values=values,
            error=f"No value for: {', '.join(missing)}.",
        )

    lookup: dict[str, Any] = {}
    if mapping.updates:
        try:
            lookup, missing = _resolve_fields(mapping.lookup_fields(), document)
        except Exception as exc:
            return MappingOutcome(mapping=mapping, status=DeliveryStatus.FAILED, error=str(exc))
        empty = [name for name, value in lookup.items() if value in (None, "")]
        if (missing or empty) and mapping.skip_when_lookup_is_empty:
            return MappingOutcome(
                mapping=mapping,
                status=DeliveryStatus.SKIPPED,
                action="empty_lookup",
                values=values,
                error=f"No value to look up by: {', '.join(missing or empty)}.",
            )

    try:
        with transaction.atomic():
            return _write(mapping, model, lookup, values)
    except Exception as exc:
        logger.exception("Questionnaire mapping %s failed", mapping.key)
        return MappingOutcome(
            mapping=mapping, status=DeliveryStatus.FAILED, values=values, error=str(exc)
        )


def _write(
    mapping: ResponseMapping,
    model: type[Model],
    lookup: dict[str, Any],
    values: dict[str, Any],
) -> MappingOutcome:
    defaults = dict(mapping.defaults or {})
    if mapping.operation == MappingOperation.INSERT:
        target = model._default_manager.create(**{**defaults, **values})
        return MappingOutcome(
            mapping=mapping,
            status=DeliveryStatus.SUCCEEDED,
            action="created",
            target=target,
            values=values,
        )

    existing = model._default_manager.filter(**lookup).first()
    if existing is None:
        if mapping.operation == MappingOperation.UPDATE:
            return MappingOutcome(
                mapping=mapping,
                status=DeliveryStatus.SKIPPED,
                action="not_found",
                values=values,
                error="Nothing matched the lookup.",
            )
        # An upsert creates it, and the lookup is what identifies it.
        target = model._default_manager.create(**{**defaults, **lookup, **values})
        return MappingOutcome(
            mapping=mapping,
            status=DeliveryStatus.SUCCEEDED,
            action="created",
            target=target,
            values={**lookup, **values},
        )

    written = {**defaults, **values} if mapping.update_defaults else values
    for name, value in written.items():
        setattr(existing, name, value)
    existing.save()
    return MappingOutcome(
        mapping=mapping,
        status=DeliveryStatus.SUCCEEDED,
        action="updated",
        target=existing,
        values=written,
    )


def _resolve_fields(
    fields: Iterable[Any], document: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Every field's expression, and the names of the required ones with nothing in them."""
    values: dict[str, Any] = {}
    missing: list[str] = []
    for mapped in fields:
        value = resolve(mapped.expression, document)
        if value is None and mapped.is_required:
            missing.append(mapped.target_field)
            continue
        if value is None and mapped.role == FieldRole.VALUE:
            # An unanswered optional question does not overwrite what is there.
            continue
        values[mapped.target_field] = value
    return values, missing


def _record_mapping(
    mapping: ResponseMapping, response: QuestionnaireResponse, outcome: MappingOutcome
) -> MappingRun:
    target = outcome.target
    return MappingRun.objects.create(
        mapping=mapping,
        response=response,
        status=outcome.status,
        action=outcome.action,
        content_type=ContentType.objects.get_for_model(type(target)) if target else None,
        object_id=str(target.pk) if target else "",
        values=_jsonable(outcome.values),
        error=outcome.error,
    )


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
    except TypeError:
        return {key: str(entry) for key, entry in (value or {}).items()}
    return value


# ------------------------------------------------------------------ webhooks


@dataclass(frozen=True)
class WebhookRequest:
    """What a sender is handed."""

    method: str
    url: str
    headers: dict[str, str]
    body: Any
    timeout: int


@dataclass(frozen=True)
class WebhookResult:
    """What a sender hands back."""

    status_code: int | None = None
    body: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.error == "" and self.status_code is not None and 200 <= self.status_code < 300


def send_with_urllib(request: WebhookRequest) -> WebhookResult:
    """The default sender: the standard library, so there is no new dependency."""
    data = None
    headers = dict(request.headers)
    if request.body is not None and request.method in {"POST", "PUT", "PATCH"}:
        data = json.dumps(request.body).encode()
        headers.setdefault("Content-Type", "application/json")
    prepared = urllib.request.Request(
        request.url, data=data, headers=headers, method=request.method
    )
    try:
        with urllib.request.urlopen(prepared, timeout=request.timeout) as reply:
            return WebhookResult(status_code=reply.status, body=_read(reply))
    except urllib.error.HTTPError as exc:
        return WebhookResult(status_code=exc.code, body=_read(exc), error=str(exc))
    except Exception as exc:
        return WebhookResult(error=str(exc))


def _read(reply: Any, limit: int = 4000) -> str:
    try:
        return str(reply.read(limit).decode(errors="replace"))
    except Exception:
        return ""


def get_sender() -> Any:
    """The configured sender, or the standard library one."""
    path = getattr(settings, SENDER_SETTING, None)
    return import_string(path) if path else send_with_urllib


def webhooks_for(response: QuestionnaireResponse, *, trigger: str) -> list[ResponseWebhook]:
    version = response.questionnaire_version
    return [
        webhook
        for webhook in ResponseWebhook.objects.filter(
            questionnaire=version.questionnaire, is_active=True, trigger=trigger
        ).select_related("scope")
        if webhook.applies_to(version) and webhook.applies_to_scope(response.scope_key)
    ]


def build_request(webhook: ResponseWebhook, document: dict[str, Any]) -> WebhookRequest:
    """The request this webhook would send for *document*."""
    params = {
        name: resolve(str(expression), document)
        for name, expression in (webhook.url_params or {}).items()
    }
    missing = [name for name, value in params.items() if value is None]
    if missing:
        raise ValueError(f"The URL needs values for: {', '.join(sorted(missing))}.")
    url = URL_PLACEHOLDER.sub(lambda match: str(params[match.group(1)]), webhook.url_template)

    headers = {
        str(name): "" if value is None else str(value)
        for name, value in (resolve_template(webhook.headers or {}, document) or {}).items()
    }
    body = resolve_template(webhook.body or {}, document) if webhook.sends_a_body else None
    return WebhookRequest(
        method=webhook.method, url=url, headers=headers, body=body, timeout=webhook.timeout
    )


def deliver_webhook(
    webhook: ResponseWebhook,
    response: QuestionnaireResponse,
    *,
    document: dict[str, Any] | None = None,
    record: bool = True,
) -> WebhookDelivery | None:
    """Send one webhook, and write down what happened either way."""
    document = response_document(response) if document is None else document

    if not evaluate_condition(webhook.condition, document):
        return (
            _record_delivery(
                webhook, response, DeliveryStatus.SKIPPED, error="The condition did not hold."
            )
            if record
            else None
        )

    try:
        request = build_request(webhook, document)
    except Exception as exc:
        return (
            _record_delivery(webhook, response, DeliveryStatus.SKIPPED, error=str(exc))
            if record
            else None
        )

    result = get_sender()(request)
    if not record:
        return None
    return _record_delivery(
        webhook,
        response,
        DeliveryStatus.SUCCEEDED if result.ok else DeliveryStatus.FAILED,
        request=request,
        result=result,
    )


def _record_delivery(
    webhook: ResponseWebhook,
    response: QuestionnaireResponse,
    status: str,
    *,
    request: WebhookRequest | None = None,
    result: WebhookResult | None = None,
    error: str = "",
) -> WebhookDelivery:
    return WebhookDelivery.objects.create(
        webhook=webhook,
        response=response,
        status=status,
        method=request.method if request else webhook.method,
        url=(request.url if request else webhook.url_template)[:1000],
        request_body=_jsonable(request.body if request else {}) or {},
        status_code=result.status_code if result else None,
        response_body=(result.body if result else "")[:4000],
        error=error or (result.error if result else ""),
    )


# ---------------------------------------------------------------- the runner


@dataclass
class IntegrationReport:
    """Everything one trigger produced."""

    mappings: list[MappingOutcome] = field(default_factory=list)
    deliveries: list[WebhookDelivery] = field(default_factory=list)

    @property
    def failed(self) -> list[Any]:
        return [
            outcome for outcome in self.mappings if outcome.status == DeliveryStatus.FAILED
        ] + [delivery for delivery in self.deliveries if delivery.status == DeliveryStatus.FAILED]


def run_integrations(
    response: QuestionnaireResponse, *, trigger: str = IntegrationTrigger.ON_COMPLETION
) -> IntegrationReport:
    """Run every mapping and webhook that *trigger* applies to."""
    document = response_document(response)
    report = IntegrationReport()
    for mapping in mappings_for(response, trigger=trigger):
        report.mappings.append(run_mapping(mapping, response, document=document))
    for webhook in webhooks_for(response, trigger=trigger):
        delivery = deliver_webhook(webhook, response, document=document)
        if delivery is not None:
            report.deliveries.append(delivery)
    return report


def integrations_are_enabled() -> bool:
    return bool(getattr(settings, RUN_SETTING, True))


__all__ = [
    "IntegrationReport",
    "MappingOutcome",
    "WebhookRequest",
    "WebhookResult",
    "build_request",
    "deliver_webhook",
    "get_sender",
    "integrations_are_enabled",
    "resolve",
    "resolve_template",
    "response_document",
    "run_integrations",
    "run_mapping",
    "send_with_urllib",
]
