"""Mappings and webhooks: what a response does once it has been given."""

from __future__ import annotations

import json

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from tests.conftest import make_question
from tests.testapp.models import Client
from vinta_django_questionnaires.integrations import (
    WebhookRequest,
    WebhookResult,
    build_request,
    deliver_webhook,
    resolve_template,
    response_document,
    run_integrations,
    run_mapping,
)
from vinta_django_questionnaires.models import (
    DeliveryStatus,
    FieldRole,
    IntegrationTrigger,
    MappingField,
    MappingOperation,
    MappingRun,
    Page,
    QuestionnaireResponse,
    ResponseMapping,
    ResponseWebhook,
    Section,
    WebhookDelivery,
)
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.submissions import start_response, submit_page


@pytest.fixture
def filled(version):
    """A version with one page of answers already given."""
    page = Page.objects.create(questionnaire_version=version, key="about", title="About")
    section = Section.objects.create(page=page, key="basics", title="Basics")
    make_question(section, key="email", title="Email", order=0)
    make_question(section, key="company", title="Company", order=1)
    make_question(
        section, key="headcount", title="Headcount", order=2, question_type=QuestionType.NUMBER
    )
    version.status = "published"
    version.save()
    response = start_response(version, external_id="session:1")
    submit_page(
        response,
        page,
        {"email": "hugo@vinta.com.br", "company": "Vinta", "headcount": 40},
    )
    response.refresh_from_db()
    return response


@pytest.fixture
def client_type(db):
    return ContentType.objects.get_for_model(Client)


def make_mapping(version, client_type, *, operation=MappingOperation.INSERT, **kwargs):
    return ResponseMapping.objects.create(
        key=kwargs.pop("key", "clients"),
        name="Clients",
        questionnaire=version.questionnaire,
        content_type=client_type,
        operation=operation,
        **kwargs,
    )


def add_field(mapping, target_field, expression, **kwargs):
    return MappingField.objects.create(
        mapping=mapping, target_field=target_field, expression=expression, **kwargs
    )


# ------------------------------------------------------------------ document


def test_the_document_carries_the_answers_twice(filled):
    document = response_document(filled)

    assert document["answers"]["email"] == "hugo@vinta.com.br"
    # ...and flat, so an expression reads the same as a condition does.
    assert document["email"] == "hugo@vinta.com.br"
    assert document["questionnaire"] == "intake"
    assert document["status"] == "completed"
    assert json.loads(json.dumps(document))


# ------------------------------------------------------------------ mappings


def test_an_insert_creates_a_record_from_the_expressions(filled, client_type):
    mapping = make_mapping(filled.questionnaire_version, client_type)
    add_field(mapping, "email", "answers.email")
    add_field(mapping, "name", "answers.company")

    outcome = run_mapping(mapping, filled)

    assert outcome.ok
    assert outcome.action == "created"
    client = Client.objects.get()
    assert client.email == "hugo@vinta.com.br"
    assert client.name == "Vinta"


def test_defaults_are_written_and_a_mapped_field_wins(filled, client_type):
    mapping = make_mapping(
        filled.questionnaire_version,
        client_type,
        defaults={"source": "questionnaire", "name": "?"},
    )
    add_field(mapping, "email", "answers.email")
    add_field(mapping, "name", "answers.company")

    run_mapping(mapping, filled)

    client = Client.objects.get()
    assert client.source == "questionnaire"
    assert client.name == "Vinta"


def test_an_update_writes_to_the_record_the_lookup_finds(filled, client_type):
    existing = Client.objects.create(email="hugo@vinta.com.br", name="Old")
    other = Client.objects.create(email="someone@else.com", name="Untouched")
    mapping = make_mapping(
        filled.questionnaire_version, client_type, operation=MappingOperation.UPDATE
    )
    add_field(mapping, "email", "answers.email", role=FieldRole.LOOKUP)
    add_field(mapping, "name", "answers.company")

    outcome = run_mapping(mapping, filled)

    assert outcome.action == "updated"
    existing.refresh_from_db()
    other.refresh_from_db()
    assert existing.name == "Vinta"
    assert other.name == "Untouched"


def test_an_update_that_finds_nothing_is_skipped_rather_than_creating(filled, client_type):
    mapping = make_mapping(
        filled.questionnaire_version, client_type, operation=MappingOperation.UPDATE
    )
    add_field(mapping, "email", "answers.email", role=FieldRole.LOOKUP)
    add_field(mapping, "name", "answers.company")

    outcome = run_mapping(mapping, filled)

    assert outcome.status == DeliveryStatus.SKIPPED
    assert outcome.action == "not_found"
    assert not Client.objects.exists()


