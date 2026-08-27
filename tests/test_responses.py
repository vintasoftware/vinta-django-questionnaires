"""Filling in a response, page by page."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from tests.conftest import make_question
from vinta_django_questionnaires.editing import acknowledged_edit
from vinta_django_questionnaires.models import (
    Answer,
    EditPolicy,
    Page,
    PageResponseStatus,
    QuestionValidator,
    ResponseStatus,
    Section,
    SkipReason,
)
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.submissions import (
    EditingClosed,
    EditingNotAllowed,
    PageNotApplicable,
    PageNotSkippable,
    PageValidationError,
    RespondingClosed,
    ResponseAlreadyCompleted,
    skip_page,
    start_response,
    submit_page,
)
from vinta_django_questionnaires.validators import BaseValidator, registry


@pytest.fixture
def flow(version):
    """Three pages: one always asked, one conditional, one skippable."""
    about = Page.objects.create(questionnaire_version=version, key="about", title="About", order=0)
    basics = Section.objects.create(page=about, key="basics", title="Basics")
    name = make_question(basics, key="name", title="Name")
    QuestionValidator.objects.create(question=name, validator="required")
    make_question(basics, key="has_company", title="Has a company", order=1)

    company = Page.objects.create(
        questionnaire_version=version,
        key="company",
        title="Company",
        order=1,
        condition="has_company == 'yes'",
    )
    company_section = Section.objects.create(page=company, key="details", title="Details")
    make_question(company_section, key="company_name", title="Company name")

    extras = Page.objects.create(
        questionnaire_version=version,
        key="extras",
        title="Extras",
        order=2,
        is_skippable=True,
    )
    extras_section = Section.objects.create(page=extras, key="more", title="More")
    make_question(extras_section, key="notes", title="Notes")

    return {"version": version, "about": about, "company": company, "extras": extras}


@pytest.fixture
def response(flow):
    return start_response(flow["version"])


class TestStarting:
    def test_a_new_response_is_in_progress_on_the_first_page(self, flow, response):
        assert response.status == ResponseStatus.IN_PROGRESS
        assert response.current_page == flow["about"]

    def test_a_page_ruled_out_from_the_start_is_recorded_as_such(self, flow, response):
        skipped = response.page_responses.get(page=flow["company"])

        assert skipped.status == PageResponseStatus.SKIPPED
        assert skipped.skip_reason == SkipReason.FALSE_CONDITION
        assert "company" not in response.progress()["pending"]

    def test_the_context_answers_conditions_too(self, flow):
        flow["extras"].condition = "role == 'staff'"
        flow["extras"].save()

        response = start_response(flow["version"], context={"role": "staff"})

        assert flow["extras"].key in response.progress()["pending"]


class TestSubmitting:
    def test_a_page_that_does_not_validate_is_rejected_whole(self, flow, response):
        with pytest.raises(PageValidationError) as excinfo:
            submit_page(response, flow["about"], {"has_company": "no"})

        assert excinfo.value.validation.as_dict()["name"][0]["errorKey"] == "required"
        assert not response.page_responses.filter(page=flow["about"]).exists()
        assert Answer.objects.count() == 0

    def test_a_valid_page_is_recorded_and_the_flow_moves_on(self, flow, response):
        page_response = submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        assert page_response.status == PageResponseStatus.COMPLETED
        assert page_response.submitted_at is not None
        assert response.answers == {"name": "Hugo", "has_company": "no"}
        assert response.current_page == flow["extras"]

    def test_answering_turns_a_conditional_page_back_on(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "yes"})

        assert not response.page_responses.filter(page=flow["company"]).exists()
        assert response.progress()["pending"] == ["company", "extras"]
        assert response.current_page == flow["company"]

    def test_changing_an_answer_rules_the_page_out_again(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "yes"})
        submit_page(response, flow["company"], {"company_name": "Vinta"})

        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        company_response = response.page_responses.get(page=flow["company"])
        assert company_response.skip_reason == SkipReason.FALSE_CONDITION
        # The answer is kept, but it no longer counts.
        assert Answer.objects.filter(question__key="company_name").exists()
        assert "company_name" not in response.answers

    def test_answering_back_the_other_way_restores_it(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "yes"})
        submit_page(response, flow["company"], {"company_name": "Vinta"})
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "yes"})

        company_response = response.page_responses.get(page=flow["company"])
        assert company_response.status == PageResponseStatus.COMPLETED
        assert response.answers["company_name"] == "Vinta"

    def test_a_page_whose_condition_does_not_hold_cannot_be_submitted(self, flow, response):
        with pytest.raises(PageNotApplicable):
            submit_page(response, flow["company"], {"company_name": "Vinta"})

    def test_the_response_completes_when_nothing_is_pending(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        submit_page(response, flow["extras"], {"notes": ""})

        response.refresh_from_db()
        assert response.status == ResponseStatus.COMPLETED
        assert response.completed_at is not None
        assert response.progress()["isComplete"] is True

    def test_the_caller_can_keep_the_response_open(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        submit_page(response, flow["extras"], {"notes": ""}, complete_when_done=False)

        response.refresh_from_db()
        assert response.status == ResponseStatus.IN_PROGRESS
        assert response.is_complete is True

    def test_a_completed_response_takes_no_more_pages(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        submit_page(response, flow["extras"], {"notes": ""})

        with pytest.raises(ResponseAlreadyCompleted):
            submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

    def test_keys_the_page_is_not_asking_about_are_ignored(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no", "nope": 1})

        assert "nope" not in response.answers


class TestSkipping:
    def test_a_skippable_page_stays_pending_for_later(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        page_response = skip_page(response, flow["extras"])

        assert page_response.skip_reason == SkipReason.MANUAL_ACTION
        assert response.progress()["skipped"] == [
            {"page": "company", "reason": SkipReason.FALSE_CONDITION},
            {"page": "extras", "reason": SkipReason.MANUAL_ACTION},
        ]
        # Skipping means later, so the response is not done.
        assert response.progress()["pending"] == ["extras"]
        assert response.is_complete is False

    def test_a_page_that_is_not_skippable_says_so(self, flow, response):
        with pytest.raises(PageNotSkippable):
            skip_page(response, flow["about"])

    def test_coming_back_to_a_skipped_page_completes_it(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        skip_page(response, flow["extras"])

        submit_page(response, flow["extras"], {"notes": "Later, then."})

        response.refresh_from_db()
        assert response.status == ResponseStatus.COMPLETED
        assert response.page_responses.get(page=flow["extras"]).skip_reason == ""


class TestAnswerShapes:
    def test_a_question_the_section_stopped_asking_keeps_no_answer(self, flow, response):
        section = flow["about"].sections.get(key="basics")
        with acknowledged_edit(reason="Added mid-flight for this test"):
            make_question(
                section, key="reason", title="Why not?", order=2, condition="has_company == 'no'"
            )

        submit_page(
            response, flow["about"], {"name": "Hugo", "has_company": "no", "reason": "Freelance"}
        )
        assert response.answers["reason"] == "Freelance"

        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "yes"})
        assert "reason" not in response.answers
        assert not Answer.objects.filter(question__key="reason").exists()

    def test_a_list_answer_is_stored_as_a_list(self, flow, response):
        section = flow["extras"].sections.get(key="more")
        with acknowledged_edit(reason="Added mid-flight for this test"):
            question = make_question(
                section,
                key="tags",
                title="Tags",
                question_type=QuestionType.MULTIPLE_CHOICE,
                order=1,
            )
            QuestionValidator.objects.create(
                question=question, validator="max_items", params={"maximum": 2}
            )

        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        with pytest.raises(PageValidationError):
            submit_page(response, flow["extras"], {"notes": "", "tags": ["a", "b", "c"]})

        submit_page(response, flow["extras"], {"notes": "", "tags": ["a", "b"]})
        assert response.answers["tags"] == ["a", "b"]


class TestRespondingWindow:
    def test_a_response_cannot_be_opened_after_the_deadline(self, flow):
        flow["version"].responses_due_at = timezone.now() - timedelta(minutes=1)
        flow["version"].save()

        with pytest.raises(RespondingClosed):
            start_response(flow["version"])

    def test_a_page_cannot_be_answered_after_the_deadline(self, flow, response):
        flow["version"].responses_due_at = timezone.now() - timedelta(minutes=1)
        flow["version"].save()

        with pytest.raises(RespondingClosed):
            submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

    def test_a_deadline_ahead_changes_nothing(self, flow, response):
        flow["version"].responses_due_at = timezone.now() + timedelta(days=1)
        flow["version"].save()

        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        assert response.answers["name"] == "Hugo"


class TestEditing:
    def test_by_default_a_page_can_be_revised_while_in_progress(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        submit_page(response, flow["about"], {"name": "Hugo Bessa", "has_company": "no"})

        assert response.answers["name"] == "Hugo Bessa"

    def test_by_default_a_completed_response_is_closed(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        submit_page(response, flow["extras"], {"notes": ""})

        with pytest.raises(ResponseAlreadyCompleted):
            submit_page(response, flow["about"], {"name": "Hugo Bessa", "has_company": "no"})

    def test_a_version_that_never_allows_edits_takes_the_first_answer_only(self, flow, response):
        flow["version"].edit_policy = EditPolicy.NEVER
        flow["version"].save()
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        with pytest.raises(EditingNotAllowed):
            submit_page(response, flow["about"], {"name": "Hugo Bessa", "has_company": "no"})

        # Answering a page that has nothing recorded is not an edit.
        submit_page(response, flow["extras"], {"notes": "Fine."})
        assert response.answers["notes"] == "Fine."

    def test_a_version_that_always_allows_edits_reopens_a_completed_response(self, flow, response):
        flow["version"].edit_policy = EditPolicy.ALWAYS
        flow["version"].save()
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        submit_page(response, flow["extras"], {"notes": ""})
        assert response.status == ResponseStatus.COMPLETED

        submit_page(response, flow["about"], {"name": "Hugo Bessa", "has_company": "no"})

        response.refresh_from_db()
        assert response.answers["name"] == "Hugo Bessa"
        assert response.status == ResponseStatus.COMPLETED

    def test_an_edit_that_brings_a_page_back_makes_the_response_incomplete_again(
        self, flow, response
    ):
        flow["version"].edit_policy = EditPolicy.ALWAYS
        flow["version"].save()
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        submit_page(response, flow["extras"], {"notes": ""})

        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "yes"})

        response.refresh_from_db()
        assert response.status == ResponseStatus.IN_PROGRESS
        assert response.completed_at is None
        assert response.current_page == flow["company"]

    def test_edits_stop_at_their_own_deadline(self, flow, response):
        flow["version"].edit_policy = EditPolicy.ALWAYS
        flow["version"].edits_due_at = timezone.now() - timedelta(minutes=1)
        flow["version"].save()
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})

        with pytest.raises(EditingClosed):
            submit_page(response, flow["about"], {"name": "Hugo Bessa", "has_company": "no"})

    def test_the_two_deadlines_are_independent(self, flow, response):
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        flow["version"].edit_policy = EditPolicy.ALWAYS
        flow["version"].responses_due_at = timezone.now() - timedelta(minutes=1)
        flow["version"].edits_due_at = timezone.now() + timedelta(days=1)
        flow["version"].save()

        # What is recorded can still be corrected...
        submit_page(response, flow["about"], {"name": "Hugo Bessa", "has_company": "no"})
        assert response.answers["name"] == "Hugo Bessa"

        # ... but a page that was never answered cannot be answered now.
        with pytest.raises(RespondingClosed):
            submit_page(response, flow["extras"], {"notes": "Too late."})

    def test_skipping_a_page_that_was_answered_counts_as_an_edit(self, flow, response):
        flow["version"].edit_policy = EditPolicy.NEVER
        flow["version"].save()
        submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        submit_page(response, flow["extras"], {"notes": "Done."})

        with pytest.raises(EditingNotAllowed):
            skip_page(response, flow["extras"])

    def test_an_edit_deadline_needs_a_version_that_allows_edits(self, version):
        version.edit_policy = EditPolicy.NEVER
        version.edits_due_at = timezone.now() + timedelta(days=1)

        with pytest.raises(ValidationError, match="never allows edits"):
            version.save()


class TestValidatorContext:
    def test_a_validator_sees_the_response_it_is_validating(self, flow, response):
        seen = {}

        class SeesTheResponse(BaseValidator):
            key = "test_sees_response"
            error_messages = {"nope": "Never happens."}

            def validate(self, value, context):
                seen["response"] = context.extra.get("response")
                seen["page"] = context.extra.get("page")
                seen["answers"] = dict(context.answers)
                return

        registry.register(SeesTheResponse, force=True)
        try:
            name = flow["about"].sections.get(key="basics").questions.get(key="name")
            with acknowledged_edit(reason="Test setup"):
                QuestionValidator.objects.create(question=name, validator="test_sees_response")

            submit_page(response, flow["about"], {"name": "Hugo", "has_company": "no"})
        finally:
            registry.unregister("test_sees_response")

        assert seen["response"] == response
        assert seen["page"] == flow["about"]
        assert seen["answers"]["has_company"] == "no"
