"""The authoring API: the catalog, the document, and who is allowed near them."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from tests.conftest import make_question
from vinta_django_questionnaires.definition import definition_document
from vinta_django_questionnaires.models import (
    AcknowledgedEdit,
    Page,
    Question,
    QuestionnaireResponse,
    Section,
)


@pytest.fixture
def author(db):
    return get_user_model().objects.create_user(
        username="author", password="questionnaires", is_staff=True
    )


@pytest.fixture
def respondent(db):
    return get_user_model().objects.create_user(username="hugo", password="questionnaires")


@pytest.fixture
def authored(version, ranges):
    page = Page.objects.create(questionnaire_version=version, key="about", title="About")
    section = Section.objects.create(page=page, key="basics", title="Basics")
    make_question(section, key="name", title="Your name")
    return version


def definition_url(version):
    return reverse(
        "questionnaires-authoring:version-definition",
        kwargs={"questionnaire_key": version.questionnaire.key, "version": version.version},
    )


def put(client, url, payload):
    return client.put(url, data=json.dumps(payload), content_type="application/json")


# ------------------------------------------------------------------- access


def test_the_catalog_is_staff_only(client, respondent):
    client.force_login(respondent)

    response = client.get(reverse("questionnaires-authoring:catalog"))

    assert response.status_code == 403


def test_an_anonymous_visitor_gets_nowhere(client, authored):
    assert client.get(definition_url(authored)).status_code == 403


def test_an_author_reads_the_catalog(client, author, authored):
    client.force_login(author)

    payload = client.get(reverse("questionnaires-authoring:catalog")).json()

    assert payload["catalogVersion"] == 1
    assert payload["questionTypes"]
    assert payload["validators"]


# ------------------------------------------------------------------ reading


def test_an_author_reads_a_version_as_a_document(client, author, authored):
    client.force_login(author)

    payload = client.get(definition_url(authored)).json()

    assert payload["document"]["pages"][0]["key"] == "about"


def test_the_list_says_what_there_is_to_edit(client, author, authored):
    client.force_login(author)

    payload = client.get(reverse("questionnaires-authoring:questionnaire-list")).json()

    assert payload["questionnaires"][0]["key"] == "intake"
    assert payload["questionnaires"][0]["versions"][0]["responseCount"] == 0


# ------------------------------------------------------------------ writing


def test_putting_a_document_applies_it(client, author, authored):
    client.force_login(author)
    document = definition_document(authored)
    document["pages"][0]["title"] = "About you"

    response = put(client, definition_url(authored), {"document": document})

    assert response.status_code == 200
    assert response.json()["document"]["pages"][0]["title"] == "About you"
    assert Page.objects.get(key="about").title == "About you"


def test_a_document_that_does_not_hold_up_comes_back_as_422(client, author, authored):
    client.force_login(author)
    document = definition_document(authored)
    document["pages"][0]["sections"][0]["questions"][0]["questionType"] = "nope"

    response = put(client, definition_url(authored), {"document": document})

    assert response.status_code == 422
    issue = response.json()["issues"][0]
    assert issue["path"] == "pages.0.sections.0.questions.0"
    assert issue["errors"]["question_type"]


def test_editing_a_version_with_responses_needs_the_box_ticked(client, author, authored):
    client.force_login(author)
    QuestionnaireResponse.objects.create(questionnaire_version=authored)
    document = definition_document(authored)
    document["pages"][0]["sections"][0]["questions"][0]["title"] = "Full name"

    refused = put(client, definition_url(authored), {"document": document})
    assert refused.status_code == 422
    assert Question.objects.get(key="name").title == "Your name"

    accepted = put(
        client,
        definition_url(authored),
        {
            "document": document,
            "acknowledgement": {"understood": True, "reason": "Clearer wording"},
        },
    )

    assert accepted.status_code == 200
    assert Question.objects.get(key="name").title == "Full name"
    record = AcknowledgedEdit.objects.get(target_key="name")
    assert record.acknowledged_by is not None
    assert record.acknowledged_by.username == "author"
    assert record.reason == "Clearer wording"


def test_a_body_without_a_document_is_a_bad_request(client, author, authored):
    client.force_login(author)

    assert put(client, definition_url(authored), {}).status_code == 400


# ------------------------------------------------------------------ forking


def test_forking_copies_the_version_into_a_new_draft(client, author, authored):
    client.force_login(author)
    url = reverse(
        "questionnaires-authoring:version-fork",
        kwargs={"questionnaire_key": "intake", "version": 1},
    )

    response = client.post(url, data="{}", content_type="application/json")

    assert response.status_code == 201
    document = response.json()["document"]
    assert document["version"] == 2
    assert document["status"] == "draft"
    assert document["pages"][0]["sections"][0]["questions"][0]["key"] == "name"
    assert authored.questionnaire.versions.count() == 2
