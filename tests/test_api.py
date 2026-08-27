"""The response API."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from tests.conftest import make_question
from vinta_django_questionnaires.models import (
    EditPolicy,
    Page,
    QuestionValidator,
    Section,
    SkipReason,
    ValueSet,
    ValueSetOption,
    ValueSetSource,
)
from vinta_django_questionnaires.submissions import start_response


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="hugo", password="questionnaires")


@pytest.fixture
def published(version):
    about = Page.objects.create(questionnaire_version=version, key="about", title="About", order=0)
    section = Section.objects.create(page=about, key="basics", title="Basics")
    name = make_question(section, key="name", title="Name")
    QuestionValidator.objects.create(question=name, validator="required")
    QuestionValidator.objects.create(
        question=name, validator="min_length", order=1, params={"minimum": 2}
    )

    extras = Page.objects.create(
        questionnaire_version=version, key="extras", title="Extras", order=1, is_skippable=True
    )
    Section.objects.create(page=extras, key="more", title="More")
    make_question(extras.sections.get(key="more"), key="notes", title="Notes")

    version.publish()
    return version


def post(client, url, payload=None):
    return client.post(url, data=json.dumps(payload or {}), content_type="application/json")


class TestOpeningAResponse:
    def test_it_needs_a_signed_in_respondent(self, client, published):
        result = post(
            client, reverse("questionnaires:response-create"), {"questionnaire": "intake"}
        )

        assert result.status_code == 403

    def test_it_returns_the_plan_and_where_to_start(self, client, user, published):
        client.force_login(user)

        result = post(
            client, reverse("questionnaires:response-create"), {"questionnaire": "intake"}
        )

        assert result.status_code == 201
        body = result.json()
        assert body["questionnaire"] == "intake"
        assert body["progress"]["current"] == "about"
        assert [page["key"] for page in body["plan"]["pages"]] == ["about", "extras"]
        assert body["plan"]["pages"][1]["isSkippable"] is True

    def test_an_unpublished_questionnaire_is_not_offered(self, client, user, version):
        client.force_login(user)

        result = post(
            client, reverse("questionnaires:response-create"), {"questionnaire": "intake"}
        )

        assert result.status_code == 400
        assert "no published version" in result.json()["detail"]


class TestPushingAPage:
    @pytest.fixture
    def response(self, user, published):
        return start_response(published, respondent=user)

    def test_it_records_the_page_and_reports_the_progress(self, client, user, response):
        client.force_login(user)

        result = post(
            client,
            reverse(
                "questionnaires:page-submit",
                kwargs={"response_uuid": response.uuid, "page_key": "about"},
            ),
            {"answers": {"name": "Hugo"}},
        )

        assert result.status_code == 200
        body = result.json()
        assert body["page"]["status"] == "completed"
        assert body["response"]["answers"] == {"name": "Hugo"}
        assert body["response"]["progress"]["current"] == "extras"

    def test_it_returns_the_issues_per_question(self, client, user, response):
        client.force_login(user)

        result = post(
            client,
            reverse(
                "questionnaires:page-submit",
                kwargs={"response_uuid": response.uuid, "page_key": "about"},
            ),
            {"answers": {"name": "H"}},
        )

        assert result.status_code == 422
        assert result.json() == {
            "errors": {
                "name": [
                    {
                        "validator": "min_length",
                        "errorKey": "too_short",
                        "message": "Use at least 2 characters.",
                    }
                ]
            }
        }

    def test_a_page_of_another_questionnaire_is_not_found(self, client, user, response):
        client.force_login(user)

        result = post(
            client,
            reverse(
                "questionnaires:page-submit",
                kwargs={"response_uuid": response.uuid, "page_key": "nowhere"},
            ),
            {"answers": {}},
        )

        assert result.status_code == 404

    def test_someone_else_s_response_is_not_found(self, client, db, response):
        intruder = get_user_model().objects.create_user(username="other", password="nope")
        client.force_login(intruder)

        result = post(
            client,
            reverse(
                "questionnaires:page-submit",
                kwargs={"response_uuid": response.uuid, "page_key": "about"},
            ),
            {"answers": {"name": "Hugo"}},
        )

        assert result.status_code == 404


class TestSkippingAPage:
    @pytest.fixture
    def response(self, user, published):
        return start_response(published, respondent=user)

    def test_a_skippable_page_can_be_put_off(self, client, user, response):
        client.force_login(user)

        result = post(
            client,
            reverse(
                "questionnaires:page-skip",
                kwargs={"response_uuid": response.uuid, "page_key": "extras"},
            ),
        )

        assert result.status_code == 200
        assert result.json()["page"]["skipReason"] == SkipReason.MANUAL_ACTION
        assert result.json()["response"]["progress"]["pending"] == ["about", "extras"]

    def test_a_page_that_is_not_skippable_is_refused(self, client, user, response):
        client.force_login(user)

        result = post(
            client,
            reverse(
                "questionnaires:page-skip",
                kwargs={"response_uuid": response.uuid, "page_key": "about"},
            ),
        )

        assert result.status_code == 409
        assert "cannot be skipped" in result.json()["detail"]


class TestReadingAResponse:
    def test_it_reports_the_state_and_can_leave_the_plan_out(self, client, user, published):
        response = start_response(published, respondent=user)
        client.force_login(user)
        url = reverse("questionnaires:response-detail", kwargs={"response_uuid": response.uuid})

        with_plan = client.get(url)
        without_plan = client.get(f"{url}?plan=0")

        assert "plan" in with_plan.json()
        assert "plan" not in without_plan.json()
        assert without_plan.json()["status"] == "in_progress"

    def test_a_body_that_is_not_json_is_refused(self, client, user, published):
        client.force_login(user)

        result = client.post(
            reverse("questionnaires:response-create"),
            data="not json",
            content_type="application/json",
        )

        assert result.status_code == 400


class TestWhatIsStillAllowed:
    def test_the_payload_says_what_the_version_allows(self, client, user, published):
        published.edit_policy = EditPolicy.ALWAYS
        published.edits_due_at = timezone.now() + timedelta(days=2)
        published.save()
        client.force_login(user)

        result = post(
            client, reverse("questionnaires:response-create"), {"questionnaire": "intake"}
        )

        policy = result.json()["policy"]
        assert policy["editPolicy"] == EditPolicy.ALWAYS
        assert policy["canRespond"] is True
        assert policy["canEdit"] is True
        assert policy["editsDueAt"] is not None
        assert policy["responsesDueAt"] is None

    def test_a_response_cannot_be_opened_after_the_deadline(self, client, user, published):
        published.responses_due_at = timezone.now() - timedelta(minutes=1)
        published.save()
        client.force_login(user)

        result = post(
            client, reverse("questionnaires:response-create"), {"questionnaire": "intake"}
        )

        assert result.status_code == 409
        assert "stopped accepting responses" in result.json()["detail"]

    def test_a_recorded_answer_cannot_be_changed_when_the_version_forbids_it(
        self, client, user, published
    ):
        response = start_response(published, respondent=user)
        client.force_login(user)
        url = reverse(
            "questionnaires:page-submit",
            kwargs={"response_uuid": response.uuid, "page_key": "about"},
        )
        assert post(client, url, {"answers": {"name": "Hugo"}}).status_code == 200

        published.edit_policy = EditPolicy.NEVER
        published.save()
        result = post(client, url, {"answers": {"name": "Hugo Bessa"}})

        assert result.status_code == 409
        assert "does not allow answers to be changed" in result.json()["detail"]
        assert not result.json().get("errors")

    def test_a_completed_response_reports_that_it_is_closed(self, client, user, published):
        response = start_response(published, respondent=user)
        client.force_login(user)
        for page_key, answers in (("about", {"name": "Hugo"}), ("extras", {"notes": ""})):
            post(
                client,
                reverse(
                    "questionnaires:page-submit",
                    kwargs={"response_uuid": response.uuid, "page_key": page_key},
                ),
                {"answers": answers},
            )

        detail = client.get(
            reverse("questionnaires:response-detail", kwargs={"response_uuid": response.uuid})
        ).json()

        assert detail["status"] == "completed"
        assert detail["policy"]["canEdit"] is False


class TestValueSetOptions:
    def test_a_static_set_is_resolved_by_the_server(self, client, user, db):
        value_set = ValueSet.objects.create(key="sizes", name="Sizes")
        ValueSetOption.objects.create(value_set=value_set, value="s", label="Small", order=0)
        ValueSetOption.objects.create(value_set=value_set, value="l", label="Large", order=1)
        ValueSetOption.objects.create(
            value_set=value_set, value="xl", label="Huge", order=2, is_active=False
        )
        client.force_login(user)

        result = client.get(reverse("questionnaires:value-set-options", kwargs={"key": "sizes"}))

        assert result.status_code == 200
        assert [option["value"] for option in result.json()["options"]] == ["s", "l"]

    def test_a_model_set_is_filtered_by_its_expression(self, client, user, db):
        Group.objects.create(name="tech-python")
        Group.objects.create(name="internal-billing")
        ValueSet.objects.create(
            key="technologies",
            name="Technologies",
            source=ValueSetSource.MODEL,
            content_type=ContentType.objects.get_for_model(Group),
            filter_expression='name startswith "tech-"',
            value_field="name",
            label_field="name",
        )
        client.force_login(user)

        result = client.get(
            reverse("questionnaires:value-set-options", kwargs={"key": "technologies"})
        )

        assert [option["value"] for option in result.json()["options"]] == ["tech-python"]

    def test_an_endpoint_set_hands_the_client_the_endpoint(self, client, user, db):
        ValueSet.objects.create(
            key="live",
            name="Live",
            source=ValueSetSource.ENDPOINT,
            endpoint_url="https://example.com/options",
            endpoint_results_path="data.results",
        )
        client.force_login(user)

        body = client.get(
            reverse("questionnaires:value-set-options", kwargs={"key": "live"})
        ).json()

        assert "options" not in body
        assert body["endpoint"]["url"] == "https://example.com/options"
        assert body["endpoint"]["resultsPath"] == "data.results"