def test_an_upsert_creates_when_there_is_nothing_and_updates_when_there_is(filled, client_type):
    mapping = make_mapping(
        filled.questionnaire_version, client_type, operation=MappingOperation.UPSERT
    )
    add_field(mapping, "email", "answers.email", role=FieldRole.LOOKUP)
    add_field(mapping, "name", "answers.company")

    first = run_mapping(mapping, filled)
    assert first.action == "created"
    assert Client.objects.get().email == "hugo@vinta.com.br"

    second = run_mapping(mapping, filled)
    assert second.action == "updated"
    assert Client.objects.count() == 1


def test_an_upsert_writes_its_defaults_only_when_it_creates(filled, client_type):
    mapping = make_mapping(
        filled.questionnaire_version,
        client_type,
        operation=MappingOperation.UPSERT,
        defaults={"source": "first-run"},
    )
    add_field(mapping, "email", "answers.email", role=FieldRole.LOOKUP)
    add_field(mapping, "name", "answers.company")

    run_mapping(mapping, filled)
    Client.objects.update(source="changed-by-hand")
    run_mapping(mapping, filled)

    assert Client.objects.get().source == "changed-by-hand"


def test_defaults_can_be_made_to_apply_on_update_too(filled, client_type):
    mapping = make_mapping(
        filled.questionnaire_version,
        client_type,
        operation=MappingOperation.UPSERT,
        defaults={"source": "questionnaire"},
        update_defaults=True,
    )
    add_field(mapping, "email", "answers.email", role=FieldRole.LOOKUP)

    run_mapping(mapping, filled)
    Client.objects.update(source="changed-by-hand")
    run_mapping(mapping, filled)

    assert Client.objects.get().source == "questionnaire"


def test_a_missing_required_field_abandons_the_whole_mapping(filled, client_type):
    mapping = make_mapping(filled.questionnaire_version, client_type)
    add_field(mapping, "email", "answers.email")
    add_field(mapping, "company", "answers.not_asked", is_required=True)

    outcome = run_mapping(mapping, filled)

    assert outcome.status == DeliveryStatus.SKIPPED
    assert outcome.action == "missing_required"
    assert not Client.objects.exists()


def test_an_unanswered_optional_field_is_left_out_rather_than_nulled(filled, client_type):
    mapping = make_mapping(filled.questionnaire_version, client_type)
    add_field(mapping, "email", "answers.email")
    add_field(mapping, "notes", "answers.not_asked")

    run_mapping(mapping, filled)

    assert Client.objects.get().notes == ""


def test_an_empty_lookup_is_skipped_rather_than_matching_everything(filled, client_type):
    Client.objects.create(email="someone@else.com", name="Untouched")
    mapping = make_mapping(
        filled.questionnaire_version, client_type, operation=MappingOperation.UPDATE
    )
    add_field(mapping, "email", "answers.not_asked", role=FieldRole.LOOKUP)
    add_field(mapping, "name", "answers.company")

    outcome = run_mapping(mapping, filled)

    assert outcome.action == "empty_lookup"
    assert Client.objects.get().name == "Untouched"


def test_a_mapping_whose_condition_does_not_hold_does_nothing(filled, client_type):
    mapping = make_mapping(
        filled.questionnaire_version, client_type, condition="headcount > `100`"
    )
    add_field(mapping, "email", "answers.email")

    outcome = run_mapping(mapping, filled)

    assert outcome.status == DeliveryStatus.SKIPPED
    assert outcome.action == "condition"
    assert not Client.objects.exists()


def test_a_mapping_that_blows_up_is_recorded_rather_than_raised(filled, client_type):
    Client.objects.create(email="hugo@vinta.com.br")
    mapping = make_mapping(filled.questionnaire_version, client_type)
    add_field(mapping, "email", "answers.email")  # the unique constraint will refuse

    outcome = run_mapping(mapping, filled)

    assert outcome.status == DeliveryStatus.FAILED
    assert outcome.error
    assert MappingRun.objects.get().status == DeliveryStatus.FAILED


def test_every_run_is_written_down_with_what_it_touched(filled, client_type):
    mapping = make_mapping(filled.questionnaire_version, client_type)
    add_field(mapping, "email", "answers.email")

    run_mapping(mapping, filled)

    record = MappingRun.objects.get()
    assert record.status == DeliveryStatus.SUCCEEDED
    assert record.target == Client.objects.get()
    assert record.values == {"email": "hugo@vinta.com.br"}


# ---------------------------------------------------------------- validation


def test_a_field_naming_something_the_model_does_not_have_is_refused(filled, client_type):
    mapping = make_mapping(filled.questionnaire_version, client_type)

    with pytest.raises(ValidationError) as raised:
        add_field(mapping, "not_a_field", "answers.email")

    assert "target_field" in raised.value.message_dict


