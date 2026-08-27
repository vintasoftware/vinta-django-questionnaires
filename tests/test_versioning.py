"""Editing a live questionnaire, and forking a new version instead."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from tests.conftest import make_question
from vinta_django_questionnaires.editing import Acknowledgement, acknowledged_edit
from vinta_django_questionnaires.fingerprints import compare_versions
from vinta_django_questionnaires.forms import AcknowledgedEditForm
from vinta_django_questionnaires.models import (
    AcknowledgedEdit,
    EditAction,
    LayerColumns,
    Page,
    Question,
    QuestionChoice,
    QuestionMinimumColumns,
    QuestionValidator,
    Section,
    VersionStatus,
)
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.submissions import start_response, submit_page
from vinta_django_questionnaires.versioning import new_version_from


@pytest.fixture
def built(version, ranges):
    """A version with a bit of everything, so a copy has something to get wrong."""
    LayerColumns.objects.create(
        questionnaire_version=version, window_size_range=ranges["desktop"], columns=8
    )
    page = Page.objects.create(questionnaire_version=version, key="about", title="About", order=0)
    LayerColumns.objects.create(page=page, window_size_range=ranges["mobile"], columns=4)
    section = Section.objects.create(page=page, key="basics", title="Basics")
    LayerColumns.objects.create(section=section, window_size_range=ranges["desktop"], columns=6)

    question = make_question(section, key="colour", question_type=QuestionType.SINGLE_CHOICE)
    QuestionChoice.objects.create(question=question, value="red", label="Red")
    QuestionChoice.objects.create(question=question, value="blue", label="Blue")
    QuestionValidator.objects.create(question=question, validator="required")
    QuestionMinimumColumns.objects.create(
        question=question, window_size_range=ranges["desktop"], minimum_columns=3
    )
    return version


class TestForkingANewVersion:
    def test_it_copies_the_whole_tree_into_a_draft(self, built):
        draft = new_version_from(built)

        assert draft.version == 2
        assert draft.status == VersionStatus.DRAFT
        assert draft.published_at is None
        assert [page.key for page in draft.pages.all()] == ["about"]
        question = draft.pages.get(key="about").sections.get(key="basics").questions.get()
        assert question.key == "colour"
        assert [choice.value for choice in question.choices.all()] == ["red", "blue"]
        assert [binding.validator for binding in question.validators.all()] == ["required"]

    def test_the_copy_gets_its_own_rows(self, built):
        draft = new_version_from(built)

        original = built.pages.get(key="about")
        copied = draft.pages.get(key="about")
        assert copied.pk != original.pk
        assert copied.sections.get().pk != original.sections.get().pk

    def test_the_column_settings_follow_the_copy_s_own_breakpoints(self, built, ranges):
        draft = new_version_from(built)

        # The ranges were copied too, so nothing points back at the original's.
        assert set(draft.window_size_ranges.values_list("key", flat=True)) == {"mobile", "desktop"}
        assert not LayerColumns.objects.filter(
            questionnaire_version=draft, window_size_range__questionnaire_version=built
        ).exists()
        section = draft.pages.get(key="about").sections.get(key="basics")
        assert section.column_layout() == {"mobile": 4, "desktop": 6}
        question = section.questions.get()
        assert question.minimum_column_layout() == {"mobile": 12, "desktop": 3}

    def test_the_original_is_untouched(self, built):
        new_version_from(built)

        assert built.version == 1
        assert built.pages.count() == 1
        assert built.pages.get().sections.get().questions.count() == 1

    def test_responses_stay_with_the_version_they_were_given_to(self, built):
        built.publish()
        response = start_response(built)
        submit_page(response, built.pages.get(key="about"), {"colour": "red"})

        draft = new_version_from(built)

        assert built.responses.count() == 1
        assert draft.responses.count() == 0
        answer = response.answer_records.get()
        assert answer.question.section.page.questionnaire_version_id == built.pk


class TestEditingInPlace:
    def test_a_version_without_responses_is_edited_freely(self, built):
        question = built.pages.get().sections.get().questions.get()

        question.title = "Favourite colour"
        question.save()

        assert AcknowledgedEdit.objects.count() == 0

    def test_a_version_with_responses_refuses_an_unacknowledged_edit(self, built):
        built.publish()
        start_response(built)
        question = built.pages.get().sections.get().questions.get()
        question.title = "Favourite colour"

        with pytest.raises(ValidationError, match="already has responses"):
            question.save()

    def test_an_acknowledged_edit_goes_through_and_is_written_down(self, built, django_user_model):
        user = django_user_model.objects.create_user(username="hugo", password="questionnaires")
        built.publish()
        start_response(built)
        question = built.pages.get().sections.get().questions.get()

        with acknowledged_edit(user=user, reason="The old wording was ambiguous"):
            question.title = "Favourite colour"
            question.save()

        record = AcknowledgedEdit.objects.get()
        assert record.action == EditAction.UPDATED
        assert record.target_label == "vinta_django_questionnaires.question"
        assert record.target_key == "colour"
        assert record.changes == {"title": {"from": "Your name", "to": "Favourite colour"}}
        assert record.acknowledged_by == user
        assert record.reason == "The old wording was ambiguous"
        assert record.responses_at_edit == 1
        assert record.target == question
        assert record.questionnaire_version == built

    def test_an_acknowledgement_can_be_passed_to_one_save(self, built):
        built.publish()
        start_response(built)
        question = built.pages.get().sections.get().questions.get()
        question.title = "Favourite colour"

        question.save(acknowledgement=Acknowledgement(reason="One-off"))

        assert AcknowledgedEdit.objects.get().reason == "One-off"

    def test_saving_without_changing_anything_is_not_an_edit(self, built):
        built.publish()
        start_response(built)
        question = built.pages.get().sections.get().questions.get()

        question.save()

        assert AcknowledgedEdit.objects.count() == 0

    def test_choices_and_validators_are_covered_too(self, built):
        built.publish()
        start_response(built)
        question = built.pages.get().sections.get().questions.get()
        choice = question.choices.get(value="red")

        with pytest.raises(ValidationError, match="already has responses"):
            QuestionChoice.objects.create(question=question, value="green", label="Green")

        with acknowledged_edit(reason="Dropped an option"):
            choice.delete()

        record = AcknowledgedEdit.objects.get()
        assert record.action == EditAction.DELETED
        assert record.target_key == "colour.red"

    def test_layout_is_not_gated(self, built, ranges):
        built.publish()
        start_response(built)
        section = built.pages.get().sections.get()

        LayerColumns.objects.create(
            section=section, window_size_range=ranges["mobile"], columns=12
        )

        # Rearranging a form does not change what an answer meant.
        assert AcknowledgedEdit.objects.count() == 0


class TestFingerprints:
    def test_a_copy_asks_exactly_the_same_thing(self, built):
        draft = new_version_from(built)

        assert draft.content_fingerprint == built.content_fingerprint
        assert compare_versions(built, draft).is_identical

    def test_changing_a_question_moves_only_its_own_fingerprint(self, built):
        draft = new_version_from(built)
        other = make_question(
            draft.pages.get().sections.get(), key="notes", title="Notes", order=1
        )
        make_question(built.pages.get().sections.get(), key="notes", title="Notes", order=1)
        before = {q.key: q.content_fingerprint for q in built.iter_questions()}

        other.title = "Anything else?"
        other.save()

        after = {q.key: q.content_fingerprint for q in draft.iter_questions()}
        assert after["colour"] == before["colour"]
        assert after["notes"] != before["notes"]

    def test_it_says_which_answers_can_be_pooled(self, built):
        draft = new_version_from(built)
        question = draft.pages.get().sections.get().questions.get()
        question.title = "Favourite colour"
        question.save()
        make_question(draft.pages.get().sections.get(), key="notes", title="Notes", order=1)

        comparison = compare_versions(built, draft)

        assert comparison.changed == ["colour"]
        assert comparison.added == ["notes"]
        assert comparison.removed == []
        assert comparison.can_pool("colour") is False

    def test_moving_a_question_does_not_change_what_it_asks(self, built):
        question = built.pages.get().sections.get().questions.get()
        before = question.content_fingerprint

        question.order = 5
        question.requires_being_first_in_a_row = True
        question.save()

        assert question.content_fingerprint == before


class TestTheBox:
    """The acknowledgement as someone actually meets it: a form field."""

    @pytest.fixture
    def form_class(self):
        class QuestionForm(AcknowledgedEditForm):
            class Meta:
                model = Question
                fields = ["key", "title", "question_type"]

        return QuestionForm

    @pytest.fixture
    def live_question(self, built):
        built.publish()
        start_response(built)
        return built.pages.get().sections.get().questions.get()

    def test_it_is_not_asked_for_when_nothing_has_been_answered_yet(self, built, form_class):
        question = built.pages.get().sections.get().questions.get()
        form = form_class(
            instance=question,
            data={
                "key": "colour",
                "title": "Favourite colour",
                "question_type": question.question_type,
            },
        )

        assert form.needs_acknowledgement() is False
        assert form.is_valid(), form.errors

    def test_the_form_will_not_save_without_it(self, live_question, form_class):
        form = form_class(
            instance=live_question,
            data={
                "key": "colour",
                "title": "Favourite colour",
                "question_type": live_question.question_type,
            },
        )

        assert form.is_valid() is False
        assert "understood" in form.errors

    def test_ticking_it_saves_and_signs_the_record(
        self, live_question, form_class, django_user_model
    ):
        user = django_user_model.objects.create_user(username="hugo", password="questionnaires")
        form = form_class(
            instance=live_question,
            acknowledged_by=user,
            data={
                "key": "colour",
                "title": "Favourite colour",
                "question_type": live_question.question_type,
                "understood": True,
                "edit_reason": "Wording was ambiguous",
            },
        )

        assert form.is_valid(), form.errors
        form.save()

        record = AcknowledgedEdit.objects.get()
        assert record.acknowledged_by == user
        assert record.reason == "Wording was ambiguous"
        assert record.changes["title"]["to"] == "Favourite colour"
