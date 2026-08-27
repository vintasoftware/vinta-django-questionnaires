"""Responses as a table, and the endpoints that serve one."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from tests.conftest import make_question
from vinta_django_questionnaires.models import Page, Questionnaire, QuestionnaireVersion, Section
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.reporting import (
    Column,
    as_cell,
    columns_for,
    csv_rows,
    default_columns,
    response_queryset,
    rows_for,
    select_columns,
)
from vinta_django_questionnaires.submissions import start_response, submit_page


@pytest.fixture
def answered(version):
    """Three responses to a two-question version, one of them unfinished."""
    page = Page.objects.create(questionnaire_version=version, key="about", title="About")
    section = Section.objects.create(page=page, key="basics", title="Basics")
    make_question(section, key="email", title="Email", order=0)
    make_question(
        section,
        key="languages",
        title="Languages",
        order=1,
        question_type=QuestionType.MULTIPLE_CHOICE,
    )
    version.status = "published"
    version.save()

    for index, email in enumerate(["a@vinta.com.br", "b@vinta.com.br"]):
        response = start_response(version, external_id=f"session:{index}")
        submit_page(response, page, {"email": email, "languages": ["python", "typescript"]})
    start_response(version, external_id="session:unfinished")
    return version


@pytest.fixture
def author(db):
    return get_user_model().objects.create_user(
        username="author", password="questionnaires", is_staff=True
    )


# ------------------------------------------------------------------ columns


def test_the_columns_are_the_metadata_plus_one_per_question(answered):
    columns = columns_for(answered)

    assert [column.key for column in columns if column.group == "answer"] == [
        "email",
        "languages",
    ]
    assert "status" in {column.key for column in columns if column.group == "meta"}
    email = next(column for column in columns if column.key == "email")
    assert email.page == "About"
    assert email.section == "Basics"
    assert email.question_type == QuestionType.FREE_TEXT


def test_without_a_version_there_are_only_metadata_columns():
    assert {column.group for column in columns_for(None)} == {"meta"}


def test_the_default_view_is_the_useful_metadata_and_the_first_questions(answered):
    keys = default_columns(answered)

    assert keys[0] == "id"
    assert "email" in keys
    assert "external_id" not in keys


def test_picking_columns_keeps_the_order_asked_for_and_drops_the_unknown(answered):
    picked = select_columns(columns_for(answered), ["email", "nope", "status"])

    assert [column.key for column in picked] == ["email", "status"]


def test_asking_for_nothing_gets_everything(answered):
    assert len(select_columns(columns_for(answered), [])) == len(columns_for(answered))


# --------------------------------------------------------------------- rows


def test_a_row_holds_the_metadata_and_the_answers(answered):
    columns = select_columns(columns_for(answered), ["id", "status", "email", "languages"])
    responses = list(response_queryset(questionnaire="intake").order_by("created_at"))

    rows = rows_for(responses, columns)

    assert rows[0]["email"] == "a@vinta.com.br"
    assert rows[0]["languages"] == ["python", "typescript"]
    assert rows[0]["status"] == "completed"
    assert rows[2]["email"] is None


def test_the_rows_of_a_page_take_one_query_whatever_the_row_count(
    answered, django_assert_num_queries
):
    """The listing must not cost a query per row, which is what a table is for."""
    columns = select_columns(columns_for(answered), ["id", "email", "progress", "status"])
    responses = list(response_queryset())

    with django_assert_num_queries(1):
        rows_for(responses, columns)


def test_filtering_narrows_the_queryset(answered):
    assert response_queryset(questionnaire="intake").count() == 3
    assert response_queryset(status="completed").count() == 2
    assert response_queryset(questionnaire="nope").count() == 0
    assert response_queryset(search="unfinished").count() == 1


# ---------------------------------------------------------------------- CSV


def test_a_cell_holds_whatever_the_answer_was():
    assert as_cell(None) == ""
    assert as_cell("hugo") == "hugo"
    assert as_cell(40) == "40"
    assert as_cell(True) == "true"
    assert as_cell(["python", "typescript"]) == "python, typescript"
    # Nothing flat to fall back on, so it goes in as the JSON it already is.
    assert as_cell({"monday": ["morning"]}) == '{"monday": ["morning"]}'


def test_the_export_streams_a_header_and_a_line_per_response(answered):
    columns = select_columns(columns_for(answered), ["status", "email", "languages"])

    text = "".join(csv_rows(response_queryset(questionnaire="intake"), columns, chunk_size=2))
    lines = [line for line in text.splitlines() if line]

    assert lines[0] == "Status,Email,Languages"
    assert len(lines) == 4
    assert '"python, typescript"' in text


# ----------------------------------------------------------------- the API


def test_the_listing_is_staff_only(client, answered, db):
    assert client.get(reverse("questionnaires-authoring:response-list")).status_code == 403


def test_the_listing_carries_the_columns_with_the_rows(client, author, answered):
    client.force_login(author)

    payload = client.get(
        reverse("questionnaires-authoring:response-list"), {"questionnaire": "intake"}
    ).json()

    assert payload["total"] == 3
    assert payload["page"] == 1
    assert "email" in {column["key"] for column in payload["columns"]}
    assert payload["results"][0]["id"]


def test_the_listing_paginates(client, author, answered):
    client.force_login(author)
    url = reverse("questionnaires-authoring:response-list")

    first = client.get(url, {"questionnaire": "intake", "pageSize": 2}).json()
    second = client.get(url, {"questionnaire": "intake", "pageSize": 2, "page": 2}).json()

    assert len(first["results"]) == 2
    assert len(second["results"]) == 1
    assert first["totalPages"] == 2


def test_the_listing_returns_only_the_columns_asked_for(client, author, answered):
    client.force_login(author)

    payload = client.get(
        reverse("questionnaires-authoring:response-list"),
        {"questionnaire": "intake", "columns": "id,email"},
    ).json()

    assert payload["selectedColumns"] == ["id", "email"]
    assert set(payload["results"][0]) == {"id", "email"}
    # ...and still says what else there was to pick.
    assert len(payload["columns"]) > 2


def test_a_page_size_that_is_not_a_number_is_a_bad_request(client, author, answered):
    client.force_login(author)

    response = client.get(reverse("questionnaires-authoring:response-list"), {"pageSize": "lots"})

    assert response.status_code == 400


def test_the_export_is_csv_named_after_the_questionnaire(client, author, answered):
    client.force_login(author)

    response = client.get(
        reverse("questionnaires-authoring:response-export"),
        {"questionnaire": "intake", "columns": "status,email"},
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"] == 'attachment; filename="intake-responses.csv"'
    body = b"".join(response.streaming_content).decode()
    assert body.splitlines()[0] == "Status,Email"
    assert "a@vinta.com.br" in body


# ------------------------------------------------------- creating and deleting


def test_an_author_creates_a_questionnaire_and_its_first_draft(client, author, db):
    client.force_login(author)

    response = client.post(
        reverse("questionnaires-authoring:questionnaire-create"),
        data=json.dumps({"key": "onboarding", "name": "Onboarding"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    document = response.json()["document"]
    assert document["questionnaire"]["key"] == "onboarding"
    assert document["version"] == 1
    assert document["status"] == "draft"
    assert QuestionnaireVersion.objects.filter(questionnaire__key="onboarding").count() == 1


def test_a_key_that_is_taken_is_refused(client, author, version):
    client.force_login(author)

    response = client.post(
        reverse("questionnaires-authoring:questionnaire-create"),
        data=json.dumps({"key": "intake", "name": "Intake again"}),
        content_type="application/json",
    )

    assert response.status_code == 400


def test_a_draft_can_be_deleted(client, author, version):
    client.force_login(author)

    response = client.delete(
        reverse(
            "questionnaires-authoring:version-definition",
            kwargs={"questionnaire_key": "intake", "version": 1},
        )
    )

    assert response.status_code == 204
    assert not QuestionnaireVersion.objects.exists()


def test_a_version_with_responses_is_not_deleted(client, author, answered):
    client.force_login(author)

    response = client.delete(
        reverse(
            "questionnaires-authoring:version-definition",
            kwargs={"questionnaire_key": "intake", "version": 1},
        )
    )

    assert response.status_code == 400
    assert QuestionnaireVersion.objects.exists()


def test_a_questionnaire_with_no_responses_can_be_deleted_whole(client, author, version):
    client.force_login(author)

    response = client.delete(
        reverse(
            "questionnaires-authoring:questionnaire-detail",
            kwargs={"questionnaire_key": "intake"},
        )
    )

    assert response.status_code == 204
    assert not Questionnaire.objects.exists()


def test_a_questionnaire_that_has_been_answered_is_not(client, author, answered):
    client.force_login(author)

    response = client.delete(
        reverse(
            "questionnaires-authoring:questionnaire-detail",
            kwargs={"questionnaire_key": "intake"},
        )
    )

    assert response.status_code == 400
    assert Questionnaire.objects.exists()


def test_the_column_dictionary_is_json(answered):
    assert json.loads(json.dumps([column.as_dict() for column in columns_for(answered)]))
    assert Column(key="a", label="A", group="meta").as_dict()["label"] == "A"