def test_a_field_whose_expression_is_not_jmespath_is_refused(filled, client_type):
    mapping = make_mapping(filled.questionnaire_version, client_type)

    with pytest.raises(ValidationError) as raised:
        add_field(mapping, "email", "answers[")

    assert "expression" in raised.value.message_dict


def test_only_an_update_looks_a_record_up(filled, client_type):
    mapping = make_mapping(filled.questionnaire_version, client_type)

    with pytest.raises(ValidationError) as raised:
        add_field(mapping, "email", "answers.email", role=FieldRole.LOOKUP)

    assert "role" in raised.value.message_dict


def test_an_update_without_a_lookup_is_refused(filled, client_type):
    mapping = make_mapping(
        filled.questionnaire_version, client_type, operation=MappingOperation.UPDATE
    )
    add_field(mapping, "name", "answers.company")

    with pytest.raises(ValidationError) as raised:
        mapping.full_clean()

    assert "operation" in raised.value.message_dict


def test_a_lookup_may_span_a_relation(filled, client_type):
    mapping = make_mapping(
        filled.questionnaire_version, client_type, operation=MappingOperation.UPDATE
    )

    add_field(mapping, "email__iexact", "answers.email", role=FieldRole.LOOKUP)

    assert mapping.lookup_fields().count() == 1


# ------------------------------------------------------------------ webhooks


def make_webhook(version, **kwargs):
    return ResponseWebhook.objects.create(
        key=kwargs.pop("key", "crm"),
        name="CRM",
        questionnaire=version.questionnaire,
        url_template=kwargs.pop("url_template", "https://crm.example.com/leads/"),
        **kwargs,
    )


def test_a_template_resolves_its_expressions_and_leaves_literals_alone(filled):
    document = response_document(filled)

    resolved = resolve_template(
        {
            "source": "questionnaire",
            "email": {"$jmespath": "answers.email"},
            "nested": {"size": {"$jmespath": "answers.headcount"}},
            "list": [{"$jmespath": "answers.company"}, "literal"],
        },
        document,
    )

    assert resolved == {
        "source": "questionnaire",
        "email": "hugo@vinta.com.br",
        "nested": {"size": 40},
        "list": ["Vinta", "literal"],
    }


def test_the_url_takes_its_placeholders_from_expressions(filled):
    webhook = make_webhook(
        filled.questionnaire_version,
        url_template="https://crm.example.com/companies/{company}/leads/",
        url_params={"company": "answers.company"},
    )

    request = build_request(webhook, response_document(filled))

    assert request.url == "https://crm.example.com/companies/Vinta/leads/"


def test_a_url_placeholder_with_no_expression_is_refused_on_save(filled):
    with pytest.raises(ValidationError) as raised:
        make_webhook(
            filled.questionnaire_version,
            url_template="https://crm.example.com/{company}/",
            url_params={},
        )

    assert "url_params" in raised.value.message_dict


def test_an_expression_with_no_placeholder_is_refused_too(filled):
    with pytest.raises(ValidationError) as raised:
        make_webhook(filled.questionnaire_version, url_params={"nothing": "answers.email"})

    assert "url_params" in raised.value.message_dict


def test_a_body_holding_an_expression_that_does_not_compile_is_refused(filled):
    with pytest.raises(ValidationError) as raised:
        make_webhook(filled.questionnaire_version, body={"email": {"$jmespath": "answers["}})

    assert "body" in raised.value.message_dict


def test_a_webhook_sends_what_its_templates_resolve_to(filled, settings, monkeypatch):
    sent = []

    def sender(request: WebhookRequest) -> WebhookResult:
        sent.append(request)
        return WebhookResult(status_code=201, body='{"ok": true}')

    monkeypatch.setattr("vinta_django_questionnaires.integrations.get_sender", lambda: sender)
    webhook = make_webhook(
        filled.questionnaire_version,
        headers={"X-Source": "questionnaires", "X-Company": {"$jmespath": "answers.company"}},
        body={"email": {"$jmespath": "answers.email"}, "size": {"$jmespath": "answers.headcount"}},
    )

    delivery = deliver_webhook(webhook, filled)
    assert delivery is not None

    assert sent[0].method == "POST"
    assert sent[0].headers == {"X-Source": "questionnaires", "X-Company": "Vinta"}
    assert sent[0].body == {"email": "hugo@vinta.com.br", "size": 40}
    assert delivery.status == DeliveryStatus.SUCCEEDED
    assert delivery.status_code == 201


def test_a_get_webhook_sends_no_body(filled, monkeypatch):
    sent = []

    def sender(request: WebhookRequest) -> WebhookResult:
        sent.append(request)
        return WebhookResult(status_code=200)

    monkeypatch.setattr("vinta_django_questionnaires.integrations.get_sender", lambda: sender)
    webhook = make_webhook(filled.questionnaire_version, method="GET", body={"a": 1})

    deliver_webhook(webhook, filled)

    assert sent[0].body is None


def test_a_webhook_that_fails_is_recorded_and_raises_nothing(filled, monkeypatch):
    monkeypatch.setattr(
        "vinta_django_questionnaires.integrations.get_sender",
        lambda: lambda request: WebhookResult(status_code=500, body="boom", error="Server error"),
    )
    webhook = make_webhook(filled.questionnaire_version)

    delivery = deliver_webhook(webhook, filled)
    assert delivery is not None

    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.status_code == 500
    assert delivery.error == "Server error"


def test_a_webhook_whose_condition_does_not_hold_is_recorded_as_skipped(filled, monkeypatch):
    monkeypatch.setattr(
        "vinta_django_questionnaires.integrations.get_sender",
        lambda: pytest.fail,
    )
    webhook = make_webhook(filled.questionnaire_version, condition="headcount > `100`")

    delivery = deliver_webhook(webhook, filled)
    assert delivery is not None

    assert delivery.status == DeliveryStatus.SKIPPED


def test_a_url_that_will_not_build_is_recorded_rather_than_raised(filled, monkeypatch):
    monkeypatch.setattr("vinta_django_questionnaires.integrations.get_sender", lambda: pytest.fail)
    webhook = make_webhook(
        filled.questionnaire_version,
        url_template="https://crm.example.com/{missing}/",
        url_params={"missing": "answers.not_asked"},
    )

    delivery = deliver_webhook(webhook, filled)
    assert delivery is not None

    assert delivery.status == DeliveryStatus.SKIPPED
    assert "missing" in delivery.error


# ------------------------------------------------------------------- running


def test_running_a_trigger_does_the_mappings_and_the_webhooks(filled, client_type, monkeypatch):
    monkeypatch.setattr(
        "vinta_django_questionnaires.integrations.get_sender",
        lambda: lambda request: WebhookResult(status_code=200),
    )
    mapping = make_mapping(filled.questionnaire_version, client_type)
    add_field(mapping, "email", "answers.email")
    make_webhook(filled.questionnaire_version)

    report = run_integrations(filled, trigger=IntegrationTrigger.ON_COMPLETION)

    assert [outcome.action for outcome in report.mappings] == ["created"]
    assert [delivery.status for delivery in report.deliveries] == [DeliveryStatus.SUCCEEDED]
    assert report.failed == []


def test_an_integration_pinned_to_another_version_does_not_run(filled, client_type):
    other = QuestionnaireResponse.objects.create(
        questionnaire_version=filled.questionnaire_version
    ).questionnaire_version
    mapping = make_mapping(filled.questionnaire_version, client_type)
    add_field(mapping, "email", "answers.email")
    mapping.questionnaire_version = other
    mapping.save()

    assert run_integrations(filled).mappings  # same version, so it does run

    mapping.is_active = False
    mapping.save()
    assert run_integrations(filled).mappings == []


def test_submitting_the_last_page_runs_the_completion_integrations(
    version, client_type, monkeypatch, django_capture_on_commit_callbacks
):
    page = Page.objects.create(questionnaire_version=version, key="about", title="About")
    section = Section.objects.create(page=page, key="basics", title="Basics")
    make_question(section, key="email", title="Email")
    version.status = "published"
    version.save()
    mapping = make_mapping(version, client_type)
    add_field(mapping, "email", "answers.email")

    response = start_response(version, external_id="session:2")
    with django_capture_on_commit_callbacks(execute=True):
        submit_page(response, page, {"email": "hugo@vinta.com.br"})

    assert Client.objects.get().email == "hugo@vinta.com.br"


def test_integrations_can_be_turned_off_for_a_task_queue(
    version, client_type, settings, django_capture_on_commit_callbacks
):
    settings.QUESTIONNAIRES_RUN_INTEGRATIONS = False
    page = Page.objects.create(questionnaire_version=version, key="about", title="About")
    section = Section.objects.create(page=page, key="basics", title="Basics")
    make_question(section, key="email", title="Email")
    version.status = "published"
    version.save()
    mapping = make_mapping(version, client_type)
    add_field(mapping, "email", "answers.email")

    response = start_response(version, external_id="session:3")
    with django_capture_on_commit_callbacks(execute=True):
        submit_page(response, page, {"email": "hugo@vinta.com.br"})

    assert not Client.objects.exists()
    assert not WebhookDelivery.objects.exists()
